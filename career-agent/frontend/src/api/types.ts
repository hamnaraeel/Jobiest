// Mirrors app/schemas/*.py exactly -- field names and nullability match
// the live OpenAPI schema, checked against a running backend rather than
// guessed. Keep in sync by hand; there are only a handful of shapes the
// UI actually needs (dashboard, recommendations, jobs, applications).

export type Nullable<T> = T | null

// --- Dashboard / analytics -------------------------------------------

export interface FunnelStats {
  discovered: number
  shortlisted: number
  applied: number
  responses: number
  interviews: number
  offers: number
  accepted: number
}

export interface ConversionRates {
  shortlist_rate: Nullable<number>
  application_rate: Nullable<number>
  response_rate: Nullable<number>
  interview_rate: Nullable<number>
  offer_rate: Nullable<number>
  overall_offer_rate: Nullable<number>
}

export interface DurationStats {
  average: Nullable<number>
  median: Nullable<number>
  minimum: Nullable<number>
  maximum: Nullable<number>
  count: number
}

export interface VelocityStats {
  applications_per_week: number
  applications_per_month: number
  jobs_reviewed_per_week: number
  interviews_per_month: number
  offers_per_month: number
}

export interface DashboardAnalytics {
  funnel: FunnelStats
  conversion_rates: ConversionRates
  time_to_response_days: DurationStats
  time_to_interview_days: DurationStats
  time_to_offer_days: DurationStats
  velocity: VelocityStats
  rejections: number
  withdrawals: number
}

export interface DashboardResponse {
  jobs: { total: number; discovered: number; shortlisted: number }
  applications: { total: number; prepared: number; submitted: number; under_review: number }
  interviews: { total: number; scheduled: number }
  offers: { total: number }
  followups: { pending: number; due_today: number }
  analytics: DashboardAnalytics
}

export interface NotificationItem {
  type: string
  due_date: Nullable<string>
  application_id: Nullable<number>
  job_id: Nullable<number>
  message: string
}

export interface CalendarItem {
  type: string
  date: string
  application_id: Nullable<number>
  message: string
}

// --- Jobs --------------------------------------------------------------

export type JobStatus =
  | 'discovered' | 'analyzed' | 'matched' | 'shortlisted' | 'skipped'
  | 'preparing' | 'ready_to_apply' | 'applied' | 'withdrawn' | 'closed'
  | 'rejected' | 'archived'

export type PriorityLevel = 'low' | 'medium' | 'high' | 'critical'

export interface JobRead {
  id: number
  title: Nullable<string>
  company: Nullable<string>
  location: Nullable<string>
  employment_type: Nullable<string>
  workplace_type: Nullable<string>
  url: Nullable<string>
  source: Nullable<string>
  description: Nullable<string>
  summary: Nullable<string>
  keywords: string[]
  salary_min: Nullable<number>
  salary_max: Nullable<number>
  salary_currency: Nullable<string>
  posted_date: Nullable<string>
  application_deadline: Nullable<string>
  deadline_source: Nullable<string>
  extracted_at: Nullable<string>
  status: JobStatus
  duplicate_of_job_id: Nullable<number>
  external_job_id: Nullable<string>
  priority: PriorityLevel
  tags: string[]
  created_at: string
  updated_at: string
}

export interface JobListResponse {
  items: JobRead[]
  total: number
  limit: number
  offset: number
}

// --- Applications --------------------------------------------------------

export type ApplicationStatus =
  | 'not_started' | 'preparing' | 'browser_open' | 'filling' | 'needs_user_input'
  | 'ready_for_review' | 'approved_for_submission' | 'submitting' | 'submitted'
  | 'failed' | 'abandoned' | 'blocked' | 'under_review' | 'recruiter_contact'
  | 'interview' | 'technical_interview' | 'final_interview' | 'offer' | 'accepted'
  | 'rejected' | 'withdrawn' | 'ghosted' | 'closed'

export interface ApplicationRead {
  id: number
  job_id: number
  cv_version_id: Nullable<number>
  cover_letter_id: Nullable<number>
  original_job_url: Nullable<string>
  application_url: Nullable<string>
  platform: string
  status: ApplicationStatus
  submission_approved: boolean
  started_at: Nullable<string>
  submitted_at: Nullable<string>
  confirmation_reference: Nullable<string>
  priority: PriorityLevel
  tags: string[]
  source: Nullable<string>
  archived: boolean
  material_snapshot: Nullable<Record<string, unknown>>
  rejection_reason: Nullable<string>
  rejection_reason_custom: Nullable<string>
  created_at: string
  updated_at: string
}

