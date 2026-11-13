import logging
from typing import Any
from langchain_core.language_models.chat_models import BaseChatModel
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

try:
    from backend.app.config import get_settings
except ImportError:
    from app.config import get_settings  # type: ignore

logger = logging.getLogger(__name__)


def _is_retryable_exception(exc: BaseException) -> bool:
    """Return True if exception is a transient network, timeout, or rate-limit error."""
    name = exc.__class__.__name__.lower()
    msg = str(exc).lower()
    retryable_terms = ["timeout", "rate", "429", "connection", "network", "resourceexhausted", "unavailable", "503"]
    return any(term in name or term in msg for term in retryable_terms)


def llm_retry_decorator() -> Any:
    """Tenacity retry decorator for async LLM calls with 3 attempts and exponential backoff."""
    return retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception(_is_retryable_exception),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )


def get_llm(temperature: float = 0.0) -> BaseChatModel:
    """Return configured ChatModel based strictly on LLM_PROVIDER ('gemini' or 'anthropic')."""
    settings = get_settings()
    provider = settings.llm_provider.lower().strip()

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required when LLM_PROVIDER is 'gemini'.")

        return ChatGoogleGenerativeAI(
            model=settings.llm_model,
            google_api_key=settings.google_api_key,
            temperature=temperature,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER is 'anthropic'.")

        return ChatAnthropic(
            model=settings.llm_model,
            api_key=settings.anthropic_api_key,
            temperature=temperature,
        )

    raise ValueError(
        f"Unsupported LLM provider '{settings.llm_provider}'. Expected 'gemini' or 'anthropic'."
    )
