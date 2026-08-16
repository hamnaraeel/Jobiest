"""Pydantic models the LLM's JSON output is validated against. Nothing
downstream trusts free-form LLM text -- every AI call must produce a
payload that parses cleanly into one of these models, or it is treated as
a malformed-response error, never guessed at."""

from pydantic import BaseModel, Field


class JobAnalysisResult(BaseModel):
    job_title: str | None = None
    company: str | None = None
    location: str | None = None

    job_summary: str

    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    required_experience: list[str] = Field(default_factory=list)
    preferred_experience: list[str] = Field(default_factory=list)
    education_requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    location_requirements: list[str] = Field(default_factory=list)
    work_authorization_requirements: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class MatchExplanationResult(BaseModel):
    reasoning_summary: str


# --- Step 4: cover letters & application answers (Ollama-backed) ----------


class CoverLetterOutput(BaseModel):
    opening: str
    role_alignment: str
    experience_alignment: str
    company_alignment: str
    closing: str
    full_text: str


class ApplicationAnswerOutput(BaseModel):
    answer: str
