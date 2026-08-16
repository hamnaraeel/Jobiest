from pydantic import BaseModel


class FunnelStats(BaseModel):
    discovered: int
    shortlisted: int
    applied: int
    responses: int
    interviews: int
    offers: int
    accepted: int


class ConversionRates(BaseModel):
    shortlist_rate: float | None
    application_rate: float | None
    response_rate: float | None
    interview_rate: float | None
    offer_rate: float | None
    overall_offer_rate: float | None


class DurationStats(BaseModel):
    average: float | None
    median: float | None
    minimum: float | None
    maximum: float | None
    count: int


class VelocityStats(BaseModel):
    applications_per_week: float
    applications_per_month: float
    jobs_reviewed_per_week: float
    interviews_per_month: float
    offers_per_month: float


class OverviewResponse(BaseModel):
    funnel: FunnelStats
    conversion_rates: ConversionRates
    time_to_response_days: DurationStats
    time_to_interview_days: DurationStats
    time_to_offer_days: DurationStats
    velocity: VelocityStats


class DashboardAnalytics(OverviewResponse):
    rejections: int
    withdrawals: int


class GroupStats(BaseModel):
    """Shared shape for company/role/source analytics groupings (spec
    sections 36-37, 41)."""

    applications: int
    interviews: int
    offers: int
    response_rate: float | None
    average_match_score: float | None


class VersionStats(BaseModel):
    """CV/cover-letter version analytics (spec sections 42-43) --
    "observed application performance," never a causal claim."""

    applications: int
    interviews: int
    offers: int


class SkillGapEntry(BaseModel):
    skill: str
    jobs_requested: int


class SkillAnalyticsResponse(BaseModel):
    demand: dict[str, int]
    potential_gaps: list[SkillGapEntry]


class MatchScoreBucketStats(BaseModel):
    applications: int
    interviews: int
    offers: int


class CVVersionAnalyticsResponse(BaseModel):
    cv_versions: dict[str, VersionStats]
    cover_letter_versions: dict[str, VersionStats]


class PeriodAnalyticsResponse(BaseModel):
    period: str
    start: str
    end: str
    jobs_discovered: int
    jobs_shortlisted: int
    applications: int
    responses: int
    interviews: int
    offers: int


class DashboardJobsSummary(BaseModel):
    total: int
    discovered: int
    shortlisted: int


class DashboardApplicationsSummary(BaseModel):
    total: int
    prepared: int
    submitted: int
    under_review: int


class DashboardInterviewsSummary(BaseModel):
    total: int
    scheduled: int


class DashboardOffersSummary(BaseModel):
    total: int


class DashboardFollowUpsSummary(BaseModel):
    pending: int
    due_today: int


class DashboardResponse(BaseModel):
    jobs: DashboardJobsSummary
    applications: DashboardApplicationsSummary
    interviews: DashboardInterviewsSummary
    offers: DashboardOffersSummary
    followups: DashboardFollowUpsSummary
    analytics: DashboardAnalytics
