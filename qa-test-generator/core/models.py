"""
Core data models for the QA Test Case Generator.
Defines the structure for inputs, outputs, and internal data.
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum
from datetime import datetime


# ============================================
# ENUMS
# ============================================

class InputType(str, Enum):
    """Type of requirement input."""
    PLAIN_TEXT = "plain_text"
    ACCEPTANCE_CRITERIA = "acceptance_criteria"
    USER_STORY = "user_story"


class TestCaseType(str, Enum):
    """Type of test case output."""
    MANUAL = "manual"
    API_AUTOMATION = "api_automation"
    UI_AUTOMATION = "ui_automation"


class Priority(str, Enum):
    """Test case priority levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ScenarioType(str, Enum):
    """Type of test scenario."""
    HAPPY_PATH = "happy_path"
    NEGATIVE = "negative"
    EDGE_CASE = "edge_case"
    BOUNDARY = "boundary"
    SECURITY = "security"
    CROSS_PLATFORM = "cross_platform"


# ============================================
# INPUT MODELS
# ============================================

class RequirementInput(BaseModel):
    """Input requirement from user."""
    content: str = Field(..., description="The requirement text (AC, user story, or description)")
    input_type: InputType = Field(default=InputType.PLAIN_TEXT, description="Type of input")
    project_context: Optional[str] = Field(default=None, description="Project or domain context")
    tech_stack: Optional[str] = Field(default=None, description="Technology stack information")
    additional_context: Optional[str] = Field(default=None, description="Any additional context")


class GenerationConfig(BaseModel):
    """Configuration for test case generation."""
    include_manual: bool = Field(default=True, description="Generate manual test cases")
    include_api: bool = Field(default=True, description="Generate API automation scripts")
    include_ui: bool = Field(default=True, description="Generate UI automation scripts")
    framework: str = Field(default="playwright", description="Automation framework to use")
    language: str = Field(default="typescript", description="Programming language for scripts")
    scenarios: list[ScenarioType] = Field(
        default=[
            ScenarioType.HAPPY_PATH,
            ScenarioType.NEGATIVE,
            ScenarioType.EDGE_CASE,
            ScenarioType.BOUNDARY,
            ScenarioType.SECURITY,
        ],
        description="Types of scenarios to cover"
    )


# ============================================
# PLANNER OUTPUT MODELS
# ============================================

class PlannerAnalysis(BaseModel):
    """Output from the Planner Agent."""
    feature_name: str = Field(..., description="Identified feature name")
    domain: str = Field(..., description="Domain/module of the feature")
    intent: str = Field(..., description="What the feature is supposed to do")
    tech_stack: list[str] = Field(default=[], description="Identified technologies")
    scope: str = Field(..., description="Scope of testing needed")
    endpoints: list[str] = Field(default=[], description="Identified API endpoints")
    ui_elements: list[str] = Field(default=[], description="Identified UI elements")
    dependencies: list[str] = Field(default=[], description="External dependencies")
    test_focus_areas: list[str] = Field(default=[], description="Key areas to focus testing")
    

# ============================================
# TEST CASE MODELS
# ============================================

class TestStep(BaseModel):
    """Single step in a manual test case."""
    step_number: int = Field(..., description="Step number")
    action: str = Field(..., description="Action to perform")
    expected_result: str = Field(..., description="Expected outcome")
    test_data: Optional[str] = Field(default=None, description="Test data to use")


class ManualTestCase(BaseModel):
    """Manual test case with step-by-step instructions."""
    test_case_id: str = Field(..., description="Unique test case ID")
    title: str = Field(..., description="Test case title")
    description: str = Field(default="", description="Test case description")
    priority: Priority = Field(default=Priority.MEDIUM, description="Priority level")
    scenario_type: ScenarioType = Field(..., description="Type of scenario")
    preconditions: list[str] = Field(default=[], description="Preconditions")
    steps: list[TestStep] = Field(..., description="Test steps")
    postconditions: list[str] = Field(default=[], description="Postconditions/cleanup")
    tags: list[str] = Field(default=[], description="Tags for categorization")


class AutomationTestCase(BaseModel):
    """Automated test case (API or UI)."""
    test_case_id: str = Field(..., description="Unique test case ID")
    title: str = Field(..., description="Test case title")
    test_type: TestCaseType = Field(..., description="Type of automation test")
    scenario_type: ScenarioType = Field(..., description="Type of scenario")
    priority: Priority = Field(default=Priority.MEDIUM, description="Priority level")
    code: str = Field(..., description="The automation script code")
    file_name: str = Field(..., description="Suggested file name")
    dependencies: list[str] = Field(default=[], description="Required imports/dependencies")


# ============================================
# REVIEW OUTPUT MODELS
# ============================================

class CoverageReport(BaseModel):
    """Test coverage analysis from Review Agent."""
    total_test_cases: int = Field(..., description="Total number of test cases")
    by_type: dict[str, int] = Field(default={}, description="Count by test type")
    by_scenario: dict[str, int] = Field(default={}, description="Count by scenario type")
    by_priority: dict[str, int] = Field(default={}, description="Count by priority")
    coverage_gaps: list[str] = Field(default=[], description="Identified coverage gaps")
    suggestions: list[str] = Field(default=[], description="Suggestions for improvement")
    quality_score: float = Field(..., ge=0, le=100, description="Quality score 0-100")


class ReviewResult(BaseModel):
    """Complete review from Review Agent."""
    coverage: CoverageReport = Field(..., description="Coverage analysis")
    issues_found: list[str] = Field(default=[], description="Issues found in test cases")
    improvements_made: list[str] = Field(default=[], description="Improvements applied")
    final_score: float = Field(..., ge=0, le=100, description="Final quality score")


# ============================================
# FINAL OUTPUT MODEL
# ============================================

class GeneratedTestSuite(BaseModel):
    """Complete output from the system."""
    feature_name: str = Field(..., description="Feature being tested")
    generated_at: datetime = Field(default_factory=datetime.now, description="Generation timestamp")
    analysis: PlannerAnalysis = Field(..., description="Planner analysis")
    manual_test_cases: list[ManualTestCase] = Field(default=[], description="Manual test cases")
    api_test_cases: list[AutomationTestCase] = Field(default=[], description="API automation tests")
    ui_test_cases: list[AutomationTestCase] = Field(default=[], description="UI automation tests")
    review: Optional[ReviewResult] = Field(default=None, description="Review results")
    markdown_output: str = Field(default="", description="Formatted markdown output")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
