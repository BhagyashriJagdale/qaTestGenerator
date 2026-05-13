"""Extended unit tests for FormatterAgent (format_manual_section, header, summary, coverage)."""

import pytest
from agents.formatter_agent import FormatterAgent
from core.models import (
    ManualTestCase,
    AutomationTestCase,
    TestCaseType,
    ScenarioType,
    Priority,
    TestStep,
    PlannerAnalysis,
    CoverageReport,
    ReviewResult,
)


@pytest.fixture
def formatter():
    return FormatterAgent()


# ── helpers ───────────────────────────────────────────────────────────────────

def _step(n=1, data=None):
    return TestStep(step_number=n, action=f"Action {n}", expected_result=f"Result {n}", test_data=data)


def _manual(tc_id="MTC-001", scenario="happy_path", priority="high", steps=2):
    return ManualTestCase(
        test_case_id=tc_id,
        title=f"Test {tc_id}",
        scenario_type=ScenarioType(scenario),
        priority=Priority(priority),
        steps=[_step(i) for i in range(1, steps + 1)],
        preconditions=["Pre A"],
        postconditions=["Post B"],
    )


def _auto(tc_id="ATC-001", file_name="auth.spec.ts", scenario="happy_path", refs=None):
    return AutomationTestCase(
        test_case_id=tc_id,
        title=f"Auto {tc_id}",
        test_type=TestCaseType.API_AUTOMATION,
        scenario_type=ScenarioType(scenario),
        priority=Priority.HIGH,
        code=f"test('{tc_id}', () => {{ expect(true).toBeTruthy(); }});",
        file_name=file_name,
        manual_test_refs=refs or ["MTC-001"],
    )


def _analysis():
    return PlannerAnalysis(
        feature_name="User Login",
        domain="Auth",
        intent="Allow login",
        scope="Full stack",
        test_focus_areas=["valid creds", "invalid creds"],
    )


def _review(score=85.0, gaps=None, suggestions=None):
    return ReviewResult(
        coverage=CoverageReport(
            total_test_cases=3,
            quality_score=score,
            by_type={"manual": 2, "api_automation": 1},
            by_scenario={"happy_path": 2, "negative": 1},
            by_priority={"high": 3},
            coverage_gaps=gaps or ["Missing boundary tests"],
            suggestions=suggestions or ["Add edge cases"],
        ),
        issues_found=["Issue 1"],
        improvements_made=["Improvement 1"],
        final_score=score,
    )


# ── format_manual_section ─────────────────────────────────────────────────────

def test_format_manual_section_has_heading(formatter):
    result = formatter.format_manual_section([_manual()])
    assert "## 1. Manual Test Cases" in result


def test_format_manual_section_contains_tc_id(formatter):
    result = formatter.format_manual_section([_manual("MTC-042")])
    assert "MTC-042" in result


def test_format_manual_section_shows_priority_and_scenario(formatter):
    result = formatter.format_manual_section([_manual(scenario="negative", priority="critical")])
    assert "Critical" in result
    assert "Negative" in result


def test_format_manual_section_shows_steps_table(formatter):
    result = formatter.format_manual_section([_manual(steps=3)])
    assert "| Step |" in result
    assert "Action 1" in result
    assert "Action 3" in result


def test_format_manual_section_shows_preconditions(formatter):
    result = formatter.format_manual_section([_manual()])
    assert "Pre A" in result


def test_format_manual_section_shows_postconditions(formatter):
    result = formatter.format_manual_section([_manual()])
    assert "Post B" in result


def test_format_manual_section_multiple_tests(formatter):
    tests = [_manual("MTC-001"), _manual("MTC-002", scenario="negative")]
    result = formatter.format_manual_section(tests)
    assert "MTC-001" in result
    assert "MTC-002" in result


def test_format_manual_section_test_data_shown(formatter):
    step = TestStep(step_number=1, action="Enter", expected_result="OK", test_data="admin@test.com")
    tc = ManualTestCase(
        test_case_id="MTC-001",
        title="Login",
        scenario_type=ScenarioType.HAPPY_PATH,
        steps=[step],
    )
    result = formatter.format_manual_section([tc])
    assert "admin@test.com" in result


