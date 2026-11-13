import asyncio
import logging
from typing import Any

from backend.app.llm import get_llm, llm_retry_decorator
from backend.app.schemas import Claim, ClaimVerdict, ReportDraft, ReportSection

logger = logging.getLogger(__name__)

VERIFY_CLAIM_PROMPT = """You are a strict, meticulous fact-checker.
Compare the following Claim against the Cited Supporting Snippet(s).
Determine whether the Claim is completely and directly substantiated by the snippet text.

CRITICAL RULES:
1. supported = True ONLY if the snippet explicitly supports every factual detail in the claim.
2. If the claim exaggerates, extrapolates, or introduces unmentioned facts, supported = False.
3. Provide a concise, clear reason.

Claim to Verify:
"{claim_text}"

Cited Snippets:
{snippets_text}"""


@llm_retry_decorator()
async def _verify_single_claim(llm: Any, claim: Claim, snippets_text: str) -> ClaimVerdict:
    """Verify a single claim against its cited snippets using structured LLM output."""
    if not snippets_text.strip():
        return ClaimVerdict(
            claim_text=claim.text,
            supported=False,
            reason="No valid supporting snippets were cited for this claim.",
        )

    prompt = VERIFY_CLAIM_PROMPT.format(
        claim_text=claim.text,
        snippets_text=snippets_text,
    )
    structured_llm = llm.with_structured_output(ClaimVerdict)
    result = await structured_llm.ainvoke(prompt)
    return result


async def verify_claims(report: ReportDraft, numbered_notes: list[dict[str, Any]]) -> list[ClaimVerdict]:
    """Verify all report claims concurrently against cited snippet evidence."""
    llm = get_llm(temperature=0.0)
    note_lookup = {n["note_number"]: n for n in numbered_notes}

    # Extract all claims across all sections
    all_claims: list[Claim] = []
    for section in report.sections:
        all_claims.extend(section.claims)

    tasks = []
    for claim in all_claims:
        cited_snippets: list[str] = []
        for num in claim.note_numbers:
            note = note_lookup.get(num)
            if note and note.get("snippet"):
                cited_snippets.append(f"[Note {num} Snippet]: \"{note['snippet']}\"")

        snippets_text = "\n".join(cited_snippets)
        tasks.append(_verify_single_claim(llm, claim, snippets_text))

    verdicts = await asyncio.gather(*tasks)
    return list(verdicts)


def apply_verdicts(report: ReportDraft, verdicts: list[ClaimVerdict]) -> tuple[ReportDraft, list[str]]:
    """Remove unsupported claims from the report, returning cleaned report and list of removed claims."""
    verdict_map = {v.claim_text.strip(): v.supported for v in verdicts}
    removed_claims: list[str] = []

    cleaned_sections: list[ReportSection] = []
    for section in report.sections:
        retained_claims: list[Claim] = []
        for claim in section.claims:
            is_supported = verdict_map.get(claim.text.strip(), True)
            if is_supported:
                retained_claims.append(claim)
            else:
                removed_claims.append(claim.text)

        cleaned_sections.append(
            ReportSection(
                heading=section.heading,
                claims=retained_claims,
            )
        )

    cleaned_report = ReportDraft(
        title=report.title,
        summary=report.summary,
        sections=cleaned_sections,
    )
    return cleaned_report, removed_claims
