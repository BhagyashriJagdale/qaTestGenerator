"""Unit tests for ReviewAgent deterministic methods (no LLM calls)."""

import pytest
from unittest.mock import MagicMock, patch
from core.models import (
    ManualTestCase,
    AutomationTestCase,
    TestCaseType,
    ScenarioType,
    Priority,
    TestStep,
    PlannerAnalysis,
)


# ── fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def agent():
    with patch("core.llm_client.get_llm_client", return_value=MagicMock()):
        from agents.review_agent import ReviewAgent
        return ReviewAgent()


def _step():
    return TestStep(step_number=1, action="Do X", expected_result="X done")


def _manual(tc_id="MTC-001", scenario="happy_path", priority="high"):
    return ManualTestCase(
        test_case_id=tc_id,
        title=f"Test {tc_id}",
        scenario_type=ScenarioType(scenario),
        priority=Priority(priority),
        steps=[_step(), _step()],
        preconditions=["User logged in"],
    )


def _auto(tc_id="ATC-001", code="test('x',()=>{});", refs=None, scenario="happy_path"):
    return AutomationTestCase(
        test_case_id=tc_id,
        title=f"Auto {tc_id}",
        test_type=TestCaseType.API_AUTOMATION,
        scenario_type=ScenarioType(scenario),
        priority=Priority.HIGH,
        code=code,
        file_name="test.spec.ts",
        manual_test_refs=refs or ["MTC-001"],
    )


def _analysis():
    return PlannerAnalysis(
        feature_name="Login",
        domain="Auth",
        intent="Allow login",
        scope="Full",
        test_focus_areas=["happy path", "security"],
    )


# ── _format_manual_tests ──────────────────────────────────────────────────────

def test_format_manual_no_tests(agent):
    result = agent._format_manual_tests([])
    assert "No manual tests" in result


def test_format_manual_contains_id(agent):
    tests = [_manual("MTC-042")]
    result = agent._format_manual_tests(tests)
    assert "MTC-042" in result


def test_format_manual_contains_priority_and_scenario(agent):
    tests = [_manual(priority="critical", scenario="security")]
    result = agent._format_manual_tests(tests)
    assert "critical" in result
    assert "security" in result


def test_format_manual_shows_step_count(agent):
    tests = [_manual()]
    result = agent._format_manual_tests(tests)
    # _manual creates 2 steps
    assert "2" in result


def test_format_manual_shows_first_step_action(agent):
    step = TestStep(step_number=1, action="Navigate to login page", expected_result="Page shown")
    tc = ManualTestCase(
        test_case_id="MTC-001",
        title="Login",
        scenario_type=ScenarioType.HAPPY_PATH,
        steps=[step],
    )
    result = agent._format_manual_tests([tc])
    assert "Navigate to login page" in result


# ── _format_automation_tests ──────────────────────────────────────────────────

def test_format_automation_no_tests(agent):
    result = agent._format_automation_tests([], "API")
    assert "No API tests" in result


def test_format_automation_contains_id(agent):
    tests = [_auto("ATC-007")]
    result = agent._format_automation_tests(tests, "API")
    assert "ATC-007" in result


def test_format_automation_shows_manual_refs(agent):
    tests = [_auto(refs=["MTC-003", "MTC-005"])]
    result = agent._format_automation_tests(tests, "API")
    assert "MTC-003" in result
    assert "MTC-005" in result


def test_format_automation_shows_code_preview(agent):
    tests = [_auto(code="test('login', () => { expect(true).toBeTruthy(); });")]
    result = agent._format_automation_tests(tests, "API")
    assert "test('login'" in result


def test_format_automation_truncates_long_code(agent):
    long_code = "x" * 2000
    tests = [_auto(code=long_code)]
    result = agent._format_automation_tests(tests, "API")
    assert "..." in result


# ── _build_user_message ───────────────────────────────────────────────────────

def test_build_user_message_contains_feature(agent):
    analysis = _analysis()
    msg = agent._build_user_message(analysis, [_manual()], [], [])
    assert "Login" in msg
    assert "Auth" in msg


def test_build_user_message_shows_counts(agent):
    msg = agent._build_user_message(_analysis(), [_manual(), _manual("MTC-002")], [_auto()], [])
    assert "2 total" in msg
    assert "1 total" in msg


def test_build_user_message_has_display_preview_note(agent):
    msg = agent._build_user_message(_analysis(), [], [], [])
    assert "display preview" in msg


# ── _parse_review ─────────────────────────────────────────────────────────────

def test_parse_review_counts_from_lists(agent):
    manual = [_manual("MTC-001"), _manual("MTC-002")]
    api = [_auto("ATC-001")]
    ui = []
    data = {"coverage": {"quality_score": 80.0}, "final_score": 80.0}
    result = agent._parse_review(data, manual, api, ui)
    assert result.coverage.by_type["manual"] == 2
    assert result.coverage.by_type["api_automation"] == 1
    assert result.coverage.by_type["ui_automation"] == 0
    assert result.coverage.total_test_cases == 3


def test_parse_review_scenario_counts(agent):
    manual = [_manual(scenario="happy_path"), _manual("MTC-002", scenario="negative")]
    data = {"coverage": {"quality_score": 70.0}, "final_score": 70.0}
    result = agent._parse_review(data, manual, [], [])
    assert result.coverage.by_scenario["happy_path"] == 1
    assert result.coverage.by_scenario["negative"] == 1


def test_parse_review_priority_counts(agent):
    manual = [_manual(priority="high"), _manual("MTC-002", priority="critical")]
    data = {"coverage": {"quality_score": 90.0}, "final_score": 90.0}
    result = agent._parse_review(data, manual, [], [])
    assert result.coverage.by_priority["high"] == 1
    assert result.coverage.by_priority["critical"] == 1


def test_parse_review_qualitative_from_llm(agent):
    data = {
        "coverage": {
            "quality_score": 75.0,
            "coverage_gaps": ["Missing boundary tests"],
            "suggestions": ["Add more edge cases"],
        },
        "issues_found": ["TC-001 lacks test data"],
        "improvements_made": ["Added negative scenarios"],
        "final_score": 78.0,
    }
    result = agent._parse_review(data, [], [], [])
    assert result.coverage.coverage_gaps == ["Missing boundary tests"]
    assert result.coverage.suggestions == ["Add more edge cases"]
    assert result.issues_found == ["TC-001 lacks test data"]
    assert result.final_score == 78.0


def test_parse_review_caps_issues_at_10(agent):
    data = {
        "coverage": {"quality_score": 50.0},
        "issues_found": [f"Issue {i}" for i in range(15)],
        "final_score": 50.0,
    }
    result = agent._parse_review(data, [], [], [])
    assert len(result.issues_found) == 10


def test_parse_review_caps_suggestions_at_5(agent):
    data = {
        "coverage": {
            "quality_score": 60.0,
            "suggestions": [f"Suggestion {i}" for i in range(10)],
        },
        "final_score": 60.0,
    }
    result = agent._parse_review(data, [], [], [])
    assert len(result.coverage.suggestions) == 5
