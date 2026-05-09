"""
Planner Agent - Analyzes requirements and creates a testing plan.
First agent in the pipeline.
"""

import re
from typing import Optional
from .base_agent import BaseAgent
from .prompts import PLANNER_SYSTEM_PROMPT
from core.models import RequirementInput, PlannerAnalysis
from rich.console import Console

console = Console()

MIN_REQUIREMENT_LENGTH = 10
MAX_REQUIREMENT_LENGTH = 50_000


class InvalidRequirementError(ValueError):
    """Raised when the requirement input is not a valid software requirement."""
    pass


class IncompleteRequirementError(ValueError):
    """Raised when the requirement is valid but lacks enough detail to generate tests."""

    def __init__(self, issues: list[str], missing: list[str], suggestion: str = ""):
        self.issues = issues
        self.missing = missing
        self.suggestion = suggestion
        lines = ["Requirement is incomplete. Please provide more detail.\n"]
        lines.append("What is unclear:")
        lines.extend(f"  • {i}" for i in issues)
        if missing:
            lines.append("\nInformation needed:")
            lines.extend(f"  • {q}" for q in missing)
        if suggestion:
            lines.append(f"\nExample of a complete requirement:\n  \"{suggestion}\"")
        super().__init__("\n".join(lines))


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
        rag_context: Optional[str] = None,
        skip_validation: bool = False,
    ) -> PlannerAnalysis:
        """
        Analyze the requirement and produce a testing plan.

        Args:
            requirement: The input requirement to analyze
            rag_context: Optional context from RAG system

        Returns:
            PlannerAnalysis with structured analysis

        Raises:
            InvalidRequirementError: If the input is not a valid software requirement
        """
        console.print(f"\n[bold blue]{'='*50}[/bold blue]")
        console.print(f"[bold blue]PLANNER AGENT[/bold blue]")
        console.print(f"[bold blue]{'='*50}[/bold blue]")

        # Step 1: Pre-LLM deterministic validation (skipped in refinement passes)
        if not skip_validation:
            self._validate_input(requirement)

        # Step 2: Build message and call LLM
        user_message = self._build_user_message(requirement)
        full_message = self._build_context(user_message, rag_context=rag_context)

        try:
            result = self._generate_json(full_message, temperature=0.3)
        except Exception as e:
            console.print(f"[red]Error in Planner Agent: {e}[/red]")
            raise

        # Step 3: Check LLM-level validation flag
        if not result.get("is_valid", True):
            reason = result.get("validation_error", "Input is not a valid software requirement.")
            console.print(f"[red]✗ Invalid requirement: {reason}[/red]")
            raise InvalidRequirementError(reason)

        # Step 4: Check LLM-level completeness flag
        if not result.get("is_complete", True):
            issues = result.get("completeness_issues", ["Requirement lacks sufficient detail."])
            missing = result.get("missing_information", [])
            suggestion = result.get("suggestion", "")
            console.print(f"[yellow]✗ Incomplete requirement — {len(issues)} issue(s) found[/yellow]")
            for issue in issues:
                console.print(f"  [yellow]• {issue}[/yellow]")
            raise IncompleteRequirementError(issues, missing, suggestion)

        # Step 5: Parse into PlannerAnalysis (drop the extra validation fields the LLM added)
        result.pop("is_valid", None)
        result.pop("is_complete", None)
        result.pop("validation_error", None)
        result.pop("completeness_issues", None)
        result.pop("missing_information", None)
        result.pop("suggestion", None)

        try:
            analysis = PlannerAnalysis(**result)
        except Exception as e:
            console.print(f"[red]Error parsing planner output: {e}[/red]")
            raise

        self._log_analysis(analysis)
        return analysis

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_input(self, requirement: RequirementInput) -> None:
        """
        Run fast deterministic checks before hitting the LLM.
        Raises InvalidRequirementError with a clear user-facing message.
        """
        text = requirement.content.strip()

        if not text:
            raise InvalidRequirementError(
                "Requirement is empty. Please provide a description of the software feature you want to test."
            )

        if len(text) < MIN_REQUIREMENT_LENGTH:
            raise InvalidRequirementError(
                f"Requirement is too short ({len(text)} characters). "
                "Please provide a meaningful description of at least 10 characters."
            )

        if len(text) > MAX_REQUIREMENT_LENGTH:
            raise InvalidRequirementError(
                f"Requirement is too long ({len(text)} characters). "
                f"Please keep it under {MAX_REQUIREMENT_LENGTH:,} characters."
            )

        # Detect gibberish: high ratio of non-alphanumeric/non-space characters
        non_word_ratio = len(re.findall(r"[^a-zA-Z0-9\s.,;:()\-'\"!?/]", text)) / len(text)
        if non_word_ratio > 0.4:
            raise InvalidRequirementError(
                "Input appears to contain mostly special characters or symbols. "
                "Please provide a plain-text description of a software feature."
            )

        # Detect single repeated character spam (e.g. "aaaaaaa", "!!!!!!!")
        if re.fullmatch(r"(.)\1{4,}", text.replace(" ", "")):
            raise InvalidRequirementError(
                "Input looks like repeated characters and is not a valid requirement."
            )

        # Detect numeric-only input
        if re.fullmatch(r"[\d\s.,]+", text):
            raise InvalidRequirementError(
                "Input contains only numbers. Please describe the software feature you want tested."
            )

        # Detect obviously incomplete: single word with no verb or outcome implied
        words = text.split()
        if len(words) == 1:
            raise IncompleteRequirementError(
                issues=["A single word is not enough to generate meaningful test cases."],
                missing=[
                    "Who is the actor? (e.g. 'user', 'admin', 'guest')",
                    "What action are they performing?",
                    "What is the expected outcome?",
                ],
                suggestion=f"User can {text.lower()} using valid credentials and is redirected to the dashboard on success."
            )

        # Detect vague action-only patterns: "fix X", "add X", "update X", "test X"
        vague_patterns = re.compile(
            r"^(fix|add|update|test|change|remove|delete|create|make|do|check|handle|implement)\s+\w+$",
            re.IGNORECASE,
        )
        if vague_patterns.match(text):
            raise IncompleteRequirementError(
                issues=["Requirement is a vague action without behaviour, inputs, or expected outcomes."],
                missing=[
                    "What specific behaviour should be implemented or fixed?",
                    "What inputs does the feature accept?",
                    "What is the expected outcome for success and failure cases?",
                ],
                suggestion=f"As a user, I want to {text.lower()} so that [describe the business outcome]."
            )

        console.print(f"[green]✓ Input validation passed[/green] ({len(text)} chars)")
    
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
