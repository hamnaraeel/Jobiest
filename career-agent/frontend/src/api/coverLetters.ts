import { api } from './client'
import type { CoverLetterRead } from './types'

export const generateCoverLetter = (jobId: number) => api.post<CoverLetterRead>(`/jobs/${jobId}/cover-letter/generate`)
export const getCoverLetter = (id: number) => api.get<CoverLetterRead>(`/cover-letters/${id}`)
export const regenerateCoverLetter = (id: number) => api.post<CoverLetterRead>(`/cover-letters/${id}/regenerate`)
export const approveCoverLetter = (id: number) => api.patch<CoverLetterRead>(`/cover-letters/${id}/status`, { status: 'approved' })
export const rejectCoverLetter = (id: number) => api.patch<CoverLetterRead>(`/cover-letters/${id}/status`, { status: 'rejected' })
