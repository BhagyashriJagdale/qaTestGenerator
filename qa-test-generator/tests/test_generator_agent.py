"""Unit tests for GeneratorAgent pure methods (no LLM calls)."""

import pytest
from unittest.mock import MagicMock, patch
from core.models import (
    ManualTestCase,
    AutomationTestCase,
    TestCaseType,
    ScenarioType,
    Priority,
    TestStep,
    RequirementInput,
    GenerationConfig,
    PlannerAnalysis,
)


# ── fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def agent():
    with patch("core.llm_client.get_llm_client", return_value=MagicMock()):
        from agents.generator_agent import GeneratorAgent
        return GeneratorAgent()


def _step():
    return TestStep(step_number=1, action="Do X", expected_result="X done")


def _manual(tc_id="MTC-001", scenario="happy_path"):
    return ManualTestCase(
        test_case_id=tc_id,
        title=f"Test {tc_id}",
        scenario_type=ScenarioType(scenario),
        steps=[_step()],
    )


def _auto(tc_id="ATC-001", code="test('x',()=>{});", refs=None):
    return AutomationTestCase(
        test_case_id=tc_id,
        title=f"Auto {tc_id}",
        test_type=TestCaseType.API_AUTOMATION,
        scenario_type=ScenarioType.HAPPY_PATH,
        code=code,
        file_name="test.spec.ts",
        manual_test_refs=refs or [],
    )


# ── _normalize_ids ────────────────────────────────────────────────────────────

def test_normalize_ids_reassigns_sequential(agent):
    tests = [_manual("MTC-099"), _manual("MTC-003")]
    result = agent._normalize_ids(tests, "MTC")
    assert [t.test_case_id for t in result] == ["MTC-001", "MTC-002"]


def test_normalize_ids_correct_ids_unchanged(agent):
    tests = [_manual("MTC-001"), _manual("MTC-002")]
    result = agent._normalize_ids(tests, "MTC")
    assert result[0].test_case_id == "MTC-001"
    assert result[1].test_case_id == "MTC-002"


def test_normalize_ids_returns_new_list(agent):
    tests = [_manual("MTC-001")]
    result = agent._normalize_ids(tests, "MTC")
    assert result is not tests


def test_normalize_ids_empty(agent):
    assert agent._normalize_ids([], "MTC") == []


def test_normalize_ids_atc_prefix(agent):
    tests = [_auto("OLD-001"), _auto("OLD-002")]
    result = agent._normalize_ids(tests, "ATC")
    assert [t.test_case_id for t in result] == ["ATC-001", "ATC-002"]


# ── _format_manual_context ────────────────────────────────────────────────────

def test_format_manual_context_empty(agent):
    assert agent._format_manual_context([]) == ""


def test_format_manual_context_includes_id_and_title(agent):
    tc = _manual("MTC-001")
    result = agent._format_manual_context([tc])
    assert "MTC-001" in result
    assert "happy_path" in result


def test_format_manual_context_includes_steps(agent):
    tc = _manual()
    result = agent._format_manual_context([tc])
    assert "Do X" in result
    assert "X done" in result


def test_format_manual_context_respects_max_chars(agent):
    # Create 20 tests — should be truncated to max_chars
    tests = [_manual(f"MTC-{i:03d}") for i in range(1, 21)]
    result = agent._format_manual_context(tests, max_chars=500)
    assert len(result) <= 600  # small slack for last entry boundary


def test_format_manual_context_single_large_entry_truncated(agent):
    # Single entry whose serialized form exceeds max_chars — should be truncated, not exceed
    long_step = TestStep(step_number=1, action="A" * 2000, expected_result="B" * 2000)
    tc = ManualTestCase(
        test_case_id="MTC-001", title="Big", scenario_type=ScenarioType.HAPPY_PATH, steps=[long_step]
    )
    result = agent._format_manual_context([tc], max_chars=500)
    assert len(result) <= 510  # truncated to max_chars with tiny slack


