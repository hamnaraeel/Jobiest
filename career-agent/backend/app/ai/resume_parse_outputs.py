"""Structured output for parsing an uploaded resume into Career Profile
shape. Dates are plain strings here (LLM structured output is far more
reliable with primitives than date types) -- resume_import_service parses
them into real `date` objects afterward, safely falling back to None on
anything that doesn't parse rather than guessing."""

from pydantic import BaseModel, Field


class ParsedSkill(BaseModel):
    name: str
    category: str = Field(description="One of: Programming, ML/DL, NLP, Computer Vision, LLM, MLOps, Cloud, Databases, Framework, Tool, Other")
    proficiency: str | None = Field(None, description="One of: beginner, intermediate, advanced, expert -- only if stated or clearly implied")
    years_used: float | None = None


class ParsedExperienceBullet(BaseModel):
    bullet: str
    skills: list[str] = Field(default_factory=list)


class ParsedExperience(BaseModel):
    company: str
    role: str
    employment_type: str | None = Field(None, description="One of: full_time, part_time, contract, internship, freelance, self_employed")
    location: str | None = None
    start_date: str | None = Field(None, description="ISO date YYYY-MM-DD, or YYYY-MM-01 if only month/year is known")
    end_date: str | None = None
    currently_working: bool = False
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    bullets: list[ParsedExperienceBullet] = Field(default_factory=list)


class ParsedEducation(BaseModel):
    institution: str
    degree: str
    field: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    location: str | None = None
    grade: str | None = None


class ParsedProjectResult(BaseModel):
    description: str
    metric: str | None = None


class ParsedProject(BaseModel):
    name: str
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    github_url: str | None = None
    demo_url: str | None = None
    results: list[ParsedProjectResult] = Field(default_factory=list)


class ParsedCertification(BaseModel):
    name: str
    issuer: str
    issue_date: str | None = None
    credential_url: str | None = None


class ParsedAchievement(BaseModel):
    title: str
    description: str | None = None
    category: str = Field("professional", description="One of: research, competition, award, publication, academic, professional")


class ParsedResearch(BaseModel):
    title: str
    description: str | None = None
    research_area: str | None = None


class ResumeParseOutput(BaseModel):
    full_name: str | None = None
    professional_title: str | None = None
    email: str | None = None
    phone: str | None = None
    city: str | None = None
    country: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    summary: str | None = None

    skills: list[ParsedSkill] = Field(default_factory=list)
    experience: list[ParsedExperience] = Field(default_factory=list)
    education: list[ParsedEducation] = Field(default_factory=list)
    projects: list[ParsedProject] = Field(default_factory=list)
    certifications: list[ParsedCertification] = Field(default_factory=list)
    achievements: list[ParsedAchievement] = Field(default_factory=list)
    research: list[ParsedResearch] = Field(default_factory=list)
