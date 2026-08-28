from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CVSectionType, CVStatus, EntityType


class CVBullet(BaseModel):
    """A single generated line of CV content, always traceable back to a
    specific Career Profile row. `verified` mirrors that source row's own
    `verified` flag -- it is never set independently by the generator."""

    text: str
    source_type: EntityType
    source_id: int
    verified: bool


class CVHeader(BaseModel):
    name: str
    tagline: str | None = None
    email: str
    phone: str | None = None
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None
    location: str | None = None


class CVSkillCategory(BaseModel):
    category: str
    skills: list[str] = Field(default_factory=list)


class CVExperienceEntry(BaseModel):
    experience_id: int
    company: str
    role: str
    location: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    currently_working: bool = False
    bullets: list[CVBullet] = Field(default_factory=list)


class CVProjectEntry(BaseModel):
    project_id: int
    name: str
    category: str
    technologies: list[str] = Field(default_factory=list)
    github_url: str | None = None
    demo_url: str | None = None
    bullets: list[CVBullet] = Field(default_factory=list)


class CVResearchEntry(BaseModel):
    research_id: int
    title: str
    research_area: str | None = None
    technologies: list[str] = Field(default_factory=list)
    description: str | None = None


class CVEducationEntry(BaseModel):
    education_id: int
    institution: str
    degree: str
    field: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    grade: str | None = None


class CVCertificationEntry(BaseModel):
    certification_id: int
    name: str
    issuer: str
    issue_date: date | None = None


class CVAchievementEntry(BaseModel):
    achievement_id: int
    title: str
    description: str | None = None
    metric: str | None = None


class CVContent(BaseModel):
    """The complete structured CV -- what actually gets rendered to
    LaTeX. Every bullet in it carries a source; education, certifications,
    research, and achievements are copied verbatim from the profile (never
    LLM-rewritten), so they need no separate per-item verification check."""

    header: CVHeader
    summary: str
    skills: list[CVSkillCategory] = Field(default_factory=list)
    experience: list[CVExperienceEntry] = Field(default_factory=list)
    projects: list[CVProjectEntry] = Field(default_factory=list)
    research: list[CVResearchEntry] = Field(default_factory=list)
    education: list[CVEducationEntry] = Field(default_factory=list)
    certifications: list[CVCertificationEntry] = Field(default_factory=list)
    achievements: list[CVAchievementEntry] = Field(default_factory=list)
    section_order: list[CVSectionType] = Field(default_factory=list)


class CVVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    profile_id: int
    version_name: str
    version_number: int
    template_name: str
    status: CVStatus
    summary: str | None
    skills: list
    experience: list
    projects: list
    education: list
    certifications: list
    research: list
    achievements: list
    pdf_path: str | None
    match_score_before: int | None
    match_score_after: int | None
    warnings: list[str]
    created_at: datetime
    updated_at: datetime


class CVStatusUpdateRequest(BaseModel):
    status: CVStatus


class CVListResponse(BaseModel):
    items: list[CVVersionRead]
    total: int
    limit: int
    offset: int


class CVPreviewResponse(BaseModel):
    version_id: int | None
    summary: str
    skills: list[CVSkillCategory]
    experience: list[CVExperienceEntry]
    projects: list[CVProjectEntry]
    education: list[CVEducationEntry]
    warnings: list[str] = Field(default_factory=list)


class CVComparisonEntry(BaseModel):
    change_type: str
    section: str
    original_text: str | None = None
    customized_text: str | None = None
    source_id: str | None = None
    reason: str | None = None


class CVComparisonResponse(BaseModel):
    cv_id: int
    job_id: int
    match_score_before: int | None
    match_score_after: int | None
    added_skills: list[str]
    removed_skills: list[str]
    reordered_skills: list[str]
    de_emphasized_skills: list[str]
    added_projects: list[str]
    removed_projects: list[str]
    summary_changed: bool
    section_order: list[str]
    changes: list[CVComparisonEntry]
