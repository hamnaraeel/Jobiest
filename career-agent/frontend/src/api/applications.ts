import { api } from './client'
import type {
  ApplicationIntelligenceResponse,
  ApplicationListResponse,
  ApplicationNoteRead,
  ApplicationRead,
  ApplicationStatusHistoryRead,
  FollowUpRead,
  InterviewRead,
  OfferRead,
  TimelineResponse,
} from './types'

export interface ApplicationSearchParams {
  company?: string
  role?: string
  status?: string
  priority?: string
  sort?: string
  limit?: number
  offset?: number
}

export const searchApplications = (params: ApplicationSearchParams = {}) => {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') query.set(key, String(value))
  })
  const qs = query.toString()
  return api.get<ApplicationListResponse>(`/applications/search${qs ? `?${qs}` : ''}`)
}

export const getApplication = (id: number) => api.get<ApplicationRead>(`/applications/${id}`)
export const getApplicationIntelligence = (id: number) => api.get<ApplicationIntelligenceResponse>(`/intelligence/applications/${id}`)
export const getApplicationTimeline = (id: number) => api.get<TimelineResponse>(`/applications/${id}/timeline`)
export const getApplicationStatusHistory = (id: number) => api.get<ApplicationStatusHistoryRead[]>(`/applications/${id}/status-history`)
export const getApplicationInterviews = (id: number) => api.get<InterviewRead[]>(`/applications/${id}/interviews`)
export const getApplicationOffers = (id: number) => api.get<OfferRead[]>(`/applications/${id}/offers`)
export const getApplicationNotes = (id: number) => api.get<ApplicationNoteRead[]>(`/applications/${id}/notes`)
export const getApplicationFollowups = (id: number) => api.get<FollowUpRead[]>(`/applications/${id}/followups`)

export const updateApplicationStatus = (id: number, status: string, reason?: string) =>
  api.patch<ApplicationRead>(`/applications/${id}/status`, { status, reason })

export const addApplicationNote = (id: number, content: string, note_type = 'general') =>
  api.post<ApplicationNoteRead>(`/applications/${id}/notes`, { content, note_type })

export const archiveApplication = (id: number) => api.post<ApplicationRead>(`/applications/${id}/archive`)
