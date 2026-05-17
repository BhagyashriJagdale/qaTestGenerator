"""
Database repository — thin wrappers around Supabase table operations.
All methods scope queries to the caller's user_id so one user cannot
access another user's data.
"""

from typing import Optional
from datetime import datetime, timezone
from .client import get_supabase_client


# ── helpers ───────────────────────────────────────────────────────────────────

def _client():
    return get_supabase_client()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Projects ──────────────────────────────────────────────────────────────────

def create_project(user_id: str, name: str, description: Optional[str] = None) -> dict:
    row = {"user_id": user_id, "name": name, "description": description}
    result = _client().table("projects").insert(row).execute()
    return result.data[0]


def list_projects(user_id: str) -> list[dict]:
    result = (
        _client()
        .table("projects")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def get_project(project_id: str, user_id: str) -> Optional[dict]:
    result = (
        _client()
        .table("projects")
        .select("*")
        .eq("id", project_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    return result.data


def update_project(project_id: str, user_id: str, name: str, description: Optional[str] = None) -> dict:
    result = (
        _client()
        .table("projects")
        .update({"name": name, "description": description})
        .eq("id", project_id)
        .eq("user_id", user_id)
        .execute()
    )
    return result.data[0]


def delete_project(project_id: str, user_id: str) -> None:
    _client().table("projects").delete().eq("id", project_id).eq("user_id", user_id).execute()


# ── Requirements ──────────────────────────────────────────────────────────────

def save_requirement(
    project_id: str,
    user_id: str,
    content: str,
    input_type: str = "plain_text",
    project_context: Optional[str] = None,
    tech_stack: Optional[str] = None,
    additional_context: Optional[str] = None,
    github_repo_url: Optional[str] = None,
    website_url: Optional[str] = None,
) -> dict:
    row = {
        "project_id": project_id,
        "user_id": user_id,
        "content": content,
        "input_type": input_type,
        "project_context": project_context,
        "tech_stack": tech_stack,
        "additional_context": additional_context,
        "github_repo_url": github_repo_url,
        "website_url": website_url,
    }
    result = _client().table("requirements").insert(row).execute()
    return result.data[0]


def list_requirements(project_id: str, user_id: str, limit: int = 50) -> list[dict]:
    result = (
        _client()
        .table("requirements")
        .select("*")
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


# ── Test Suites ───────────────────────────────────────────────────────────────

def save_test_suite(
    project_id: str,
    user_id: str,
    requirement_id: Optional[str],
    feature_name: str,
    total_test_cases: int,
    quality_score: float,
    manual_output: Optional[str],
    api_output: Optional[str],
    ui_output: Optional[str],
    markdown_output: Optional[str],
) -> dict:
    row = {
        "project_id": project_id,
        "user_id": user_id,
        "requirement_id": requirement_id,
        "feature_name": feature_name,
        "total_test_cases": total_test_cases,
        "quality_score": quality_score,
        "manual_output": manual_output,
        "api_output": api_output,
        "ui_output": ui_output,
        "markdown_output": markdown_output,
    }
    result = _client().table("test_suites").insert(row).execute()
    return result.data[0]


def list_test_suites(project_id: str, user_id: str, limit: int = 50) -> list[dict]:
    result = (
        _client()
        .table("test_suites")
        .select("id, project_id, requirement_id, feature_name, total_test_cases, quality_score, created_at")
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


def get_test_suite(suite_id: str, user_id: str) -> Optional[dict]:
    result = (
        _client()
        .table("test_suites")
        .select("*")
        .eq("id", suite_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    return result.data


# ── Execution Logs ────────────────────────────────────────────────────────────

def create_log(
    project_id: str,
    user_id: str,
    job_id: str,
    requirement_id: Optional[str] = None,
) -> dict:
    row = {
        "project_id": project_id,
        "user_id": user_id,
        "job_id": job_id,
        "requirement_id": requirement_id,
        "status": "running",
        "started_at": _now_iso(),
    }
    result = _client().table("execution_logs").insert(row).execute()
    return result.data[0]


def complete_log(
    log_id: str,
    status: str,
    feature_name: Optional[str] = None,
    total_test_cases: int = 0,
    quality_score: float = 0.0,
    test_suite_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> dict:
    update = {
        "status": status,
        "feature_name": feature_name,
        "total_test_cases": total_test_cases,
        "quality_score": quality_score,
        "test_suite_id": test_suite_id,
        "error_message": error_message,
        "completed_at": _now_iso(),
    }
    result = _client().table("execution_logs").update(update).eq("id", log_id).execute()
    return result.data[0]


def list_logs(project_id: str, user_id: str, limit: int = 50) -> list[dict]:
    result = (
        _client()
        .table("execution_logs")
        .select("*")
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data
