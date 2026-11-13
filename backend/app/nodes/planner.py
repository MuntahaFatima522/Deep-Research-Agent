import logging
from typing import Any

from backend.app.llm import get_llm, llm_retry_decorator
from backend.app.schemas import ResearchPlan

logger = logging.getLogger(__name__)

PLANNER_PROMPT = """You are a research lead.
Analyze the user's research question and break it down into a comprehensive research plan.

CRITICAL INSTRUCTIONS:
1. Formulate 3 to 5 specific, searchable, non-overlapping sub-questions.
2. Assign sequential IDs starting with q1, q2, q3, q4, q5.
3. For each sub-question, write a concise why_it_matters explanation of how it contributes to the overarching topic.
4. Provide a clear, one-sentence goal.

User Research Question:
{question}"""


@llm_retry_decorator()
async def make_plan(question: str) -> ResearchPlan:
    """Decompose research question into 3-5 structured sub-questions with IDs and rationale."""
    llm = get_llm(temperature=0.0)
    prompt = PLANNER_PROMPT.format(question=question)

    structured_llm = llm.with_structured_output(ResearchPlan)
    plan: ResearchPlan = await structured_llm.ainvoke(prompt)
    return plan
