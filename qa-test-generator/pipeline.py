"""
Main Pipeline - Orchestrates all agents to generate test cases.
This is the main entry point for test case generation.
"""

from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.panel import Panel

from core.models import (
    RequirementInput,
    GenerationConfig,
    GeneratedTestSuite,
)
from agents import (
    PlannerAgent,
    GeneratorAgent,
    ReviewAgent,
    FormatterAgent,
)
from rag import get_rag_system
from rag.context_scorer import filter_by_relevance
from tools.github_fetcher import GitHubContextFetcher
from tools.website_crawler import WebsiteContextFetcher, WebsiteContext

console = Console()


MAX_REFINEMENT_LOOPS = 1
QUALITY_THRESHOLD = 75.0          # stop early if score reaches this
_DEDUP_JACCARD_THRESHOLD = 0.65   # token-overlap ratio above which two tests are considered duplicate (DESIGN-4)


class TestGeneratorPipeline:
    """
    Main pipeline that orchestrates all agents to generate
    comprehensive test cases from requirements.
    """

    def __init__(self, use_rag: bool = True, website_fetcher: Optional[WebsiteContextFetcher] = None):
        """
        Initialize the pipeline.

        Args:
            use_rag: Whether to use RAG for context retrieval
            website_fetcher: Optional WebsiteContextFetcher instance for injection
                             (useful in tests to avoid real HTTP calls). (INTEGRATION-1)
        """
        self.use_rag = use_rag
        self._website_fetcher = website_fetcher

        # Initialize agents
        self.planner = PlannerAgent()
        self.generator = GeneratorAgent()
        self.reviewer = ReviewAgent()
        self.formatter = FormatterAgent()

        # Initialize RAG if enabled
        self.rag = get_rag_system() if use_rag else None
    
    def run(
        self,
        requirement: RequirementInput,
        config: Optional[GenerationConfig] = None,
        tool_context: Optional[str] = None
    ) -> GeneratedTestSuite:
        """
        Run the full pipeline to generate test cases.
        
        Args:
            requirement: The requirement input
            config: Generation configuration (uses defaults if not provided)
            tool_context: Optional context from tools (Jira, API docs, etc.)
            
        Returns:
            GeneratedTestSuite with all outputs
        """
        # Use default config if not provided
        if config is None:
            config = GenerationConfig()

        # Print header
        self._print_header(requirement)

        # Step 0: Fetch external context (GitHub repo and/or website).
        # website_ctx is a WebsiteContext object kept SEPARATE from tool_context so it
        # can be injected directly into generator task prompts as structured mandatory
        # data — not as generic background context (DESIGN-1).
        caller_tool_context = tool_context  # preserve original caller-supplied context
        github_ctx = ""
        website_ctx: Optional[WebsiteContext] = None

        if requirement.github_repo_url:
            github_ctx = self._fetch_github_context(requirement.github_repo_url)

        if requirement.website_url:
            website_ctx = self._fetch_website_context(requirement.website_url)

        # Planner gets full picture (github + website formatted text) to assess relevance
        planner_parts = [c for c in [
            github_ctx,
            website_ctx.formatted if website_ctx else "",
            requirement.additional_context or "",  # plumb additional_context (INTEGRATION-3)
            caller_tool_context or "",
        ] if c]
        planner_tool_ctx = "\n\n".join(planner_parts) or None

        # Step 1: Planner Agent
        rag_context = None
        if self.use_rag and self.rag:
            rag_context = self._get_initial_rag_context(requirement)

        analysis = self.planner.run(
            requirement,
            rag_context=rag_context,
            tool_context=planner_tool_ctx,
        )

        # Mismatch check: only applies to GitHub — if the repo is unrelated to the
        # requirement, drop it.  Website context is NEVER dropped: it IS the live UI.
        if github_ctx and not getattr(self.planner, "codebase_relevant", True):
            console.print(
                "[yellow]⚠ GitHub link and requirement are mismatched — "
                "generating test cases and automation scripts based on requirement input only.[/yellow]"
            )
            github_ctx = ""  # drop mismatched repo; website_ctx is unaffected

        # Generator tool_context = github (if still relevant) + any caller context.
        # website_ctx (WebsiteContext object) is passed SEPARATELY so the generator can
        # inject exact locators/endpoints directly into the task prompt. (DESIGN-1)
        # NOTE: if website fetch failed on pass 1 (website_ctx is None), refinement
        # passes also receive None — no retry is attempted. (INTEGRATION-2)
        generator_tool_ctx = "\n\n".join(
            c for c in [github_ctx, caller_tool_context] if c
        ) or None

        # Step 2: Get enhanced RAG context based on analysis
        if self.use_rag and self.rag:
            rag_context = self.rag.get_context_for_generation(
                feature_name=analysis.feature_name,
                domain=analysis.domain,
                intent=analysis.intent
            )

        # Step 3: Generator Agent
        manual_tests, api_tests, ui_tests = self.generator.run(
            requirement=requirement,
            analysis=analysis,
            config=config,
            rag_context=rag_context,
            tool_context=generator_tool_ctx,
            website_context=website_ctx,
        )
        
        # Step 4: Guard — skip review and refinement if nothing was generated
        if not manual_tests and not api_tests and not ui_tests:
            console.print("[yellow]⚠ No test cases generated — skipping review and refinement.[/yellow]")
            review = self._empty_review()
        else:
            review = self.reviewer.run(
                analysis=analysis,
                manual_tests=manual_tests,
                api_tests=api_tests,
                ui_tests=ui_tests,
            )

        # Step 5: Refinement loop — feed gaps/issues back to Planner → Generator
        for iteration in range(1, MAX_REFINEMENT_LOOPS + 1):
            gaps = review.coverage.coverage_gaps
            issues = review.issues_found

            if (not gaps and not issues) or review.final_score >= QUALITY_THRESHOLD:
                console.print(f"\n[bold cyan]✓ No further refinement needed (score: {review.final_score}%)[/bold cyan]")
                break

            console.print(f"\n[bold cyan]{'='*50}[/bold cyan]")
            console.print(f"[bold cyan]REFINEMENT LOOP {iteration}/{MAX_REFINEMENT_LOOPS}[/bold cyan]")
            console.print(f"[bold cyan]{'='*50}[/bold cyan]")
            console.print(f"  Gaps to fix: {len(gaps)}")
            console.print(f"  Issues to fix: {len(issues)}")

            # Build gap context and re-run Planner (skip validation — requirement already passed)
            gap_context = self._build_refinement_context(
                gaps, issues, iteration,
                existing_manual=manual_tests,
                existing_api=api_tests,
                existing_ui=ui_tests,
            )
            analysis = self.planner.run(requirement, rag_context=gap_context, skip_validation=True)

            # Only regenerate types that have actual gaps — skip types that are already sufficient
            gap_text = " ".join(gaps + issues).lower()
            needs_manual = config.include_manual and any(
                k in gap_text for k in ("manual", "step", "precondition", "coverage")
            )
            needs_api = config.include_api and any(
                k in gap_text for k in ("api", "endpoint", "request", "status", "response")
            )
            needs_ui = config.include_ui and any(
                k in gap_text for k in ("ui", "browser", "page", "element", "selector", "form")
            )
            # If gaps are generic (not type-specific), regenerate all enabled types
            if not needs_manual and not needs_api and not needs_ui:
                needs_manual = config.include_manual
                needs_api = config.include_api
                needs_ui = config.include_ui

            refinement_config = config.model_copy(update={
                "include_manual": needs_manual,
                "include_api": needs_api,
                "include_ui": needs_ui,
            })
            console.print(f"  Regenerating: manual={needs_manual} api={needs_api} ui={needs_ui}")

            new_manual, new_api, new_ui = self.generator.run(
                requirement=requirement,
                analysis=analysis,
                config=refinement_config,
                rag_context=gap_context,
                tool_context=generator_tool_ctx,
                website_context=website_ctx,
                existing_manual_tests=manual_tests,
            )

            # Merge and immediately deduplicate to keep the set clean
            prev_total = len(manual_tests) + len(api_tests) + len(ui_tests)
            manual_tests = self._deduplicate(
                self._merge_tests(manual_tests, new_manual, f"R{iteration}")
            )
            api_tests = self._deduplicate(
                self._merge_tests(api_tests, new_api, f"R{iteration}")
            )
            ui_tests = self._deduplicate(
                self._merge_tests(ui_tests, new_ui, f"R{iteration}")
            )
            new_total = len(manual_tests) + len(api_tests) + len(ui_tests)

            # Skip re-review if the refinement produced no net-new test cases
            if new_total == prev_total:
                console.print("[yellow]  ⚠ Refinement added no new tests — skipping re-review.[/yellow]")
                continue

            # Re-review the full deduplicated set
            review = self.reviewer.run(
                analysis=analysis,
                manual_tests=manual_tests,
                api_tests=api_tests,
                ui_tests=ui_tests,
            )

        # Final deduplication pass before formatting
        manual_tests = self._deduplicate(manual_tests)
        api_tests = self._deduplicate(api_tests)
        ui_tests = self._deduplicate(ui_tests)

        # Re-assign sequential IDs to remove any -R1/-R2 suffixes from merge collisions.
        # Capture the manual ID mapping so automation refs can be updated to match.
        manual_tests, manual_id_map = self._renormalize_ids(manual_tests, "MTC")
        api_tests, _ = self._renormalize_ids(api_tests, "ATC")
        ui_tests, _ = self._renormalize_ids(ui_tests, "UTC")

        # Update manual_test_refs in automation tests to reflect any renumbered manual IDs
        if manual_id_map:
            api_tests = self._update_manual_refs(api_tests, manual_id_map)
            ui_tests = self._update_manual_refs(ui_tests, manual_id_map)

        self._log_deduplication(manual_tests, api_tests, ui_tests)

        # Step 6: Formatter Agent
        markdown_output = self.formatter.run(
            analysis=analysis,
            manual_tests=manual_tests,
            api_tests=api_tests,
            ui_tests=ui_tests,
            review=review
        )
        
        # Build final output with separate per-tab sections
        result = GeneratedTestSuite(
            feature_name=analysis.feature_name,
            generated_at=datetime.now(),
            analysis=analysis,
            manual_test_cases=manual_tests,
            api_test_cases=api_tests,
            ui_test_cases=ui_tests,
            review=review,
            markdown_output=markdown_output,
            manual_output=self.formatter.format_manual_section(manual_tests),
            api_output=self.formatter.format_api_section(api_tests),
            ui_output=self.formatter.format_ui_section(ui_tests),
        )
        
        # Store in RAG for future use
        if self.use_rag and self.rag:
            self._store_in_rag(result)
        
        # Print summary
        self._print_summary(result)
        
        return result
    
    def _deduplicate(self, tests: list) -> list:
        """
        Remove duplicate test cases keeping the first occurrence.
        Two tests are considered duplicates if they share the same:
          - test_case_id, OR
          - (scenario_type + normalised title), OR
          - title Jaccard similarity > 0.65 within the same scenario bucket
            (catches paraphrased refinement duplicates like "Login happy path" vs "Successful login")
        """
        import re as _re
        seen_ids: set[str] = set()
        seen_titles: dict[str, list[str]] = {}  # scenario → list of seen norm_titles
        unique = []

        for test in tests:
            if test.test_case_id in seen_ids:
                continue

            norm_title = _re.sub(r"[^a-z0-9 ]", "", test.title.lower()).strip()
            norm_title = " ".join(norm_title.split())
            scenario = str(getattr(test, "scenario_type", ""))

            bucket = seen_titles.setdefault(scenario, [])

            # Exact match
            if norm_title in bucket:
                continue

            # Jaccard near-duplicate check (token overlap)
            if any(self._jaccard(norm_title, t) > _DEDUP_JACCARD_THRESHOLD for t in bucket):
                continue

            seen_ids.add(test.test_case_id)
            bucket.append(norm_title)
            unique.append(test)

        return unique

    @staticmethod
    def _jaccard(a: str, b: str) -> float:
        """Token-level Jaccard similarity between two strings."""
        if not a or not b:
            return 0.0
        tokens_a = set(a.split())
        tokens_b = set(b.split())
        union = len(tokens_a | tokens_b)
        return len(tokens_a & tokens_b) / union if union else 0.0

    def _renormalize_ids(self, tests: list, prefix: str) -> tuple[list, dict[str, str]]:
        """Re-assign clean sequential IDs, removing -R1/-R2 suffixes from merge collisions.

        Returns (renormalized_tests, id_map) where id_map maps old_id → new_id for every
        test whose ID actually changed. Callers use id_map to update cross-references.
        """
        result = []
        id_map: dict[str, str] = {}
        for i, test in enumerate(tests, start=1):
            new_id = f"{prefix}-{i:03d}"
            if test.test_case_id != new_id:
                id_map[test.test_case_id] = new_id
                test = test.model_copy(update={"test_case_id": new_id})
            result.append(test)
        return result, id_map

    def _update_manual_refs(self, tests: list, id_map: dict[str, str]) -> list:
        """Update manual_test_refs in automation tests to reflect renumbered manual IDs."""
        result = []
        for test in tests:
            new_refs = [id_map.get(ref, ref) for ref in test.manual_test_refs]
            if new_refs != test.manual_test_refs:
                test = test.model_copy(update={"manual_test_refs": new_refs})
            result.append(test)
        return result

    def _log_deduplication(self, manual: list, api: list, ui: list) -> None:
        console.print(
            f"\n[cyan]✓ After deduplication — "
            f"Manual: {len(manual)} | API: {len(api)} | UI: {len(ui)}[/cyan]"
        )

    def _build_refinement_context(
        self,
        gaps: list[str],
        issues: list[str],
        iteration: int,
        existing_manual: list | None = None,
        existing_api: list | None = None,
        existing_ui: list | None = None,
    ) -> str:
        """Format review gaps/issues into a concise context string — cap to avoid prompt bloat."""
        top_gaps = gaps[:3]
        top_issues = issues[:3]
        lines = [f"### REFINEMENT PASS {iteration} — fill these specific gaps ONLY:"]
        if top_gaps:
            lines.append("Gaps: " + "; ".join(top_gaps))
        if top_issues:
            lines.append("Issues: " + "; ".join(top_issues))
        lines.append("Generate ONLY the missing test cases. Do NOT regenerate any existing test.")

        # List existing IDs+scenarios so the LLM doesn't recreate them
        def _summarise(tests: list) -> str:
            parts = []
            for t in tests:
                st = getattr(t, "scenario_type", None)
                parts.append(f"{t.test_case_id}[{st.value if st else ''}]")
            return ", ".join(parts)

        if existing_manual:
            lines.append(f"EXISTING MANUAL (skip these): {_summarise(existing_manual)}")
        if existing_api:
            lines.append(f"EXISTING API (skip these): {_summarise(existing_api)}")
        if existing_ui:
            lines.append(f"EXISTING UI (skip these): {_summarise(existing_ui)}")

        return "\n".join(lines)

    def _merge_tests(self, existing: list, new: list, prefix: str) -> list:
        """Merge new tests into existing without mutating the original list. Re-IDs collisions."""
        result = list(existing)
        existing_ids = {t.test_case_id for t in result}
        for test in new:
            if test.test_case_id in existing_ids:
                test = test.model_copy(update={"test_case_id": f"{test.test_case_id}-{prefix}"})
            existing_ids.add(test.test_case_id)
            result.append(test)
        return result

    def _empty_review(self):
        """Return a zeroed ReviewResult when no tests were generated."""
        from core.models import ReviewResult, CoverageReport
        return ReviewResult(
            coverage=CoverageReport(
                total_test_cases=0,
                by_type={},
                by_scenario={},
                by_priority={},
                coverage_gaps=["No test cases were generated."],
                suggestions=[],
                quality_score=0.0,
            ),
            issues_found=["Generation produced no output."],
            improvements_made=[],
            final_score=0.0,
        )

    def _fetch_github_context(self, repo_url: str) -> str:
        """Fetch and return structured context from a GitHub repository."""
        from config import get_settings
        try:
            token = get_settings().github_token
            fetcher = GitHubContextFetcher(github_token=token)
            return fetcher.fetch(repo_url)
        except Exception as e:
            console.print(f"[yellow]  ⚠ GitHub context fetch failed: {e}[/yellow]")
            return ""

    def _fetch_website_context(self, url: str) -> Optional[WebsiteContext]:
        """Crawl a hosted website and return a WebsiteContext (None on failure)."""
        try:
            fetcher = self._website_fetcher or WebsiteContextFetcher()
            return fetcher.fetch(url)
        except Exception as e:
            console.print(f"[yellow]  ⚠ Website context fetch failed: {e}[/yellow]")
            return None

    def _get_initial_rag_context(self, requirement: RequirementInput) -> str:
        """Get relevance-filtered initial RAG context based on requirement."""
        if not self.rag:
            return ""

        results = self.rag.search(query=requirement.content[:500], n_results=5)
        relevant = filter_by_relevance(results)

        if not relevant:
            return ""

        context_parts = ["### Related Context from Knowledge Base"]
        chars = len(context_parts[0])
        for doc in relevant:
            snippet = f"- {doc['content'][:200]}..."
            if chars + len(snippet) > 1000:
                break
            context_parts.append(snippet)
            chars += len(snippet)

        return "\n".join(context_parts)
    
    def _store_in_rag(self, result: GeneratedTestSuite) -> None:
        """Store generated test cases in RAG for future use."""
        if not self.rag:
            return
        
        try:
            # Store manual test cases
            for test in result.manual_test_cases:
                content = f"""
Test Case: {test.title}
Type: Manual
Scenario: {test.scenario_type.value}
Steps: {len(test.steps)}
"""
                self.rag.add_test_case(
                    test_case_content=content,
                    feature=result.feature_name,
                    domain=result.analysis.domain,
                    test_type="manual",
                    tags=test.tags
                )
            
            # Store automation test summaries (not full code)
            for test in result.api_test_cases + result.ui_test_cases:
                content = f"""
Test Case: {test.title}
Type: {test.test_type.value}
Scenario: {test.scenario_type.value}
File: {test.file_name}
"""
                self.rag.add_test_case(
                    test_case_content=content,
                    feature=result.feature_name,
                    domain=result.analysis.domain,
                    test_type=test.test_type.value,
                    tags=[]
                )
                
        except Exception as e:
            console.print(f"[yellow]Could not store in RAG: {e}[/yellow]")
    
    def _print_header(self, requirement: RequirementInput) -> None:
        """Print pipeline header."""
        github_line = (
            f"\n[cyan]GitHub Repo:[/cyan] {requirement.github_repo_url}"
            if requirement.github_repo_url else ""
        )
        website_line = (
            f"\n[cyan]Website URL:[/cyan] {requirement.website_url}"
            if requirement.website_url else ""
        )
        console.print("\n")
        console.print(Panel(
            f"[bold white]QA TEST CASE GENERATOR[/bold white]\n\n"
            f"[cyan]Input Type:[/cyan] {requirement.input_type.value}\n"
            f"[cyan]Content Length:[/cyan] {len(requirement.content)} characters\n"
            f"[cyan]RAG Enabled:[/cyan] {self.use_rag}"
            f"{github_line}"
            f"{website_line}",
            title="🧪 Starting Pipeline",
            border_style="blue"
        ))
    
    def _print_summary(self, result: GeneratedTestSuite) -> None:
        """Print final summary."""
        total = (
            len(result.manual_test_cases) +
            len(result.api_test_cases) +
            len(result.ui_test_cases)
        )
        
        console.print("\n")
        console.print(Panel(
            f"[bold green]✓ GENERATION COMPLETE[/bold green]\n\n"
            f"[white]Feature:[/white] {result.feature_name}\n"
            f"[white]Total Test Cases:[/white] {total}\n"
            f"  • Manual: {len(result.manual_test_cases)}\n"
            f"  • API Automation: {len(result.api_test_cases)}\n"
            f"  • UI Automation: {len(result.ui_test_cases)}\n\n"
            f"[white]Quality Score:[/white] {result.review.final_score}%\n"
            f"[white]Output Length:[/white] {len(result.markdown_output)} characters",
            title="📊 Summary",
            border_style="green"
        ))


