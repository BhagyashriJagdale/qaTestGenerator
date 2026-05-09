"""
Generator Agent - Creates test cases based on planner analysis.
Second agent in the pipeline.
Makes three separate LLM calls (manual / API / UI) to avoid token-limit truncation.
"""

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
from rich.console import Console

console = Console()

# Token budget per call — well below DeepSeek / OpenAI limits
_TOKENS_PER_CALL = 8000


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
        tool_context: Optional[str] = None
    ) -> tuple[list[ManualTestCase], list[AutomationTestCase], list[AutomationTestCase]]:
        """
        Generate test cases in three separate LLM calls to prevent truncation.

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

        # --- Call 1: Manual test cases ---
        if config.include_manual:
            console.print("\n[cyan]  → Generating manual test cases...[/cyan]")
            result, err = self._generate_manual(full_base)
            manual_tests = result
            if err:
                failures.append(f"Manual: {err}")

        # --- Call 2: API automation ---
        if config.include_api:
            console.print("\n[cyan]  → Generating API automation scripts...[/cyan]")
            result, err = self._generate_api(full_base)
            api_tests = result
            if err:
                failures.append(f"API: {err}")

        # --- Call 3: UI automation ---
        if config.include_ui:
            console.print("\n[cyan]  → Generating UI automation scripts...[/cyan]")
            result, err = self._generate_ui(full_base)
            ui_tests = result
            if err:
                failures.append(f"UI: {err}")

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
            console.print(f"[red]Manual generation failed: {e}[/red]")
            return [], str(e)

    def _generate_api(self, base: str) -> tuple[list[AutomationTestCase], Optional[str]]:
        message = base + """

## YOUR TASK — API AUTOMATION SCRIPTS ONLY
Generate ONLY Playwright TypeScript API automation tests. Return a JSON object with this exact shape:
{
  "api_test_cases": [ ...test case objects... ]
}

ID FORMAT — MANDATORY:
- Use prefix ATC- for every API test case ID: ATC-001, ATC-002, ATC-003 ...
- Sequential numbers starting from 001. No other prefix is allowed.

Rules:
- Use Playwright's APIRequestContext.
- Include all imports at the top of every file.
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
            console.print(f"[red]API generation failed: {e}[/red]")
            return [], str(e)

    def _generate_ui(self, base: str) -> tuple[list[AutomationTestCase], Optional[str]]:
        message = base + """

## YOUR TASK — UI AUTOMATION SCRIPTS ONLY
Generate ONLY Playwright TypeScript UI automation tests. Return a JSON object with this exact shape:
{
  "ui_test_cases": [ ...test case objects... ]
}

ID FORMAT — MANDATORY:
- Use prefix UTC- for every UI test case ID: UTC-001, UTC-002, UTC-003 ...
- Sequential numbers starting from 001. No other prefix is allowed.

Rules:
- Use Playwright page object model.
- Locators: prefer data-testid, then id, then CSS — NEVER xpath.
- Include all imports at the top of every file.
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
            console.print(f"[red]UI generation failed: {e}[/red]")
            return [], str(e)

    # ------------------------------------------------------------------
    # Message builders
    # ------------------------------------------------------------------

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
        """Re-assign sequential IDs with the correct type prefix regardless of what the LLM generated."""
        for i, test in enumerate(tests, start=1):
            correct_id = f"{prefix}-{i:03d}"
            if test.test_case_id != correct_id:
                tests[i - 1] = test.model_copy(update={"test_case_id": correct_id})
        return tests

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
