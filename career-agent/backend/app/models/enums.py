import enum


class ProficiencyLevel(str, enum.Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class SkillCategory(str, enum.Enum):
    PROGRAMMING = "Programming"
    ML_DL = "ML/DL"
    NLP = "NLP"
    COMPUTER_VISION = "Computer Vision"
    LLM = "LLM"
    MLOPS = "MLOps"
    CLOUD = "Cloud"
    DATABASES = "Databases"
    FRAMEWORK = "Framework"
    TOOL = "Tool"
    OTHER = "Other"


class EmploymentType(str, enum.Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    FREELANCE = "freelance"
    SELF_EMPLOYED = "self_employed"


class RemotePreference(str, enum.Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    FLEXIBLE = "flexible"


class SourceType(str, enum.Enum):
    CV = "CV"
    RESUME = "Resume"
    GITHUB = "GitHub"
    RESEARCH_PAPER = "Research Paper"
    PROJECT = "Project"
    CERTIFICATE = "Certificate"
    EMPLOYMENT_RECORD = "Employment Record"
    USER_PROVIDED = "User Provided"
    OTHER = "Other"


class EntityType(str, enum.Enum):
    SKILL = "skill"
    EDUCATION = "education"
    EXPERIENCE = "experience"
    EXPERIENCE_BULLET = "experience_bullet"
    PROJECT = "project"
    PROJECT_RESULT = "project_result"
    RESEARCH = "research"
    CERTIFICATION = "certification"
    ACHIEVEMENT = "achievement"


class AchievementCategory(str, enum.Enum):
    RESEARCH = "research"
    COMPETITION = "competition"
    AWARD = "award"
    PUBLICATION = "publication"
    ACADEMIC = "academic"
    PROFESSIONAL = "professional"


# --- Step 2: job ingestion / analysis / matching ---


class JobEmploymentType(str, enum.Enum):
    """Deliberately separate from EmploymentType (Step 1's *my* work
    history) since job postings use a different value set (e.g. temporary,
    unknown) and conflating the two would let a job posting's employment
    type silently masquerade as a fact about my own employment history."""

    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"
    UNKNOWN = "unknown"


class WorkplaceType(str, enum.Enum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class JobStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    ANALYZED = "analyzed"
    MATCHED = "matched"
    SHORTLISTED = "shortlisted"
    SKIPPED = "skipped"


class RequirementCategory(str, enum.Enum):
    TECHNICAL_SKILL = "technical_skill"
    SOFT_SKILL = "soft_skill"
    EDUCATION = "education"
    EXPERIENCE = "experience"
    CERTIFICATION = "certification"
    RESPONSIBILITY = "responsibility"
    LOCATION = "location"
    WORK_AUTHORIZATION = "work_authorization"
    LANGUAGE = "language"
    OTHER = "other"


class RequirementImportance(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MatchStatus(str, enum.Enum):
    MATCHED = "matched"
    PARTIAL = "partial"
    MISSING = "missing"
    UNKNOWN = "unknown"


class Recommendation(str, enum.Enum):
    APPLY = "apply"
    MAYBE = "maybe"
    SKIP = "skip"


# --- Step 3: CV customization, versioning, and PDF generation ---


class CVStatus(str, enum.Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class CVSectionType(str, enum.Enum):
    SUMMARY = "summary"
    SKILLS = "skills"
    EXPERIENCE = "experience"
    PROJECTS = "projects"
    RESEARCH = "research"
    EDUCATION = "education"
    CERTIFICATIONS = "certifications"
    ACHIEVEMENTS = "achievements"


class CVChangeType(str, enum.Enum):
    ADDED = "added"
    REMOVED = "removed"
    REWRITTEN = "rewritten"
    REORDERED = "reordered"
    EMPHASIZED = "emphasized"
    DE_EMPHASIZED = "de_emphasized"


# --- Step 4: cover letters & application question answers ---

# Cover letters and application answers go through the identical
# draft -> validated -> approved -> rejected -> archived workflow as a CV
# (Step 3) -- reusing CVStatus directly rather than defining an identical
# enum a second time. The alias exists purely so call sites read clearly.
ApplicationMaterialStatus = CVStatus


class ApplicationQuestionType(str, enum.Enum):
    MOTIVATION = "motivation"
    EXPERIENCE = "experience"
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    COMPANY = "company"
    SALARY = "salary"
    AVAILABILITY = "availability"
    RELOCATION = "relocation"
    AUTHORIZATION = "authorization"
    GENERAL = "general"
    UNKNOWN = "unknown"
