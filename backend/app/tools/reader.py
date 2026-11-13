import logging
from typing import Any
from tenacity import before_sleep_log, retry, retry_if_exception, stop_after_attempt, wait_exponential

try:
    from ..schemas import SourceDoc
    from ..config import get_settings
except ImportError:
    try:
        from app.schemas import SourceDoc  # type: ignore
        from app.config import get_settings  # type: ignore
    except ImportError:
        from backend.app.schemas import SourceDoc  # type: ignore
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
async def _execute_extract(client: Any, urls: list[str]) -> dict[str, Any]:
    """Execute extract via Tavily client with retries on transient network errors."""
    return await client.extract(urls=urls)


async def read_pages(urls: list[str], max_chars: int = 6000) -> list[SourceDoc]:
    """Extract page text using Tavily, trimming to max_chars and skipping failed pages."""
    if not urls:
        return []

    api_key = get_settings().tavily_api_key
    if not api_key:
        logger.warning("TAVILY_API_KEY is not set in environment.")
        return []

    try:
        from tavily import AsyncTavilyClient

        client = AsyncTavilyClient(api_key=api_key)
        response = await _execute_extract(client=client, urls=urls)
        results = response.get("results", [])

        docs: list[SourceDoc] = []
        for item in results:
            content = item.get("raw_content") or item.get("content") or ""
            url = item.get("url") or ""
            if not content or not url:
                continue

            title = item.get("title") or url
            trimmed_content = content[:max_chars]

            docs.append(
                SourceDoc(
                    url=url,
                    title=title,
                    content=trimmed_content,
                )
            )
        return docs
    except Exception as exc:
        logger.warning("read_pages failed for urls %s: %s", urls, exc)
        return []
