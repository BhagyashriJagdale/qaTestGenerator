"""
Project management endpoints.

GET  /projects                        — list current user's projects
POST /projects                        — create a project
GET  /projects/{id}                   — get project detail
PUT  /projects/{id}                   — rename / update description
DELETE /projects/{id}                 — delete project and all its data

GET  /projects/{id}/requirements      — requirements submitted to this project
GET  /projects/{id}/test-suites       — generated test suites
GET  /projects/{id}/test-suites/{sid} — full test suite with outputs
GET  /projects/{id}/logs              — execution history
GET  /projects/{id}/summary           — counts + last activity
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from api.auth import get_current_user
import db.repository as repo

router = APIRouter(prefix="/projects", tags=["projects"])


# ── Request / Response models ─────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)


class UpdateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)


# ── Projects ──────────────────────────────────────────────────────────────────

@router.get("")
async def list_projects(user_id: str = Depends(get_current_user)):
    """List all projects belonging to the authenticated user."""
    return repo.list_projects(user_id)


@router.post("", status_code=201)
async def create_project(
    body: CreateProjectRequest,
    user_id: str = Depends(get_current_user),
):
    """Create a new project."""
    return repo.create_project(user_id, body.name, body.description)


@router.get("/{project_id}")
async def get_project(project_id: str, user_id: str = Depends(get_current_user)):
    """Get a single project (must belong to the authenticated user)."""
    project = repo.get_project(project_id, user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}")
async def update_project(
    project_id: str,
    body: UpdateProjectRequest,
    user_id: str = Depends(get_current_user),
):
    """Update a project's name or description."""
    project = repo.get_project(project_id, user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return repo.update_project(project_id, user_id, body.name, body.description)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, user_id: str = Depends(get_current_user)):
    """Delete a project and all associated data (cascades in DB)."""
    project = repo.get_project(project_id, user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    repo.delete_project(project_id, user_id)


# ── Project data endpoints ────────────────────────────────────────────────────

@router.get("/{project_id}/requirements")
async def get_requirements(
    project_id: str,
    user_id: str = Depends(get_current_user),
):
    """Return all requirements submitted to this project, newest first."""
    _assert_owns(project_id, user_id)
    return repo.list_requirements(project_id, user_id)


@router.get("/{project_id}/test-suites")
async def get_test_suites(
    project_id: str,
    user_id: str = Depends(get_current_user),
):
    """Return all generated test suites for this project (summary only)."""
    _assert_owns(project_id, user_id)
    return repo.list_test_suites(project_id, user_id)


@router.get("/{project_id}/test-suites/{suite_id}")
async def get_test_suite(
    project_id: str,
    suite_id: str,
    user_id: str = Depends(get_current_user),
):
    """Return a single test suite with full markdown/tab outputs."""
    _assert_owns(project_id, user_id)
    suite = repo.get_test_suite(suite_id, user_id)
    if not suite or suite.get("project_id") != project_id:
        raise HTTPException(status_code=404, detail="Test suite not found")
    return suite


@router.get("/{project_id}/logs")
async def get_logs(
    project_id: str,
    user_id: str = Depends(get_current_user),
):
    """Return execution history for this project, newest first."""
    _assert_owns(project_id, user_id)
    return repo.list_logs(project_id, user_id)


@router.get("/{project_id}/summary")
async def get_summary(
    project_id: str,
    user_id: str = Depends(get_current_user),
):
    """Return aggregate counts and latest activity for the project."""
    _assert_owns(project_id, user_id)
    requirements = repo.list_requirements(project_id, user_id)
    suites = repo.list_test_suites(project_id, user_id)
    logs = repo.list_logs(project_id, user_id)

    total_tests = sum(s.get("total_test_cases", 0) for s in suites)
    avg_quality = (
        sum(s.get("quality_score", 0) for s in suites) / len(suites) if suites else 0.0
    )
    last_run = logs[0].get("started_at") if logs else None

    return {
        "total_requirements": len(requirements),
        "total_test_suites": len(suites),
        "total_test_cases": total_tests,
        "average_quality_score": round(avg_quality, 1),
        "total_executions": len(logs),
        "last_run_at": last_run,
    }


# ── helpers ───────────────────────────────────────────────────────────────────

def _assert_owns(project_id: str, user_id: str) -> None:
    """Raise 404 if the project doesn't exist or doesn't belong to the user."""
    if not repo.get_project(project_id, user_id):
        raise HTTPException(status_code=404, detail="Project not found")
