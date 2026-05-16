"""
FastAPI server for the QA Test Case Generator.
Provides REST API endpoints for test case generation.
"""

import ipaddress
from fastapi import FastAPI, HTTPException, BackgroundTasks
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


@app.post("/generate", response_model=GenerateResponse)
async def generate_test_cases(request: GenerateRequest):
    """
    Generate test cases from a requirement.
    This is a synchronous endpoint - for large requests, use /generate/async
    """
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
            scenarios = [
                ScenarioType.HAPPY_PATH,
                ScenarioType.NEGATIVE,
                ScenarioType.EDGE_CASE
            ]
        
        # Create requirement
        requirement = RequirementInput(
            content=request.requirement,
            input_type=input_type,
            project_context=request.project_context,
            tech_stack=request.tech_stack,
            additional_context=request.additional_context or None,
            github_repo_url=request.github_repo_url or None,
            website_url=request.website_url or None,
        )

        # Create config
        config = GenerationConfig(
            include_manual=request.include_manual,
            include_api=request.include_api,
            include_ui=request.include_ui,
            scenarios=scenarios
        )

        # Run pipeline in a thread so the async event loop is not blocked
        website_fetcher = (
            WebsiteContextFetcher(timeout=request.crawler_timeout)
            if request.website_url else None
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

        return GenerateResponse(
            job_id=str(uuid.uuid4()),
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
        raise HTTPException(status_code=422, detail={"error": "invalid_requirement", "message": str(e)})
    except IncompleteRequirementError as e:
        raise HTTPException(status_code=422, detail={
            "error": "incomplete_requirement",
            "message": str(e),
            "issues": e.issues,
            "missing_information": e.missing,
            "suggestion": e.suggestion,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate/async", response_model=JobStatus)
async def generate_test_cases_async(
    request: GenerateRequest,
    background_tasks: BackgroundTasks
):
    """
    Generate test cases asynchronously.
    Returns a job ID that can be polled for status.
    """
    job_id = str(uuid.uuid4())
    
    # Initialize job
    jobs[job_id] = {
        "status": "pending",
        "progress": 0,
        "result": None,
        "error": None,
        "created_at": datetime.now()
    }
    
    # Add background task
    background_tasks.add_task(
        _run_generation_job,
        job_id,
        request
    )
    
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

async def _run_generation_job(job_id: str, request: GenerateRequest):
    """Run generation job in background thread so the event loop stays free."""
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

        def _progress(pct: int):
            jobs[job_id]["progress"] = pct

        # Run pipeline in a thread — each LLM call is blocking I/O
        website_fetcher = (
            WebsiteContextFetcher(timeout=request.crawler_timeout)
            if request.website_url else None
        )
        pipeline = TestGeneratorPipeline(use_rag=request.use_rag, website_fetcher=website_fetcher)
        loop = asyncio.get_running_loop()

        _progress(20)  # planning
        result = await loop.run_in_executor(None, pipeline.run, requirement, config)
        _progress(90)  # formatting done

        total = (
            len(result.manual_test_cases) +
            len(result.api_test_cases) +
            len(result.ui_test_cases)
        )
        final_score = result.review.final_score if result.review else 0.0

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

    except InvalidRequirementError as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = f"Invalid requirement: {e}"
    except IncompleteRequirementError as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = f"Incomplete requirement: {e}"
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


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
