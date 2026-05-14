"""Integration tests for TestGeneratorPipeline.run() with all agents mocked."""

import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime
from core.models import (
    RequirementInput,
    GenerationConfig,
    ScenarioType,
    PlannerAnalysis,
    ManualTestCase,
    AutomationTestCase,
    TestCaseType,
    Priority,
    TestStep,
    CoverageReport,
    ReviewResult,
    GeneratedTestSuite,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _step():
    return TestStep(step_number=1, action="Do X", expected_result="X done")


def _manual(tc_id="MTC-001", scenario="happy_path"):
    return ManualTestCase(
        test_case_id=tc_id,
        title=f"Login {scenario}",
        scenario_type=ScenarioType(scenario),
        priority=Priority.HIGH,
        steps=[_step()],
    )


def _auto(tc_id="ATC-001", type_=TestCaseType.API_AUTOMATION, refs=None):
    return AutomationTestCase(
        test_case_id=tc_id,
        title=f"Auto {tc_id}",
        test_type=type_,
        scenario_type=ScenarioType.HAPPY_PATH,
        priority=Priority.HIGH,
        code="test('x',()=>{});",
        file_name="auth.spec.ts",
        manual_test_refs=refs or ["MTC-001"],
    )


def _analysis():
    return PlannerAnalysis(
        feature_name="User Login",
        domain="Auth",
        intent="Allow users to log in",
        scope="Full stack",
        test_focus_areas=["valid credentials", "invalid credentials"],
    )


def _review(score=80.0, gaps=None):
    return ReviewResult(
        coverage=CoverageReport(
            total_test_cases=3,
            quality_score=score,
            coverage_gaps=gaps or [],
        ),
        final_score=score,
    )


def _req():
    return RequirementInput(
        content="User can log in with valid email and password and is redirected to dashboard."
    )


def _config():
    return GenerationConfig(
        include_manual=True,
        include_api=True,
        include_ui=False,
        scenarios=[ScenarioType.HAPPY_PATH, ScenarioType.NEGATIVE],
    )


# ── pipeline factory ──────────────────────────────────────────────────────────

def _make_pipeline(
    *,
    analysis=None,
    manual=None,
    api=None,
    ui=None,
    review=None,
):
    """Create a TestGeneratorPipeline with all agents replaced by MagicMocks."""
    analysis = analysis or _analysis()
    manual = manual if manual is not None else [_manual()]
    api = api if api is not None else [_auto()]
    ui = ui if ui is not None else []
    review = review or _review(score=80.0)

    mock_planner = MagicMock()
    mock_planner.run.return_value = analysis

    mock_generator = MagicMock()
    mock_generator.run.return_value = (manual, api, ui)

    mock_reviewer = MagicMock()
    mock_reviewer.run.return_value = review

    mock_formatter = MagicMock()
    mock_formatter.run.return_value = "# Test Cases: Login\n\n..."
    mock_formatter.format_manual_section.return_value = "## Manual\n..."
    mock_formatter.format_api_section.return_value = "## API\n..."
    mock_formatter.format_ui_section.return_value = "## UI\n..."

    with patch("pipeline.PlannerAgent", return_value=mock_planner), \
         patch("pipeline.GeneratorAgent", return_value=mock_generator), \
         patch("pipeline.ReviewAgent", return_value=mock_reviewer), \
         patch("pipeline.FormatterAgent", return_value=mock_formatter), \
         patch("pipeline.get_rag_system"):
        from pipeline import TestGeneratorPipeline
        p = TestGeneratorPipeline(use_rag=False)
        # Replace the already-instantiated agents with our mocks
        p.planner = mock_planner
        p.generator = mock_generator
        p.reviewer = mock_reviewer
        p.formatter = mock_formatter

    return p, mock_planner, mock_generator, mock_reviewer, mock_formatter


# ── run() — basic happy path ──────────────────────────────────────────────────

def test_run_returns_generated_test_suite():
    p, *_ = _make_pipeline()
    result = p.run(_req(), _config())
    assert isinstance(result, GeneratedTestSuite)


def test_run_feature_name_from_analysis():
    p, *_ = _make_pipeline(analysis=_analysis())
    result = p.run(_req(), _config())
    assert result.feature_name == "User Login"


def test_run_includes_manual_tests():
    p, *_ = _make_pipeline(manual=[_manual("MTC-001"), _manual("MTC-002", "negative")])
    result = p.run(_req(), _config())
    assert len(result.manual_test_cases) == 2


def test_run_includes_api_tests():
    p, *_ = _make_pipeline(api=[_auto("ATC-001"), _auto("ATC-002")])
    result = p.run(_req(), _config())
    assert len(result.api_test_cases) == 2


def test_run_assigns_review():
    p, *_ = _make_pipeline(review=_review(score=90.0))
    result = p.run(_req(), _config())
    assert result.review is not None
    assert result.review.final_score == 90.0


def test_run_has_markdown_output():
    p, *_ = _make_pipeline()
    result = p.run(_req(), _config())
    assert result.markdown_output  # non-empty


def test_run_has_per_tab_sections():
    p, *_ = _make_pipeline()
    result = p.run(_req(), _config())
    assert result.manual_output
    assert result.api_output
    assert result.ui_output


# ── run() — agent call sequence ───────────────────────────────────────────────

def test_run_calls_planner_first():
    p, mock_planner, mock_generator, mock_reviewer, _ = _make_pipeline()
    call_order = []
    mock_planner.run.side_effect = lambda *a, **kw: (call_order.append("planner") or _analysis())
    mock_generator.run.side_effect = lambda *a, **kw: (call_order.append("generator") or ([_manual()], [_auto()], []))
    mock_reviewer.run.side_effect = lambda *a, **kw: (call_order.append("reviewer") or _review())
    p.run(_req(), _config())
    assert call_order[0] == "planner"
    assert "generator" in call_order
    assert "reviewer" in call_order


def test_run_calls_reviewer_after_generator():
    p, _, mock_generator, mock_reviewer, _ = _make_pipeline()
    call_order = []
    mock_generator.run.side_effect = lambda *a, **kw: (call_order.append("gen") or ([_manual()], [], []))
    mock_reviewer.run.side_effect = lambda *a, **kw: (call_order.append("rev") or _review())
    p.run(_req(), _config())
    gen_idx = call_order.index("gen")
    rev_idx = call_order.index("rev")
    assert gen_idx < rev_idx


# ── run() — no tests generated ───────────────────────────────────────────────

def test_run_skips_reviewer_when_no_tests_generated():
    p, _, _, mock_reviewer, _ = _make_pipeline(manual=[], api=[], ui=[])
    p.run(_req(), _config())
    mock_reviewer.run.assert_not_called()


def test_run_returns_suite_even_when_no_tests_generated():
    p, *_ = _make_pipeline(manual=[], api=[], ui=[])
    result = p.run(_req(), _config())
    assert isinstance(result, GeneratedTestSuite)


# ── run() — score above threshold skips refinement ───────────────────────────

def test_run_skips_refinement_when_score_above_threshold():
    from pipeline import QUALITY_THRESHOLD
    p, mock_planner, mock_generator, _, _ = _make_pipeline(review=_review(score=QUALITY_THRESHOLD + 1))
    p.run(_req(), _config())
    # Planner called once (initial); generator called once (initial). No refinement.
    assert mock_planner.run.call_count == 1
    assert mock_generator.run.call_count == 1


# ── run() — default config ────────────────────────────────────────────────────

def test_run_uses_default_config_when_none_given():
    p, _, mock_generator, _, _ = _make_pipeline()
    p.run(_req())
    assert mock_generator.run.called


# ── run() — ID renormalization ────────────────────────────────────────────────

def test_run_renormalizes_ids_after_dedup():
    # Generator returns tests with odd IDs; pipeline should renormalize
    manual = [_manual("MTC-099"), _manual("MTC-003", "negative")]
    p, *_ = _make_pipeline(manual=manual, api=[], ui=[])
    result = p.run(_req(), _config())
    ids = [t.test_case_id for t in result.manual_test_cases]
    assert ids == ["MTC-001", "MTC-002"]


def test_run_renormalizes_api_ids():
    api = [_auto("ATC-099"), _auto("ATC-003")]
    p, *_ = _make_pipeline(api=api)
    result = p.run(_req(), _config())
    ids = [t.test_case_id for t in result.api_test_cases]
    assert ids == ["ATC-001", "ATC-002"]


# ── run() — deduplication ─────────────────────────────────────────────────────

def test_run_deduplicates_identical_ids():
    # Two tests with same ID — only one should survive
    manual = [_manual("MTC-001"), _manual("MTC-001", "negative")]
    p, *_ = _make_pipeline(manual=manual, api=[], ui=[])
    result = p.run(_req(), _config())
    assert len(result.manual_test_cases) == 1
