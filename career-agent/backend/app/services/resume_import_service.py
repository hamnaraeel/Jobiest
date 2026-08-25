"""The "Profile Parser": turns an uploaded resume into a *proposed* set
of Career Profile facts. Nothing here writes to the Career Profile
directly -- parse_resume() only ever creates a ResumeImport row
(status=pending_review); only confirm_import(), an explicit human action,
writes real Skill/Experience/Education/... rows, and it forces
verified=False on every single one of them regardless of what the AI
extracted, exactly like every other AI-touched fact in this system (spec:
"nothing invented, nothing auto-verified"). Rejecting an import discards
it -- nothing is ever written.
"""

import io
import logging
import re
from datetime import date, datetime, timezone

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.client import (
    AIConfigurationError,
    STRUCTURED_OUTPUT_MAX_TOKENS,
    get_ai_client,
    get_ai_extra_params,
    get_ai_model,
)
from app.ai.resume_parse_outputs import ResumeParseOutput
from app.ai.resume_parse_prompts import RESUME_PARSE_PROMPT_V1
from app.models.achievement import Achievement
from app.models.certification import Certification
from app.models.education import Education
from app.models.enums import (
    AchievementCategory,
    EmploymentType,
    ProficiencyLevel,
    ResumeImportStatus,
    SkillCategory,
)
from app.models.experience import Experience, ExperienceBullet
from app.models.profile import CareerProfile
from app.models.project import Project, ProjectResult
from app.models.research import Research
from app.models.resume_import import ResumeImport
from app.models.skill import Skill

logger = logging.getLogger("app.resume_import")

MIN_USABLE_TEXT_LENGTH = 100
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


class ResumeImportError(ValueError):
    pass


class AIResponseError(RuntimeError):
    pass


def extract_text(filename: str, content: bytes) -> str:
    lower = filename.lower()
    ext = next((e for e in SUPPORTED_EXTENSIONS if lower.endswith(e)), None)
    if ext is None:
        raise ResumeImportError(
            f"Unsupported file type for '{filename}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}."
        )

    if ext == ".pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise ResumeImportError(f"Could not read '{filename}' as a PDF: {exc}") from exc
    else:
        text = content.decode("utf-8", errors="replace")

    text = text.strip()
    if len(text) < MIN_USABLE_TEXT_LENGTH:
        raise ResumeImportError(
            f"Couldn't extract enough readable text from '{filename}' "
            f"(got {len(text)} characters) -- it may be a scanned image PDF, which isn't supported."
        )
    return text


def _call_resume_parse(text: str, max_retries: int = 1) -> ResumeParseOutput:
    client = get_ai_client()  # raises AIConfigurationError if the configured provider's key is unset

    last_error: Exception = AIResponseError("unknown error")
    for attempt in range(max_retries + 1):
        try:
            completion = client.chat.completions.parse(
                model=get_ai_model(),
                messages=[
                    {"role": "system", "content": RESUME_PARSE_PROMPT_V1},
                    {"role": "user", "content": text},
                ],
                response_format=ResumeParseOutput,
                max_tokens=STRUCTURED_OUTPUT_MAX_TOKENS,
                **get_ai_extra_params(),
            )
        except Exception as exc:
            # Small/fast structured-output models (e.g. Groq's gpt-oss-20b)
            # occasionally emit slightly malformed JSON on a large, repetitive
            # schema like this one -- worth one retry before surfacing it.
            logger.warning("resume parse call failed (attempt %d): %s", attempt + 1, exc.__class__.__name__)
            last_error = AIResponseError(f"OpenAI request failed: {exc}")
            continue

        parsed = completion.choices[0].message.parsed
        if parsed is None:
            refusal = getattr(completion.choices[0].message, "refusal", None)
            last_error = AIResponseError(f"Model did not return structured output: {refusal or 'unknown reason'}")
            continue

        try:
            return ResumeParseOutput.model_validate(parsed.model_dump())
        except ValidationError as exc:
            last_error = AIResponseError(f"AI response failed schema validation: {exc}")
            continue

    raise last_error


