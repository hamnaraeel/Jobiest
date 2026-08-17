import { api } from './client'
import type { RecommendationListResponse, RecommendationRead } from './types'

export const listRecommendations = (params?: { status?: string; type?: string }) => {
  const query = new URLSearchParams()
  if (params?.status) query.set('status', params.status)
  if (params?.type) query.set('type', params.type)
  const qs = query.toString()
  return api.get<RecommendationListResponse>(`/intelligence/recommendations${qs ? `?${qs}` : ''}`)
}

export const generateRecommendations = () => api.post<RecommendationListResponse>('/intelligence/recommendations/generate')
export const getRecommendation = (id: number) => api.get<RecommendationRead>(`/intelligence/recommendations/${id}`)
export const acceptRecommendation = (id: number) => api.post<RecommendationRead>(`/intelligence/recommendations/${id}/accept`)
export const dismissRecommendation = (id: number) => api.post<RecommendationRead>(`/intelligence/recommendations/${id}/dismiss`)
export const completeRecommendation = (id: number) => api.post<RecommendationRead>(`/intelligence/recommendations/${id}/complete`)
