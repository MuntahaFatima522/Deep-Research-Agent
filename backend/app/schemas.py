from pydantic import BaseModel, Field


class SubQuestion(BaseModel):
    id: str = Field(description="Unique identifier for the sub-question (e.g. q1, q2)")  # Sub-question identifier
    question: str = Field(description="Focused, searchable sub-question")  # Research question to investigate
    why_it_matters: str = Field(description="Why this sub-question is critical to the overall goal")  # Rationale for sub-question


class ResearchPlan(BaseModel):
    goal: str = Field(description="One-sentence goal of the research")  # Overarching research objective
    sub_questions: list[SubQuestion] = Field(
        ...,
        min_length=3,
        max_length=5,
        description="3 to 5 non-overlapping sub-questions",
    )  # List of 3 to 5 targeted sub-questions


class Note(BaseModel):
    sub_question_id: str = Field(description="ID of the sub-question this note answers")  # Sub-question ID
    fact: str = Field(description="Single factual takeaway extracted from the page")  # Extracted fact
    source_url: str = Field(description="Full URL of the source page")  # Source page URL
    source_title: str = Field(description="Title of the source webpage")  # Source webpage title
    snippet: str = Field(description="Direct verbatim snippet from the page supporting the fact")  # Verbatim supporting excerpt


class SourceDoc(BaseModel):
    url: str = Field(description="Webpage URL")  # Webpage URL
    title: str = Field(description="Webpage title")  # Webpage title
    content: str = Field(description="Extracted text content from the page")  # Extracted page text


class GapCheck(BaseModel):
    is_enough: bool = Field(description="True if current evidence is sufficient to answer the research question")  # Whether evidence is sufficient
    missing: list[str] = Field(default_factory=list, description="List of missing information or unanswered points")  # Missing knowledge gaps
    new_sub_questions: list[SubQuestion] = Field(
        default_factory=list,
        max_length=2,
        description="At most 2 new targeted sub-questions to search",
    )  # New sub-questions to fill gaps


class Claim(BaseModel):
    text: str = Field(description="Specific factual claim made in the report")  # Report claim statement
    note_numbers: list[int] = Field(description="List of supporting note numbers (1-indexed)")  # Supporting note numbers


class ReportSection(BaseModel):
    heading: str = Field(description="Section heading title")  # Section heading
    claims: list[Claim] = Field(description="List of factual claims in this section")  # Section claims


class ReportDraft(BaseModel):
    title: str = Field(description="Report title")  # Main report title
    summary: str = Field(description="3-4 sentence summary for a beginner in simple English")  # Executive summary
    sections: list[ReportSection] = Field(description="3-5 structured report sections")  # Report sections


class ClaimVerdict(BaseModel):
    claim_text: str = Field(description="The claim text being evaluated")  # Evaluated claim text
    supported: bool = Field(description="Whether the claim is verified by the cited snippets")  # Support verdict
    reason: str = Field(description="Explanation of why the claim is supported or unsupported")  # Verdict reasoning
