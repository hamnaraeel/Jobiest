# Import every model here so anything that needs the full schema
# (Alembic autogenerate, Base.metadata.create_all, relationship() string
# resolution) sees it by importing this package once. Kept separate from
# app.db.base to avoid a circular import: models import Base from
# app.db.base, so app.db.base cannot import models itself.
from app.models.profile import CareerProfile  # noqa: F401
from app.models.education import Education  # noqa: F401
from app.models.experience import Experience, ExperienceBullet  # noqa: F401
from app.models.project import Project, ProjectResult  # noqa: F401
from app.models.skill import Skill  # noqa: F401
from app.models.certification import Certification  # noqa: F401
from app.models.achievement import Achievement  # noqa: F401
from app.models.research import Research  # noqa: F401
from app.models.evidence import Evidence, EvidenceLink  # noqa: F401
from app.models.job import Job  # noqa: F401
from app.models.job_requirement import JobRequirement  # noqa: F401
from app.models.job_match import JobMatch  # noqa: F401
from app.models.cv_version import CVVersion  # noqa: F401
from app.models.cv_section import CVSection  # noqa: F401
from app.models.cv_change import CVChange  # noqa: F401
from app.models.cover_letter import CoverLetter  # noqa: F401
from app.models.application_question import ApplicationQuestion  # noqa: F401
from app.models.application_answer import ApplicationAnswer  # noqa: F401
from app.models.application import Application  # noqa: F401
from app.models.application_event import ApplicationEvent  # noqa: F401
from app.models.application_field import ApplicationField  # noqa: F401
from app.models.application_session import ApplicationSession  # noqa: F401
from app.models.application_status_history import ApplicationStatusHistory  # noqa: F401
from app.models.application_followup import ApplicationFollowUp  # noqa: F401
from app.models.interview import Interview  # noqa: F401
from app.models.offer import Offer  # noqa: F401
from app.models.application_note import ApplicationNote  # noqa: F401
from app.models.job_note import JobNote  # noqa: F401
from app.models.recommendation import Recommendation  # noqa: F401
from app.models.user_job_search_goal import UserJobSearchGoal  # noqa: F401
from app.models.discovery_run import DiscoveryRun  # noqa: F401
