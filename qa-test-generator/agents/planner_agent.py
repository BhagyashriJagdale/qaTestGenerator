"""
Planner Agent - Analyzes requirements and creates a testing plan.
First agent in the pipeline.
"""

from typing import Optional
from .base_agent import BaseAgent
from .prompts import PLANNER_SYSTEM_PROMPT
from core.models import RequirementInput, PlannerAnalysis
from rich.console import Console

console = Console()


class PlannerAgent(BaseAgent):
    """
    Planner Agent analyzes incoming requirements and produces
    a structured analysis for downstream agents.
    """
    
    def __init__(self):
        super().__init__(
            name="Planner Agent",
            system_prompt=PLANNER_SYSTEM_PROMPT
        )
    
    def run(
        self,
        requirement: RequirementInput,
        rag_context: Optional[str] = None
    ) -> PlannerAnalysis:
        """
        Analyze the requirement and produce a testing plan.
        
        Args:
            requirement: The input requirement to analyze
            rag_context: Optional context from RAG system
            
        Returns:
            PlannerAnalysis with structured analysis
        """
        console.print(f"\n[bold blue]{'='*50}[/bold blue]")
        console.print(f"[bold blue]PLANNER AGENT[/bold blue]")
        console.print(f"[bold blue]{'='*50}[/bold blue]")
        
        # Build the user message
        user_message = self._build_user_message(requirement)
        
        # Add RAG context if available
        full_message = self._build_context(user_message, rag_context=rag_context)
        
        # Generate analysis
        try:
            result = self._generate_json(full_message, temperature=0.3)
            analysis = PlannerAnalysis(**result)
            
            self._log_analysis(analysis)
            return analysis
            
        except Exception as e:
            console.print(f"[red]Error in Planner Agent: {e}[/red]")
            raise
    
    def _build_user_message(self, requirement: RequirementInput) -> str:
        """Build the user message from requirement input."""
        parts = [
            f"## REQUIREMENT INPUT",
            f"**Type:** {requirement.input_type.value}",
            f"**Content:**\n{requirement.content}"
        ]
        
        if requirement.project_context:
            parts.append(f"\n**Project Context:** {requirement.project_context}")
        
        if requirement.tech_stack:
            parts.append(f"\n**Tech Stack:** {requirement.tech_stack}")
        
        if requirement.additional_context:
            parts.append(f"\n**Additional Context:** {requirement.additional_context}")
        
        parts.append("\n\nAnalyze this requirement and provide your structured analysis.")
        
        return "\n".join(parts)
    
    def _log_analysis(self, analysis: PlannerAnalysis) -> None:
        """Log the analysis results."""
        console.print(f"\n[green]✓ Analysis Complete[/green]")
        console.print(f"  Feature: [bold]{analysis.feature_name}[/bold]")
        console.print(f"  Domain: {analysis.domain}")
        console.print(f"  Intent: {analysis.intent}")
        console.print(f"  Scope: {analysis.scope}")
        
        if analysis.endpoints:
            console.print(f"  Endpoints: {', '.join(analysis.endpoints)}")
        
        if analysis.test_focus_areas:
            console.print(f"  Focus Areas: {', '.join(analysis.test_focus_areas)}")
