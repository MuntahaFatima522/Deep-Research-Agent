import logging
from typing import Any

from backend.app.llm import get_llm, llm_retry_decorator
from backend.app.schemas import ReportDraft

logger = logging.getLogger(__name__)

REPORT_SYNTHESIS_PROMPT = """You are a senior science and technology communicator.
Your task is to write a comprehensive research report in response to the user's research question.

CRITICAL INSTRUCTIONS:
1. Write for a beginner in clear, simple English.
2. Use ONLY the facts provided in the numbered notes below. NEVER invent facts or add outside knowledge.
3. Every factual statement must be captured as a Claim with the exact note numbers that support it (e.g. note_numbers=[1, 3]).
4. Report structure:
   - title: Clear, descriptive report title
   - summary: Exactly 3 to 4 sentences providing an executive overview
   - sections: 3 to 5 structured sections, each with a heading and a list of factual claims

User Research Question:
{question}

Available Numbered Evidence Notes:
{notes_text}"""


@llm_retry_decorator()
async def write_report(question: str, numbered_notes: list[dict[str, Any]]) -> ReportDraft:
    """Generate structured research report grounded exclusively on the numbered notes."""
    llm = get_llm(temperature=0.0)

    # Format numbered notes for the LLM context
    notes_formatted_lines: list[str] = []
    for n in numbered_notes:
        notes_formatted_lines.append(
            f"[Note {n['note_number']}] {n['fact']} (Snippet: \"{n.get('snippet', '')}\")"
        )
    notes_text = "\n".join(notes_formatted_lines) if notes_formatted_lines else "No evidence collected."

    prompt = REPORT_SYNTHESIS_PROMPT.format(
        question=question,
        notes_text=notes_text,
    )

    structured_llm = llm.with_structured_output(ReportDraft)
    report = await structured_llm.ainvoke(prompt)
    if isinstance(report, ReportDraft):
        return report
    return ReportDraft.model_validate(report)
