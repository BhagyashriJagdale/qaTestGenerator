"""Unit tests for PlannerAgent.run() with LLM mocked."""

import pytest
from unittest.mock import MagicMock, patch
from core.models import RequirementInput


@pytest.fixture
def planner():
    with patch("core.llm_client.get_llm_client", return_value=MagicMock()):
        from agents.planner_agent import PlannerAgent
        return PlannerAgent()


def _req(text: str) -> RequirementInput:
    return RequirementInput(content=text)


_VALID_REQ = (
    "As a registered user, I want to log in with a valid email and password "
    "so that I can access my account dashboard."
)

_VALID_LLM_RESPONSE = {
    "is_valid": True,
    "is_complete": True,
    "feature_name": "User Login",
    "domain": "Authentication",
    "intent": "Allow users to log in",
    "scope": "UI + API",
    "endpoints": ["/api/login"],
    "ui_elements": ["email_input", "password_input", "submit_btn"],
    "dependencies": [],
    "tech_stack": ["React", "Express"],
    "test_focus_areas": ["valid credentials", "invalid credentials"],
}


# ── run() — happy path ────────────────────────────────────────────────────────

def test_run_returns_planner_analysis(planner):
    planner.client.generate_json = MagicMock(return_value=_VALID_LLM_RESPONSE.copy())
    result = planner.run(_req(_VALID_REQ))
    assert result.feature_name == "User Login"
    assert result.domain == "Authentication"


def test_run_strips_validation_flags(planner):
    from core.models import PlannerAnalysis
    planner.client.generate_json = MagicMock(return_value=_VALID_LLM_RESPONSE.copy())
    result = planner.run(_req(_VALID_REQ))
    assert isinstance(result, PlannerAnalysis)
    # PlannerAnalysis doesn't have is_valid or is_complete fields
    assert not hasattr(result, "is_valid")
    assert not hasattr(result, "is_complete")


def test_run_populates_endpoints(planner):
    planner.client.generate_json = MagicMock(return_value=_VALID_LLM_RESPONSE.copy())
    result = planner.run(_req(_VALID_REQ))
    assert "/api/login" in result.endpoints


def test_run_populates_test_focus_areas(planner):
    planner.client.generate_json = MagicMock(return_value=_VALID_LLM_RESPONSE.copy())
    result = planner.run(_req(_VALID_REQ))
    assert len(result.test_focus_areas) >= 1


# ── run() — skip_validation flag ─────────────────────────────────────────────

def test_run_skip_validation_bypasses_validate(planner):
    planner.client.generate_json = MagicMock(return_value=_VALID_LLM_RESPONSE.copy())
    # Short text would normally fail validation — skip_validation lets it through
    result = planner.run(_req("Fix it"), skip_validation=True)
    assert result.feature_name == "User Login"


# ── run() — LLM says invalid ──────────────────────────────────────────────────

def test_run_raises_invalid_when_llm_says_invalid(planner):
    from agents.planner_agent import InvalidRequirementError
    planner.client.generate_json = MagicMock(return_value={
        "is_valid": False,
        "is_complete": False,
        "validation_error": "Not a software requirement",
    })
    with pytest.raises(InvalidRequirementError):
        planner.run(_req(_VALID_REQ))


# ── run() — LLM says incomplete ───────────────────────────────────────────────

def test_run_raises_incomplete_when_llm_says_incomplete(planner):
    from agents.planner_agent import IncompleteRequirementError
    planner.client.generate_json = MagicMock(return_value={
        "is_valid": True,
        "is_complete": False,
        "completeness_issues": ["No expected outcome specified"],
        "missing_information": ["What should happen on success?"],
        "suggestion": "When user submits valid credentials, they should see the dashboard.",
    })
    with pytest.raises(IncompleteRequirementError) as exc_info:
        planner.run(_req(_VALID_REQ))
    assert exc_info.value.issues == ["No expected outcome specified"]
    assert exc_info.value.missing == ["What should happen on success?"]


# ── run() — LLM raises exception ─────────────────────────────────────────────

def test_run_propagates_llm_exception(planner):
    planner.client.generate_json = MagicMock(side_effect=RuntimeError("LLM timeout"))
    with pytest.raises(RuntimeError, match="LLM timeout"):
        planner.run(_req(_VALID_REQ))


# ── run() — with rag_context ──────────────────────────────────────────────────

