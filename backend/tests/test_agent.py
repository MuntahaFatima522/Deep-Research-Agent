"""Integration tests for the LangGraph research workflow (no live API calls)."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.app.graph import build_graph
from backend.app.schemas import (
    Claim,
    ClaimVerdict,
    GapCheck,
    Note,
    ReportDraft,
    ReportSection,
    ResearchPlan,
    SourceDoc,
    SubQuestion,
)


def _sample_plan() -> ResearchPlan:
    return ResearchPlan(
        goal="Summarize AI impact on healthcare diagnostics.",
        sub_questions=[
            SubQuestion(id="q1", question="How does AI help medical imaging?", why_it_matters="Core use case."),
            SubQuestion(id="q2", question="What are FDA-approved AI diagnostic tools?", why_it_matters="Regulation."),
            SubQuestion(id="q3", question="What accuracy gains are reported?", why_it_matters="Outcomes."),
        ],
    )


def _note(sq_id: str, url: str, title: str, fact: str, snippet: str) -> Note:
    return Note(
        sub_question_id=sq_id,
        fact=fact,
        source_url=url,
        source_title=title,
        snippet=snippet,
    )


@pytest.mark.asyncio
async def test_graph_end_to_end_with_three_sources() -> None:
    plan = _sample_plan()

    async def fake_worker(sub_question: SubQuestion, **kwargs: object) -> dict:
        idx = sub_question.id
        url = f"https://example.com/{idx}"
        return {
            "notes": [
                _note(
                    idx,
                    url,
                    f"Source {idx}",
                    f"Fact from {idx}",
                    f"Snippet text for {idx}",
                )
            ],
            "sources": [SourceDoc(url=url, title=f"Source {idx}", content=f"Snippet text for {idx}")],
            "search_count": 1,
        }

    report = ReportDraft(
        title="AI Diagnostics",
        summary="AI helps clinicians read scans faster and more consistently.",
        sections=[
            ReportSection(
                heading="Imaging",
                claims=[Claim(text="Fact from q1", note_numbers=[1])],
            )
        ],
    )

    with (
        patch("backend.app.graph.make_plan", AsyncMock(return_value=plan)),
        patch("backend.app.graph.run_worker", side_effect=fake_worker),
        patch(
            "backend.app.graph.check_gaps",
            AsyncMock(return_value=GapCheck(is_enough=True, missing=[], new_sub_questions=[])),
        ),
        patch("backend.app.graph.write_report", AsyncMock(return_value=report)),
        patch(
            "backend.app.graph.verify_claims",
            AsyncMock(
                return_value=[ClaimVerdict(claim_text="Fact from q1", supported=True, reason="Matches snippet")]
            ),
        ),
    ):
        graph = build_graph()
        final = await graph.ainvoke(
            {
                "run_id": "test_run",
                "question": "What is the impact of AI on healthcare diagnostics?",
                "round_number": 0,
                "search_count": 0,
                "notes": [],
                "sources": [],
                "events": [],
            },
            config={"configurable": {"thread_id": "test_run"}},
        )

    assert final.get("error") is None
    assert len(final.get("source_index", {})) >= 3
    assert final.get("report") is not None
    assert final["report"].title == "AI Diagnostics"


@pytest.mark.asyncio
async def test_one_failing_worker_does_not_stop_run() -> None:
    plan = _sample_plan()

    async def fake_worker(sub_question: SubQuestion, **kwargs: object) -> dict:
        if sub_question.id == "q2":
            return {"notes": [], "sources": [], "search_count": 0}
        url = f"https://example.com/{sub_question.id}"
        return {
            "notes": [_note(sub_question.id, url, "T", "Fact", "Snippet")],
            "sources": [SourceDoc(url=url, title="T", content="Snippet")],
            "search_count": 1,
        }

    report = ReportDraft(
        title="Partial",
        summary="Some evidence was collected despite one worker failure.",
        sections=[ReportSection(heading="S", claims=[Claim(text="Fact", note_numbers=[1])])],
    )

    with (
        patch("backend.app.graph.make_plan", AsyncMock(return_value=plan)),
        patch("backend.app.graph.run_worker", side_effect=fake_worker),
        patch(
            "backend.app.graph.check_gaps",
            AsyncMock(return_value=GapCheck(is_enough=True, missing=[], new_sub_questions=[])),
        ),
        patch("backend.app.graph.write_report", AsyncMock(return_value=report)),
        patch(
            "backend.app.graph.verify_claims",
            AsyncMock(return_value=[ClaimVerdict(claim_text="Fact", supported=True, reason="ok")]),
        ),
    ):
        graph = build_graph()
        final = await graph.ainvoke(
            {
                "run_id": "test_partial",
                "question": "What is the impact of AI on healthcare diagnostics?",
                "round_number": 0,
                "search_count": 0,
                "notes": [],
                "sources": [],
                "events": [],
            },
            config={"configurable": {"thread_id": "test_partial"}},
        )

    assert final.get("error") is None
    assert final.get("report") is not None
    event_types = [e["type"] for e in final.get("events", [])]
    assert "worker_failed" in event_types or "worker_finished" in event_types


@pytest.mark.asyncio
async def test_all_workers_failing_returns_error() -> None:
    plan = _sample_plan()

    async def empty_worker(sub_question: SubQuestion, **kwargs: object) -> dict:
        return {"notes": [], "sources": [], "search_count": 0}

    with (
        patch("backend.app.graph.make_plan", AsyncMock(return_value=plan)),
        patch("backend.app.graph.run_worker", side_effect=empty_worker),
        patch(
            "backend.app.graph.check_gaps",
            AsyncMock(return_value=GapCheck(is_enough=False, missing=["all"], new_sub_questions=[])),
        ),
    ):
        graph = build_graph()
        final = await graph.ainvoke(
            {
                "run_id": "test_fail",
                "question": "What is the impact of AI on healthcare diagnostics?",
                "round_number": 0,
                "search_count": 0,
                "notes": [],
                "sources": [],
                "events": [],
            },
            config={"configurable": {"thread_id": "test_fail"}},
        )

    assert final.get("error")
    assert final.get("report") is None
