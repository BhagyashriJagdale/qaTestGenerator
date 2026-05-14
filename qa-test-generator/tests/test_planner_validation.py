"""Unit tests for PlannerAgent._validate_input (deterministic, no LLM calls)."""

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


# ── invalid inputs ────────────────────────────────────────────────────────────

def test_empty_string_raises(planner):
    from agents.planner_agent import InvalidRequirementError
    with pytest.raises(InvalidRequirementError):
        planner._validate_input(_req(""))


def test_whitespace_only_raises(planner):
    from agents.planner_agent import InvalidRequirementError
    with pytest.raises(InvalidRequirementError):
        planner._validate_input(_req("   \n\t  "))


def test_too_short_raises(planner):
    from agents.planner_agent import InvalidRequirementError
    with pytest.raises(InvalidRequirementError):
        planner._validate_input(_req("login"))  # < 10 chars after strip


def test_single_word_raises(planner):
    from agents.planner_agent import InvalidRequirementError
    with pytest.raises(InvalidRequirementError):
        planner._validate_input(_req("authentication"))


def test_numeric_only_raises(planner):
    from agents.planner_agent import InvalidRequirementError
    with pytest.raises(InvalidRequirementError):
        planner._validate_input(_req("12345 678"))


def test_gibberish_symbols_raises(planner):
    from agents.planner_agent import InvalidRequirementError
    with pytest.raises(InvalidRequirementError):
        planner._validate_input(_req("@#$%^&*()!@#$%^&*()"))


def test_repeated_characters_raises(planner):
    from agents.planner_agent import InvalidRequirementError
    with pytest.raises(InvalidRequirementError):
        planner._validate_input(_req("aaaaaaaaaa"))


# ── incomplete inputs ─────────────────────────────────────────────────────────

def test_vague_action_two_words_raises_incomplete(planner):
    from agents.planner_agent import IncompleteRequirementError
    with pytest.raises(IncompleteRequirementError):
        planner._validate_input(_req("fix authentication"))


def test_vague_add_raises_incomplete(planner):
    from agents.planner_agent import IncompleteRequirementError
    with pytest.raises(IncompleteRequirementError):
        planner._validate_input(_req("add button"))


# ── valid inputs ──────────────────────────────────────────────────────────────

def test_valid_plain_text_passes(planner):
    # Should not raise
    planner._validate_input(_req(
        "User can log in with a valid email and password and is redirected to the dashboard."
    ))


def test_valid_user_story_passes(planner):
    planner._validate_input(_req(
        "As a registered user, I want to reset my password via email "
        "so that I can regain access to my account when I forget my credentials."
    ))


def test_valid_acceptance_criteria_passes(planner):
    planner._validate_input(_req(
        "Given a user with a valid account, "
        "when they submit correct credentials on the login page, "
        "then they should be redirected to the dashboard within 2 seconds."
    ))
