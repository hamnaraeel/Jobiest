from pydantic import BaseModel, Field


class CVPlan(BaseModel):
    """How to frame the candidate for this job, decided before any
    wording is generated. Mirrors the AI's CVPlanOutput but is the
    service-facing type used across the rest of the pipeline (kept
    separate so validation/defaults applied after the AI call don't leak
    back into the LLM-facing schema). Deliberately has no content-
    selection fields -- the full profile is always included verbatim;
    only target_role/priority_skills (which feed the summary and skill
    selection) vary per job."""

    target_role: str
    priority_skills: list[str] = Field(default_factory=list)
    reasoning: str = ""


class CVGenerateRequest(BaseModel):
    template_name: str = "ats/ml_engineer"
    compile_pdf: bool = True


class ValidationIssue(BaseModel):
    code: str
    message: str
    section: str | None = None