def generate_test_cases(
    requirement_text: str,
    input_type: str = "plain_text",
    project_context: Optional[str] = None,
    tech_stack: Optional[str] = None,
    additional_context: Optional[str] = None,
    use_rag: bool = True,
    config: Optional[GenerationConfig] = None,
    github_repo_url: Optional[str] = None,
    website_url: Optional[str] = None,
    website_fetcher=None,
) -> GeneratedTestSuite:
    """
    Convenience function to generate test cases.

    Args:
        requirement_text: The requirement content
        input_type: Type of input (plain_text, acceptance_criteria, user_story)
        project_context: Optional project context
        tech_stack: Optional tech stack info
        use_rag: Whether to use RAG
        config: Optional generation config
        github_repo_url: Optional GitHub repo URL — fetches routes, models, and
                         components so tests are grounded in the real codebase
        website_url: Optional hosted website URL — crawled for exact Playwright
                     locators and API endpoint URLs

    Returns:
        GeneratedTestSuite with all outputs
    """
    from core.models import InputType

    try:
        parsed_type = InputType(input_type)
    except ValueError:
        parsed_type = InputType.PLAIN_TEXT

    requirement = RequirementInput(
        content=requirement_text,
        input_type=parsed_type,
        project_context=project_context,
        tech_stack=tech_stack,
        additional_context=additional_context,
        github_repo_url=github_repo_url,
        website_url=website_url,
    )

    pipeline = TestGeneratorPipeline(use_rag=use_rag, website_fetcher=website_fetcher)
    return pipeline.run(requirement, config=config)