def test_format_manual_context_includes_test_data(agent):
    step = TestStep(step_number=1, action="Enter", expected_result="OK", test_data="user@test.com")
    tc = ManualTestCase(
        test_case_id="MTC-001",
        title="Login",
        scenario_type=ScenarioType.HAPPY_PATH,
        steps=[step],
    )
    result = agent._format_manual_context([tc])
    assert "user@test.com" in result


# ── _base_context ─────────────────────────────────────────────────────────────

def _analysis():
    return PlannerAnalysis(
        feature_name="Login",
        domain="Auth",
        intent="Allow login",
        scope="Full stack",
        test_focus_areas=["happy path", "negative"],
        endpoints=["/api/login"],
    )


def _config():
    return GenerationConfig(scenarios=[ScenarioType.HAPPY_PATH, ScenarioType.NEGATIVE])


def test_base_context_contains_requirement(agent):
    req = RequirementInput(content="User can log in with valid credentials")
    result = agent._base_context(req, _analysis(), _config())
    assert "User can log in with valid credentials" in result


def test_base_context_contains_feature(agent):
    req = RequirementInput(content="Some requirement text here")
    result = agent._base_context(req, _analysis(), _config())
    assert "Login" in result
    assert "Auth" in result


def test_base_context_contains_scenarios(agent):
    req = RequirementInput(content="Some requirement text here")
    result = agent._base_context(req, _analysis(), _config())
    assert "happy_path" in result
    assert "negative" in result


# ── _parse_manual_tests ───────────────────────────────────────────────────────

def test_parse_manual_tests_valid(agent):
    data = [
        {
            "test_case_id": "MTC-001",
            "title": "Login test",
            "scenario_type": "happy_path",
            "steps": [{"step_number": 1, "action": "Click", "expected_result": "Page loads"}],
        }
    ]
    result = agent._parse_manual_tests(data)
    assert len(result) == 1
    assert result[0].test_case_id == "MTC-001"


def test_parse_manual_tests_skips_invalid(agent):
    data = [
        {"title": "Missing required fields"},  # no test_case_id, scenario_type, steps
        {
            "test_case_id": "MTC-001",
            "title": "Good",
            "scenario_type": "happy_path",
            "steps": [{"step_number": 1, "action": "A", "expected_result": "B"}],
        },
    ]
    result = agent._parse_manual_tests(data)
    assert len(result) == 1
    assert result[0].test_case_id == "MTC-001"


def test_parse_manual_tests_empty(agent):
    assert agent._parse_manual_tests([]) == []


# ── _parse_automation_tests ───────────────────────────────────────────────────

def test_parse_automation_tests_valid(agent):
    data = [
        {
            "test_case_id": "ATC-001",
            "title": "API test",
            "scenario_type": "happy_path",
            "code": "test('x',()=>{});",
            "file_name": "auth.spec.ts",
        }
    ]
    result = agent._parse_automation_tests(data, TestCaseType.API_AUTOMATION)
    assert len(result) == 1
    assert result[0].test_type == TestCaseType.API_AUTOMATION


def test_parse_automation_tests_injects_test_type(agent):
    data = [
        {
            "test_case_id": "UTC-001",
            "title": "UI test",
            "scenario_type": "negative",
            "code": "// code",
            "file_name": "login.spec.ts",
        }
    ]
    result = agent._parse_automation_tests(data, TestCaseType.UI_AUTOMATION)
    assert result[0].test_type == TestCaseType.UI_AUTOMATION


def test_parse_automation_tests_skips_invalid(agent):
    data = [
        {"title": "broken"},
        {
            "test_case_id": "ATC-001",
            "title": "OK",
            "scenario_type": "happy_path",
            "code": "// ok",
            "file_name": "ok.spec.ts",
        },
    ]
    result = agent._parse_automation_tests(data, TestCaseType.API_AUTOMATION)
    assert len(result) == 1


# ── _build_website_instruction (uses WebsiteContext directly — DESIGN-1) ─────

from tools.website_crawler import WebsiteContext


def _make_ctx(**kwargs) -> WebsiteContext:
    defaults = dict(
        url="https://myapp.com/login",
        title="Login",
        locators=["[data-testid='email-input']", "#password", "[data-testid='login-btn']"],
        api_urls=["/api/auth/login", "/api/users"],
        form_actions=["/api/auth/login"],
        formatted="",
    )
    defaults.update(kwargs)
    return WebsiteContext(**defaults)


