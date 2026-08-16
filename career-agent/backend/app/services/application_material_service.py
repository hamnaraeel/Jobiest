"""Assembles the read-only application-materials package (GET
/jobs/{job_id}/application-materials) that a future application-automation
step would consume. Only ever reads already-generated data -- never
generates or approves anything itself. See spec section 32: nothing is
"ready for application" unless a human explicitly approved it.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application_answer import ApplicationAnswer
from app.models.application_question import ApplicationQuestion
from app.models.cover_letter import CoverLetter
from app.models.cv_version import CVVersion
from app.models.enums import ApplicationMaterialStatus
from app.models.job import Job
from app.models.job_match import JobMatch


def build_application_material_package(db: Session, job: Job) -> dict:
    match = db.execute(select(JobMatch).where(JobMatch.job_id == job.id)).scalar_one_or_none()

    latest_cv = db.execute(
        select(CVVersion).where(CVVersion.job_id == job.id).order_by(CVVersion.version_number.desc()).limit(1)
    ).scalar_one_or_none()

    latest_cover_letter = db.execute(
        select(CoverLetter).where(CoverLetter.job_id == job.id).order_by(CoverLetter.version_number.desc()).limit(1)
    ).scalar_one_or_none()

    questions = db.execute(select(ApplicationQuestion).where(ApplicationQuestion.job_id == job.id)).scalars().all()

    answer_items = []
    all_required_approved = True
    for question in questions:
        latest_answer = db.execute(
            select(ApplicationAnswer)
            .where(ApplicationAnswer.question_id == question.id)
            .order_by(ApplicationAnswer.id.desc())
            .limit(1)
        ).scalar_one_or_none()

        status_value = latest_answer.status.value if latest_answer else None
        if question.required and status_value != ApplicationMaterialStatus.APPROVED.value:
            all_required_approved = False

        answer_items.append({
            "question_id": question.id,
            "question": question.question,
            "question_type": question.question_type.value,
            "required": question.required,
            "answer_id": latest_answer.id if latest_answer else None,
            "status": status_value,
            "character_count": latest_answer.character_count if latest_answer else None,
            "character_limit": question.character_limit,
        })

    cv_approved = bool(latest_cv and latest_cv.status == ApplicationMaterialStatus.APPROVED)
    cover_letter_approved = bool(latest_cover_letter and latest_cover_letter.status == ApplicationMaterialStatus.APPROVED)

    return {
        "job": {
            "id": job.id, "title": job.title, "company": job.company,
            "location": job.location, "status": job.status.value,
        },
        "match": {"score": match.overall_score, "recommendation": match.recommendation.value} if match else None,
        "cv": {"id": latest_cv.id, "status": latest_cv.status.value, "version_name": latest_cv.version_name} if latest_cv else None,
        "cover_letter": (
            {"id": latest_cover_letter.id, "status": latest_cover_letter.status.value, "version_name": latest_cover_letter.version_name}
            if latest_cover_letter else None
        ),
        "answers": answer_items,
        "ready_for_application": cv_approved and cover_letter_approved and all_required_approved,
    }
