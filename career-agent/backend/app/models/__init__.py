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
