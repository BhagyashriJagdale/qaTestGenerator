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

console = Console()

PIPELINE_MAX_LOOPS = 2   # max feedback iterations after the first run (total runs = 3)
SCORE_THRESHOLD   = 75.0 # stop early when score reaches this


class TestGeneratorPipeline:
    """
    Main pipeline that orchestrates all agents to generate
    comprehensive test cases from requirements.
    """
    
    def __init__(self, use_rag: bool = True):
        """
        Initialize the pipeline.
        
        Args:
            use_rag: Whether to use RAG for context retrieval
        """
        self.use_rag = use_rag
        
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
        
        self._print_header(requirement)

        # ── Step 1: Initial Planner analysis ──────────────────────────────────
        rag_context = None
        if self.use_rag and self.rag:
            rag_context = self._get_initial_rag_context(requirement)

        analysis = self.planner.run(requirement, rag_context=rag_context)

        # Track the best result across all iterations
        best: dict = {
            "score": -1.0,
            "manual_tests": [],
            "api_tests": [],
            "ui_tests": [],
            "review": None,
            "analysis": analysis,
        }

        # ── Feedback loop: Generator → Reviewer → Planner (refine) ───────────
        total_iterations = PIPELINE_MAX_LOOPS + 1
        for iteration in range(1, total_iterations + 1):
            self._print_loop_header(iteration, total_iterations)

            # Enhanced RAG context from current analysis
            if self.use_rag and self.rag:
                rag_context = self.rag.get_context_for_generation(
                    feature_name=analysis.feature_name,
                    domain=analysis.domain,
                    intent=analysis.intent
                )

            # Generator
            manual_tests, api_tests, ui_tests = self.generator.run(
                requirement=requirement,
                analysis=analysis,
                config=config,
                rag_context=rag_context,
                tool_context=tool_context
            )

            # Reviewer
            review = self.reviewer.run(
                analysis=analysis,
                manual_tests=manual_tests,
                api_tests=api_tests,
                ui_tests=ui_tests
            )

            # Keep track of the highest-scoring result
            if review.final_score > best["score"]:
                best.update({
                    "score": review.final_score,
                    "manual_tests": manual_tests,
                    "api_tests": api_tests,
                    "ui_tests": ui_tests,
                    "review": review,
                    "analysis": analysis,
                })
                console.print(
                    f"[green]  ✓ New best score: {review.final_score:.1f}% "
                    f"(iteration {iteration})[/green]"
                )

            # Stop early if quality threshold reached
            if review.final_score >= SCORE_THRESHOLD:
                console.print(
                    f"[green]Score {review.final_score:.1f}% ≥ threshold "
                    f"{SCORE_THRESHOLD}% — stopping early.[/green]"
                )
                break

            # No more refinement passes after last iteration
            if iteration == total_iterations:
                console.print(
                    f"[yellow]Max iterations ({total_iterations}) reached — "
                    f"using best result (score: {best['score']:.1f}%).[/yellow]"
                )
                break

            # Feed review feedback back to Planner for a refined analysis
            self._print_feedback_summary(review, iteration)
            analysis = self.planner.refine(
                requirement, analysis, review, rag_context=rag_context
            )

        # ── Use best result ───────────────────────────────────────────────────
        manual_tests = best["manual_tests"]
        api_tests    = best["api_tests"]
        ui_tests     = best["ui_tests"]
        review       = best["review"]
        analysis     = best["analysis"]

        # ── Formatter ─────────────────────────────────────────────────────────
        markdown_output = self.formatter.run(
            analysis=analysis,
            manual_tests=manual_tests,
            api_tests=api_tests,
            ui_tests=ui_tests,
            review=review
        )

        result = GeneratedTestSuite(
            feature_name=analysis.feature_name,
            generated_at=datetime.now(),
            analysis=analysis,
            manual_test_cases=manual_tests,
            api_test_cases=api_tests,
            ui_test_cases=ui_tests,
            review=review,
            markdown_output=markdown_output
        )

        if self.use_rag and self.rag:
            self._store_in_rag(result)

        self._print_summary(result)
        return result
    
    def _print_loop_header(self, iteration: int, total: int) -> None:
        """Print a banner marking the start of each pipeline iteration."""
        console.print("\n")
        console.print(Panel(
            f"[bold white]Iteration {iteration} of {total}[/bold white]\n"
            f"[cyan]Planner → Generator → Reviewer[/cyan]"
            + (f"\n[dim](feedback loop — refining analysis from previous review)[/dim]"
               if iteration > 1 else ""),
            title=f"🔄 Pipeline Loop {iteration}/{total}",
            border_style="cyan"
        ))

    def _print_feedback_summary(self, review, iteration: int) -> None:
        """Print which review feedback is being passed back to the Planner."""
        console.print(f"\n[bold yellow]{'='*50}[/bold yellow]")
        console.print(f"[bold yellow]FEEDBACK LOOP — Passing Review to Planner[/bold yellow]")
        console.print(f"[bold yellow]Iteration {iteration} score: {review.final_score:.1f}% "
                      f"(threshold: {SCORE_THRESHOLD}%)[/bold yellow]")
        console.print(f"[bold yellow]{'='*50}[/bold yellow]")

        if review.coverage.coverage_gaps:
            console.print("[yellow]  Coverage gaps to address:[/yellow]")
            for gap in review.coverage.coverage_gaps:
                console.print(f"    • {gap}")

        if review.issues_found:
            console.print("[yellow]  Issues to fix:[/yellow]")
            for issue in review.issues_found:
                console.print(f"    • {issue}")

        if review.coverage.suggestions:
            console.print("[yellow]  Suggestions:[/yellow]")
            for suggestion in review.coverage.suggestions:
                console.print(f"    • {suggestion}")

    def _get_initial_rag_context(self, requirement: RequirementInput) -> str:
        """Get initial RAG context based on requirement."""
        if not self.rag:
            return ""
        
        # Simple keyword search on requirement content
        results = self.rag.search(
            query=requirement.content[:500],  # First 500 chars
            n_results=3
        )
        
        if not results:
            return ""
        
        context_parts = ["### Related Context from Knowledge Base"]
        for doc in results:
            context_parts.append(f"- {doc['content'][:200]}...")
        
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
        console.print("\n")
        console.print(Panel(
            f"[bold white]QA TEST CASE GENERATOR[/bold white]\n\n"
            f"[cyan]Input Type:[/cyan] {requirement.input_type.value}\n"
            f"[cyan]Content Length:[/cyan] {len(requirement.content)} characters\n"
            f"[cyan]RAG Enabled:[/cyan] {self.use_rag}",
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
    use_rag: bool = True,
    config: Optional[GenerationConfig] = None
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
        
    Returns:
        GeneratedTestSuite with all outputs
    """
    from core.models import InputType
    
    # Parse input type
    try:
        parsed_type = InputType(input_type)
    except ValueError:
        parsed_type = InputType.PLAIN_TEXT
    
    # Create requirement
    requirement = RequirementInput(
        content=requirement_text,
        input_type=parsed_type,
        project_context=project_context,
        tech_stack=tech_stack
    )
    
    # Run pipeline
    pipeline = TestGeneratorPipeline(use_rag=use_rag)
    return pipeline.run(requirement, config=config)
