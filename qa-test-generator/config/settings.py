"""
Configuration management using Pydantic Settings.
Loads from environment variables and .env file.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Provider selection
    llm_provider: str = Field(default="openai", description="LLM provider: 'openai', 'anthropic', or 'huggingface'")

    # OpenAI API
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API Key")
    model_name: str = Field(default="gpt-4o", description="Model to use")
    max_tokens: int = Field(default=4096, description="Max tokens for responses")

    # Anthropic API (optional, used when llm_provider=anthropic)
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API Key")
    openai_base_url: Optional[str] = Field(default=None, description="OpenAI API base URL (for Groq etc)")

    # DeepSeek API (optional, used when llm_provider=deepseek)
    deepseek_api_key: Optional[str] = Field(default=None, description="DeepSeek API Key")
    
    # RAG Configuration
    chroma_persist_dir: str = Field(default="./data/chroma", description="ChromaDB persistence directory")
    embedding_model: str = Field(default="all-MiniLM-L6-v2", description="Sentence transformer model")
    
    # GitHub Integration (Optional — increases rate limit from 60 to 5000 req/hr)
    github_token: Optional[str] = Field(default=None, description="GitHub personal access token")

    # Jira Integration (Optional)
    jira_url: Optional[str] = Field(default=None, description="Jira instance URL")
    jira_email: Optional[str] = Field(default=None, description="Jira account email")
    jira_api_token: Optional[str] = Field(default=None, description="Jira API token")
    
    # API Configuration
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    debug: bool = Field(default=False, description="Debug mode")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
