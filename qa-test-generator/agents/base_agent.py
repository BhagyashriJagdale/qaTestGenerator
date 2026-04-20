"""
Base Agent class that all agents inherit from.
Provides common functionality for LLM interaction.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
from core.llm_client import get_llm_client, BaseLLMClient
from rich.console import Console

console = Console()


class BaseAgent(ABC):
    """Abstract base class for all agents."""
    
    def __init__(self, name: str, system_prompt: str):
        """
        Initialize the agent.
        
        Args:
            name: Human-readable agent name
            system_prompt: The system prompt defining agent behavior
        """
        self.name = name
        self.system_prompt = system_prompt
        self.client: BaseLLMClient = get_llm_client()
    
    @abstractmethod
    def run(self, *args, **kwargs) -> Any:
        """
        Execute the agent's main task.
        Must be implemented by subclasses.
        """
        pass
    
    def _generate(
        self,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """Generate a text response."""
        console.print(f"[cyan]🤖 {self.name}[/cyan] is thinking...")
        return self.client.generate(
            system_prompt=self.system_prompt,
            user_message=user_message,
            temperature=temperature,
            max_tokens=max_tokens
        )
    
    def _generate_json(
        self,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None
    ) -> dict:
        """Generate a JSON response."""
        console.print(f"[cyan]🤖 {self.name}[/cyan] is analyzing...")
        return self.client.generate_json(
            system_prompt=self.system_prompt,
            user_message=user_message,
            temperature=temperature,
            max_tokens=max_tokens
        )
    
    def _build_context(
        self,
        base_message: str,
        rag_context: Optional[str] = None,
        tool_context: Optional[str] = None
    ) -> str:
        """
        Build the full context message with optional RAG and tool data.
        
        Args:
            base_message: The main user message
            rag_context: Retrieved context from RAG
            tool_context: Context from tool calls (Jira, API docs, etc.)
            
        Returns:
            Complete context string
        """
        parts = [base_message]
        
        if rag_context:
            parts.append(f"\n\n## RELEVANT CONTEXT FROM KNOWLEDGE BASE:\n{rag_context}")
        
        if tool_context:
            parts.append(f"\n\n## ADDITIONAL CONTEXT FROM TOOLS:\n{tool_context}")
        
        return "\n".join(parts)
