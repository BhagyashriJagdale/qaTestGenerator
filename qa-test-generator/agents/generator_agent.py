"""
Generator Agent - Creates test cases based on planner analysis.
Second agent in the pipeline.
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
    ScenarioType,
    Priority,
    TestStep,
)
from rich.console import Console

console = Console()

MAX_RETRIES = 2


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
        Generate test cases based on analysis and configuration.
        
        Args:
            requirement: Original requirement input
            analysis: Planner's analysis
            config: Generation configuration
            rag_context: Optional RAG context
            tool_context: Optional tool context (Jira, API docs)
            
        Returns:
            Tuple of (manual_tests, api_tests, ui_tests)
        """
        console.print(f"\n[bold green]{'='*50}[/bold green]")
        console.print(f"[bold green]GENERATOR AGENT[/bold green]")
        console.print(f"[bold green]{'='*50}[/bold green]")
        
        # Build the user message
        user_message = self._build_user_message(requirement, analysis, config)
        
        # Add contexts
        full_message = self._build_context(
            user_message,
            rag_context=rag_context,
            tool_context=tool_context
        )
        
        manual_tests: list[ManualTestCase] = []
        api_tests: list[AutomationTestCase] = []
        ui_tests: list[AutomationTestCase] = []

        for attempt in range(1, MAX_RETRIES + 2):
            try:
                # Raise temperature slightly on retries to avoid the same empty response
                temperature = 0.5 + (attempt - 1) * 0.1
                result = self._generate_json(full_message, temperature=temperature, max_tokens=8000)

                manual_tests = self._ensure_negative_manual_scenarios(
                    self._ensure_preconditions(
                        self._parse_manual_tests(result.get("manual_test_cases", [])),
                        analysis,
                    ),
                    analysis,
                )
                api_tests = self._ensure_negative_automation_scenarios(
                    self._parse_automation_tests(
                        result.get("api_test_cases", []), TestCaseType.API_AUTOMATION
                    ),
                    TestCaseType.API_AUTOMATION,
                    analysis,
                )
                ui_tests = self._ensure_negative_automation_scenarios(
                    self._parse_automation_tests(
                        result.get("ui_test_cases", []), TestCaseType.UI_AUTOMATION
                    ),
                    TestCaseType.UI_AUTOMATION,
                    analysis,
                )

                self._print_iteration_results(attempt, manual_tests, api_tests, ui_tests)

                total = len(manual_tests) + len(api_tests) + len(ui_tests)
                if total > 0:
                    break

                if attempt <= MAX_RETRIES:
                    console.print(
                        f"[yellow]Attempt {attempt}: 0 test cases generated — retrying "
                        f"({attempt}/{MAX_RETRIES})...[/yellow]"
                    )
                else:
                    console.print(
                        f"[red]All {MAX_RETRIES + 1} attempts produced 0 test cases.[/red]"
                    )

            except Exception as e:
                console.print(f"[red]Error in Generator Agent (attempt {attempt}): {e}[/red]")
                if attempt > MAX_RETRIES:
                    raise

        self._log_generation(manual_tests, api_tests, ui_tests)
        return manual_tests, api_tests, ui_tests
    
    def _build_user_message(
        self,
        requirement: RequirementInput,
        analysis: PlannerAnalysis,
        config: GenerationConfig
    ) -> str:
        """Build the user message with all context."""
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
- **Generate Manual Tests:** {config.include_manual}
- **Generate API Tests:** {config.include_api}
- **Generate UI Tests:** {config.include_ui}
- **Framework:** {config.framework}
- **Language:** {config.language}
- **Scenarios to Cover:** {scenarios_str}

Generate comprehensive test cases following the specified configuration.
Ensure all scenario types are covered where applicable.
Use Playwright with TypeScript for automation scripts.

MANUAL TEST CASE QUALITY REQUIREMENTS:
- Every step action must name the exact UI element, field, button, or endpoint being interacted with.
- Every step expected_result must be specific and measurable — state the exact text, HTTP code,
  field value, or visual change the tester should observe. Never use vague phrases like
  "works correctly", "success message appears", or "user is redirected".
