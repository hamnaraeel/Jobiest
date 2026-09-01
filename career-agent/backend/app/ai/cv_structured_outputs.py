"""Pydantic models the CV-generation LLM calls must validate against.

Note what's deliberately absent: there is no field anywhere here for the
model to select which experiences/projects/bullets/skills appear (the
full profile is always included -- see
cv_customization_service._master_skill_categories() for the Skills
section specifically, which is a deterministic grouping of the
candidate's own stored skills, only reordered by job relevance, never
AI-selected).

`CVBulletRewriteOutput` carries rewritten wording only, keyed by an
opaque id the caller minted for each of the candidate's *existing*
bullets -- the model cannot add a bullet, drop one, or change which
experience a bullet belongs to, because ids it did not receive are
ignored and ids it fails to return keep their original text.
"""

from pydantic import BaseModel, Field


class CVPlanOutput(BaseModel):
    target_role: str
    priority_skills: list[str] = Field(default_factory=list)
    reasoning: str = ""


class CVContentOutput(BaseModel):
    summary: str


class RewrittenBullet(BaseModel):
    id: str
    text: str


class CVBulletRewriteOutput(BaseModel):
    bullets: list[RewrittenBullet] = Field(default_factory=list)
