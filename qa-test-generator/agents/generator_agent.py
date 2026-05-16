"""
Generator Agent - Creates test cases based on planner analysis.
Second agent in the pipeline.
Generates manual tests first (sequential), then API and UI automation in parallel,
passing the manual tests as context so automation scripts align with manual scenarios.
"""

import concurrent.futures
import traceback
from typing import Optional
from .base_agent import BaseAgent
from .prompts import GENERATOR_SYSTEM_PROMPT
from core.models import (
    RequirementInput,
    GenerationConfig,
    PlannerAnalysis,
    ManualTestCase,
    AutomationTestCase,
    TestCaseType,
)
from tools.website_crawler import WebsiteContext
from rich.console import Console

console = Console()

# Token budget per call — capped to DeepSeek's effective output window (~4096 tokens)
_TOKENS_PER_CALL = 4000


class GeneratorAgent(BaseAgent):
    """
    Generator Agent creates comprehensive test cases based on
    the planner's analysis and generation configuration.
    """

    def __init__(self):
        super().__init__(
            name="Generator Agent",
            system_prompt=GENERATOR_SYSTEM_PROMPT
        )

    def run(
        self,
        requirement: RequirementInput,
        analysis: PlannerAnalysis,
        config: GenerationConfig,
        rag_context: Optional[str] = None,
        tool_context: Optional[str] = None,
        website_context: Optional[WebsiteContext] = None,
        existing_manual_tests: Optional[list[ManualTestCase]] = None,
    ) -> tuple[list[ManualTestCase], list[AutomationTestCase], list[AutomationTestCase]]:
        """
        Generate test cases with manual tests first, then API/UI automation using
        manual test cases as context so automation aligns with manual scenarios.

        Args:
            tool_context: GitHub/codebase context (grounding for code structure).
            website_context: Structured WebsiteContext from the crawler. Injected
                             directly into task prompts as mandatory locator/endpoint
                             data so the LLM uses exact selectors from the real app.
            existing_manual_tests: Already-generated manual tests to use as context
                                   when regenerating only API/UI (refinement passes).

        Returns:
            Tuple of (manual_tests, api_tests, ui_tests)
        """
        console.print(f"\n[bold green]{'='*50}[/bold green]")
        console.print(f"[bold green]GENERATOR AGENT[/bold green]")
        console.print(f"[bold green]{'='*50}[/bold green]")

        base = self._base_context(requirement, analysis, config)
        full_base = self._build_context(base, rag_context=rag_context, tool_context=tool_context)

        manual_tests: list[ManualTestCase] = []
        api_tests: list[AutomationTestCase] = []
        ui_tests: list[AutomationTestCase] = []
        failures: list[str] = []

        # Step 1: Generate manual test cases first (sequential) so they can inform automation
        if config.include_manual:
            console.print("\n[cyan]  → Generating manual test cases...[/cyan]")
            manual_result, manual_err = self._generate_manual(full_base)
            manual_tests = manual_result
            if manual_err:
                failures.append(f"Manual: {manual_err}")

        # Determine which manual tests to use as context for automation generation.
        # Prefer newly generated tests; fall back to existing_manual_tests in refinement passes
        # so automation always has manual context even when manual regeneration fails.
        manual_context_tests = manual_tests or existing_manual_tests or []
        manual_context = self._format_manual_context(manual_context_tests)

        # Step 2: Generate API and UI automation in parallel, both informed by manual test cases
        enabled: dict[str, concurrent.futures.Future] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            if config.include_api:
                console.print("[cyan]  → Generating API automation scripts (based on manual tests)...[/cyan]")
                enabled["api"] = pool.submit(self._generate_api, full_base, manual_context, website_context)
            if config.include_ui:
                console.print("[cyan]  → Generating UI automation scripts (based on manual tests)...[/cyan]")
                enabled["ui"] = pool.submit(self._generate_ui, full_base, manual_context, website_context)
            concurrent.futures.wait(enabled.values())

        if "api" in enabled:
            api_result, api_err = enabled["api"].result()
            api_tests = api_result
            if api_err:
                failures.append(f"API: {api_err}")

        if "ui" in enabled:
            ui_result, ui_err = enabled["ui"].result()
            ui_tests = ui_result
            if ui_err:
                failures.append(f"UI: {ui_err}")

        if failures:
            for f in failures:
                console.print(f"[yellow]  ⚠ Generation warning — {f}[/yellow]")

        if not manual_tests and not api_tests and not ui_tests:
            raise RuntimeError(
                "All generation calls failed — no test cases produced. "
                f"Failures: {'; '.join(failures)}"
            )

        self._log_generation(manual_tests, api_tests, ui_tests)
        return manual_tests, api_tests, ui_tests

    # ------------------------------------------------------------------
    # Per-type generation
    # ------------------------------------------------------------------

    def _generate_manual(self, base: str) -> tuple[list[ManualTestCase], Optional[str]]:
        message = base + """

## YOUR TASK — MANUAL TEST CASES ONLY
Generate ONLY manual test cases. Return a JSON object with this exact shape:
{
  "manual_test_cases": [ ...test case objects... ]
}

ID FORMAT — MANDATORY:
- Use prefix MTC- for every manual test case ID: MTC-001, MTC-002, MTC-003 ...
- Sequential numbers starting from 001. No other prefix is allowed.

Rules:
- MINIMUM 5 steps per test case with exact UI element names and exact input values.
- Expected result must be a specific, observable, measurable outcome.
- Include concrete test data in every test_data field.
- Cover happy_path, negative (invalid inputs, wrong credentials), edge_case, boundary, security scenarios.
- NEVER write vague steps or results.
"""
        try:
            result = self._generate_json(message, temperature=0.1, max_tokens=_TOKENS_PER_CALL)
            tests = self._parse_manual_tests(result.get("manual_test_cases", []))
            return self._normalize_ids(tests, "MTC"), None
        except Exception as e:
            console.print(f"[red]Manual generation failed: {type(e).__name__}: {e}[/red]")
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            return [], f"{type(e).__name__}: {e}"

    def _generate_api(
        self, base: str, manual_context: str = "", website_context: Optional[WebsiteContext] = None
    ) -> tuple[list[AutomationTestCase], Optional[str]]:
        manual_section = (
            f"\n\n## MANUAL TEST CASES TO AUTOMATE\n"
            f"Your API tests MUST cover the same scenarios as these manual test cases.\n"
            f"Use the same test data, scenario types, and expected outcomes — translated to HTTP status codes and response body assertions.\n"
            f"{manual_context}"
        ) if manual_context else ""

        website_section = (
            self._build_website_instruction(website_context, mode="api")
            if website_context and not website_context.is_empty()
            else ""
        )

        message = base + manual_section + website_section + """

## YOUR TASK — API AUTOMATION SCRIPTS ONLY
Generate ONLY Playwright TypeScript API automation tests. Return a JSON object with this exact shape:
{
  "api_test_cases": [ ...test case objects... ]
}

ID FORMAT — MANDATORY:
- Use prefix ATC- for every API test case ID: ATC-001, ATC-002, ATC-003 ...
- Sequential numbers starting from 001. No other prefix is allowed.
- "manual_test_refs": REQUIRED on every test — list the MTC-XXX IDs this test automates (e.g. ["MTC-001"]). Empty array is NOT acceptable when manual tests exist.
- "priority": MUST match the priority of the referenced manual test case exactly.

Rules:
- Each API test must correspond to a manual test case scenario (happy path, negative, edge case, boundary, security).
- Use the same test data values from the manual test cases in your API requests.
- Use Playwright's APIRequestContext.
- COMPACT CODE REQUIRED: Use a single describe block per file. Reuse the auth token set in beforeAll — do NOT redeclare imports or variables per test.
- Declare imports once at the top; no repeated import statements inside tests.
- Every test must be FULLY implemented — no placeholders, no "// TODO".
- Every test block must be fully closed with all braces — never cut off mid-function.
- MANDATORY negative scenarios (write a dedicated test for each):
    1. Missing required fields → assert status 400 + exact error message field
    2. Invalid field format → assert status 400 + error detail
    3. Wrong credentials → assert status 401 + body.message
    4. Duplicate/conflict → assert status 409
    5. Forbidden action → assert status 403
    6. Resource not found → assert status 404
    7. Expired/invalid token → assert status 401
- Each negative test must assert BOTH the HTTP status AND the response body error field.
- Include beforeAll/afterAll hooks for auth setup and cleanup.
"""
        try:
            result = self._generate_json(message, temperature=0.1, max_tokens=_TOKENS_PER_CALL)
            tests = self._parse_automation_tests(
                result.get("api_test_cases", []), TestCaseType.API_AUTOMATION
            )
            return self._normalize_ids(tests, "ATC"), None
        except Exception as e:
            console.print(f"[red]API generation failed: {type(e).__name__}: {e}[/red]")
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            return [], f"{type(e).__name__}: {e}"

    def _generate_ui(
        self, base: str, manual_context: str = "", website_context: Optional[WebsiteContext] = None
    ) -> tuple[list[AutomationTestCase], Optional[str]]:
        manual_section = (
            f"\n\n## MANUAL TEST CASES TO AUTOMATE\n"
            f"Your UI tests MUST cover the same scenarios as these manual test cases.\n"
            f"Use the same test data, action sequences, and expected outcomes — translated to Playwright page interactions and assertions.\n"
            f"{manual_context}"
        ) if manual_context else ""

        website_section = (
            self._build_website_instruction(website_context, mode="ui")
            if website_context and not website_context.is_empty()
            else ""
        )

        message = base + manual_section + website_section + """

## YOUR TASK — UI AUTOMATION SCRIPTS ONLY
Generate ONLY Playwright TypeScript UI automation tests. Return a JSON object with this exact shape:
{
  "ui_test_cases": [ ...test case objects... ]
}

ID FORMAT — MANDATORY:
- Use prefix UTC- for every UI test case ID: UTC-001, UTC-002, UTC-003 ...
- Sequential numbers starting from 001. No other prefix is allowed.
- "manual_test_refs": REQUIRED on every test — list the MTC-XXX IDs this test automates (e.g. ["MTC-001"]). Empty array is NOT acceptable when manual tests exist.
- "priority": MUST match the priority of the referenced manual test case exactly.

Rules:
- Each UI test must correspond to a manual test case scenario (happy path, negative, edge case, boundary, security).
- Mirror the manual test steps as Playwright actions using the same test data values.
- Use Playwright page object model.
- COMPACT CODE REQUIRED: Use a single describe block per file. Share page setup in beforeEach — do NOT redeclare imports or locator variables per test.
- Declare imports once at the top; no repeated import statements inside tests.
- Locators: prefer data-testid, then id, then CSS — NEVER xpath.
- Every test must be FULLY implemented — no placeholders, no "// assert here".
- Every test block must be fully closed with all braces — never cut off mid-function.
- MANDATORY negative scenarios (write a dedicated test for each):
    1. Empty required field → assert inline error element visible with exact text
    2. Invalid format input → assert field-level error message text
    3. Wrong credentials → assert error banner text AND URL stays unchanged
    4. Boundary value (max-length, zero) → assert error or clamped value shown
    5. Double-click submit → assert button disabled after first click
    6. Network failure (use page.route to mock 500) → assert user-visible error message
- Each negative test must assert the exact error element text AND that page state did not change.
- Include beforeEach for navigation and afterEach for cleanup.
"""
        try:
            result = self._generate_json(message, temperature=0.1, max_tokens=_TOKENS_PER_CALL)
            tests = self._parse_automation_tests(
                result.get("ui_test_cases", []), TestCaseType.UI_AUTOMATION
            )
            return self._normalize_ids(tests, "UTC"), None
        except Exception as e:
            console.print(f"[red]UI generation failed: {type(e).__name__}: {e}[/red]")
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            return [], f"{type(e).__name__}: {e}"

    # ------------------------------------------------------------------
    # Website context injection (DESIGN-1: uses structured data directly)
    # ------------------------------------------------------------------

    def _build_website_instruction(self, website_context: WebsiteContext, mode: str) -> str:
        """
        Build an explicit mandatory instruction block from a WebsiteContext object.
        Injected directly into the task prompt — no regex re-parsing needed.

        mode="ui"  → page URL + locators for Playwright page interactions
        mode="api" → API endpoints and form actions for request URLs
        """
        lines = [
            "\n\n## ⚠ LIVE WEBSITE DATA — MANDATORY (from automated crawl)",
            "The values below were extracted from the actual running application.",
            "You MUST use ONLY these values. Do not guess, invent, or substitute any locators or URLs.",
        ]

        if mode == "ui":
            if website_context.url:
                lines.append(f"\n**PAGE URL** — use in every `page.goto()` call:")
                lines.append(f"  {website_context.url}")

            if website_context.locators:
                lines.append(
                    "\n**LOCATORS** — use these EXACT strings in every "
                    "`page.locator()`, `page.fill()`, `page.click()` call:"
                )
                for loc in website_context.locators:
                    lines.append(f"  - `{loc}`")
            else:
                # PROMPT-3: no form fields found — guide the LLM away from form scenarios
                lines.append(
                    "\n⚠ No interactive form elements were found on this page. "
                    "Skip form-related negative scenarios (empty field, invalid format input). "
                    "Focus instead on: navigation, page-load states, network errors, and auth/session scenarios."
                )

            if website_context.api_urls or website_context.form_actions:
                lines.append("\n**API PATHS** — use these in `page.route()` mock patterns:")
                for url in dict.fromkeys(website_context.form_actions + website_context.api_urls):
                    lines.append(f"  - `{url}`")

            if website_context.locators:
                lines.append(
                    "\nCRITICAL: Every selector in your generated code must appear in the LOCATORS list above. "
                    "If a UI element is not listed, do NOT write a test for it."
                )

        else:  # api
            all_endpoints = list(dict.fromkeys(website_context.form_actions + website_context.api_urls))

            if website_context.url:
                lines.append(f"\n**BASE URL** — extract origin for `baseURL` config:")
                lines.append(f"  {website_context.url}")

            if all_endpoints:
                lines.append("\n**API ENDPOINTS** — use these EXACT paths for every request URL:")
                for ep in all_endpoints:
                    lines.append(f"  - `{ep}`")
                # PROMPT-2: explicit guidance for page.route() patterns
                lines.append(
                    "\nFor `page.route()` interception, use `**<path>` glob patterns "
                    "(e.g. `**/<endpoint-path>`) matching paths from the list above."
                )
            else:
                lines.append(
                    "\n(No API endpoints were extracted from the page — infer from requirement context.)"
                )

            lines.append(
                "\nCRITICAL: Every `request.post()`, `request.get()` etc. must use a path from the list above. "
                "Do not invent endpoint paths."
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Message builders
    # ------------------------------------------------------------------

    def _format_manual_context(
        self, manual_tests: list[ManualTestCase], max_chars: int = 1500
    ) -> str:
        """Serialize manual test cases into a compact context string for automation prompts.

        Capped at max_chars to leave room for code output within the token budget.
        """
        if not manual_tests:
            return ""
        lines: list[str] = []
        chars = 0
        for tc in manual_tests:
            block: list[str] = [f"\n### {tc.test_case_id}: {tc.title} [{tc.scenario_type.value}]"]
            for step in tc.steps:
                data_part = f" [Data: {step.test_data}]" if step.test_data else ""
                block.append(
                    f"  Step {step.step_number}: {step.action}{data_part}"
                    f" → {step.expected_result}"
                )
            entry = "\n".join(block)
            # BUG-4 fix: check budget BEFORE appending, even for the first entry.
            # Truncate the first entry rather than blindly including it if it is huge.
            if chars + len(entry) > max_chars:
                if chars == 0:
                    # Always include at least a truncated version of the first entry
                    lines.append(entry[:max_chars])
                break
            lines.append(entry)
            chars += len(entry)
        return "\n".join(lines)

    def _base_context(
        self,
        requirement: RequirementInput,
        analysis: PlannerAnalysis,
        config: GenerationConfig,
    ) -> str:
        scenarios_str = ", ".join([s.value for s in config.scenarios])
        return f"""## ORIGINAL REQUIREMENT
{requirement.content}

## PLANNER ANALYSIS
- **Feature:** {analysis.feature_name}
- **Domain:** {analysis.domain}
- **Intent:** {analysis.intent}
- **Scope:** {analysis.scope}
- **Endpoints:** {', '.join(analysis.endpoints) if analysis.endpoints else 'N/A'}
- **UI Elements:** {', '.join(analysis.ui_elements) if analysis.ui_elements else 'N/A'}
- **Focus Areas:** {', '.join(analysis.test_focus_areas)}

## GENERATION CONFIG
- **Framework:** {config.framework}
- **Language:** {config.language}
- **Scenarios to Cover:** {scenarios_str}"""

    # ------------------------------------------------------------------
    # ID normalisation
    # ------------------------------------------------------------------

    def _normalize_ids(self, tests: list, prefix: str) -> list:
        """Re-assign sequential IDs with the correct type prefix. Returns a new list."""
        result = []
        for i, test in enumerate(tests, start=1):
            correct_id = f"{prefix}-{i:03d}"
            if test.test_case_id != correct_id:
                test = test.model_copy(update={"test_case_id": correct_id})
            result.append(test)
        return result

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    def _parse_manual_tests(self, data: list[dict]) -> list[ManualTestCase]:
        tests = []
        for item in data:
            try:
                tests.append(ManualTestCase(**item))
            except Exception as e:
                console.print(f"[yellow]Warning: Could not parse manual test: {e}[/yellow]")
        return tests

    def _parse_automation_tests(
        self, data: list[dict], test_type: TestCaseType
    ) -> list[AutomationTestCase]:
        tests = []
        for item in data:
            try:
                item["test_type"] = test_type
                tests.append(AutomationTestCase(**item))
            except Exception as e:
                console.print(f"[yellow]Warning: Could not parse automation test: {e}[/yellow]")
        return tests

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_generation(
        self,
        manual_tests: list[ManualTestCase],
        api_tests: list[AutomationTestCase],
        ui_tests: list[AutomationTestCase],
    ) -> None:
        console.print(f"\n[green]✓ Test Cases Generated[/green]")
        console.print(f"  Manual Tests:    [bold]{len(manual_tests)}[/bold]")
        console.print(f"  API Automation:  [bold]{len(api_tests)}[/bold]")
        console.print(f"  UI Automation:   [bold]{len(ui_tests)}[/bold]")
        console.print(f"  [bold]Total: {len(manual_tests) + len(api_tests) + len(ui_tests)}[/bold]")