def test_run_passes_rag_context_to_llm(planner):
    planner.client.generate_json = MagicMock(return_value=_VALID_LLM_RESPONSE.copy())
    planner.run(_req(_VALID_REQ), rag_context="## Prior context: login pattern")
    call_args = planner.client.generate_json.call_args
    assert "Prior context" in call_args[1]["user_message"] or "Prior context" in str(call_args)


# ── run() — with tool_context (codebase) ─────────────────────────────────────

def test_run_suppresses_incomplete_when_codebase_present(planner):
    from agents.planner_agent import IncompleteRequirementError
    # LLM says incomplete, but codebase context is provided — should NOT raise
    planner.client.generate_json = MagicMock(return_value={
        **_VALID_LLM_RESPONSE,
        "is_complete": False,
        "completeness_issues": ["No endpoint specified"],
        "missing_information": ["Which API endpoint?"],
    })
    # Should not raise even though is_complete=False
    result = planner.run(
        _req("Admin checks flight status"),
        tool_context="## routes/flights.ts\nexport const getFlightStatus = ...",
    )
    assert result.feature_name == "User Login"


def test_run_raises_incomplete_without_codebase(planner):
    from agents.planner_agent import IncompleteRequirementError
    planner.client.generate_json = MagicMock(return_value={
        **_VALID_LLM_RESPONSE,
        "is_complete": False,
        "completeness_issues": ["Too vague"],
        "missing_information": ["What endpoint?"],
    })
    with pytest.raises(IncompleteRequirementError):
        planner.run(_req(_VALID_REQ))  # no tool_context — should still raise


def test_run_passes_tool_context_to_llm(planner):
    planner.client.generate_json = MagicMock(return_value=_VALID_LLM_RESPONSE.copy())
    planner.run(_req(_VALID_REQ), tool_context="## src/routes/auth.ts\nrouter.post('/login')")
    call_args = planner.client.generate_json.call_args
    full_msg = call_args[1]["user_message"]
    assert "auth.ts" in full_msg


def test_run_includes_codebase_note_in_message(planner):
    planner.client.generate_json = MagicMock(return_value=_VALID_LLM_RESPONSE.copy())
    planner.run(_req(_VALID_REQ), tool_context="## routes/flights.ts\n...")
    call_args = planner.client.generate_json.call_args
    full_msg = call_args[1]["user_message"]
    assert "codebase" in full_msg.lower() or "is_complete=false" in full_msg


# ── codebase mismatch detection ──────────────────────────────────────────────

def test_codebase_relevant_true_by_default(planner):
    planner.client.generate_json = MagicMock(return_value=_VALID_LLM_RESPONSE.copy())
    planner.run(_req(_VALID_REQ))
    assert planner.codebase_relevant is True


def test_codebase_mismatch_sets_flag_false(planner):
    planner.client.generate_json = MagicMock(return_value={
        **_VALID_LLM_RESPONSE,
        "codebase_relevant": False,
        "mismatch_reason": "Codebase is a flight booking system; requirement is about auth.",
    })
    planner.run(
        _req(_VALID_REQ),
        tool_context="## routes/flights.ts\nexport const bookFlight = ...",
    )
    assert planner.codebase_relevant is False


def test_codebase_mismatch_does_not_raise(planner):
    # Mismatch should warn but still return a valid PlannerAnalysis
    planner.client.generate_json = MagicMock(return_value={
        **_VALID_LLM_RESPONSE,
        "codebase_relevant": False,
        "mismatch_reason": "Unrelated codebase.",
    })
    result = planner.run(
        _req(_VALID_REQ),
        tool_context="## routes/flights.ts\n...",
    )
    assert result.feature_name == "User Login"


def test_no_mismatch_when_no_codebase(planner):
    # Without tool_context, codebase_relevant should default True (nothing to mismatch)
    planner.client.generate_json = MagicMock(return_value={
        **_VALID_LLM_RESPONSE,
        "codebase_relevant": False,  # LLM returns false but there's no codebase
    })
    planner.run(_req(_VALID_REQ))
    # codebase_relevant is stored as-is from LLM; pipeline checks has_codebase separately
    assert planner.codebase_relevant is False  # stored, but pipeline ignores it without tool_context


# ── IncompleteRequirementError message ────────────────────────────────────────

def test_incomplete_error_message_contains_issues():
    from agents.planner_agent import IncompleteRequirementError
    err = IncompleteRequirementError(
        issues=["No outcome specified"],
        missing=["Expected result?"],
        suggestion="When user logs in...",
    )
    assert "No outcome specified" in str(err)
    assert "Expected result?" in str(err)
    assert "When user logs in" in str(err)
