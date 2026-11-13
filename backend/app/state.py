import operator
from typing import Annotated, Any, TypedDict

try:
    from backend.app.schemas import (
        ClaimVerdict,
        GapCheck,
        Note,
        ReportDraft,
        ResearchPlan,
        SourceDoc,
        SubQuestion,
    )
except ImportError:
    from app.schemas import (  # type: ignore
        ClaimVerdict,
        GapCheck,
        Note,
        ReportDraft,
        ResearchPlan,
        SourceDoc,
        SubQuestion,
    )


class ResearchState(TypedDict, total=False):
    run_id: str  # Unique identifier for the research execution run
    question: str  # Original user research question
    plan: ResearchPlan | None  # Structured plan containing sub-questions
    pending_sub_questions: list[SubQuestion]  # Sub-questions currently awaiting parallel worker execution
    notes: Annotated[list[Note], operator.add]  # Raw extracted evidence notes, merged by appending
    sources: Annotated[list[SourceDoc], operator.add]  # Full-text fetched source pages, merged by appending
    round_number: int  # Current research round counter (starts at 0, max 2 extra rounds)
    search_count: Annotated[int, operator.add]  # Cumulative count of web search calls performed
    source_index: dict[int, dict[str, str]]  # Deduplicated numbered source mapping {number: {url, title}}
    numbered_notes: list[dict[str, Any]]  # Deduplicated notes with assigned source citation numbers
    gaps: GapCheck | None  # Result of the latest gap analysis pass
    report: ReportDraft | None  # Grounded final draft report with sections and claim citations
    verdicts: list[ClaimVerdict]  # Verification verdicts for each claim tested against cited snippets
    removed_claims: list[str]  # Claims removed during verification due to lack of snippet support
    events: Annotated[list[dict[str, Any]], operator.add]  # Live stream events {type, message, data}, merged by appending
    usage: dict[str, Any]  # Token usage, search counts, and estimated cost breakdown
    stop_reason: str | None  # Explanation for why the research stopped (e.g. 'enough evidence', 'max rounds')
    error: str | None  # Fatal error description if the run fails
