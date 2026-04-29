"""
Planner Agent - Analyzes requirements and creates a testing plan.
First agent in the pipeline.
"""

from typing import Optional
from .base_agent import BaseAgent
from .prompts import PLANNER_SYSTEM_PROMPT
from core.models import RequirementInput, PlannerAnalysis, ReviewResult
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
    
    def refine(
        self,
        requirement: RequirementInput,
        previous_analysis: PlannerAnalysis,
        review: ReviewResult,
        rag_context: Optional[str] = None,
    ) -> PlannerAnalysis:
        """
        Re-analyze the requirement incorporating review feedback to produce
        a refined analysis that addresses coverage gaps and quality issues.
        """
        console.print(f"\n[bold blue]{'='*50}[/bold blue]")
        console.print(f"[bold blue]PLANNER AGENT — Refinement Pass[/bold blue]")
        console.print(f"[bold blue]{'='*50}[/bold blue]")

        user_message = self._build_refinement_message(requirement, previous_analysis, review)
        full_message = self._build_context(user_message, rag_context=rag_context)

        try:
            result = self._generate_json(full_message, temperature=0.3)
            analysis = PlannerAnalysis(**result)
            self._log_analysis(analysis)
            return analysis
        except Exception as e:
            console.print(f"[red]Error in Planner Agent (refinement): {e}[/red]")
            raise

    def _build_refinement_message(
        self,
        requirement: RequirementInput,
        previous_analysis: PlannerAnalysis,
        review: ReviewResult,
    ) -> str:
        """Build the refinement request message from review feedback."""
        gaps = "\n".join(f"  - {g}" for g in review.coverage.coverage_gaps) or "  None identified"
        issues = "\n".join(f"  - {i}" for i in review.issues_found) or "  None identified"
        suggestions = "\n".join(f"  - {s}" for s in review.coverage.suggestions) or "  None identified"

        return f"""## REFINEMENT REQUEST
A previous generation pass produced test cases that scored {review.final_score:.1f}%.
Produce a REFINED analysis that addresses all the feedback below so the next generation pass achieves better coverage.

## ORIGINAL REQUIREMENT
**Type:** {requirement.input_type.value}
**Content:**
{requirement.content}

## PREVIOUS ANALYSIS
- **Feature:** {previous_analysis.feature_name}
- **Domain:** {previous_analysis.domain}
- **Intent:** {previous_analysis.intent}
- **Scope:** {previous_analysis.scope}
- **Endpoints:** {', '.join(previous_analysis.endpoints) if previous_analysis.endpoints else 'None'}
- **UI Elements:** {', '.join(previous_analysis.ui_elements) if previous_analysis.ui_elements else 'None'}
- **Test Focus Areas:** {', '.join(previous_analysis.test_focus_areas)}

## REVIEW FEEDBACK — address ALL of these in the refined analysis

### Coverage Gaps (missing scenarios):
{gaps}

### Issues Found in Generated Tests:
{issues}

### Suggestions for Improvement:
{suggestions}

## REFINEMENT INSTRUCTIONS
1. Expand test_focus_areas to explicitly cover every identified gap.
2. Add any missing endpoints or UI elements implied by the issues or suggestions.
3. Broaden scope if the gaps indicate untested paths.
4. Keep all correct parts of the previous analysis intact.
Return the same JSON structure as a normal analysis."""

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