def parse_resume(db: Session, filename: str, content: bytes, profile_id: int | None = None) -> ResumeImport:
    text = extract_text(filename, content)
    result = _call_resume_parse(text)

    warnings = []
    if not result.email:
        warnings.append("No email address was found -- required to create a brand-new profile from this import.")
    if not result.full_name:
        warnings.append("No name was found -- required to create a brand-new profile from this import.")
    if not result.skills and not result.experience:
        warnings.append("No skills or experience were extracted -- the file may not be a resume, or the text didn't extract cleanly.")

    resume_import = ResumeImport(
        profile_id=profile_id, filename=filename, raw_text=text,
        parsed_data=result.model_dump(mode="json"), warnings=warnings,
        status=ResumeImportStatus.PENDING_REVIEW,
    )
    db.add(resume_import)
    db.commit()
    db.refresh(resume_import)
    logger.info("resume import parsed id=%s filename=%s skills=%d experience=%d", resume_import.id, filename, len(result.skills), len(result.experience))
    return resume_import


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _safe_enum(enum_cls, value: str | None, default=None):
    if not value:
        return default
    normalized = value.strip().lower().replace(" ", "_")
    for member in enum_cls:
        if member.value.lower().replace(" ", "_") == normalized or member.name.lower() == normalized:
            return member
    return default


