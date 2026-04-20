"""
Generator Agent - Creates test cases based on planner analysis.
Second agent in the pipeline.
"""

from typing import Optional
from .base_agent import BaseAgent
from .prompts import GENERATOR_SYSTEM_PROMPT
from core.models import (
    RequirementInput,
    GenerationConfig,
    PlannerAnalysis,
    ManualTestCase,
    AutomationTestCase,
    TestCaseType,
)
from rich.console import Console

console = Console()


class GeneratorAgent(BaseAgent):
    """
    Generator Agent creates comprehensive test cases based on
    the planner's analysis and generation configuration.
    """
    
    def __init__(self):
        super().__init__(
            name="Generator Agent",
            system_prompt=GENERATOR_SYSTEM_PROMPT
        )
    
    def run(
        self,
        requirement: RequirementInput,
        analysis: PlannerAnalysis,
        config: GenerationConfig,
        rag_context: Optional[str] = None,
        tool_context: Optional[str] = None
    ) -> tuple[list[ManualTestCase], list[AutomationTestCase], list[AutomationTestCase]]:
        """
        Generate test cases based on analysis and configuration.
        
        Args:
            requirement: Original requirement input
            analysis: Planner's analysis
            config: Generation configuration
            rag_context: Optional RAG context
            tool_context: Optional tool context (Jira, API docs)
            
        Returns:
            Tuple of (manual_tests, api_tests, ui_tests)
        """
        console.print(f"\n[bold green]{'='*50}[/bold green]")
        console.print(f"[bold green]GENERATOR AGENT[/bold green]")
        console.print(f"[bold green]{'='*50}[/bold green]")
        
        # Build the user message
        user_message = self._build_user_message(requirement, analysis, config)
        
        # Add contexts
        full_message = self._build_context(
            user_message,
            rag_context=rag_context,
            tool_context=tool_context
        )
        
        # Generate test cases
        try:
            result = self._generate_json(full_message, temperature=0.5, max_tokens=8000)
            
            manual_tests = self._parse_manual_tests(result.get("manual_test_cases", []))
            api_tests = self._parse_automation_tests(
                result.get("api_test_cases", []),
                TestCaseType.API_AUTOMATION
            )
            ui_tests = self._parse_automation_tests(
                result.get("ui_test_cases", []),
                TestCaseType.UI_AUTOMATION
            )
            
            self._log_generation(manual_tests, api_tests, ui_tests)
            
            return manual_tests, api_tests, ui_tests
            
        except Exception as e:
            console.print(f"[red]Error in Generator Agent: {e}[/red]")
            raise
    
    def _build_user_message(
        self,
        requirement: RequirementInput,
        analysis: PlannerAnalysis,
        config: GenerationConfig
    ) -> str:
        """Build the user message with all context."""
        scenarios_str = ", ".join([s.value for s in config.scenarios])
        
        return f"""## ORIGINAL REQUIREMENT
{requirement.content}

## PLANNER ANALYSIS
- **Feature:** {analysis.feature_name}
- **Domain:** {analysis.domain}
- **Intent:** {analysis.intent}
- **Scope:** {analysis.scope}
- **Endpoints:** {', '.join(analysis.endpoints) if analysis.endpoints else 'N/A'}
- **UI Elements:** {', '.join(analysis.ui_elements) if analysis.ui_elements else 'N/A'}
- **Focus Areas:** {', '.join(analysis.test_focus_areas)}

## GENERATION CONFIG
- **Generate Manual Tests:** {config.include_manual}
- **Generate API Tests:** {config.include_api}
- **Generate UI Tests:** {config.include_ui}
- **Framework:** {config.framework}
- **Language:** {config.language}
- **Scenarios to Cover:** {scenarios_str}

Generate comprehensive test cases following the specified configuration.
Ensure all scenario types are covered where applicable.
Use Playwright with TypeScript for automation scripts."""
    
    def _parse_manual_tests(self, data: list[dict]) -> list[ManualTestCase]:
        """Parse manual test cases from JSON."""
        tests = []
        for item in data:
            try:
                test = ManualTestCase(**item)
                tests.append(test)
            except Exception as e:
                console.print(f"[yellow]Warning: Could not parse manual test: {e}[/yellow]")
        return tests
    
    def _parse_automation_tests(
        self,
        data: list[dict],
        test_type: TestCaseType
    ) -> list[AutomationTestCase]:
        """Parse automation test cases from JSON."""
        tests = []
        for item in data:
            try:
                item["test_type"] = test_type
                test = AutomationTestCase(**item)
                tests.append(test)
            except Exception as e:
                console.print(f"[yellow]Warning: Could not parse automation test: {e}[/yellow]")
        return tests
    
    def _log_generation(
        self,
        manual_tests: list[ManualTestCase],
        api_tests: list[AutomationTestCase],
        ui_tests: list[AutomationTestCase]
    ) -> None:
        """Log generation results."""
        console.print(f"\n[green]✓ Test Cases Generated[/green]")
        console.print(f"  Manual Tests: [bold]{len(manual_tests)}[/bold]")
        console.print(f"  API Automation: [bold]{len(api_tests)}[/bold]")
        console.print(f"  UI Automation: [bold]{len(ui_tests)}[/bold]")
        console.print(f"  [bold]Total: {len(manual_tests) + len(api_tests) + len(ui_tests)}[/bold]")
