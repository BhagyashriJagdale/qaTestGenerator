"""Unit tests for Pydantic models in core/models.py."""

import pytest
from datetime import datetime
from pydantic import ValidationError
from core.models import (
    InputType,
    TestCaseType,
    Priority,
    ScenarioType,
    RequirementInput,
    GenerationConfig,
    PlannerAnalysis,
    TestStep,
    ManualTestCase,
    AutomationTestCase,
    CoverageReport,
    ReviewResult,
    GeneratedTestSuite,
)


# ── Enums ────────────────────────────────────────────────────────────────────

def test_input_type_values():
    assert InputType.PLAIN_TEXT == "plain_text"
    assert InputType.ACCEPTANCE_CRITERIA == "acceptance_criteria"
    assert InputType.USER_STORY == "user_story"


def test_test_case_type_values():
    assert TestCaseType.MANUAL == "manual"
    assert TestCaseType.API_AUTOMATION == "api_automation"
    assert TestCaseType.UI_AUTOMATION == "ui_automation"


def test_priority_values():
    assert Priority.CRITICAL == "critical"
    assert Priority.HIGH == "high"
    assert Priority.MEDIUM == "medium"
    assert Priority.LOW == "low"


def test_scenario_type_values():
    assert ScenarioType.HAPPY_PATH == "happy_path"
    assert ScenarioType.NEGATIVE == "negative"
    assert ScenarioType.EDGE_CASE == "edge_case"
    assert ScenarioType.BOUNDARY == "boundary"
    assert ScenarioType.SECURITY == "security"
    assert ScenarioType.CROSS_PLATFORM == "cross_platform"


# ── RequirementInput ──────────────────────────────────────────────────────────

def test_requirement_input_minimal():
    req = RequirementInput(content="User can log in")
    assert req.content == "User can log in"
    assert req.input_type == InputType.PLAIN_TEXT
    assert req.project_context is None
    assert req.tech_stack is None
    assert req.additional_context is None
    assert req.github_repo_url is None


def test_requirement_input_full():
    req = RequirementInput(
        content="Full requirement",
        input_type=InputType.USER_STORY,
        project_context="E-commerce",
        tech_stack="React + Node.js",
        additional_context="Checkout flow",
        github_repo_url="https://github.com/owner/repo",
    )
    assert req.input_type == InputType.USER_STORY
    assert req.project_context == "E-commerce"
    assert req.github_repo_url == "https://github.com/owner/repo"


def test_requirement_input_missing_content_raises():
    with pytest.raises(ValidationError):
        RequirementInput()  # type: ignore[call-arg]


# ── GenerationConfig ──────────────────────────────────────────────────────────

def test_generation_config_defaults():
    cfg = GenerationConfig()
    assert cfg.include_manual is True
    assert cfg.include_api is True
    assert cfg.include_ui is True
    assert cfg.framework == "playwright"
    assert cfg.language == "typescript"
    assert ScenarioType.HAPPY_PATH in cfg.scenarios


def test_generation_config_custom():
    cfg = GenerationConfig(
        include_manual=False,
        include_api=True,
        include_ui=False,
        scenarios=[ScenarioType.NEGATIVE, ScenarioType.BOUNDARY],
    )
    assert cfg.include_manual is False
    assert cfg.scenarios == [ScenarioType.NEGATIVE, ScenarioType.BOUNDARY]


# ── PlannerAnalysis ───────────────────────────────────────────────────────────

def test_planner_analysis_minimal():
    pa = PlannerAnalysis(
        feature_name="Login",
        domain="Auth",
        intent="Allow users to log in",
        scope="UI + API",
        test_focus_areas=["valid credentials", "invalid credentials"],
    )
    assert pa.feature_name == "Login"
    assert pa.tech_stack == []
    assert pa.endpoints == []
    assert pa.ui_elements == []
    assert pa.dependencies == []


def test_planner_analysis_full():
    pa = PlannerAnalysis(
        feature_name="Password Reset",
        domain="Auth",
        intent="Reset user password",
        scope="Full stack",
        endpoints=["/api/reset", "/api/verify"],
        ui_elements=["email_input", "submit_btn"],
        dependencies=["SendGrid"],
        tech_stack=["React", "Express"],
        test_focus_areas=["email delivery", "token expiry"],
    )
    assert pa.endpoints == ["/api/reset", "/api/verify"]
    assert len(pa.tech_stack) == 2


