import { api } from './client'
import type { JobIntelligenceResponse, JobListResponse, JobRead } from './types'

export interface JobSearchParams {
  company?: string
  role?: string
  status?: string
  priority?: string
  sort?: string
  limit?: number
  offset?: number
}

export const searchJobs = (params: JobSearchParams = {}) => {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') query.set(key, String(value))
  })
  const qs = query.toString()
  return api.get<JobListResponse>(`/jobs/search${qs ? `?${qs}` : ''}`)
}

export const getJob = (id: number) => api.get<JobRead>(`/jobs/${id}`)
export const getJobIntelligence = (id: number) => api.get<JobIntelligenceResponse>(`/intelligence/jobs/${id}`)
export const archiveJob = (id: number) => api.post<JobRead>(`/jobs/${id}/archive`)
// Auto-analyzes the job first if that hasn't happened yet -- the one call
// needed before cv.generate/cover_letter.generate will accept a job that
// was only ever discovered, never analyzed.
export const matchJob = (id: number) => api.post(`/jobs/${id}/match`)
