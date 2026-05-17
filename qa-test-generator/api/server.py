"""
FastAPI server for the QA Test Case Generator.
Provides REST API endpoints for test case generation.
"""

import ipaddress
from fastapi import FastAPI, HTTPException, BackgroundTasks, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from urllib.parse import urlparse
import asyncio
import uuid

from config import get_settings
from core.models import (
    InputType,
    ScenarioType,
    GenerationConfig,
    GeneratedTestSuite,
)
from pipeline import TestGeneratorPipeline, RequirementInput
from rag import get_rag_system
from agents.planner_agent import InvalidRequirementError, IncompleteRequirementError
from tools.website_crawler import WebsiteContextFetcher
from api.auth import get_current_user
from db.client import get_supabase_client
import db.repository as repo

# Initialize FastAPI app
app = FastAPI(
    title="QA Test Case Generator API",
    description="AI-powered test case generation from requirements",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://qagen-automata.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import logging

# Mount project management routes
from api.projects import router as projects_router
app.include_router(projects_router)

# In-memory job storage — jobs are lost on server restart.
# For production, replace with Redis or a database-backed store.
jobs: dict[str, dict] = {}


@app.on_event("startup")
async def _warn_in_memory_store():
    logging.getLogger(__name__).warning(
        "Using in-memory job store. All jobs will be lost on server restart. "
        "Set up Redis or a persistent store for production."
    )


# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class GenerateRequest(BaseModel):
    """Request model for test case generation."""
    requirement: str = Field(..., description="The requirement text")
    input_type: str = Field(default="plain_text", description="Type of input")
    project_context: Optional[str] = Field(default=None, description="Project context")
    tech_stack: Optional[str] = Field(default=None, description="Technology stack")
    project_id: Optional[str] = Field(
        default=None,
        description="Project ID — when provided the requirement, test suite, and execution log are saved to the project"
    )
    github_repo_url: Optional[str] = Field(
        default=None,
        description="GitHub repository URL — the pipeline fetches routes, models, and components to ground test cases in the actual codebase"
    )
    website_url: Optional[str] = Field(
        default=None,
        description="Hosted website URL — crawled for exact Playwright locators and API endpoint URLs to ground UI/API test generation"
    )
    additional_context: Optional[str] = Field(
        default=None,
        description="Any extra context to pass to the planner (domain rules, constraints, notes)"
    )
    include_manual: bool = Field(default=True, description="Generate manual tests")
    include_api: bool = Field(default=True, description="Generate API tests")
    include_ui: bool = Field(default=True, description="Generate UI tests")
    scenarios: list[str] = Field(
        default=["happy_path", "negative", "edge_case", "boundary", "security"],
        description="Scenario types to cover"
    )
    use_rag: bool = Field(default=True, description="Use RAG for context")
    crawler_timeout: int = Field(default=15, description="HTTP timeout in seconds for website crawl")

    @field_validator("website_url")
    @classmethod
    def validate_website_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v.startswith(("http://", "https://")):
            raise ValueError("website_url must start with http:// or https://")
        # C-1: SSRF guard — reject obvious private/loopback targets
        host = (urlparse(v).hostname or "").lower()
        if host in ("localhost", "localhost.localdomain"):
            raise ValueError(f"website_url must point to a public host, not '{host}'")
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
                raise ValueError(
                    f"website_url points to a non-public IP address '{host}'"
                )
        except ValueError as exc:
            if "non-public" in str(exc) or "public host" in str(exc):
                raise
            # host is a domain name, not an IP literal — DNS not resolved here
        return v


class GenerateResponse(BaseModel):
    """Response model for test case generation."""
    job_id: str
    status: str
    feature_name: Optional[str] = None
    total_test_cases: int = 0
    quality_score: float = 0.0
    markdown_output: Optional[str] = None
    manual_output: Optional[str] = None   # Manual Test Cases tab
    api_output: Optional[str] = None      # Playwright API tab
    ui_output: Optional[str] = None       # Playwright UI tab
    created_at: datetime


class JobStatus(BaseModel):
    """Job status response."""
    job_id: str
    status: str
    progress: int
    result: Optional[GenerateResponse] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    rag_status: dict
    timestamp: datetime


class AddKnowledgeRequest(BaseModel):
    """Request to add knowledge to RAG."""
    content: str
    domain: str
    knowledge_type: str = Field(default="best_practice")


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


class AuthTokenResponse(BaseModel):
    access_token: Optional[str] = None
    token_type: str = "bearer"
    email_confirmation_required: bool = False


# ============================================
# ENDPOINTS
# ============================================

@app.get("/", response_model=dict)
async def root():
    """Root endpoint with API info."""
    return {
        "name": "QA Test Case Generator API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    rag = get_rag_system()
    return HealthResponse(
        status="healthy",
        rag_status=rag.get_stats(),
        timestamp=datetime.now()
    )


@app.post("/auth/login", response_model=AuthTokenResponse)
async def login(request: LoginRequest):
    """Authenticate with email + password; returns a short-lived Supabase JWT."""
    try:
        client = get_supabase_client()
        response = client.auth.sign_in_with_password({"email": request.email, "password": request.password})
        if not response.session:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        return AuthTokenResponse(access_token=response.session.access_token)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid email or password")


@app.post("/auth/signup", response_model=AuthTokenResponse)
async def signup(request: SignupRequest):
    """Register a new user; returns a JWT or signals that email confirmation is needed."""
    try:
        client = get_supabase_client()
        response = client.auth.sign_up({"email": request.email, "password": request.password})
        if response.session:
            return AuthTokenResponse(access_token=response.session.access_token)
        return AuthTokenResponse(email_confirmation_required=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/generate", response_model=GenerateResponse)
async def generate_test_cases(
    request: GenerateRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Generate test cases from a requirement. Requires a valid Bearer token.
    Pass project_id to persist results to the project.
    """
    requirement_id: Optional[str] = None
    log_id: Optional[str] = None
    try:
        # Parse input type
        try:
            input_type = InputType(request.input_type)
        except ValueError:
            input_type = InputType.PLAIN_TEXT

        # Parse scenarios
        scenarios = []
        for s in request.scenarios:
            try:
                scenarios.append(ScenarioType(s))
            except ValueError:
                pass
        if not scenarios:
            scenarios = [ScenarioType.HAPPY_PATH, ScenarioType.NEGATIVE, ScenarioType.EDGE_CASE]

        # Save requirement to project if project_id provided
        job_id = str(uuid.uuid4())

        if request.project_id:
            try:
                req_record = repo.save_requirement(
                    project_id=request.project_id,
                    user_id=user_id,
                    content=request.requirement,
                    input_type=request.input_type,
                    project_context=request.project_context,
                    tech_stack=request.tech_stack,
                    additional_context=request.additional_context,
                    github_repo_url=request.github_repo_url,
                    website_url=request.website_url,
                )
                requirement_id = req_record["id"]
                log_record = repo.create_log(
                    project_id=request.project_id,
                    user_id=user_id,
                    job_id=job_id,
                    requirement_id=requirement_id,
                )
                log_id = log_record["id"]
            except Exception:
                pass  # DB failure must not block generation

        # Create pipeline inputs
        requirement = RequirementInput(
            content=request.requirement,
            input_type=input_type,
            project_context=request.project_context,
            tech_stack=request.tech_stack,
            additional_context=request.additional_context or None,
            github_repo_url=request.github_repo_url or None,
            website_url=request.website_url or None,
        )
        config = GenerationConfig(
            include_manual=request.include_manual,
            include_api=request.include_api,
            include_ui=request.include_ui,
            scenarios=scenarios,
        )

        # Run pipeline in a thread so the async event loop is not blocked
        website_fetcher = (
            WebsiteContextFetcher(timeout=request.crawler_timeout) if request.website_url else None
        )
        pipeline = TestGeneratorPipeline(use_rag=request.use_rag, website_fetcher=website_fetcher)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, pipeline.run, requirement, config)

        total = (
            len(result.manual_test_cases) +
            len(result.api_test_cases) +
            len(result.ui_test_cases)
        )
        final_score = result.review.final_score if result.review else 0.0

        # Persist test suite and close execution log
        if request.project_id:
            try:
                suite_record = repo.save_test_suite(
                    project_id=request.project_id,
                    user_id=user_id,
                    requirement_id=requirement_id,
                    feature_name=result.feature_name,
                    total_test_cases=total,
                    quality_score=final_score,
                    manual_output=result.manual_output,
                    api_output=result.api_output,
                    ui_output=result.ui_output,
                    markdown_output=result.markdown_output,
                )
                if log_id:
                    repo.complete_log(
                        log_id=log_id,
                        status="completed",
                        feature_name=result.feature_name,
                        total_test_cases=total,
                        quality_score=final_score,
                        test_suite_id=suite_record["id"],
                    )
            except Exception:
                pass  # DB failure must not break the response

        return GenerateResponse(
            job_id=job_id,
            status="completed",
            feature_name=result.feature_name,
            total_test_cases=total,
            quality_score=final_score,
            markdown_output=result.markdown_output,
            manual_output=result.manual_output or None,
            api_output=result.api_output or None,
            ui_output=result.ui_output or None,
            created_at=result.generated_at,
        )

    except InvalidRequirementError as e:
        if log_id:
            try:
                repo.complete_log(log_id=log_id, status="failed", error_message=str(e))
            except Exception:
                pass
        raise HTTPException(status_code=422, detail={"error": "invalid_requirement", "message": str(e)})
    except IncompleteRequirementError as e:
        if log_id:
            try:
                repo.complete_log(log_id=log_id, status="failed", error_message=str(e))
            except Exception:
                pass
        raise HTTPException(status_code=422, detail={
            "error": "incomplete_requirement",
            "message": str(e),
            "issues": e.issues,
            "missing_information": e.missing,
            "suggestion": e.suggestion,
        })
    except Exception as e:
        if log_id:
            try:
                repo.complete_log(log_id=log_id, status="failed", error_message=str(e))
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate/async", response_model=JobStatus)
async def generate_test_cases_async(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user),
):
    """
    Generate test cases asynchronously. Requires a valid Bearer token.
    Returns a job ID that can be polled for status.
    Pass project_id to persist results to the project.
    """
    job_id = str(uuid.uuid4())

    jobs[job_id] = {
        "status": "pending",
        "progress": 0,
        "result": None,
        "error": None,
        "created_at": datetime.now(),
    }

    background_tasks.add_task(_run_generation_job, job_id, request, user_id)
    
    return JobStatus(
        job_id=job_id,
        status="pending",
        progress=0
    )


@app.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get the status of a generation job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    return JobStatus(
        job_id=job_id,
        status=job["status"],
        progress=job["progress"],
        result=job.get("result"),
        error=job.get("error")
    )


@app.get("/output/{job_id}/markdown", response_class=PlainTextResponse)
async def get_markdown_output(job_id: str):
    """Get the markdown output for a completed job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")
    
    if not job.get("result") or not job["result"].markdown_output:
        raise HTTPException(status_code=404, detail="No output available")
    
    return job["result"].markdown_output


@app.post("/knowledge/add")
async def add_knowledge(request: AddKnowledgeRequest):
    """Add domain knowledge to the RAG system."""
    rag = get_rag_system()
    
    success = rag.add_domain_knowledge(
        content=request.content,
        domain=request.domain,
        knowledge_type=request.knowledge_type
    )
    
    if success:
        return {"status": "success", "message": "Knowledge added"}
    else:
        raise HTTPException(status_code=500, detail="Failed to add knowledge")


@app.get("/knowledge/stats")
async def get_knowledge_stats():
    """Get RAG knowledge base statistics."""
    rag = get_rag_system()
    return rag.get_stats()


# ============================================
# BACKGROUND TASKS
# ============================================

async def _run_generation_job(
    job_id: str,
    request: GenerateRequest,
    user_id: Optional[str] = None,
):
    """Run generation job in background thread so the event loop stays free."""
    log_id: Optional[str] = None
    requirement_id: Optional[str] = None

    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["progress"] = 5

        try:
            input_type = InputType(request.input_type)
        except ValueError:
            input_type = InputType.PLAIN_TEXT

        scenarios = []
        for s in request.scenarios:
            try:
                scenarios.append(ScenarioType(s))
            except ValueError:
                pass

        jobs[job_id]["progress"] = 10

        # Persist requirement + open execution log for the project
        if request.project_id and user_id:
            try:
                req_record = repo.save_requirement(
                    project_id=request.project_id,
                    user_id=user_id,
                    content=request.requirement,
                    input_type=request.input_type,
                    project_context=request.project_context,
                    tech_stack=request.tech_stack,
                    additional_context=request.additional_context,
                    github_repo_url=request.github_repo_url,
                    website_url=request.website_url,
                )
                requirement_id = req_record["id"]
                log_record = repo.create_log(
                    project_id=request.project_id,
                    user_id=user_id,
                    job_id=job_id,
                    requirement_id=requirement_id,
                )
                log_id = log_record["id"]
            except Exception:
                pass

        requirement = RequirementInput(
            content=request.requirement,
            input_type=input_type,
            project_context=request.project_context,
            tech_stack=request.tech_stack,
            additional_context=request.additional_context or None,
            github_repo_url=request.github_repo_url or None,
            website_url=request.website_url or None,
        )
        config = GenerationConfig(
            include_manual=request.include_manual,
            include_api=request.include_api,
            include_ui=request.include_ui,
            scenarios=scenarios or [ScenarioType.HAPPY_PATH, ScenarioType.NEGATIVE],
        )

        jobs[job_id]["progress"] = 15

        # Run pipeline in a thread — each LLM call is blocking I/O
        website_fetcher = (
            WebsiteContextFetcher(timeout=request.crawler_timeout)
            if request.website_url else None
        )
        pipeline = TestGeneratorPipeline(use_rag=request.use_rag, website_fetcher=website_fetcher)
        loop = asyncio.get_running_loop()

        jobs[job_id]["progress"] = 20
        result = await loop.run_in_executor(None, pipeline.run, requirement, config)
        jobs[job_id]["progress"] = 90

        total = (
            len(result.manual_test_cases) +
            len(result.api_test_cases) +
            len(result.ui_test_cases)
        )
        final_score = result.review.final_score if result.review else 0.0

        # Persist test suite + close log
        if request.project_id and user_id:
            try:
                suite_record = repo.save_test_suite(
                    project_id=request.project_id,
                    user_id=user_id,
                    requirement_id=requirement_id,
                    feature_name=result.feature_name,
                    total_test_cases=total,
                    quality_score=final_score,
                    manual_output=result.manual_output,
                    api_output=result.api_output,
                    ui_output=result.ui_output,
                    markdown_output=result.markdown_output,
                )
                if log_id:
                    repo.complete_log(
                        log_id=log_id,
                        status="completed",
                        feature_name=result.feature_name,
                        total_test_cases=total,
                        quality_score=final_score,
                        test_suite_id=suite_record["id"],
                    )
            except Exception:
                pass

        jobs[job_id]["result"] = GenerateResponse(
            job_id=job_id,
            status="completed",
            feature_name=result.feature_name,
            total_test_cases=total,
            quality_score=final_score,
            markdown_output=result.markdown_output,
            manual_output=result.manual_output or None,
            api_output=result.api_output or None,
            ui_output=result.ui_output or None,
            created_at=result.generated_at,
        )
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["progress"] = 100

    except (InvalidRequirementError, IncompleteRequirementError, Exception) as e:
        error_msg = str(e)
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = error_msg
        if log_id:
            try:
                repo.complete_log(log_id=log_id, status="failed", error_message=error_msg)
            except Exception:
                pass


# ============================================
# MAIN
# ============================================

def start_server():
    """Start the FastAPI server."""
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "api.server:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug
    )


if __name__ == "__main__":
    start_server()
