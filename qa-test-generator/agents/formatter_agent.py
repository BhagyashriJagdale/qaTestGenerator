"""
Formatter Agent - Formats test cases into clean documentation.
Fourth and final agent in the pipeline.
"""

from datetime import datetime
from .base_agent import BaseAgent
from core.models import (
    PlannerAnalysis,
    ManualTestCase,
    AutomationTestCase,
    ReviewResult,
)
from rich.console import Console

console = Console()


class FormatterAgent(BaseAgent):
    """
    Formatter Agent takes all generated content and produces
    clean, professional markdown documentation.
    """
    
    def __init__(self):
        super().__init__(
            name="Formatter Agent",
            system_prompt=""  # Formatter works deterministically — no LLM calls made
        )
    
    def run(
        self,
        analysis: PlannerAnalysis,
        manual_tests: list[ManualTestCase],
        api_tests: list[AutomationTestCase],
        ui_tests: list[AutomationTestCase],
        review: ReviewResult
    ) -> str:
        """
        Format all test cases into markdown documentation.
        
        Args:
            analysis: Planner's analysis
            manual_tests: Generated manual test cases
            api_tests: Generated API automation tests
            ui_tests: Generated UI automation tests
            review: Review results
            
        Returns:
            Formatted markdown string
        """
        console.print(f"\n[bold magenta]{'='*50}[/bold magenta]")
        console.print(f"[bold magenta]FORMATTER AGENT[/bold magenta]")
        console.print(f"[bold magenta]{'='*50}[/bold magenta]")
        
        # For formatting, we can do this deterministically without LLM
        # to save tokens and ensure consistent output
        markdown = self._format_markdown(
            analysis, manual_tests, api_tests, ui_tests, review
        )
        
        console.print(f"\n[green]✓ Documentation Generated[/green]")
        console.print(f"  Output Length: [bold]{len(markdown)} characters[/bold]")
        
        return markdown
    
    def _format_markdown(
        self,
        analysis: PlannerAnalysis,
        manual_tests: list[ManualTestCase],
        api_tests: list[AutomationTestCase],
        ui_tests: list[AutomationTestCase],
        review: ReviewResult
    ) -> str:
        """Generate the markdown documentation."""
        sections = []
        
        # Header
        sections.append(self._format_header(analysis, review))
        
        # Summary
        sections.append(self._format_summary(manual_tests, api_tests, ui_tests, review))
        
        # Manual Test Cases
        if manual_tests:
            sections.append(self.format_manual_section(manual_tests))

        # API Automation
        if api_tests:
            sections.append(self.format_api_section(api_tests))

        # UI Automation
        if ui_tests:
            sections.append(self.format_ui_section(ui_tests))
        
        # Coverage Report
        sections.append(self._format_coverage_section(review))
        
        # Notes
        sections.append(self._format_notes_section(review))
        
        return "\n\n".join(sections)
    
    def _format_header(self, analysis: PlannerAnalysis, review: ReviewResult) -> str:
        """Format document header."""
        return f"""# Test Cases: {analysis.feature_name}

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
**Quality Score:** {review.final_score}%  
**Domain:** {analysis.domain}

---"""
    
    def _format_summary(
        self,
        manual_tests: list[ManualTestCase],
        api_tests: list[AutomationTestCase],
        ui_tests: list[AutomationTestCase],
        review: ReviewResult
    ) -> str:
        """Format summary section."""
        total = len(manual_tests) + len(api_tests) + len(ui_tests)
        
        # Build coverage checkmarks
        scenarios = review.coverage.by_scenario
        coverage_items = []
        for scenario, count in scenarios.items():
            check = "✓" if count > 0 else "✗"
            coverage_items.append(f"{scenario.replace('_', ' ').title()} {check}")
        
        coverage_str = " | ".join(coverage_items)
        
        return f"""## Summary

| Metric | Count |
|--------|-------|
| **Total Test Cases** | {total} |
| Manual Test Cases | {len(manual_tests)} |
| API Automation | {len(api_tests)} |
| UI Automation | {len(ui_tests)} |

**Coverage:** {coverage_str}"""
    
    def format_manual_section(self, tests: list[ManualTestCase]) -> str:
        """Format manual test cases section."""
        lines = ["## 1. Manual Test Cases", ""]

        for test in tests:
            lines.append(f"### {test.test_case_id}: {test.title}")
            lines.append("")
            lines.append(f"**Priority:** {test.priority.value.title()} | **Type:** {test.scenario_type.value.replace('_', ' ').title()}")
            lines.append("")

            if test.description:
                lines.append(f"*{test.description}*")
                lines.append("")

            if test.preconditions:
                lines.append("**Preconditions:**")
                for pre in test.preconditions:
                    lines.append(f"- {pre}")
                lines.append("")

            lines.append("**Steps:**")
            lines.append("")
            lines.append("| Step | Action | Test Data | Expected Result |")
            lines.append("|------|--------|-----------|-----------------|")
            for step in test.steps:
                action = step.action.replace("|", "\\|")
                expected = step.expected_result.replace("|", "\\|")
                data = (step.test_data or "—").replace("|", "\\|")
                lines.append(f"| {step.step_number} | {action} | {data} | {expected} |")
            lines.append("")

            if test.postconditions:
                lines.append("**Postconditions:**")
                for post in test.postconditions:
                    lines.append(f"- {post}")
                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def format_api_section(self, tests: list[AutomationTestCase]) -> str:
        """Format API automation section."""
        lines = ["## 2. API Automation Test Scripts", ""]
        lines.append("**Framework:** Playwright (TypeScript)")
        lines.append("")

        # Group by file
        files: dict[str, list[AutomationTestCase]] = {}
        for test in tests:
            if test.file_name not in files:
                files[test.file_name] = []
            files[test.file_name].append(test)

        for file_name, file_tests in files.items():
            lines.append(f"### File: `tests/api/{file_name}`")
            lines.append("")

            combined_code = []
            for i, test in enumerate(file_tests):
                refs = f" — Covers: {', '.join(test.manual_test_refs)}" if test.manual_test_refs else ""
                combined_code.append(f"// {test.test_case_id}: {test.title}{refs}")
                # Keep imports only from the first code block to avoid duplicate import lines
                code = test.code if i == 0 else self._strip_imports(test.code)
                combined_code.append(code)
                combined_code.append("")

            lines.append("```typescript")
            lines.append("\n".join(combined_code))
            lines.append("```")
            lines.append("")

        lines.append("---")
        return "\n".join(lines)

    def format_ui_section(self, tests: list[AutomationTestCase]) -> str:
        """Format UI automation section."""
        lines = ["## 3. UI Automation Test Scripts", ""]
        lines.append("**Framework:** Playwright (TypeScript)")
        lines.append("")

        # Group by file
        files: dict[str, list[AutomationTestCase]] = {}
        for test in tests:
            if test.file_name not in files:
                files[test.file_name] = []
            files[test.file_name].append(test)

        for file_name, file_tests in files.items():
            lines.append(f"### File: `tests/ui/{file_name}`")
            lines.append("")

            combined_code = []
            for i, test in enumerate(file_tests):
                refs = f" — Covers: {', '.join(test.manual_test_refs)}" if test.manual_test_refs else ""
                combined_code.append(f"// {test.test_case_id}: {test.title}{refs}")
                # Keep imports only from the first code block to avoid duplicate import lines
                code = test.code if i == 0 else self._strip_imports(test.code)
                combined_code.append(code)
                combined_code.append("")

            lines.append("```typescript")
            lines.append("\n".join(combined_code))
            lines.append("```")
            lines.append("")

        lines.append("---")
        return "\n".join(lines)

    def _strip_imports(self, code: str) -> str:
        """Remove TypeScript import lines from a code block.

        Used when concatenating multiple test code blocks into one file so that
        import statements from subsequent blocks don't duplicate the first block's imports.
        """
        lines = code.split("\n")
        filtered = [line for line in lines if not line.strip().startswith("import ")]
        # Drop leading blank lines left after import removal
        while filtered and not filtered[0].strip():
            filtered.pop(0)
        return "\n".join(filtered)
    
    def _format_coverage_section(self, review: ReviewResult) -> str:
        """Format coverage report section."""
        lines = ["## Coverage Report", ""]
        
        # By Type
        lines.append("### By Test Type")
        lines.append("")
        lines.append("| Type | Count |")
        lines.append("|------|-------|")
        for test_type, count in review.coverage.by_type.items():
            lines.append(f"| {test_type.replace('_', ' ').title()} | {count} |")
        lines.append("")
        
        # By Scenario
        lines.append("### By Scenario Type")
        lines.append("")
        lines.append("| Scenario | Count |")
        lines.append("|----------|-------|")
        for scenario, count in review.coverage.by_scenario.items():
            lines.append(f"| {scenario.replace('_', ' ').title()} | {count} |")
        lines.append("")
        
        # By Priority
        lines.append("### By Priority")
        lines.append("")
        lines.append("| Priority | Count |")
        lines.append("|----------|-------|")
        for priority, count in review.coverage.by_priority.items():
            lines.append(f"| {priority.title()} | {count} |")
        lines.append("")
        
        return "\n".join(lines)
    
    def _format_notes_section(self, review: ReviewResult) -> str:
        """Format notes and recommendations section."""
        lines = ["## Notes & Recommendations", ""]
        
        if review.coverage.coverage_gaps:
            lines.append("### Coverage Gaps")
            for gap in review.coverage.coverage_gaps:
                lines.append(f"- ⚠️ {gap}")
            lines.append("")
        
        if review.coverage.suggestions:
            lines.append("### Suggestions")
            for suggestion in review.coverage.suggestions:
                lines.append(f"- 💡 {suggestion}")
            lines.append("")
        
        if review.issues_found:
            lines.append("### Issues Found")
            for issue in review.issues_found:
                lines.append(f"- 🔍 {issue}")
            lines.append("")
        
        lines.append("---")
        lines.append("")
        lines.append("*Generated by QA Test Case Generator - AI Powered*")
        
        return "\n".join(lines)
