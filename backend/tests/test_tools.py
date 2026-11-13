import pytest
from unittest.mock import AsyncMock, patch

from app.schemas import SourceDoc
from app.tools.reader import read_pages
from app.tools.search import search_web


@pytest.mark.asyncio
async def test_search_web_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "fake-test-key")

    mock_client = AsyncMock()
    mock_client.search.return_value = {
        "results": [
            {
                "title": "AI in Healthcare",
                "url": "https://example.com/ai-health",
                "content": "AI is transforming diagnostics.",
            },
            {
                "title": "Medical Imaging",
                "url": "https://example.com/imaging",
                "snippet": "Deep learning assists radiologists.",
            },
        ]
    }

    with patch("tavily.AsyncTavilyClient", return_value=mock_client):
        results = await search_web("AI healthcare", max_results=2)

    assert len(results) == 2
    assert results[0] == {
        "title": "AI in Healthcare",
        "url": "https://example.com/ai-health",
        "snippet": "AI is transforming diagnostics.",
    }
    assert results[1]["snippet"] == "Deep learning assists radiologists."


@pytest.mark.asyncio
async def test_search_web_error_never_crashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "fake-test-key")

    mock_client = AsyncMock()
    mock_client.search.side_effect = RuntimeError("Network error")

    with patch("tavily.AsyncTavilyClient", return_value=mock_client):
        results = await search_web("AI healthcare", max_results=2)

    assert results == []


@pytest.mark.asyncio
async def test_read_pages_success_and_trimming(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "fake-test-key")

    long_text = "A" * 8000
    mock_client = AsyncMock()
    mock_client.extract.return_value = {
        "results": [
            {
                "url": "https://example.com/page1",
                "title": "Page 1 Title",
                "raw_content": long_text,
            },
            {
                "url": "https://example.com/page2-empty",
                "title": "Empty Page",
                "raw_content": "",  # Should be skipped
            },
        ],
        "failed_results": [{"url": "https://example.com/failed", "error": "404 Not Found"}],
    }

    with patch("tavily.AsyncTavilyClient", return_value=mock_client):
        docs = await read_pages(["https://example.com/page1", "https://example.com/page2-empty"], max_chars=6000)

    assert len(docs) == 1
    assert isinstance(docs[0], SourceDoc)
    assert docs[0].url == "https://example.com/page1"
    assert docs[0].title == "Page 1 Title"
    assert len(docs[0].content) == 6000


@pytest.mark.asyncio
async def test_read_pages_error_never_crashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "fake-test-key")

    mock_client = AsyncMock()
    mock_client.extract.side_effect = Exception("Service unavailable")

    with patch("tavily.AsyncTavilyClient", return_value=mock_client):
        docs = await read_pages(["https://example.com/bad"])

    assert docs == []