- Supply test_data for any step that requires concrete input values (e.g. email, quantity, ID).
- Minimum 3 steps for happy_path scenarios; minimum 2 steps for negative scenarios.

AUTOMATION SCRIPT ASSERTION REQUIREMENTS:
- API tests: every test() block MUST call expect(response.status()).toBe(NNN) AND check at least
  one field from the parsed response body (e.g. expect(body.id).toEqual(...) or
  expect(body.error).toContain(...)). A test that only checks the status code is a failure.
- UI tests: every test() block MUST include at least one Playwright async assertion
  (await expect(locator).toBeVisible() / toHaveText() / toHaveURL() / toHaveValue()).
  A test body with no expect() call is a failure."""
    
    def _ensure_preconditions(
        self,
        tests: list[ManualTestCase],
        analysis: PlannerAnalysis,
    ) -> list[ManualTestCase]:
        """
        Post-processing guard: any manual test that came back with an empty
        preconditions list gets populated with scenario-appropriate defaults
        so the field is never blank in the final output.
        """
        _SCENARIO_DEFAULTS: dict[ScenarioType, list[str]] = {
            ScenarioType.HAPPY_PATH: [
                "User is registered and authenticated",
                "System is in a valid, clean state",
            ],
            ScenarioType.NEGATIVE: [
                "User is authenticated unless the test specifically covers an auth failure",
                "System is in a valid state with known invalid inputs prepared",
            ],
            ScenarioType.EDGE_CASE: [
                "System is in a valid state",
                "Edge-case test data has been prepared",
            ],
            ScenarioType.BOUNDARY: [
                "System is in a valid state",
                "Boundary-value test data (min and max limits) has been prepared",
            ],
            ScenarioType.SECURITY: [
                "Application is accessible via browser or API client",
                "Test environment is isolated from production",
                "Malicious/injection payloads have been prepared",
            ],
            ScenarioType.CROSS_PLATFORM: [
                "Test environment supports the target browsers and devices",
                "User is authenticated",
            ],
        }

        domain_precondition = (
            f"{analysis.domain} module is accessible and responsive"
            if analysis.domain
            else "Application is accessible and responsive"
        )

        result: list[ManualTestCase] = []
        for test in tests:
            if not test.preconditions:
                defaults = [domain_precondition] + _SCENARIO_DEFAULTS.get(
                    test.scenario_type, ["System is in a valid state"]
                )
                console.print(
                    f"[yellow]  ⚠ {test.test_case_id}: missing preconditions — "
                    f"applying defaults for scenario '{test.scenario_type.value}'.[/yellow]"
                )
                test = test.copy(update={"preconditions": defaults})
            result.append(test)
        return result

    def _ensure_negative_manual_scenarios(
        self,
        tests: list[ManualTestCase],
        analysis: PlannerAnalysis,
    ) -> list[ManualTestCase]:
        """
        If the LLM returned no negative manual tests, synthesise two baseline
        negative test cases (invalid input + unauthorised access) so negative
        coverage is always present in the output.
        """
        if any(t.scenario_type == ScenarioType.NEGATIVE for t in tests):
            return tests

        console.print(
            "[yellow]  ⚠ No negative manual scenarios returned — "
            "synthesising baseline negative tests.[/yellow]"
        )
        feature = analysis.feature_name
        domain  = analysis.domain or "Application"

        existing_ids = {t.test_case_id for t in tests}
        def _next_id(prefix: str) -> str:
            for n in range(1, 999):
                tid = f"{prefix}-{n:03d}"
                if tid not in existing_ids:
                    existing_ids.add(tid)
                    return tid
            return f"{prefix}-FALLBACK"

        neg_tests = [
            ManualTestCase(
                test_case_id=_next_id("TC-NEG"),
                title=f"{feature} — Invalid Input Rejected",
                description=(
                    f"Verify {feature} returns a clear validation error "
                    "when required fields are missing or contain invalid data."
                ),
                priority=Priority.HIGH,
                scenario_type=ScenarioType.NEGATIVE,
                preconditions=[
                    f"{domain} is accessible",
                    "User is authenticated",
                    "Invalid test data (empty fields, wrong formats) has been prepared",
                ],
                steps=[
                    TestStep(
                        step_number=1,
                        action="Submit a request with missing or invalid required fields",
                        expected_result=(
                            "System returns a descriptive validation error; "
                            "no data is persisted"
                        ),
                    ),
                    TestStep(
                        step_number=2,
                        action="Verify the error message identifies the invalid field",
                        expected_result="Error message is user-facing and actionable",
                    ),
                ],
                postconditions=["No data is persisted from the invalid submission"],
                tags=[domain.lower().replace(" ", "_"), "negative", "validation"],
            ),
            ManualTestCase(
                test_case_id=_next_id("TC-NEG"),
                title=f"{feature} — Unauthorised Access Blocked",
                description=(
                    f"Verify {feature} prevents access by unauthenticated "
                    "or insufficiently privileged users."
                ),
                priority=Priority.HIGH,
                scenario_type=ScenarioType.NEGATIVE,
                preconditions=[
                    f"{domain} is accessible",
                    "User is NOT authenticated, OR authenticated without required permissions",
                ],
                steps=[
                    TestStep(
                        step_number=1,
                        action="Attempt to access the feature without authentication or with insufficient permissions",
                        expected_result="Request is blocked by the system",
                    ),
                    TestStep(
                        step_number=2,
                        action="Observe the response or redirect",
                        expected_result=(
                            "Returns HTTP 401/403 or redirects to login; "
                            "no sensitive data is exposed"
                        ),
                    ),
                ],
                postconditions=["Session state and data are unchanged"],
                tags=[domain.lower().replace(" ", "_"), "negative", "auth"],
            ),
        ]

        console.print(
            f"[yellow]  ✓ Synthesised {len(neg_tests)} negative manual test(s): "
            f"{[t.test_case_id for t in neg_tests]}[/yellow]"
        )
        return tests + neg_tests

    def _ensure_negative_automation_scenarios(
        self,
        tests: list[AutomationTestCase],
        test_type: TestCaseType,
        analysis: PlannerAnalysis,
    ) -> list[AutomationTestCase]:
        """
        If the LLM returned no negative automation tests for the given type,
        synthesise one with complete, runnable Playwright TypeScript code.
        """
        if any(t.scenario_type == ScenarioType.NEGATIVE for t in tests):
            return tests

        label    = "API" if test_type == TestCaseType.API_AUTOMATION else "UI"
        feature  = analysis.feature_name
        domain   = analysis.domain or "Application"
        endpoint = analysis.endpoints[0] if analysis.endpoints else "/api/resource"
        ui_el    = analysis.ui_elements[0] if analysis.ui_elements else "input"

        console.print(
            f"[yellow]  ⚠ No negative {label} scenarios returned — "
            f"synthesising baseline negative test.[/yellow]"
        )

        existing_ids = {t.test_case_id for t in tests}
        prefix = "TC-API-NEG" if test_type == TestCaseType.API_AUTOMATION else "TC-UI-NEG"
        tid = f"{prefix}-001"
        for n in range(1, 999):
            candidate = f"{prefix}-{n:03d}"
            if candidate not in existing_ids:
                tid = candidate
                break

        if test_type == TestCaseType.API_AUTOMATION:
            code = (
                "import {{ test, expect }} from '@playwright/test';\n\n"
                "test.describe('{feature} — API Negative Scenarios', () => {{\n"
                "  test.beforeEach(async ({{ request }}) => {{\n"
                "    // no shared state needed for negative tests\n"
                "  }});\n\n"
                "  test('returns 401 when no auth token is provided', async ({{ request }}) => {{\n"
                "    const response = await request.get('{endpoint}');\n"
                "    expect(response.status()).toBe(401);\n"
                "    const body = await response.json();\n"
                "    expect(body).toHaveProperty('error');\n"
                "  }});\n\n"
                "  test('returns 400 for missing required fields', async ({{ request }}) => {{\n"
                "    const response = await request.post('{endpoint}', {{ data: {{}} }});\n"
                "    expect(response.status()).toBe(400);\n"
                "    const body = await response.json();\n"
                "    expect(body).toHaveProperty('error');\n"
                "  }});\n\n"
                "  test('returns 404 for non-existent resource', async ({{ request }}) => {{\n"
                "    const response = await request.get('{endpoint}/non-existent-id-00000');\n"
                "    expect(response.status()).toBe(404);\n"
                "    const body = await response.json();\n"
                "    expect(body).toHaveProperty('error');\n"
                "  }});\n"
                "}});"
            ).format(feature=feature, endpoint=endpoint)
            file_name = f"{domain.lower().replace(' ', '_')}.negative.api.spec.ts"
        else:
            code = (
                "import {{ test, expect }} from '@playwright/test';\n\n"
                "test.describe('{feature} — UI Negative Scenarios', () => {{\n"
                "  test.beforeEach(async ({{ page }}) => {{\n"
                "    await page.goto('/');\n"
                "  }});\n\n"
                "  test('shows validation error when required field is empty', "
                "async ({{ page }}) => {{\n"
                "    await page.getByRole('button', {{ name: /submit|add|save/i }}).click();\n"
                "    await expect(page.getByRole('alert')).toBeVisible();\n"
                "  }});\n\n"
                "  test('redirects unauthenticated user to login', async ({{ page }}) => {{\n"
                "    await page.goto('/protected');\n"
                "    await expect(page).toHaveURL(/login|sign-in/i);\n"
                "  }});\n\n"
                "  test('shows inline error for invalid {ui_el} input', "
                "async ({{ page }}) => {{\n"
                "    await page.getByRole('textbox', {{ name: /{ui_el}/i }}).fill('INVALID!@#');\n"
                "    await page.getByRole('button', {{ name: /submit|add|save/i }}).click();\n"
                "    await expect(\n"
                "      page.locator('[data-testid=\"error-message\"], [role=\"alert\"]')\n"
                "    ).toBeVisible();\n"
                "  }});\n"
                "}});"
            ).format(feature=feature, ui_el=ui_el)
            file_name = f"{domain.lower().replace(' ', '_')}.negative.ui.spec.ts"

        synth = AutomationTestCase(
            test_case_id=tid,
            title=f"{feature} — {label} Negative Scenarios",
            test_type=test_type,
            scenario_type=ScenarioType.NEGATIVE,
            priority=Priority.HIGH,
            code=code,
            file_name=file_name,
            dependencies=["@playwright/test"],
        )
        console.print(f"[yellow]  ✓ Synthesised negative {label} test: {tid}[/yellow]")
        return tests + [synth]

    def _parse_manual_tests(self, data: list[dict]) -> list[ManualTestCase]:
        """Parse manual test cases from JSON."""
        tests = []
        for item in data:
            try:
                test = ManualTestCase(**item)
                tests.append(test)
            except Exception as e:
                console.print(f"[yellow]Warning: Could not parse manual test: {e}[/yellow]")
        return tests
    
    def _parse_automation_tests(
        self,
        data: list[dict],
        test_type: TestCaseType
    ) -> list[AutomationTestCase]:
        """Parse automation test cases from JSON."""
        tests = []
        for item in data:
            try:
                item["test_type"] = test_type
                test = AutomationTestCase(**item)
                tests.append(test)
            except Exception as e:
                console.print(f"[yellow]Warning: Could not parse automation test: {e}[/yellow]")
        return tests
    
    def _print_iteration_results(
        self,
        attempt: int,
        manual_tests: list[ManualTestCase],
        api_tests: list[AutomationTestCase],
        ui_tests: list[AutomationTestCase],
    ) -> None:
        """Print every test case and script generated in this iteration."""
        total = len(manual_tests) + len(api_tests) + len(ui_tests)
        console.rule(f"[bold cyan] Iteration {attempt} — {total} test case(s) generated [/bold cyan]")

        # ── Manual test cases ─────────────────────────────────────────────────
        if manual_tests:
            console.print(f"\n[bold green]▌ MANUAL TEST CASES  ({len(manual_tests)})[/bold green]")
            console.rule(style="green")
            for tc in manual_tests:
                console.print(
                    f"\n  [bold]{tc.test_case_id}[/bold]  "
                    f"[[yellow]{tc.scenario_type.value}[/yellow]]  "
                    f"[[magenta]{tc.priority.value.upper()}[/magenta]]  "
                    f"{tc.title}"
                )
                if tc.description:
                    console.print(f"  [dim]{tc.description}[/dim]")
                if tc.preconditions:
                    console.print("  [dim]Preconditions:[/dim]")
                    for pre in tc.preconditions:
                        console.print(f"    • {pre}")
                if tc.steps:
                    console.print("  [dim]Steps:[/dim]")
                    for step in tc.steps:
                        console.print(
                            f"    [bold]{step.step_number}.[/bold] {step.action}\n"
                            f"       [green]→[/green] {step.expected_result}"
                            + (f"\n       [dim]data: {step.test_data}[/dim]" if step.test_data else "")
                        )
                if tc.postconditions:
                    console.print("  [dim]Postconditions:[/dim]")
                    for post in tc.postconditions:
                        console.print(f"    • {post}")
        else:
            console.print("[dim]  (no manual test cases)[/dim]")

        # ── API automation ─────────────────────────────────────────────────────
        if api_tests:
            console.print(f"\n[bold blue]▌ API AUTOMATION SCRIPTS  ({len(api_tests)})[/bold blue]")
            console.rule(style="blue")
            for tc in api_tests:
                console.print(
                    f"\n  [bold]{tc.test_case_id}[/bold]  "
                    f"[[yellow]{tc.scenario_type.value}[/yellow]]  "
                    f"[[magenta]{tc.priority.value.upper()}[/magenta]]  "
                    f"{tc.title}"
                )
                console.print(f"  [dim]File:[/dim] [cyan]{tc.file_name}[/cyan]")
                console.print(f"  [dim]{'─' * 62}[/dim]")
                for line in tc.code.splitlines():
                    console.print(f"  [dim]│[/dim] {line}")
                console.print(f"  [dim]{'─' * 62}[/dim]")
        else:
            console.print("[dim]  (no API automation scripts)[/dim]")

        # ── UI automation ──────────────────────────────────────────────────────
        if ui_tests:
            console.print(f"\n[bold purple]▌ UI AUTOMATION SCRIPTS  ({len(ui_tests)})[/bold purple]")
            console.rule(style="purple")
            for tc in ui_tests:
                console.print(
                    f"\n  [bold]{tc.test_case_id}[/bold]  "
                    f"[[yellow]{tc.scenario_type.value}[/yellow]]  "
                    f"[[magenta]{tc.priority.value.upper()}[/magenta]]  "
                    f"{tc.title}"
                )
                console.print(f"  [dim]File:[/dim] [cyan]{tc.file_name}[/cyan]")
                console.print(f"  [dim]{'─' * 62}[/dim]")
                for line in tc.code.splitlines():
                    console.print(f"  [dim]│[/dim] {line}")
                console.print(f"  [dim]{'─' * 62}[/dim]")
        else:
            console.print("[dim]  (no UI automation scripts)[/dim]")

        console.rule(style="cyan")

    def _log_generation(
        self,
        manual_tests: list[ManualTestCase],
        api_tests: list[AutomationTestCase],
        ui_tests: list[AutomationTestCase]
    ) -> None:
        """Log generation results."""
        console.print(f"\n[green]✓ Test Cases Generated[/green]")
        console.print(f"  Manual Tests: [bold]{len(manual_tests)}[/bold]")
        console.print(f"  API Automation: [bold]{len(api_tests)}[/bold]")
        console.print(f"  UI Automation: [bold]{len(ui_tests)}[/bold]")
        console.print(f"  [bold]Total: {len(manual_tests) + len(api_tests) + len(ui_tests)}[/bold]")