def confirm_import(db: Session, resume_import: ResumeImport, profile_id: int | None = None) -> CareerProfile:
    """The only place a parsed resume actually becomes Career Profile
    data. Every row created here is verified=False, unconditionally --
    the human confirming the import is agreeing "yes, import this for my
    own review," not vouching for each individual fact's truth yet."""

    if resume_import.status != ResumeImportStatus.PENDING_REVIEW:
        raise ResumeImportError(f"This import is already '{resume_import.status.value}', not pending review.")

    data = ResumeParseOutput.model_validate(resume_import.parsed_data)

    profile = db.get(CareerProfile, profile_id) if profile_id else None
    if profile is None and profile_id is None:
        profile = db.execute(select(CareerProfile).order_by(CareerProfile.id).limit(1)).scalar_one_or_none()

    if profile is None:
        if not data.full_name or not data.email or not data.professional_title:
            raise ResumeImportError(
                "No existing career profile, and the resume didn't clearly state a name/email/professional title "
                "needed to create one. Create a profile first (POST /profile), then confirm this import against it."
            )
        profile = CareerProfile(full_name=data.full_name, professional_title=data.professional_title, email=data.email)
        db.add(profile)
        db.flush()

    # Confirming a second import against a profile that already has data
    # (re-uploading the same or an updated resume) must not fail or
    # silently duplicate everything it already has -- skills even have a
    # DB-level uniqueness constraint on (profile_id, name) that would
    # otherwise turn this into an IntegrityError. Skip anything that
    # already exists for this profile, matched on the same natural-identity
    # fields a person would recognize as "the same entry". Two independent
    # AI parses of the identical resume text routinely disagree on more
    # than whitespace/case -- one may render a title as "CloudETL" and
    # another as "CloudETL - ELT pipelines with CI/CD..." for the exact
    # same project, or drop/add a trailing city name on a company. A plain
    # (even normalized) equality check treats those as different entries
    # and duplicates them, so name-like fields are matched by prefix
    # containment instead of exact equality.
    def _norm(text: str | None) -> str:
        # Strip punctuation too, not just whitespace -- "CloudETL- X" vs
        # "CloudETL – X" (en dash, differently spaced) is exactly the
        # kind of AI-parse variance seen in practice, and word characters
        # are what actually identify the entry.
        return " ".join(re.sub(r"[^\w\s]", " ", (text or "")).split()).lower()

    def _name_matches(a: str | None, b: str | None) -> bool:
        na, nb = _norm(a), _norm(b)
        if not na or not nb:
            return na == nb
        return na == nb or na.startswith(nb) or nb.startswith(na)

    existing_skill_names = {_norm(n) for n in db.execute(select(Skill.name).where(Skill.profile_id == profile.id)).scalars()}
    existing_experiences = list(
        db.execute(select(Experience.company, Experience.role, Experience.start_date).where(Experience.profile_id == profile.id))
    )
    existing_educations = list(db.execute(select(Education.institution, Education.degree).where(Education.profile_id == profile.id)))
    existing_project_names = list(db.execute(select(Project.name).where(Project.profile_id == profile.id)).scalars())
    existing_certifications = list(
        db.execute(select(Certification.name, Certification.issuer).where(Certification.profile_id == profile.id))
    )
    existing_achievement_titles = list(db.execute(select(Achievement.title).where(Achievement.profile_id == profile.id)).scalars())
    existing_research_titles = list(db.execute(select(Research.title).where(Research.profile_id == profile.id)).scalars())

    for s in data.skills:
        if _norm(s.name) in existing_skill_names:
            continue
        db.add(Skill(
            profile_id=profile.id, name=s.name, category=_safe_enum(SkillCategory, s.category, SkillCategory.OTHER),
            proficiency=_safe_enum(ProficiencyLevel, s.proficiency), years_used=s.years_used, verified=False,
        ))

    for e in data.experience:
        e_start = _parse_date(e.start_date)
        if any(
            _name_matches(e.company, existing.company) and _norm(e.role) == _norm(existing.role) and e_start == existing.start_date
            for existing in existing_experiences
        ):
            continue
        experience = Experience(
            profile_id=profile.id, company=e.company, role=e.role,
            employment_type=_safe_enum(EmploymentType, e.employment_type), location=e.location,
            start_date=_parse_date(e.start_date), end_date=_parse_date(e.end_date),
            currently_working=e.currently_working, description=e.description,
            technologies=e.technologies, skills=e.skills, verified=False,
        )
        db.add(experience)
        db.flush()
        for b in e.bullets:
            db.add(ExperienceBullet(experience_id=experience.id, bullet=b.bullet, skills=b.skills, verified=False))

    for ed in data.education:
        if any(
            _name_matches(ed.institution, existing.institution) and _norm(ed.degree) == _norm(existing.degree)
            for existing in existing_educations
        ):
            continue
        db.add(Education(
            profile_id=profile.id, institution=ed.institution, degree=ed.degree, field=ed.field,
            start_date=_parse_date(ed.start_date), end_date=_parse_date(ed.end_date),
            location=ed.location, grade=ed.grade, verified=False,
        ))

    for p in data.projects:
        if any(_name_matches(p.name, existing) for existing in existing_project_names):
            continue
        project = Project(
            profile_id=profile.id, name=p.name, description=p.description,
            technologies=p.technologies, skills=p.skills, github_url=p.github_url, demo_url=p.demo_url, verified=False,
        )
        db.add(project)
        db.flush()
        for r in p.results:
            db.add(ProjectResult(project_id=project.id, description=r.description, metric=r.metric, verified=False))

    for c in data.certifications:
        if any(_name_matches(c.name, existing.name) and _norm(c.issuer) == _norm(existing.issuer) for existing in existing_certifications):
            continue
        db.add(Certification(
            profile_id=profile.id, name=c.name, issuer=c.issuer,
            issue_date=_parse_date(c.issue_date), credential_url=c.credential_url, verified=False,
        ))

    for a in data.achievements:
        if any(_name_matches(a.title, existing) for existing in existing_achievement_titles):
            continue
        db.add(Achievement(
            profile_id=profile.id, title=a.title, description=a.description,
            category=_safe_enum(AchievementCategory, a.category, AchievementCategory.PROFESSIONAL), verified=False,
        ))

    for r in data.research:
        if any(_name_matches(r.title, existing) for existing in existing_research_titles):
            continue
        db.add(Research(profile_id=profile.id, title=r.title, description=r.description, research_area=r.research_area, verified=False))

    resume_import.status = ResumeImportStatus.CONFIRMED
    resume_import.confirmed_at = datetime.now(timezone.utc)
    resume_import.profile_id = profile.id
    db.commit()
    db.refresh(profile)
    logger.info("resume import confirmed id=%s profile_id=%s", resume_import.id, profile.id)
    return profile


def reject_import(db: Session, resume_import: ResumeImport) -> ResumeImport:
    if resume_import.status != ResumeImportStatus.PENDING_REVIEW:
        raise ResumeImportError(f"This import is already '{resume_import.status.value}', not pending review.")
    resume_import.status = ResumeImportStatus.REJECTED
    db.commit()
    db.refresh(resume_import)
    return resume_import