def test_format_manual_section_pipe_chars_escaped(formatter):
    step = TestStep(step_number=1, action="Select A|B option", expected_result="A|B shows")
    tc = ManualTestCase(
        test_case_id="MTC-001",
        title="Pipe test",
        scenario_type=ScenarioType.EDGE_CASE,
        steps=[step],
    )
    result = formatter.format_manual_section([tc])
    assert "\\|" in result  # pipe escaped for markdown table


# ── format_ui_section ─────────────────────────────────────────────────────────

def test_format_ui_section_has_heading(formatter):
    ui_tc = AutomationTestCase(
        test_case_id="UTC-001",
        title="UI test",
        test_type=TestCaseType.UI_AUTOMATION,
        scenario_type=ScenarioType.HAPPY_PATH,
        code="test('ui', () => {});",
        file_name="login.ui.spec.ts",
    )
    result = formatter.format_ui_section([ui_tc])
    assert "## 3. UI Automation" in result


def test_format_ui_section_groups_by_file(formatter):
    a = AutomationTestCase(
        test_case_id="UTC-001",
        title="A",
        test_type=TestCaseType.UI_AUTOMATION,
        scenario_type=ScenarioType.HAPPY_PATH,
        code="test('a',()=>{});",
        file_name="login.spec.ts",
    )
    b = AutomationTestCase(
        test_case_id="UTC-002",
        title="B",
        test_type=TestCaseType.UI_AUTOMATION,
        scenario_type=ScenarioType.NEGATIVE,
        code="test('b',()=>{});",
        file_name="register.spec.ts",
    )
    result = formatter.format_ui_section([a, b])
    assert "login.spec.ts" in result
    assert "register.spec.ts" in result


# ── _format_header ────────────────────────────────────────────────────────────

def test_format_header_contains_feature_name(formatter):
    result = formatter._format_header(_analysis(), _review())
    assert "User Login" in result


def test_format_header_contains_quality_score(formatter):
    result = formatter._format_header(_analysis(), _review(score=92.0))
    assert "92.0" in result


def test_format_header_contains_domain(formatter):
    result = formatter._format_header(_analysis(), _review())
    assert "Auth" in result


# ── _format_summary ───────────────────────────────────────────────────────────

def test_format_summary_counts_correct(formatter):
    manual = [_manual("MTC-001"), _manual("MTC-002")]
    api = [_auto()]
    ui = []
    result = formatter._format_summary(manual, api, ui, _review())
    assert "| Manual Test Cases | 2 |" in result
    assert "| API Automation | 1 |" in result


def test_format_summary_shows_coverage(formatter):
    result = formatter._format_summary([], [], [], _review())
    assert "Happy Path" in result or "happy_path" in result.lower()


# ── _format_coverage_section ──────────────────────────────────────────────────

def test_format_coverage_has_type_table(formatter):
    result = formatter._format_coverage_section(_review())
    assert "By Test Type" in result
    assert "Manual" in result or "manual" in result


def test_format_coverage_has_scenario_table(formatter):
    result = formatter._format_coverage_section(_review())
    assert "By Scenario Type" in result


def test_format_coverage_has_priority_table(formatter):
    result = formatter._format_coverage_section(_review())
    assert "By Priority" in result


# ── _format_notes_section ─────────────────────────────────────────────────────

def test_format_notes_shows_coverage_gaps(formatter):
    result = formatter._format_notes_section(_review(gaps=["Need security tests"]))
    assert "Need security tests" in result


def test_format_notes_shows_suggestions(formatter):
    result = formatter._format_notes_section(_review(suggestions=["Add boundary tests"]))
    assert "Add boundary tests" in result


def test_format_notes_shows_issues(formatter):
    rv = _review()
    rv = rv.model_copy(update={"issues_found": ["ATC-001 missing assertion"]})
    result = formatter._format_notes_section(rv)
    assert "ATC-001 missing assertion" in result


# ── full run ──────────────────────────────────────────────────────────────────

def test_run_returns_nonempty_markdown(formatter):
    result = formatter.run(
        _analysis(),
        [_manual()],
        [_auto()],
        [],
        _review(),
    )
    assert len(result) > 100
    assert "User Login" in result
