"""Unit tests for pure utility methods in pipeline.py."""

import pytest
from unittest.mock import MagicMock, patch


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_manual(test_case_id: str, title: str, scenario: str = "happy_path"):
    """Create a minimal ManualTestCase-like mock."""
    from core.models import ManualTestCase, ScenarioType, TestStep
    return ManualTestCase(
        test_case_id=test_case_id,
        title=title,
        scenario_type=ScenarioType(scenario),
        steps=[TestStep(step_number=1, action="Do something", expected_result="Something happens")],
    )


def _make_automation(test_case_id: str, title: str, refs: list[str] | None = None):
    """Create a minimal AutomationTestCase-like mock."""
    from core.models import AutomationTestCase, ScenarioType, TestCaseType
    return AutomationTestCase(
        test_case_id=test_case_id,
        title=title,
        test_type=TestCaseType.API_AUTOMATION,
        scenario_type=ScenarioType.HAPPY_PATH,
        code="// code",
        file_name="test.spec.ts",
        manual_test_refs=refs or [],
    )


# Grab the pipeline methods without instantiating (they don't use self)
def _pipeline():
    """Return a bare TestGeneratorPipeline with all agent dependencies mocked."""
    with patch("pipeline.PlannerAgent"), \
         patch("pipeline.GeneratorAgent"), \
         patch("pipeline.ReviewAgent"), \
         patch("pipeline.FormatterAgent"), \
         patch("pipeline.get_rag_system"):
        from pipeline import TestGeneratorPipeline
        p = TestGeneratorPipeline.__new__(TestGeneratorPipeline)
        p.use_rag = False
        p.rag = None
        return p


# ── _jaccard ─────────────────────────────────────────────────────────────────

def test_jaccard_identical():
    from pipeline import TestGeneratorPipeline
    assert TestGeneratorPipeline._jaccard("hello world", "hello world") == 1.0


def test_jaccard_no_overlap():
    from pipeline import TestGeneratorPipeline
    assert TestGeneratorPipeline._jaccard("foo bar", "baz qux") == 0.0


def test_jaccard_partial_overlap():
    from pipeline import TestGeneratorPipeline
    score = TestGeneratorPipeline._jaccard("login happy path", "login success path")
    assert 0.0 < score < 1.0


def test_jaccard_empty_strings():
    from pipeline import TestGeneratorPipeline
    assert TestGeneratorPipeline._jaccard("", "hello") == 0.0
    assert TestGeneratorPipeline._jaccard("hello", "") == 0.0


# ── _renormalize_ids ──────────────────────────────────────────────────────────

def test_renormalize_clean_ids_no_change():
    p = _pipeline()
    tests = [_make_manual("MTC-001", "A"), _make_manual("MTC-002", "B")]
    result, id_map = p._renormalize_ids(tests, "MTC")
    assert [t.test_case_id for t in result] == ["MTC-001", "MTC-002"]
    assert id_map == {}


def test_renormalize_strips_r1_suffixes():
    p = _pipeline()
    tests = [
        _make_manual("MTC-001", "A"),
        _make_manual("MTC-002-R1", "B"),
        _make_manual("MTC-003-R1", "C"),
    ]
    result, id_map = p._renormalize_ids(tests, "MTC")
    assert [t.test_case_id for t in result] == ["MTC-001", "MTC-002", "MTC-003"]
    assert id_map == {"MTC-002-R1": "MTC-002", "MTC-003-R1": "MTC-003"}


def test_renormalize_returns_new_list():
    p = _pipeline()
    tests = [_make_manual("MTC-001-R1", "A")]
    original_id = tests[0].test_case_id
    result, _ = p._renormalize_ids(tests, "MTC")
    assert tests[0].test_case_id == original_id  # original unchanged
    assert result[0].test_case_id == "MTC-001"


# ── _update_manual_refs ───────────────────────────────────────────────────────

def test_update_manual_refs_rewrites_stale_ids():
    p = _pipeline()
    api_tests = [_make_automation("ATC-001", "Test", refs=["MTC-002-R1", "MTC-003-R1"])]
    id_map = {"MTC-002-R1": "MTC-002", "MTC-003-R1": "MTC-003"}
    result = p._update_manual_refs(api_tests, id_map)
    assert result[0].manual_test_refs == ["MTC-002", "MTC-003"]


def test_update_manual_refs_unchanged_when_clean():
    p = _pipeline()
    api_tests = [_make_automation("ATC-001", "Test", refs=["MTC-001", "MTC-002"])]
    id_map = {"MTC-003-R1": "MTC-003"}
    result = p._update_manual_refs(api_tests, id_map)
    assert result[0].manual_test_refs == ["MTC-001", "MTC-002"]


def test_update_manual_refs_returns_new_list():
    p = _pipeline()
    api_tests = [_make_automation("ATC-001", "Test", refs=["MTC-001-R1"])]
    original_refs = list(api_tests[0].manual_test_refs)
    result = p._update_manual_refs(api_tests, {"MTC-001-R1": "MTC-001"})
    assert api_tests[0].manual_test_refs == original_refs  # original unchanged
    assert result[0].manual_test_refs == ["MTC-001"]


# ── _merge_tests ──────────────────────────────────────────────────────────────

def test_merge_does_not_mutate_existing():
    p = _pipeline()
    existing = [_make_manual("MTC-001", "A")]
    new = [_make_manual("MTC-002", "B")]
    original_len = len(existing)
    p._merge_tests(existing, new, "R1")
    assert len(existing) == original_len  # original list unchanged


def test_merge_renames_collision():
    p = _pipeline()
    existing = [_make_manual("MTC-001", "A")]
    new = [_make_manual("MTC-001", "Duplicate")]
    result = p._merge_tests(existing, new, "R1")
    ids = [t.test_case_id for t in result]
    assert "MTC-001" in ids
    assert "MTC-001-R1" in ids


def test_merge_no_collision_keeps_ids():
    p = _pipeline()
    existing = [_make_manual("MTC-001", "A")]
    new = [_make_manual("MTC-002", "B")]
    result = p._merge_tests(existing, new, "R1")
    assert [t.test_case_id for t in result] == ["MTC-001", "MTC-002"]


# ── _deduplicate ──────────────────────────────────────────────────────────────

def test_deduplicate_removes_same_id():
    p = _pipeline()
    tests = [_make_manual("MTC-001", "A"), _make_manual("MTC-001", "A copy")]
    result = p._deduplicate(tests)
    assert len(result) == 1
    assert result[0].test_case_id == "MTC-001"


def test_deduplicate_removes_near_duplicate_title():
    p = _pipeline()
    # Jaccard("user login happy path scenario", "user login happy path test") = 4/6 = 0.67 > 0.65
    tests = [
        _make_manual("MTC-001", "user login happy path scenario"),
        _make_manual("MTC-002", "user login happy path test"),
    ]
    result = p._deduplicate(tests)
    assert len(result) == 1


def test_deduplicate_keeps_distinct_titles():
    p = _pipeline()
    tests = [
        _make_manual("MTC-001", "login happy path"),
        _make_manual("MTC-002", "password reset with expired token"),
    ]
    result = p._deduplicate(tests)
    assert len(result) == 2
