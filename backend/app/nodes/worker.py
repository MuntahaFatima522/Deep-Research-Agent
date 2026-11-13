import logging
from typing import Any
from pydantic import BaseModel, Field

from backend.app.llm import get_llm, llm_retry_decorator
from backend.app.schemas import Note, SourceDoc, SubQuestion
from backend.app.tools.reader import read_pages
from backend.app.tools.search import search_web

logger = logging.getLogger(__name__)

QUERY_GENERATION_PROMPT = """You are an expert research investigator.
Given a research sub-question, generate exactly 2 distinct, focused search queries.
Sub-Question: {question}
Why It Matters: {why_it_matters}

Generate 2 targeted web search queries that will find relevant, factual evidence."""

NOTE_EXTRACTION_PROMPT = """You are an evidence extraction assistant.
Extract up to 5 short factual notes from the provided webpage texts for the given sub-question.
CRITICAL RULES:
1. Use ONLY the provided page text. NEVER use your own outside knowledge.
2. One distinct fact per note.
3. Every note MUST include the exact source_url, source_title, and a direct verbatim snippet copied directly from the page text.
4. If the content does not contain relevant facts, return an empty list of notes.

Sub-Question: {question}

Webpage Documents:
{documents_text}"""


class WorkerQueries(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=2, description="1 to 2 focused search queries")


class ExtractedNotes(BaseModel):
    notes: list[Note] = Field(default_factory=list, max_length=5, description="Up to 5 factual notes from text")


@llm_retry_decorator()
async def _generate_queries(llm: Any, sub_question: SubQuestion) -> list[str]:
    """Generate 2 focused search queries using structured LLM output."""
    prompt = QUERY_GENERATION_PROMPT.format(
        question=sub_question.question,
        why_it_matters=sub_question.why_it_matters,
    )
    structured_llm = llm.with_structured_output(WorkerQueries)
    result = await structured_llm.ainvoke(prompt)
    return getattr(result, "queries", [sub_question.question])[:2]


@llm_retry_decorator()
async def _extract_notes_from_docs(llm: Any, sub_question: SubQuestion, docs: list[SourceDoc]) -> list[Note]:
    """Extract factual notes with exact snippets from retrieved documents using structured LLM output."""
    if not docs:
        return []

    docs_parts: list[str] = []
    for doc in docs:
        docs_parts.append(
            f"--- Document Title: {doc.title}\nURL: {doc.url}\nContent:\n{doc.content[:3000]}\n"
        )
    documents_text = "\n\n".join(docs_parts)

    prompt = NOTE_EXTRACTION_PROMPT.format(
        question=sub_question.question,
        documents_text=documents_text,
    )
    structured_llm = llm.with_structured_output(ExtractedNotes)
    result = await structured_llm.ainvoke(prompt)
    raw_notes = getattr(result, "notes", [])

    # Ensure every note preserves the correct sub_question_id
    validated_notes: list[Note] = []
    for n in raw_notes[:5]:
        validated_notes.append(
            Note(
                sub_question_id=sub_question.id,
                fact=n.fact,
                source_url=n.source_url,
                source_title=n.source_title,
                snippet=n.snippet,
            )
        )
    return validated_notes


async def run_worker(
    sub_question: SubQuestion,
    *,
    searches_remaining: int | None = None,
    max_searches_per_worker: int = 4,
) -> dict[str, Any]:
    """Execute research worker for a single sub-question: search, read pages, and extract notes."""
    search_count = 0
    worker_search_cap = min(max_searches_per_worker, searches_remaining if searches_remaining is not None else max_searches_per_worker)
    try:
        llm = get_llm(temperature=0.0)

        # 1. Generate 2 focused search queries
        queries = await _generate_queries(llm, sub_question)
        if not queries:
            queries = [sub_question.question]

        # 2. Search each query (respect per-worker and global budget)
        seen_urls: set[str] = set()
        unique_urls: list[str] = []
        for q in queries[:2]:
            if search_count >= worker_search_cap or worker_search_cap <= 0:
                break
            search_count += 1
            results = await search_web(q, max_results=3)
            for item in results:
                url = item.get("url")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_urls.append(url)

        # 3. Keep top 4 unique URLs
        target_urls = unique_urls[:4]
        if not target_urls:
            return {"notes": [], "sources": [], "search_count": search_count}

        # 4. Read pages
        sources = await read_pages(target_urls, max_chars=4000)
        if not sources:
            return {"notes": [], "sources": [], "search_count": search_count}

        # 5. Extract up to 5 notes
        notes = await _extract_notes_from_docs(llm, sub_question, sources)

        return {
            "notes": notes,
            "sources": sources,
            "search_count": search_count,
        }
    except Exception as exc:
        logger.warning("Worker failed for sub_question %s: %s", sub_question.id, exc)
        return {
            "notes": [],
            "sources": [],
            "search_count": search_count,
        }
