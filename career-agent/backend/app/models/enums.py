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
    # Step 6: job-search tracking lifecycle, set manually by the user
    # (or by Step 6 automation for APPLIED, mirroring an Application's
    # submitted status) -- never inferred just from analysis/matching.
    PREPARING = "preparing"
    READY_TO_APPLY = "ready_to_apply"
    APPLIED = "applied"
    WITHDRAWN = "withdrawn"
    CLOSED = "closed"
    REJECTED = "rejected"
    ARCHIVED = "archived"


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


# --- Step 5: browser-based application assistant ---


class ApplicationStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    PREPARING = "preparing"
    BROWSER_OPEN = "browser_open"
    FILLING = "filling"
    NEEDS_USER_INPUT = "needs_user_input"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED_FOR_SUBMISSION = "approved_for_submission"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    FAILED = "failed"
    ABANDONED = "abandoned"
    BLOCKED = "blocked"
    # Step 6: post-submission tracking lifecycle. Only SUBMITTED is ever
    # set automatically (by Step 5, on confirmed submission) -- everything
    # from here on is a manual PATCH /applications/{id}/status update,
    # each transition recorded in ApplicationStatusHistory.
    UNDER_REVIEW = "under_review"
    RECRUITER_CONTACT = "recruiter_contact"
    INTERVIEW = "interview"
    TECHNICAL_INTERVIEW = "technical_interview"
    FINAL_INTERVIEW = "final_interview"
    OFFER = "offer"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    GHOSTED = "ghosted"
    CLOSED = "closed"


class ApplicationEventType(str, enum.Enum):
    APPLICATION_CREATED = "application_created"
    BROWSER_OPENED = "browser_opened"
    PAGE_LOADED = "page_loaded"
    FIELD_DETECTED = "field_detected"
    FIELD_FILLED = "field_filled"
    FILE_UPLOADED = "file_uploaded"
    QUESTION_DETECTED = "question_detected"
    USER_INPUT_REQUIRED = "user_input_required"
    REVIEW_READY = "review_ready"
    SUBMISSION_APPROVED = "submission_approved"
    SUBMISSION_STARTED = "submission_started"
    SUBMISSION_COMPLETED = "submission_completed"
    SUBMISSION_FAILED = "submission_failed"
    BLOCKED = "blocked"
    # Step 6: job-search-tracking events, appended to the same append-only
    # log ApplicationEvent already provides. APPLICATION_CREATED and
    # SUBMISSION_COMPLETED (above) already cover "application_started"/
    # "application_submitted" from the Step 6 spec -- not duplicated here.
    DISCOVERED = "discovered"
    ANALYZED = "analyzed"
    SHORTLISTED = "shortlisted"
    CV_GENERATED = "cv_generated"
    COVER_LETTER_GENERATED = "cover_letter_generated"
    RECRUITER_CONTACT = "recruiter_contact"
    FOLLOW_UP = "follow_up"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    INTERVIEW_COMPLETED = "interview_completed"
    ASSESSMENT = "assessment"
    OFFER_RECEIVED = "offer_received"
    REJECTION = "rejection"
    WITHDRAWAL = "withdrawal"
    NOTE_ADDED = "note_added"
    STATUS_CHANGED = "status_changed"


class ApplicationFieldType(str, enum.Enum):
    TEXT = "text"
    TEXTAREA = "textarea"
    EMAIL = "email"
    PHONE = "phone"
    NUMBER = "number"
    DATE = "date"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    FILE = "file"
    ADDRESS = "address"
    URL = "url"
    UNKNOWN = "unknown"


class ApplicationFieldStatus(str, enum.Enum):
    DETECTED = "detected"
    MAPPED = "mapped"
    FILLED = "filled"
    NEEDS_REVIEW = "needs_review"
    SKIPPED = "skipped"
    REJECTED = "rejected"


class ApplicationPlatform(str, enum.Enum):
    GENERIC = "generic"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    WORKDAY = "workday"
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    COMPANY_SITE = "company_site"
    UNKNOWN = "unknown"


class ApplicationSessionStatus(str, enum.Enum):
    ACTIVE = "active"
    ENDED = "ended"
    ERROR = "error"


# --- Step 6: job-search tracking, analytics, and follow-up management ---


class PriorityLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FollowUpType(str, enum.Enum):
    RECRUITER_FOLLOWUP = "recruiter_followup"
    APPLICATION_FOLLOWUP = "application_followup"
    INTERVIEW_FOLLOWUP = "interview_followup"
    THANK_YOU = "thank_you"
    CUSTOM = "custom"


class FollowUpStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class InterviewType(str, enum.Enum):
    RECRUITER = "recruiter"
    PHONE_SCREEN = "phone_screen"
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    HIRING_MANAGER = "hiring_manager"
    FINAL = "final"
    OTHER = "other"


class InterviewStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"
    NO_SHOW = "no_show"


class OfferStatus(str, enum.Enum):
    RECEIVED = "received"
    NEGOTIATING = "negotiating"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


class ApplicationNoteType(str, enum.Enum):
    GENERAL = "general"
    RECRUITER = "recruiter"
    INTERVIEW = "interview"
    TECHNICAL = "technical"
    FOLLOWUP = "followup"
    OFFER = "offer"
    REJECTION = "rejection"


# --- Step 7: job-search intelligence, optimization, recommendations ---


class RecommendationType(str, enum.Enum):
    JOB_PRIORITY = "job_priority"
    JOB_SKIP = "job_skip"
    CV_IMPROVEMENT = "cv_improvement"
    SKILL_GAP = "skill_gap"
    FOLLOWUP = "followup"
    INTERVIEW_PREPARATION = "interview_preparation"
    APPLICATION_STRATEGY = "application_strategy"
    SOURCE_STRATEGY = "source_strategy"
    CAREER_DIRECTION = "career_direction"
    REJECTION_PATTERN = "rejection_pattern"
    GENERAL_INSIGHT = "general_insight"


class RecommendationStatus(str, enum.Enum):
    NEW = "new"
    VIEWED = "viewed"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    COMPLETED = "completed"
    EXPIRED = "expired"


# --- Step 8: job discovery ---


class DiscoverySource(str, enum.Enum):
    """LinkedIn and Indeed are deliberately absent -- both prohibit
    automated access in their ToS and run active anti-bot enforcement.
    Those stay a manual paste/URL flow through Step 2's ingest_job."""

    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    REMOTEOK = "remoteok"
    WEWORKREMOTELY = "weworkremotely"
    ADZUNA = "adzuna"
    USAJOBS = "usajobs"


class DiscoveryTrigger(str, enum.Enum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class RejectionReason(str, enum.Enum):
    NO_RESPONSE = "no_response"
    INSUFFICIENT_EXPERIENCE = "insufficient_experience"
    SKILLS_GAP = "skills_gap"
    LOCATION = "location"
    SALARY = "salary"
    SPONSORSHIP = "sponsorship"
    INTERNAL_CANDIDATE = "internal_candidate"
    POSITION_CLOSED = "position_closed"
    UNKNOWN = "unknown"
    OTHER = "other"


# --- Step 8: AI job search agent / orchestrator ---
# The agent never invents new capability -- every AgentPlanStep.tool
# below is a thin, validated wrapper around a Steps-1-7 service/router
# function. These enums describe the *orchestration* layer only.


class AgentTaskStatus(str, enum.Enum):
    CREATED = "created"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    WAITING_FOR_USER_INPUT = "waiting_for_user_input"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentPlanStepStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    SKIPPED = "skipped"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentEventType(str, enum.Enum):
    TASK_CREATED = "task_created"
    PLANNING_STARTED = "planning_started"
    PLAN_CREATED = "plan_created"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RECEIVED = "approval_received"
    USER_INPUT_REQUIRED = "user_input_required"
    TASK_PAUSED = "task_paused"
    TASK_RESUMED = "task_resumed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"


class ToolPermission(str, enum.Enum):
    """How a tool touches the system -- READ_ONLY tools never write;
    WRITE tools persist local data; EXTERNAL_ACTION tools reach outside
    this machine (a real browser session against a real job site)."""

    READ_ONLY = "read_only"
    WRITE = "write"
    EXTERNAL_ACTION = "external_action"


class ToolRiskLevel(str, enum.Enum):
    """LOW runs automatically. MEDIUM runs automatically unless it
    touches important persistent data (see permissions.py). HIGH always
    requires explicit approval, no exceptions -- see permissions.py's
    ALWAYS_REQUIRES_APPROVAL tools (submission, external messages,
    profile changes, offer acceptance)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AgentApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
