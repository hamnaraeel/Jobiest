import { api } from './client'
import type { CalendarItem, DashboardResponse, NotificationItem } from './types'

export const getDashboard = () => api.get<DashboardResponse>('/dashboard')
export const getUpcomingNotifications = () => api.get<NotificationItem[]>('/notifications/upcoming')
export const getUpcomingCalendar = () => api.get<CalendarItem[]>('/calendar/upcoming')
