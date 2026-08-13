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
