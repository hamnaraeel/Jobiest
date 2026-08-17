"""Step 7: job-search intelligence, optimization, and recommendations.

Every endpoint here either reuses a deterministic app/intelligence/
analyzer directly, or (only for natural-language explanation/interview
question-and-answer generation) calls the local Ollama model through
app/intelligence/recommendation_explainer.py or interview_analyzer.py --
never a paid API, and the LLM is never asked to compute a statistic
itself (spec sections 41-43).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.client import AIConfigurationError, OllamaResponseError, get_ollama_client
from app.db.database import get_db
from app.intelligence import career_insights, interview_analyzer, skill_gap_analyzer
from app.intelligence.application_analyzer import build_application_intelligence, build_job_strategy
from app.intelligence.confidence import confidence_from_sample_size
from app.models.application import Application
from app.models.enums import RecommendationStatus, RejectionReason
from app.models.job import Job
from app.models.recommendation import Recommendation
from app.schemas.application import ApplicationRead
from app.schemas.intelligence import (
    ApplicationIntelligenceResponse,
    ApplicationQualityResponse,
    CareerIntelligenceResponse,
    InterviewAnswerRequest,
    InterviewAnswerResponse,
    InterviewPreparationResponse,
    InterviewQuestionsRequest,
    InterviewQuestionsResponse,
    JobIntelligenceResponse,
    OpportunityScoreResponse,
    PriorityScoreResponse,
    SkillDemandResponse,
    SkillGapsResponse,
    SkillIntelligenceResponse,
    StrategyResponse,
    WeeklyReviewResponse,
)
from app.schemas.recommendation import (
    GoalProgressResponse,
    GoalRead,
    GoalUpdateRequest,
    RecommendationListResponse,
    RecommendationRead,
    RejectionReasonUpdateRequest,
)
from app.services import goal_service, recommendation_engine
from app.services.profile_service import get_default_profile

logger = logging.getLogger("app.api.intelligence")

intelligence_router = APIRouter(prefix="/intelligence", tags=["intelligence"])
interview_prep_router = APIRouter(prefix="/interview-prep", tags=["intelligence"])
applications_rejection_router = APIRouter(prefix="/applications", tags=["intelligence"])


def _get_job_or_404(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No job with id={job_id}")
    return job


def _get_application_or_404(db: Session, application_id: int) -> Application:
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No application with id={application_id}")
    return application


def _get_recommendation_or_404(db: Session, recommendation_id: int) -> Recommendation:
    rec = db.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No recommendation with id={recommendation_id}")
    return rec


# --- Recommendations -------------------------------------------------------


@intelligence_router.post("/recommendations/generate", response_model=RecommendationListResponse)
def generate_recommendations(db: Session = Depends(get_db)):
    recs = recommendation_engine.generate_all(db)
    return RecommendationListResponse(items=recs, total=len(recs))


@intelligence_router.get("/recommendations", response_model=RecommendationListResponse)
def list_recommendations(
    db: Session = Depends(get_db),
    status_filter: RecommendationStatus | None = Query(None, alias="status"),
    type: str | None = None,
):
    stmt = select(Recommendation)
    if status_filter:
        stmt = stmt.where(Recommendation.status == status_filter)
    if type:
        stmt = stmt.where(Recommendation.type == type)
    items = db.execute(stmt.order_by(Recommendation.created_at.desc())).scalars().all()
    return RecommendationListResponse(items=items, total=len(items))


@intelligence_router.get("/recommendations/{recommendation_id}", response_model=RecommendationRead)
def get_recommendation(recommendation_id: int, db: Session = Depends(get_db)):
    rec = _get_recommendation_or_404(db, recommendation_id)
    if rec.status == RecommendationStatus.NEW:
        rec.status = RecommendationStatus.VIEWED
        db.commit()
        db.refresh(rec)
    return rec


@intelligence_router.post("/recommendations/{recommendation_id}/accept", response_model=RecommendationRead)
def accept_recommendation(recommendation_id: int, db: Session = Depends(get_db)):
    rec = _get_recommendation_or_404(db, recommendation_id)
    rec.status = RecommendationStatus.ACCEPTED
    db.commit()
    db.refresh(rec)
    return rec


@intelligence_router.post("/recommendations/{recommendation_id}/dismiss", response_model=RecommendationRead)
def dismiss_recommendation(recommendation_id: int, db: Session = Depends(get_db)):
    rec = _get_recommendation_or_404(db, recommendation_id)
    rec.status = RecommendationStatus.DISMISSED
    db.commit()
    db.refresh(rec)
    return rec


@intelligence_router.post("/recommendations/{recommendation_id}/complete", response_model=RecommendationRead)
def complete_recommendation(recommendation_id: int, db: Session = Depends(get_db)):
    rec = _get_recommendation_or_404(db, recommendation_id)
    rec.status = RecommendationStatus.COMPLETED
    db.commit()
    db.refresh(rec)
    return rec


# --- Job / application intelligence -----------------------------------


@intelligence_router.get("/jobs/{job_id}", response_model=JobIntelligenceResponse)
def get_job_intelligence(job_id: int, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    profile = get_default_profile(db)
    strategy = build_job_strategy(db, job, profile)

    match_analysis = {}
    skill_gaps: list[dict] = []
    cv_recommendations: list[str] = []
    if job.match:
        match_analysis = {
            "matched": [m.get("requirement") for m in job.match.matched_requirements],
            "partial": [m.get("requirement") for m in job.match.partial_requirements],
            "missing": [m.get("requirement") for m in job.match.missing_requirements],
            "overall_score": job.match.overall_score,
        }
        missing_names = {m.get("requirement") for m in job.match.missing_requirements}
        if missing_names and profile:
            for gap in skill_gap_analyzer.analyze_skill_gaps(db, profile):
                if gap.skill in missing_names:
                    skill_gaps.append(gap.__dict__)
        if strategy.potential_concerns:
            cv_recommendations.append(f"Consider addressing: {', '.join(strategy.potential_concerns[:3])}, if supported by your Career Profile.")

    return JobIntelligenceResponse(
        job_id=job.id,
        priority=PriorityScoreResponse(
            score=strategy.priority.score, factors=strategy.priority.factors, reasons=strategy.priority.reasons,
            warnings=strategy.priority.warnings, confidence=strategy.priority.confidence, confidence_reason=strategy.priority.confidence_reason,
        ),
        opportunity=OpportunityScoreResponse(
            score=strategy.opportunity.score, factors=strategy.opportunity.factors,
            reasons=strategy.opportunity.reasons, warnings=strategy.opportunity.warnings,
        ),
        match_analysis=match_analysis, skill_gaps=skill_gaps, cv_recommendations=cv_recommendations,
        strong_areas=strategy.strong_areas, potential_concerns=strategy.potential_concerns,
        cv_focus=strategy.cv_focus, cover_letter_focus=strategy.cover_letter_focus,
        evidence={"priority_factors": strategy.priority.factors, "opportunity_factors": strategy.opportunity.factors},
        confidence=strategy.priority.confidence,
    )


@intelligence_router.get("/applications/{application_id}", response_model=ApplicationIntelligenceResponse)
def get_application_intelligence(application_id: int, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    result = build_application_intelligence(db, application)
    quality: ApplicationQualityResponse = ApplicationQualityResponse(**result["quality"].__dict__)

    cv_gap = result["cv_gap"].__dict__ if result["cv_gap"] else None

    return ApplicationIntelligenceResponse(
        application_id=application.id, quality=quality, match_score=result["match_score"], cv_gap=cv_gap,
        cover_letter_word_count=result["cover_letter_word_count"], missing_requirements=result["missing_requirements"],
        interview_preparation=result["interview_context"],
        followup_recommendation=(f"Suggested follow-up date: {result['suggested_followup_date'].isoformat()}" if result["suggested_followup_date"] else None),
        historical_context=result["historical_context_for_company"],
    )


# --- Skill intelligence -------------------------------------------------


@intelligence_router.get("/skills", response_model=SkillIntelligenceResponse)
def get_skill_intelligence(db: Session = Depends(get_db)):
    profile = get_default_profile(db)
    entries = skill_gap_analyzer.analyze_skill_gaps(db, profile)
    return SkillIntelligenceResponse(skills=[e.__dict__ for e in entries])


@intelligence_router.get("/skills/gaps", response_model=SkillGapsResponse)
def get_skill_gaps(db: Session = Depends(get_db)):
    profile = get_default_profile(db)
    entries = skill_gap_analyzer.missing_skill_gaps(skill_gap_analyzer.analyze_skill_gaps(db, profile))
    return SkillGapsResponse(gaps=[e.__dict__ for e in entries])


@intelligence_router.get("/skills/demand", response_model=SkillDemandResponse)
def get_skill_demand(db: Session = Depends(get_db)):
    profile = get_default_profile(db)
    entries = skill_gap_analyzer.analyze_skill_gaps(db, profile, top_n=50)
    return SkillDemandResponse(demand={e.skill: e.demand_ratio for e in entries})


# --- Career intelligence -------------------------------------------------


@intelligence_router.get("/career", response_model=CareerIntelligenceResponse)
def get_career_intelligence(db: Session = Depends(get_db)):
    profile = get_default_profile(db)
    gaps = skill_gap_analyzer.analyze_skill_gaps(db, profile) if profile else []
    strongest_skills = [g.skill for g in gaps if g.has_skill][:10]
    missing = skill_gap_analyzer.missing_skill_gaps(gaps)

    from app.services import analytics_service

    role_perf = analytics_service.role_analytics(db)
    strongest_roles = sorted(role_perf, key=lambda r: (role_perf[r].get("response_rate") or 0), reverse=True)[:5]

    best_role = career_insights.role_strategy(db)
    best_source = career_insights.source_strategy(db)
    direction = career_insights.career_direction(db)

    return CareerIntelligenceResponse(
        strongest_roles=strongest_roles, strongest_skills=strongest_skills, skill_gaps=[g.__dict__ for g in missing],
        application_performance=role_perf, interview_performance=analytics_service.match_score_analysis(db),
        recommended_target_roles=[best_role.label] if best_role.label else [],
        recommended_sources=[best_source.label] if best_source.label else [],
        career_direction={"potential_direction": direction.potential_direction, "evidence": direction.evidence, "observation": direction.observation},
    )


@intelligence_router.get("/weekly-review", response_model=WeeklyReviewResponse)
def get_weekly_review(db: Session = Depends(get_db)):
    review = career_insights.weekly_review(db)
    period = review["period"]
    confidence, confidence_reason = confidence_from_sample_size(period.get("applications", 0))

    observations = []
    if review["observed_improvement"]:
        observations.append(review["observed_improvement"])
    if review["top_skill_gap"]:
        observations.append(f"Top skill gap: {review['top_skill_gap']}.")

    return WeeklyReviewResponse(
        summary=period, metrics=period, observations=observations,
        recommendations=[review["recommendation"]], evidence=review, confidence=confidence,
    )


@intelligence_router.get("/strategy", response_model=StrategyResponse)
def get_strategy(db: Session = Depends(get_db)):
    strategy = career_insights.personalized_strategy(db)
    return StrategyResponse(
        strengths=strategy.strengths, weaknesses=strategy.weaknesses,
        best_performing_roles=strategy.best_role.label, best_performing_sources=strategy.best_source.label,
        top_skill_gaps=strategy.top_skill_gaps, recommended_target_roles=strategy.recommended_target_roles,
        application_strategy=strategy.application_strategy, suggested_weekly_targets=strategy.suggested_weekly_targets,
    )


# --- Goals ---------------------------------------------------------------


@intelligence_router.get("/goals", response_model=GoalRead | None)
def get_goal(db: Session = Depends(get_db)):
    return goal_service.get_current_goal(db)


@intelligence_router.put("/goals", response_model=GoalRead)
def update_goal(payload: GoalUpdateRequest, db: Session = Depends(get_db)):
    return goal_service.set_goal(db, payload.model_dump(exclude_unset=True))


@intelligence_router.get("/goals/progress", response_model=GoalProgressResponse)
def get_goal_progress(db: Session = Depends(get_db)):
    goal = goal_service.get_current_goal(db)
    if goal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No job-search goal has been configured yet -- PUT /intelligence/goals first.")
    return GoalProgressResponse(goal=goal, progress=goal_service.goal_progress(db, goal))


# --- Interview preparation -------------------------------------------


@intelligence_router.get("/applications/{application_id}/interview-preparation", response_model=InterviewPreparationResponse)
def get_interview_preparation(application_id: int, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    output = interview_analyzer.build_preparation_output(db, application)
    return InterviewPreparationResponse(**output.__dict__)


@interview_prep_router.post("/questions", response_model=InterviewQuestionsResponse)
def generate_interview_questions(payload: InterviewQuestionsRequest, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, payload.application_id)
    try:
        client = get_ollama_client()
        questions = interview_analyzer.generate_questions(client, client.model, application, payload.categories)
    except interview_analyzer.InterviewPrepInputError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except AIConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except OllamaResponseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    return InterviewQuestionsResponse(questions=questions)


@interview_prep_router.post("/answer", response_model=InterviewAnswerResponse)
def generate_interview_answer(payload: InterviewAnswerRequest, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, payload.application_id)
    profile = get_default_profile(db)
    if profile is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No career profile exists yet.")
    try:
        client = get_ollama_client()
        result = interview_analyzer.generate_answer(db, client, application, payload.question, profile.id, star=payload.star)
    except AIConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except OllamaResponseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    return InterviewAnswerResponse(**result)


# --- Rejection reason (extends Step 6's Application resource) -----------


@applications_rejection_router.patch("/{application_id}/rejection-reason", response_model=ApplicationRead)
def update_rejection_reason(application_id: int, payload: RejectionReasonUpdateRequest, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    try:
        application.rejection_reason = RejectionReason(payload.rejection_reason)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid rejection_reason: {payload.rejection_reason}")
    application.rejection_reason_custom = payload.rejection_reason_custom
    db.commit()
    db.refresh(application)
    return application
