from collections.abc import Mapping
import logging
from typing import Any

from backend.app.config import Settings
from backend.app.llm import get_llm, llm_retry_decorator
from backend.app.schemas import GapCheck, ResearchPlan

logger = logging.getLogger(__name__)

GAP_CHECK_PROMPT = """You are a strict, demanding research director.
Evaluate the current gathered evidence against the research question and plan.

Determine:
1. is_enough: True ONLY if all core sub-questions are answered with strong, verifiable evidence.
2. missing: List the specific missing points or unresolved questions.
3. new_sub_questions: If not enough, propose AT MOST 2 new, highly specific sub-questions with IDs 'gap_1', 'gap_2'. If enough, leave empty.

Research Question:
{question}

Research Goal:
{goal}

Collected Evidence Notes:
{notes_summary}"""


@llm_retry_decorator()
async def check_gaps(question: str, plan: ResearchPlan, numbered_notes: list[dict[str, Any]]) -> GapCheck:
    """Evaluate gathered evidence, identifying knowledge gaps and generating up to 2 extra sub-questions."""
    llm = get_llm(temperature=0.0)

    # Format evidence summary
    notes_lines = [f"- [Note {n['note_number']}] {n['fact']}" for n in numbered_notes]
    notes_summary = "\n".join(notes_lines) if notes_lines else "No evidence collected yet."

    prompt = GAP_CHECK_PROMPT.format(
        question=question,
        goal=plan.goal,
        notes_summary=notes_summary,
    )

    structured_llm = llm.with_structured_output(GapCheck)
    raw_result = await structured_llm.ainvoke(prompt)
    gap_result = raw_result if isinstance(raw_result, GapCheck) else GapCheck.model_validate(raw_result)

    # Enforce maximum of 2 new sub-questions
    gap_result.new_sub_questions = gap_result.new_sub_questions[:2]
    return gap_result


def should_continue(state: Mapping[str, Any], settings: Settings) -> tuple[bool, str]:
    """Evaluate termination conditions (evidence sufficiency, round limits, search limits)."""
    gaps: GapCheck | None = state.get("gaps")
    if gaps is not None and gaps.is_enough:
        return False, "Stopped: enough evidence"

    round_number = state.get("round_number", 0)
    if round_number >= settings.max_rounds:
        return False, f"Stopped: reached maximum rounds ({settings.max_rounds})"

    search_count = state.get("search_count", 0)
    if search_count >= settings.max_searches:
        return False, f"Stopped: reached maximum searches ({settings.max_searches})"

    pending = state.get("pending_sub_questions", [])
    if not pending:
        return False, "Stopped: no pending sub-questions"

    return True, "Continuing to next research round"
