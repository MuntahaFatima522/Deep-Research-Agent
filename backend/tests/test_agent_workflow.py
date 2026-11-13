import pytest
from unittest.mock import AsyncMock, patch

from backend.app.budget import Budget
from backend.app.config import Settings
from backend.app.nodes.evidence import organize_evidence
from backend.app.nodes.gaps import should_continue
from backend.app.nodes.verifier import apply_verdicts
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


def test_organize_evidence_deduping_and_indexing() -> None:
    sources = [
        SourceDoc(url="https://example.com/a", title="Doc A", content="Content A"),
        SourceDoc(url="https://example.com/b", title="Doc B", content="Content B"),
    ]
    notes = [
        Note(
            sub_question_id="q1",
            fact="AI improves image recognition accuracy",
            source_url="https://example.com/a",
            source_title="Doc A",
            snippet="image recognition accuracy is improved by AI",
        ),
        Note(
            sub_question_id="q1",
            fact="AI improves image recognition accuracy",  # Duplicate fact & URL
            source_url="https://example.com/a",
            source_title="Doc A",
            snippet="image recognition accuracy is improved by AI",
        ),
        Note(
            sub_question_id="q2",
            fact="Genomics pipelines use ML algorithms",
            source_url="https://example.com/b",
            source_title="Doc B",
            snippet="Genomics pipelines use ML algorithms for variant calling",
        ),
    ]

    result = organize_evidence(notes, sources)

    # Deduped to 2 unique notes
    assert len(result["numbered_notes"]) == 2
    # 2 unique sources numbered starting at 1
    assert 1 in result["source_index"]
    assert 2 in result["source_index"]
    assert result["source_index"][1]["url"] == "https://example.com/a"
    # Grouped by sub-question
    assert "q1" in result["grouped_notes"]
    assert "q2" in result["grouped_notes"]
    assert len(result["grouped_notes"]["q1"]) == 1


def test_should_continue_stop_reasons() -> None:
    settings = Settings(MAX_ROUNDS=2, MAX_SEARCHES=12)

    # 1. Stop when enough evidence
    state_enough = {
        "gaps": GapCheck(is_enough=True, missing=[], new_sub_questions=[]),
        "round_number": 0,
        "search_count": 2,
        "pending_sub_questions": [SubQuestion(id="q1", question="Q1?", why_it_matters="M1")],
    }
    cont, reason = should_continue(state_enough, settings)
    assert not cont
    assert "enough evidence" in reason

    # 2. Stop when max rounds reached
    state_max_rounds = {
        "gaps": GapCheck(is_enough=False, missing=["data"], new_sub_questions=[]),
        "round_number": 2,
        "search_count": 4,
        "pending_sub_questions": [SubQuestion(id="q1", question="Q1?", why_it_matters="M1")],
    }
    cont, reason = should_continue(state_max_rounds, settings)
    assert not cont
    assert "maximum rounds" in reason

    # 3. Stop when max searches reached
    state_max_searches = {
        "gaps": GapCheck(is_enough=False, missing=["data"], new_sub_questions=[]),
        "round_number": 1,
        "search_count": 12,
        "pending_sub_questions": [SubQuestion(id="q1", question="Q1?", why_it_matters="M1")],
    }
    cont, reason = should_continue(state_max_searches, settings)
    assert not cont
    assert "maximum searches" in reason

    # 4. Stop when no pending sub-questions
    state_no_pending = {
        "gaps": GapCheck(is_enough=False, missing=["data"], new_sub_questions=[]),
        "round_number": 1,
        "search_count": 4,
        "pending_sub_questions": [],
    }
    cont, reason = should_continue(state_no_pending, settings)
    assert not cont
    assert "no pending sub-questions" in reason

    # 5. Continue when limits not reached
    state_continue = {
        "gaps": GapCheck(is_enough=False, missing=["data"], new_sub_questions=[]),
        "round_number": 1,
        "search_count": 4,
        "pending_sub_questions": [SubQuestion(id="q2", question="Q2?", why_it_matters="M2")],
    }
    cont, reason = should_continue(state_continue, settings)
    assert cont


def test_budget_limits() -> None:
    budget = Budget(max_searches=5, max_rounds=2, max_searches_per_worker=2)

    assert budget.can_search("worker-1")
    budget.record_search("worker-1", 2)
    # worker-1 reached its limit
    assert not budget.can_search("worker-1")
    # worker-2 still can
    assert budget.can_search("worker-2")
    budget.record_search("worker-2", 3)
    # Total reached 5
    assert not budget.can_search("worker-3")
    summary = budget.summary()
    assert summary["total_searches"] == 5


def test_apply_verdicts_removes_unsupported_claims() -> None:
    claim1 = Claim(text="AI predicts sepsis 6 hours earlier", note_numbers=[1])
    claim2 = Claim(text="AI eliminates all clinical errors completely", note_numbers=[2])

    report = ReportDraft(
        title="Clinical AI",
        summary="Overview of diagnostics.",
        sections=[ReportSection(heading="Accuracy", claims=[claim1, claim2])],
    )

    verdicts = [
        ClaimVerdict(claim_text="AI predicts sepsis 6 hours earlier", supported=True, reason="Direct snippet match"),
        ClaimVerdict(claim_text="AI eliminates all clinical errors completely", supported=False, reason="Exaggeration"),
    ]

    cleaned_report, removed = apply_verdicts(report, verdicts)
    assert len(removed) == 1
    assert "AI eliminates all clinical errors completely" in removed
    assert len(cleaned_report.sections[0].claims) == 1
    assert cleaned_report.sections[0].claims[0].text == "AI predicts sepsis 6 hours earlier"
