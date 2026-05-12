"""
Review Agent - Reviews and scores generated test cases.
Third agent in the pipeline.
"""

from typing import Optional
from .base_agent import BaseAgent
from .prompts import REVIEW_SYSTEM_PROMPT
from core.models import (
    PlannerAnalysis,
    ManualTestCase,
    AutomationTestCase,
    CoverageReport,
    ReviewResult,
)
from rich.console import Console

console = Console()


class ReviewAgent(BaseAgent):
    """
    Review Agent analyzes generated test cases for coverage,
    quality, and best practices compliance.
    """
    
    def __init__(self):
        super().__init__(
            name="Review Agent",
            system_prompt=REVIEW_SYSTEM_PROMPT
        )
    
    def run(
        self,
        analysis: PlannerAnalysis,
        manual_tests: list[ManualTestCase],
        api_tests: list[AutomationTestCase],
        ui_tests: list[AutomationTestCase]
    ) -> ReviewResult:
        """
        Review the generated test cases.
        
        Args:
            analysis: Planner's analysis for context
            manual_tests: Generated manual test cases
            api_tests: Generated API automation tests
            ui_tests: Generated UI automation tests
            
        Returns:
            ReviewResult with coverage analysis and feedback
        """
        console.print(f"\n[bold yellow]{'='*50}[/bold yellow]")
        console.print(f"[bold yellow]REVIEW AGENT[/bold yellow]")
        console.print(f"[bold yellow]{'='*50}[/bold yellow]")
        
        # Build the user message with all test cases
        user_message = self._build_user_message(
            analysis, manual_tests, api_tests, ui_tests
        )
        
        try:
            result = self._generate_json(user_message, temperature=0.3)
            review = self._parse_review(result, manual_tests, api_tests, ui_tests)

            self._log_review(review)
            return review
            
        except Exception as e:
            console.print(f"[red]Error in Review Agent: {e}[/red]")
            raise
    
    def _build_user_message(
        self,
        analysis: PlannerAnalysis,
        manual_tests: list[ManualTestCase],
        api_tests: list[AutomationTestCase],
        ui_tests: list[AutomationTestCase]
    ) -> str:
        """Build the review request message."""
        # Format manual tests
        manual_summary = self._format_manual_tests(manual_tests)
        
        # Format automation tests
        api_summary = self._format_automation_tests(api_tests, "API")
        ui_summary = self._format_automation_tests(ui_tests, "UI")
        
        return f"""## FEATURE CONTEXT
- **Feature:** {analysis.feature_name}
- **Domain:** {analysis.domain}
- **Focus Areas:** {', '.join(analysis.test_focus_areas)}

## GENERATED TEST CASES

NOTE: Automation code below is a **display preview** (first 500 chars). The actual generated code is complete.
Do NOT flag "..." at the end of a code preview as truncation — that is expected and is NOT an issue.

### Manual Test Cases ({len(manual_tests)} total)
{manual_summary}

### API Automation Tests ({len(api_tests)} total)
{api_summary}

### UI Automation Tests ({len(ui_tests)} total)
{ui_summary}

Review these test cases for coverage, quality, and best practices.
Provide detailed feedback and a quality score."""
    
    def _format_manual_tests(self, tests: list[ManualTestCase]) -> str:
        """Format manual tests for review."""
        if not tests:
            return "No manual tests generated."

        lines = []
        for test in tests:
            # Include first step + test data so reviewer can assess data quality
            step_sample = ""
            if test.steps:
                s = test.steps[0]
                data_part = f" | Data: {s.test_data}" if s.test_data else ""
                step_sample = f"\n  Step 1: {s.action[:100]}{data_part}"
            lines.append(
                f"\n**{test.test_case_id}: {test.title}**"
                f"\n- Priority: {test.priority.value} | Scenario: {test.scenario_type.value}"
                f"\n- Steps: {len(test.steps)} | Preconditions: {len(test.preconditions)}"
                f"{step_sample}"
            )

        return "\n".join(lines)

    def _format_automation_tests(
        self,
        tests: list[AutomationTestCase],
        test_type: str
    ) -> str:
        """Format automation tests for review."""
        if not tests:
            return f"No {test_type} tests generated."

        lines = []
        for test in tests:
            code_preview = test.code[:500] + "..." if len(test.code) > 500 else test.code
            refs = ", ".join(test.manual_test_refs) if test.manual_test_refs else "none"
            lines.append(
                f"\n**{test.test_case_id}: {test.title}**"
                f"\n- Priority: {test.priority.value} | Scenario: {test.scenario_type.value}"
                f"\n- File: {test.file_name} | Covers manual: {refs}"
                f"\n```typescript\n{code_preview}\n```"
            )

        return "\n".join(lines)
    
    def _parse_review(
        self,
        data: dict,
        manual_tests: list[ManualTestCase],
        api_tests: list[AutomationTestCase],
        ui_tests: list[AutomationTestCase],
    ) -> ReviewResult:
        """Parse review result. Counts are computed from actual lists; qualitative fields come from LLM."""
        # Compute counts deterministically — LLMs miscount regularly
        by_type = {
            "manual": len(manual_tests),
            "api_automation": len(api_tests),
            "ui_automation": len(ui_tests),
        }
        total = sum(by_type.values())

        by_scenario: dict[str, int] = {}
        by_priority: dict[str, int] = {}
        for t in manual_tests + api_tests + ui_tests:
            st = getattr(t, "scenario_type", None)
            if st:
                by_scenario[st.value] = by_scenario.get(st.value, 0) + 1
            p = getattr(t, "priority", None)
            if p:
                by_priority[p.value] = by_priority.get(p.value, 0) + 1

        coverage_data = data.get("coverage", {})
        coverage = CoverageReport(
            total_test_cases=total,
            by_type=by_type,
            by_scenario=by_scenario,
            by_priority=by_priority,
            coverage_gaps=coverage_data.get("coverage_gaps", [])[:10],
            suggestions=coverage_data.get("suggestions", [])[:5],
            quality_score=coverage_data.get("quality_score", 0.0),
        )

        return ReviewResult(
            coverage=coverage,
            issues_found=data.get("issues_found", [])[:10],
            improvements_made=data.get("improvements_made", [])[:5],
            final_score=data.get("final_score", 0.0),
        )
    
    def _log_review(self, review: ReviewResult) -> None:
        """Log review results."""
        console.print(f"\n[green]✓ Review Complete[/green]")
        console.print(f"  Total Test Cases: [bold]{review.coverage.total_test_cases}[/bold]")
        console.print(f"  Quality Score: [bold]{review.coverage.quality_score}%[/bold]")
        console.print(f"  Final Score: [bold]{review.final_score}%[/bold]")
        
        if review.coverage.coverage_gaps:
            console.print(f"\n  [yellow]Coverage Gaps:[/yellow]")
            for gap in review.coverage.coverage_gaps:
                console.print(f"    • {gap}")
        
        if review.issues_found:
            console.print(f"\n  [yellow]Issues Found:[/yellow]")
            for issue in review.issues_found[:3]:  # Show first 3
                console.print(f"    • {issue}")
