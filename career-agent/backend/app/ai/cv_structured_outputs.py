"""Pydantic models the CV-generation LLM calls must validate against.

Note what's deliberately absent: there is no field anywhere here for the
model to select which experiences/projects/bullets/skills appear (the
full profile is always included, verbatim -- see
cv_customization_service._master_skill_categories() for the Skills
section specifically, which is a deterministic grouping of the
candidate's own stored skills, only reordered by job relevance, never
AI-selected). The only content an LLM ever authors on a tailored CV is
the summary.
"""

from pydantic import BaseModel, Field


class CVPlanOutput(BaseModel):
    target_role: str
    priority_skills: list[str] = Field(default_factory=list)
    reasoning: str = ""


class CVContentOutput(BaseModel):
    summary: str
