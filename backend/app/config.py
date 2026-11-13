import os
from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Locate .env files in backend/ or repository root
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application configuration and environment settings."""

    # LLM Provider: 'gemini' or 'anthropic'
    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gemini-1.5-flash", alias="LLM_MODEL")

    # API Keys
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")

    # LangSmith Tracing
    langsmith_tracing: bool = Field(default=True, alias="LANGSMITH_TRACING")
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="deep-research-agent", alias="LANGSMITH_PROJECT")

    # Research Execution Limits
    max_searches: int = Field(default=12, alias="MAX_SEARCHES")
    max_rounds: int = Field(default=2, alias="MAX_ROUNDS")
    max_searches_per_worker: int = Field(default=4, alias="MAX_SEARCHES_PER_WORKER")
    run_timeout_seconds: int = Field(default=300, alias="RUN_TIMEOUT_SECONDS")

    # Environment & Database
    app_env: str = Field(default="dev", alias="APP_ENV")
    database_url: str = Field(default="", alias="DATABASE_URL")
    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")

    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", BASE_DIR.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


def _apply_langsmith_env(settings: Settings) -> None:
    """Configure LangSmith tracing via environment variables only."""
    if settings.langsmith_tracing:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    if settings.langsmith_api_key:
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)
    if settings.langsmith_project:
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    settings = Settings()
    _apply_langsmith_env(settings)
    return settings
