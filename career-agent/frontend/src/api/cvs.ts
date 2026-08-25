import { api } from './client'
import type { CVVersionRead } from './types'

export const generateCv = (jobId: number) => api.post<CVVersionRead>(`/jobs/${jobId}/cv/generate`)
export const getCv = (id: number) => api.get<CVVersionRead>(`/cvs/${id}`)
export const approveCv = (id: number) => api.patch<CVVersionRead>(`/cvs/${id}/status`, { status: 'approved' })
export const rejectCv = (id: number) => api.patch<CVVersionRead>(`/cvs/${id}/status`, { status: 'rejected' })