# ── TestStep ──────────────────────────────────────────────────────────────────

def test_test_step_minimal():
    step = TestStep(step_number=1, action="Click login", expected_result="Login page appears")
    assert step.step_number == 1
    assert step.test_data is None


def test_test_step_with_data():
    step = TestStep(
        step_number=2,
        action="Enter email",
        expected_result="Field populated",
        test_data="user@example.com",
    )
    assert step.test_data == "user@example.com"


# ── ManualTestCase ────────────────────────────────────────────────────────────

def _step(n=1):
    return TestStep(step_number=n, action="Do something", expected_result="Something happens")


def test_manual_test_case_minimal():
    tc = ManualTestCase(
        test_case_id="MTC-001",
        title="Login happy path",
        scenario_type=ScenarioType.HAPPY_PATH,
        steps=[_step()],
    )
    assert tc.test_case_id == "MTC-001"
    assert tc.priority == Priority.MEDIUM
    assert tc.description == ""
    assert tc.preconditions == []
    assert tc.postconditions == []
    assert tc.tags == []


def test_manual_test_case_model_copy():
    tc = ManualTestCase(
        test_case_id="MTC-001",
        title="Login",
        scenario_type=ScenarioType.HAPPY_PATH,
        steps=[_step()],
    )
    updated = tc.model_copy(update={"test_case_id": "MTC-002"})
    assert updated.test_case_id == "MTC-002"
    assert tc.test_case_id == "MTC-001"  # original unchanged


def test_manual_test_case_missing_required_raises():
    with pytest.raises(ValidationError):
        ManualTestCase(test_case_id="MTC-001", title="X")  # type: ignore[call-arg]


# ── AutomationTestCase ────────────────────────────────────────────────────────

def test_automation_test_case_minimal():
    tc = AutomationTestCase(
        test_case_id="ATC-001",
        title="API login test",
        test_type=TestCaseType.API_AUTOMATION,
        scenario_type=ScenarioType.HAPPY_PATH,
        code="test('x', () => {});",
        file_name="auth.api.spec.ts",
    )
    assert tc.test_case_id == "ATC-001"
    assert tc.priority == Priority.MEDIUM
    assert tc.manual_test_refs == []
    assert tc.dependencies == []


def test_automation_test_case_model_copy():
    tc = AutomationTestCase(
        test_case_id="ATC-001",
        title="X",
        test_type=TestCaseType.UI_AUTOMATION,
        scenario_type=ScenarioType.NEGATIVE,
        code="// code",
        file_name="test.spec.ts",
    )
    updated = tc.model_copy(update={"test_case_id": "ATC-099"})
    assert updated.test_case_id == "ATC-099"
    assert tc.test_case_id == "ATC-001"


# ── CoverageReport ────────────────────────────────────────────────────────────

def test_coverage_report_valid():
    cr = CoverageReport(
        total_test_cases=10,
        quality_score=85.0,
        by_type={"manual": 5, "api_automation": 3, "ui_automation": 2},
        by_scenario={"happy_path": 4, "negative": 3},
        by_priority={"high": 6, "medium": 4},
    )
    assert cr.total_test_cases == 10
    assert cr.quality_score == 85.0


def test_coverage_report_score_clamped():
    with pytest.raises(ValidationError):
        CoverageReport(total_test_cases=5, quality_score=101.0)

    with pytest.raises(ValidationError):
        CoverageReport(total_test_cases=5, quality_score=-1.0)


# ── ReviewResult ──────────────────────────────────────────────────────────────

def _make_review(score=75.0):
    return ReviewResult(
        coverage=CoverageReport(total_test_cases=3, quality_score=score),
        final_score=score,
    )


def test_review_result_defaults():
    r = _make_review()
    assert r.issues_found == []
    assert r.improvements_made == []


# ── GeneratedTestSuite ────────────────────────────────────────────────────────

def test_generated_test_suite_defaults():
    pa = PlannerAnalysis(
        feature_name="F",
        domain="D",
        intent="I",
        scope="S",
        test_focus_areas=["area"],
    )
    suite = GeneratedTestSuite(feature_name="Login", analysis=pa)
    assert isinstance(suite.generated_at, datetime)
    assert suite.manual_test_cases == []
    assert suite.api_test_cases == []
    assert suite.ui_test_cases == []
    assert suite.review is None
    assert suite.markdown_output == ""
