import { api } from './client'
import type { CareerProfileRead, ResumeImportListResponse, ResumeImportRead } from './types'

export const getProfile = () => api.get<CareerProfileRead>('/profile')

export const uploadResume = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.upload<ResumeImportRead>('/profile/resume/upload', form)
}

export const listResumeImports = () => api.get<ResumeImportListResponse>('/profile/resume/imports')

export const getResumeImport = (id: number) => api.get<ResumeImportRead>(`/profile/resume/imports/${id}`)

export const confirmResumeImport = (id: number, profileId?: number) =>
  api.post<CareerProfileRead>(`/profile/resume/imports/${id}/confirm`, profileId !== undefined ? { profile_id: profileId } : {})

export const rejectResumeImport = (id: number) => api.post<ResumeImportRead>(`/profile/resume/imports/${id}/reject`)
