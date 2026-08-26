"""Pydantic models the CV-generation LLM calls must validate against.

Note what's deliberately absent: there is no field anywhere here for the
model to select which experiences/projects/bullets appear (the full
profile always does, verbatim) or to write/rewrite any bullet's text.
The only content an LLM ever authors on a tailored CV is the summary and
the choice of which already-verified skills to surface.
"""

from pydantic import BaseModel, Field


class CVPlanOutput(BaseModel):
    target_role: str
    priority_skills: list[str] = Field(default_factory=list)
    reasoning: str = ""


class SkillCategoryOutput(BaseModel):
    category: str
    skills: list[str] = Field(default_factory=list)


class CVContentOutput(BaseModel):
    summary: str
    skill_categories: list[SkillCategoryOutput] = Field(default_factory=list)
