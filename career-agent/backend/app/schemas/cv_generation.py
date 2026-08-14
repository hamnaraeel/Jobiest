from pydantic import BaseModel, Field

from app.models.enums import CVSectionType


class CVPlan(BaseModel):
    """What to include, decided before any wording is generated. Mirrors
    the AI's CVPlanOutput but is the service-facing type used across the
    rest of the pipeline (kept separate so validation/defaults applied
    after the AI call don't leak back into the LLM-facing schema)."""

    target_role: str
    priority_skills: list[str] = Field(default_factory=list)
    selected_experience_ids: list[int] = Field(default_factory=list)
    selected_project_ids: list[int] = Field(default_factory=list)
    selected_research_ids: list[int] = Field(default_factory=list)
    sections: list[CVSectionType] = Field(default_factory=list)
    reasoning: str = ""


class CVGenerateRequest(BaseModel):
    template_name: str = "ats/ml_engineer"
    compile_pdf: bool = True


class ValidationIssue(BaseModel):
    code: str
    message: str
    section: str | None = None
