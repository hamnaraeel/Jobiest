import { api } from './client'
import type { DiscoveryRunListResponse, DiscoveryRunRead, DiscoverySourceStatus } from './types'

export const listDiscoverySources = () => api.get<DiscoverySourceStatus[]>('/discovery/sources')

export const runDiscovery = (params?: { sources?: string[]; keywords?: string[]; locations?: string[]; companies?: string[] }) =>
  api.post<DiscoveryRunRead>('/discovery/run', params ?? {})

export const listDiscoveryRuns = (params?: { limit?: number; offset?: number }) => {
  const query = new URLSearchParams()
  if (params?.limit) query.set('limit', String(params.limit))
  if (params?.offset) query.set('offset', String(params.offset))
  const qs = query.toString()
  return api.get<DiscoveryRunListResponse>(`/discovery/runs${qs ? `?${qs}` : ''}`)
}

export const getDiscoveryRun = (id: number) => api.get<DiscoveryRunRead>(`/discovery/runs/${id}`)
