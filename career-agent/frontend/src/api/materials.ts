import { api } from './client'
import type { ApplicationMaterialsSummary } from './types'

export const getApplicationMaterials = (jobId: number) => api.get<ApplicationMaterialsSummary>(`/jobs/${jobId}/application-materials`)
