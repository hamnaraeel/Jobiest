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

// --- Discovery (Step 8) ---------------------------------------------------

export type DiscoveryTrigger = 'manual' | 'scheduled'

export interface DiscoverySourceResult {
  found: number
  created: number
  duplicate: number
  error: Nullable<string>
  note?: string
}

export interface DiscoveryRunRead {
  id: number
  trigger: DiscoveryTrigger
  sources: string[]
  query: { keywords: string[]; locations: string[]; companies: string[] }
  results: Record<string, DiscoverySourceResult>
  jobs_found: number
  jobs_created: number
  started_at: string
  finished_at: Nullable<string>
  created_at: string
}

export interface DiscoveryRunListResponse {
  items: DiscoveryRunRead[]
  total: number
}

export interface DiscoverySourceStatus {
  source: string
  configured: boolean
  requires_api_key: boolean
  note: string
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

// --- Career profile / resume import ------------------------------------

export interface CareerProfileRead {
  id: number
  full_name: string
  professional_title: string
  email: string
  phone: Nullable<string>
  city: Nullable<string>
  country: Nullable<string>
  linkedin_url: Nullable<string>
  github_url: Nullable<string>
  portfolio_url: Nullable<string>
  current_summary: Nullable<string>
  target_roles: string[]
  preferred_industries: string[]
  preferred_locations: string[]
  remote_preference: Nullable<string>
  years_of_experience: Nullable<number>
  salary_expectation: Nullable<string>
  work_authorization: Nullable<string>
  relocation_preference: Nullable<string>
  availability_date: Nullable<string>
  created_at: string
  updated_at: string
}

export type ResumeImportStatus = 'pending_review' | 'confirmed' | 'rejected'

export interface ResumeImportRead {
  id: number
  profile_id: Nullable<number>
  filename: string
  parsed_data: Record<string, unknown>
  warnings: string[]
  status: ResumeImportStatus
  confirmed_at: Nullable<string>
  created_at: string
  updated_at: string
}

export interface ResumeImportListResponse {
  items: ResumeImportRead[]
  total: number
}

// --- CV / cover letter generation --------------------------------------

export type CVStatus = 'draft' | 'validated' | 'approved' | 'rejected' | 'archived'
export type MaterialStatus = 'draft' | 'validated' | 'approved' | 'rejected'

export interface CVBullet {
  text: string
  source_type: string
  source_id: number
  verified: boolean
}

export interface CVSkillCategory {
  category: string
  skills: string[]
}

export interface CVExperienceEntry {
  experience_id: number
  company: string
  role: string
  location: Nullable<string>
  start_date: Nullable<string>
  end_date: Nullable<string>
  currently_working: boolean
  bullets: CVBullet[]
}

export interface CVProjectEntry {
  project_id: number
  name: string
  technologies: string[]
  github_url: Nullable<string>
  bullets: CVBullet[]
}

export interface CVVersionRead {
  id: number
  job_id: number
  profile_id: number
  version_name: string
  version_number: number
  template_name: string
  status: CVStatus
  summary: Nullable<string>
  skills: CVSkillCategory[]
  experience: CVExperienceEntry[]
  projects: CVProjectEntry[]
  education: Record<string, unknown>[]
  certifications: Record<string, unknown>[]
  research: Record<string, unknown>[]
  achievements: Record<string, unknown>[]
  pdf_path: Nullable<string>
  match_score_before: Nullable<number>
  match_score_after: Nullable<number>
  warnings: string[]
  created_at: string
  updated_at: string
}

export interface CoverLetterRead {
  id: number
  job_id: number
  cv_version_id: number
  profile_id: number
  version_name: string
  version_number: number
  title: string
  content: string
  word_count: number
  status: MaterialStatus
  source_evidence: Record<string, unknown>[]
  warnings: string[]
  pdf_path: Nullable<string>
  created_at: string
  updated_at: string
}

export interface CoverLetterListResponse {
  items: CoverLetterRead[]
  total: number
}

export interface ApplicationMaterialsSummary {
  job: { id: number; title: Nullable<string>; company: Nullable<string>; location: Nullable<string>; status: string }
  match: Nullable<{ score: number; recommendation: string }>
  cv: Nullable<{ id: number; status: CVStatus; version_name: string }>
  cover_letter: Nullable<{ id: number; status: MaterialStatus; version_name: string }>
  answers: Record<string, unknown>[]
  ready_for_application: boolean
}

// --- Browser-assisted submission (Step 5) -------------------------------
// A real submit click can only ever happen with DRY_RUN disabled AND an
// explicit approve-submission call -- see submission_guard.py. The UI
// below drives that same gated flow; it does not bypass it.

export interface ApplicationFieldRead {
  id: number
  application_id: number
  field_identifier: string
  label: Nullable<string>
  field_type: string
  page_url: Nullable<string>
  required: boolean
  detected_value: Nullable<string>
  mapped_source: Nullable<string>
  proposed_value: Nullable<string>
  final_value: Nullable<string>
  status: string
  confidence: Nullable<number>
  user_review_required: boolean
}

export interface PageAnalysisResponse {
  url: string
  title: string
  captcha_detected: boolean
  captcha_indicator: Nullable<string>
  login_required: boolean
  has_password_field: boolean
}

export interface ApplicationReviewResponse {
  application: ApplicationRead
  fields: ApplicationFieldRead[]
  warnings: string[]
  ready_for_submission: boolean
}

export interface FillResultResponse {
  filled: ApplicationFieldRead[]
  uploaded: ApplicationFieldRead[]
  needs_user_input: ApplicationFieldRead[]
}

export interface SubmitResultResponse {
  submitted: boolean
  dry_run: boolean
  reason: Nullable<string>
  confirmation_reference: Nullable<string>
}