def test_build_website_instruction_ui_contains_page_url(agent):
    result = agent._build_website_instruction(_make_ctx(), mode="ui")
    assert "https://myapp.com/login" in result


def test_build_website_instruction_ui_contains_locators(agent):
    result = agent._build_website_instruction(_make_ctx(), mode="ui")
    assert "[data-testid='email-input']" in result
    assert "#password" in result


def test_build_website_instruction_ui_says_mandatory(agent):
    result = agent._build_website_instruction(_make_ctx(), mode="ui")
    assert "LIVE WEBSITE DATA" in result


def test_build_website_instruction_api_contains_endpoints(agent):
    result = agent._build_website_instruction(_make_ctx(), mode="api")
    assert "/api/auth/login" in result
    assert "/api/users" in result


def test_build_website_instruction_api_has_endpoints_not_locators(agent):
    result = agent._build_website_instruction(_make_ctx(), mode="api")
    assert "API ENDPOINTS" in result
    assert "LOCATORS" not in result


def test_build_website_instruction_ui_no_forms_shows_warning(agent):
    ctx = _make_ctx(locators=[], form_actions=[])
    result = agent._build_website_instruction(ctx, mode="ui")
    assert "No interactive form elements" in result or "no form" in result.lower()


def test_build_website_instruction_api_no_endpoints_shows_fallback(agent):
    ctx = _make_ctx(api_urls=[], form_actions=[])
    result = agent._build_website_instruction(ctx, mode="api")
    assert "No API endpoints" in result


def test_build_website_instruction_api_page_route_guidance(agent):
    result = agent._build_website_instruction(_make_ctx(), mode="api")
    assert "page.route" in result or "route" in result.lower()


def test_build_website_instruction_api_deduplicates_form_and_api_urls(agent):
    ctx = _make_ctx(form_actions=["/api/auth/login"], api_urls=["/api/auth/login", "/api/users"])
    result = agent._build_website_instruction(ctx, mode="api")
    assert result.count("/api/auth/login") == 1


def test_build_website_instruction_empty_context_ui(agent):
    ctx = _make_ctx(url="", locators=[], api_urls=[], form_actions=[])
    result = agent._build_website_instruction(ctx, mode="ui")
    assert "LIVE WEBSITE DATA" in result  # header still present


def test_build_website_instruction_empty_context_api(agent):
    ctx = _make_ctx(url="", locators=[], api_urls=[], form_actions=[])
    result = agent._build_website_instruction(ctx, mode="api")
    assert "No API endpoints" in result


# ── _build_website_instruction — partial context (STALE-3) ───────────────────

def test_build_website_instruction_url_only_ui(agent):
    ctx = _make_ctx(locators=[], api_urls=[], form_actions=[])
    result = agent._build_website_instruction(ctx, mode="ui")
    assert "https://myapp.com/login" in result
    assert "No interactive form elements" in result or "no form" in result.lower()


def test_build_website_instruction_forms_only_api(agent):
    ctx = _make_ctx(api_urls=[], form_actions=["/api/submit"])
    result = agent._build_website_instruction(ctx, mode="api")
    assert "/api/submit" in result
    assert "API ENDPOINTS" in result


def test_build_website_instruction_api_urls_only_no_forms(agent):
    ctx = _make_ctx(form_actions=[], api_urls=["/api/data", "/api/users"])
    result = agent._build_website_instruction(ctx, mode="api")
    assert "/api/data" in result
    assert "/api/users" in result


# ── is_empty() guard in _generate_api / _generate_ui (M-2) ──────────────────

def test_build_website_instruction_ui_no_locators_critical_footer_absent(agent):
    # When locators=[], the contradictory CRITICAL selector footer must not appear
    ctx = _make_ctx(locators=[])
    result = agent._build_website_instruction(ctx, mode="ui")
    assert "Every selector" not in result


def test_build_website_instruction_ui_with_locators_critical_footer_present(agent):
    result = agent._build_website_instruction(_make_ctx(), mode="ui")
    assert "Every selector" in result
