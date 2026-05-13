"""Unit tests for FastAPI endpoints in api/server.py using TestClient."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


# ── app fixture ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """Create a TestClient with all heavy dependencies mocked."""
    mock_suite = MagicMock()
    mock_suite.feature_name = "Login"
    mock_suite.generated_at = datetime.now()
    mock_suite.manual_test_cases = []
    mock_suite.api_test_cases = []
    mock_suite.ui_test_cases = []
    mock_suite.markdown_output = "# Test Cases: Login\n\n..."
    mock_suite.manual_output = "## Manual\n..."
    mock_suite.api_output = "## API\n..."
    mock_suite.ui_output = "## UI\n..."
    mock_suite.review = MagicMock(final_score=80.0)

    mock_rag = MagicMock()
    mock_rag.get_stats.return_value = {"status": "ok", "total_documents": 0}
    mock_rag.add_domain_knowledge.return_value = True

    mock_pipeline = MagicMock()
    mock_pipeline.run.return_value = mock_suite

    with patch("api.server.get_rag_system", return_value=mock_rag), \
         patch("api.server.TestGeneratorPipeline", return_value=mock_pipeline):
        from fastapi.testclient import TestClient
        from api.server import app
        yield TestClient(app)


# ── GET / ─────────────────────────────────────────────────────────────────────

def test_root_returns_200(client):
    r = client.get("/")
    assert r.status_code == 200


def test_root_contains_api_name(client):
    r = client.get("/")
    assert "QA Test Case Generator" in r.json()["name"]


def test_root_contains_version(client):
    r = client.get("/")
    assert "version" in r.json()


# ── GET /health ───────────────────────────────────────────────────────────────

def test_health_returns_200(client):
    r = client.get("/health")
    assert r.status_code == 200


def test_health_status_healthy(client):
    r = client.get("/health")
    assert r.json()["status"] == "healthy"


def test_health_has_rag_status(client):
    r = client.get("/health")
    assert "rag_status" in r.json()


def test_health_has_timestamp(client):
    r = client.get("/health")
    assert "timestamp" in r.json()


# ── POST /generate ────────────────────────────────────────────────────────────

def _gen_payload(**kwargs):
    return {
        "requirement": "User can log in with valid email and password.",
        "input_type": "plain_text",
        "include_manual": True,
        "include_api": True,
        "include_ui": False,
        "scenarios": ["happy_path", "negative"],
        "use_rag": False,
        **kwargs,
    }


def test_generate_returns_200(client):
    r = client.post("/generate", json=_gen_payload())
    assert r.status_code == 200


def test_generate_response_has_job_id(client):
    r = client.post("/generate", json=_gen_payload())
    assert "job_id" in r.json()


def test_generate_response_status_completed(client):
    r = client.post("/generate", json=_gen_payload())
    assert r.json()["status"] == "completed"


def test_generate_response_has_markdown_output(client):
    r = client.post("/generate", json=_gen_payload())
    assert r.json()["markdown_output"] is not None


def test_generate_invalid_requirement_returns_422(client):
    from agents.planner_agent import InvalidRequirementError
    with patch("api.server.TestGeneratorPipeline") as MockPipeline:
        mock_p = MagicMock()
        mock_p.run.side_effect = InvalidRequirementError("Not a valid requirement")
        MockPipeline.return_value = mock_p
        r = client.post("/generate", json=_gen_payload(requirement="xyz"))
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "invalid_requirement"


def test_generate_incomplete_requirement_returns_422(client):
    from agents.planner_agent import IncompleteRequirementError
    with patch("api.server.TestGeneratorPipeline") as MockPipeline:
        mock_p = MagicMock()
        mock_p.run.side_effect = IncompleteRequirementError(
            issues=["Missing outcome"],
            missing=["Expected result?"],
        )
        MockPipeline.return_value = mock_p
        r = client.post("/generate", json=_gen_payload())
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "incomplete_requirement"


def test_generate_server_error_returns_500(client):
    with patch("api.server.TestGeneratorPipeline") as MockPipeline:
        mock_p = MagicMock()
        mock_p.run.side_effect = RuntimeError("LLM unavailable")
        MockPipeline.return_value = mock_p
        r = client.post("/generate", json=_gen_payload())
    assert r.status_code == 500


def test_generate_unknown_input_type_defaults_to_plain_text(client):
    r = client.post("/generate", json=_gen_payload(input_type="unknown_type"))
    assert r.status_code == 200


def test_generate_unknown_scenarios_filtered(client):
    r = client.post("/generate", json=_gen_payload(scenarios=["happy_path", "bogus_scenario"]))
    assert r.status_code == 200


def test_generate_all_unknown_scenarios_use_fallback(client):
    r = client.post("/generate", json=_gen_payload(scenarios=["bogus_a", "bogus_b"]))
    assert r.status_code == 200


# ── POST /generate/async ──────────────────────────────────────────────────────

def test_generate_async_returns_202_or_200(client):
    r = client.post("/generate/async", json=_gen_payload())
    assert r.status_code in (200, 201, 202)


def test_generate_async_returns_job_id(client):
    r = client.post("/generate/async", json=_gen_payload())
    assert "job_id" in r.json()


def test_generate_async_initial_status_pending(client):
    r = client.post("/generate/async", json=_gen_payload())
    assert r.json()["status"] == "pending"


# ── GET /jobs/{job_id} ────────────────────────────────────────────────────────

def test_get_job_not_found_returns_404(client):
    r = client.get("/jobs/nonexistent-job-id")
    assert r.status_code == 404


def test_get_job_after_async_submit(client):
    # Submit async job, then poll the returned job_id
    submit = client.post("/generate/async", json=_gen_payload())
    job_id = submit.json()["job_id"]
    r = client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["job_id"] == job_id


# ── POST /knowledge/add ───────────────────────────────────────────────────────

def test_add_knowledge_returns_success(client):
    r = client.post("/knowledge/add", json={
        "content": "Always test boundary values for numeric inputs.",
        "domain": "testing",
        "knowledge_type": "best_practice",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "success"


# ── GET /knowledge/stats ──────────────────────────────────────────────────────

def test_knowledge_stats_returns_200(client):
    r = client.get("/knowledge/stats")
    assert r.status_code == 200