export interface ApplicationListResponse {
  items: ApplicationRead[]
  total: number
}

export interface TimelineEntryRead {
  timestamp: string
  entry_type: string
  description: string
  metadata: Record<string, unknown>
}

export interface TimelineResponse {
  application_id: number
  entries: TimelineEntryRead[]
}

export interface ApplicationStatusHistoryRead {
  id: number
  application_id: number
  old_status: Nullable<ApplicationStatus>
  new_status: ApplicationStatus
  reason: Nullable<string>
  source: string
  created_at: string
}

export interface InterviewRead {
  id: number
  application_id: number
  type: string
  scheduled_at: Nullable<string>
  duration_minutes: Nullable<number>
  location: Nullable<string>
  meeting_url: Nullable<string>
  interviewer: Nullable<string>
  notes: Nullable<string>
  status: string
  created_at: string
  updated_at: string
}

export interface OfferRead {
  id: number
  application_id: number
  company: Nullable<string>
  role: Nullable<string>
  salary: Nullable<number>
  currency: Nullable<string>
  employment_type: Nullable<string>
  location: Nullable<string>
  start_date: Nullable<string>
  notes: Nullable<string>
  status: string
  created_at: string
  updated_at: string
}

export interface ApplicationNoteRead {
  id: number
  application_id: number
  content: string
  note_type: string
  created_at: string
  updated_at: string
}

export interface FollowUpRead {
  id: number
  application_id: number
  due_date: string
  type: string
  subject: Nullable<string>
  notes: Nullable<string>
  status: string
  completed_at: Nullable<string>
  created_at: string
  updated_at: string
}

// --- Recommendations -------------------------------------------------

export type RecommendationType =
  | 'job_priority' | 'job_skip' | 'cv_improvement' | 'skill_gap' | 'followup'
  | 'interview_preparation' | 'application_strategy' | 'source_strategy'
  | 'career_direction' | 'rejection_pattern' | 'general_insight'

export type RecommendationStatus = 'new' | 'viewed' | 'accepted' | 'dismissed' | 'completed' | 'expired'

export interface RecommendationRead {
  id: number
  type: RecommendationType
  title: string
  description: string
  priority: PriorityLevel
  confidence: number
  confidence_reason: string
  evidence: Record<string, unknown>
  action: Nullable<string>
  related_job_id: Nullable<number>
  related_application_id: Nullable<number>
  expires_at: Nullable<string>
  status: RecommendationStatus
  created_at: string
  updated_at: string
}

export interface RecommendationListResponse {
  items: RecommendationRead[]
  total: number
}

// --- Intelligence --------------------------------------------------------

export interface PriorityScoreResponse {
  score: number
  factors: Record<string, number>
  reasons: string[]
  warnings: string[]
  confidence: number
  confidence_reason: string
}

export interface OpportunityScoreResponse {
  score: number
  factors: Record<string, number>
  reasons: string[]
  warnings: string[]
}

export interface JobIntelligenceResponse {
  job_id: number
  priority: PriorityScoreResponse
  opportunity: OpportunityScoreResponse
  match_analysis: Record<string, unknown>
  skill_gaps: Record<string, unknown>[]
  cv_recommendations: string[]
  strong_areas: string[]
  potential_concerns: string[]
  cv_focus: Nullable<string>
  cover_letter_focus: Nullable<string>
  evidence: Record<string, unknown>
  confidence: number
}

export interface ApplicationQualityResponse {
  ready: boolean
  match_complete: boolean
  cv_approved: boolean
  cover_letter_approved: boolean
  questions_complete: boolean
  checks: Record<string, boolean>
  score: number
}

export interface ApplicationIntelligenceResponse {
  application_id: number
  quality: ApplicationQualityResponse
  match_score: Nullable<number>
  cv_gap: Nullable<Record<string, unknown>>
  cover_letter_word_count: Nullable<number>
  missing_requirements: string[]
  interview_preparation: Record<string, unknown>
  followup_recommendation: Nullable<string>
  historical_context: Record<string, unknown>
}
