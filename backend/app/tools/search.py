import logging
from typing import Any
from tenacity import before_sleep_log, retry, retry_if_exception, stop_after_attempt, wait_exponential

try:
    from ..config import get_settings
except ImportError:
    try:
        from app.config import get_settings  # type: ignore
    except ImportError:
        from backend.app.config import get_settings  # type: ignore

logger = logging.getLogger(__name__)


def _is_retryable_exception(exc: BaseException) -> bool:
    name = exc.__class__.__name__.lower()
    msg = str(exc).lower()
    retryable = ("timeout", "rate", "429", "connection", "network", "unavailable", "503")
    return any(term in name or term in msg for term in retryable)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(_is_retryable_exception),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _execute_search(client: Any, query: str, max_results: int) -> dict[str, Any]:
    """Execute search via Tavily client with retries on transient network errors."""
    return await client.search(query=query, max_results=max_results)


async def search_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search the web using Tavily and return a list of dicts with title, url, and snippet."""
    api_key = get_settings().tavily_api_key
    if not api_key:
        logger.warning("TAVILY_API_KEY is not set in environment.")
        return []

    try:
        from tavily import AsyncTavilyClient

        client = AsyncTavilyClient(api_key=api_key)
        response = await _execute_search(client=client, query=query, max_results=max_results)
        raw_results = response.get("results", [])

        # Extract title, url, and snippet for each result
        results: list[dict[str, str]] = []
        for item in raw_results:
            results.append(
                {
                    "title": str(item.get("title", "")),
                    "url": str(item.get("url", "")),
                    "snippet": str(item.get("content", "") or item.get("snippet", "")),
                }
            )
        return results
    except Exception as exc:
        logger.warning("search_web failed for query '%s': %s", query, exc)
        return []
