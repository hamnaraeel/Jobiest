"""Pydantic models the CV-generation LLM calls must validate against.

Note what's deliberately absent: there is no field anywhere here for the
model to invent a brand-new bullet's text from nothing. Experience/project
content is always a *rewrite* of an existing bullet, referenced by its
real database id (`source_bullet_id`) -- so a fabricated bullet is not a
"the AI lied" problem to catch after the fact, it's a "this id doesn't
exist" problem the deterministic validator catches mechanically.
"""

from pydantic import BaseModel, Field


class CVPlanOutput(BaseModel):
    target_role: str
    priority_skills: list[str] = Field(default_factory=list)
    selected_experience_ids: list[int] = Field(default_factory=list)
    selected_project_ids: list[int] = Field(default_factory=list)
    selected_research_ids: list[int] = Field(default_factory=list)
    sections: list[str] = Field(default_factory=list)
    reasoning: str = ""


class RewrittenBullet(BaseModel):
    source_bullet_id: int
    rewritten_text: str


class ExperienceContentOutput(BaseModel):
    experience_id: int
    bullets: list[RewrittenBullet] = Field(default_factory=list)


class ProjectContentOutput(BaseModel):
    project_id: int
    bullets: list[RewrittenBullet] = Field(default_factory=list)


class SkillCategoryOutput(BaseModel):
    category: str
    skills: list[str] = Field(default_factory=list)


class CVContentOutput(BaseModel):
    summary: str
    skill_categories: list[SkillCategoryOutput] = Field(default_factory=list)
    experience: list[ExperienceContentOutput] = Field(default_factory=list)
    projects: list[ProjectContentOutput] = Field(default_factory=list)
