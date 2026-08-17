from pydantic import BaseModel, Field


class PriorityScoreResponse(BaseModel):
    score: int
    factors: dict[str, float]
    reasons: list[str]
    warnings: list[str]
    confidence: float
    confidence_reason: str


class OpportunityScoreResponse(BaseModel):
    score: int
    factors: dict[str, float]
    reasons: list[str]
    warnings: list[str]


class JobIntelligenceResponse(BaseModel):
    job_id: int
    priority: PriorityScoreResponse
    opportunity: OpportunityScoreResponse
    match_analysis: dict
    skill_gaps: list[dict] = Field(default_factory=list)
    cv_recommendations: list[str] = Field(default_factory=list)
    strong_areas: list[str] = Field(default_factory=list)
    potential_concerns: list[str] = Field(default_factory=list)
    cv_focus: str | None = None
    cover_letter_focus: str | None = None
    evidence: dict = Field(default_factory=dict)
    confidence: float


class ApplicationQualityResponse(BaseModel):
    ready: bool
    match_complete: bool
    cv_approved: bool
    cover_letter_approved: bool
    questions_complete: bool
    checks: dict
    score: float


class ApplicationIntelligenceResponse(BaseModel):
    application_id: int
    quality: ApplicationQualityResponse
    match_score: int | None
    cv_gap: dict | None
    cover_letter_word_count: int | None
    missing_requirements: list[str]
    interview_preparation: dict
    followup_recommendation: str | None
    historical_context: dict


class SkillGapItem(BaseModel):
    skill: str
    demand_count: int
    demand_ratio: float
    importance_score: float
    relevance_score: float
    priority_score: float
    priority: str
    has_skill: bool
    current_level: str | None
    reason: str
    suggested_next_step: str | None


class SkillIntelligenceResponse(BaseModel):
    skills: list[SkillGapItem]


class SkillGapsResponse(BaseModel):
    gaps: list[SkillGapItem]


class SkillDemandResponse(BaseModel):
    demand: dict[str, float]


class CareerIntelligenceResponse(BaseModel):
    strongest_roles: list[str]
    strongest_skills: list[str]
    skill_gaps: list[SkillGapItem]
    application_performance: dict
    interview_performance: dict
    recommended_target_roles: list[str]
    recommended_sources: list[str]
    career_direction: dict


class WeeklyReviewResponse(BaseModel):
    summary: dict
    metrics: dict
    observations: list[str]
    recommendations: list[str]
    evidence: dict
    confidence: float


class StrategyResponse(BaseModel):
    strengths: list[str]
    weaknesses: list[str]
    best_performing_roles: str | None
    best_performing_sources: str | None
    top_skill_gaps: list[str]
    recommended_target_roles: list[str]
    application_strategy: str
    suggested_weekly_targets: dict


class InterviewPreparationResponse(BaseModel):
    role: str | None
    company: str | None
    top_technical_areas: list[str]
    strongest_matching_projects: list[str]
    potential_weak_areas: list[str]
    likely_question_areas: list[str]


class InterviewQuestionsRequest(BaseModel):
    application_id: int
    categories: list[str] | None = None


class InterviewQuestionItem(BaseModel):
    question: str
    category: str


class InterviewQuestionsResponse(BaseModel):
    disclaimer: str = "Potential questions inferred from the job posting -- not a guarantee of what will actually be asked."
    questions: list[InterviewQuestionItem]


class InterviewAnswerRequest(BaseModel):
    application_id: int
    question: str
    star: bool = False


class InterviewAnswerResponse(BaseModel):
    answer: str
    star: dict | None
    validated: bool
    validation_issues: list[str]
