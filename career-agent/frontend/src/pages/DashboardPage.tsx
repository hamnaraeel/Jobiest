import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getDashboard, getUpcomingCalendar } from '../api/dashboard'
import { useApi } from '../hooks/useApi'
import StatCard from '../components/StatCard'
import Card from '../components/Card'
import { LoadingState, ErrorState, EmptyState } from '../components/AsyncState'

const FUNNEL_COLORS = ['#6366f1', '#818cf8', '#a5b4fc', '#f59e0b', '#34d399', '#10b981', '#059669']

function formatRate(rate: number | null): string {
  return rate === null ? '—' : `${rate}%`
}

function formatDuration(days: number | null): string {
  return days === null ? '—' : `${days}d`
}

export default function DashboardPage() {
  const { data, loading, error } = useApi(getDashboard)
  const { data: calendar } = useApi(getUpcomingCalendar)

  if (loading) return <LoadingState label="Loading dashboard…" />
  if (error) return <ErrorState error={error} />
  if (!data) return null

  const funnelData = [
    { stage: 'Discovered', count: data.analytics.funnel.discovered },
    { stage: 'Shortlisted', count: data.analytics.funnel.shortlisted },
    { stage: 'Applied', count: data.analytics.funnel.applied },
    { stage: 'Responses', count: data.analytics.funnel.responses },
    { stage: 'Interviews', count: data.analytics.funnel.interviews },
    { stage: 'Offers', count: data.analytics.funnel.offers },
    { stage: 'Accepted', count: data.analytics.funnel.accepted },
  ]

  const rates = data.analytics.conversion_rates

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-50">Dashboard</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Your job search at a glance.</p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard label="Jobs discovered" value={data.jobs.total} hint={`${data.jobs.shortlisted} shortlisted`} />
        <StatCard label="Applications" value={data.applications.total} hint={`${data.applications.submitted} submitted`} />
        <StatCard label="Under review" value={data.applications.under_review} />
        <StatCard label="Interviews" value={data.interviews.total} hint={`${data.interviews.scheduled} scheduled`} />
        <StatCard label="Offers" value={data.offers.total} />
        <StatCard label="Follow-ups due" value={data.followups.due_today} hint={`${data.followups.pending} pending`} />
      </div>

      <Card title="Application funnel" subtitle="Discovered → Shortlisted → Applied → Response → Interview → Offer → Accepted">
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={funnelData} layout="vertical" margin={{ left: 24 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} className="stroke-slate-200 dark:stroke-slate-800" />
            <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} />
            <YAxis type="category" dataKey="stage" width={90} tick={{ fontSize: 12 }} />
            <Tooltip />
            <Bar dataKey="count" radius={[0, 4, 4, 0]}>
              {funnelData.map((entry, index) => (
                <Cell key={entry.stage} fill={FUNNEL_COLORS[index % FUNNEL_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Conversion rates" subtitle="Safe-divided -- shown as — when there isn't enough data yet">
          <dl className="grid grid-cols-2 gap-y-3 text-sm">
            <dt className="text-slate-500 dark:text-slate-400">Shortlist rate</dt>
            <dd className="text-right font-medium">{formatRate(rates.shortlist_rate)}</dd>
            <dt className="text-slate-500 dark:text-slate-400">Application rate</dt>
            <dd className="text-right font-medium">{formatRate(rates.application_rate)}</dd>
            <dt className="text-slate-500 dark:text-slate-400">Response rate</dt>
            <dd className="text-right font-medium">{formatRate(rates.response_rate)}</dd>
            <dt className="text-slate-500 dark:text-slate-400">Interview rate</dt>
            <dd className="text-right font-medium">{formatRate(rates.interview_rate)}</dd>
            <dt className="text-slate-500 dark:text-slate-400">Offer rate</dt>
            <dd className="text-right font-medium">{formatRate(rates.offer_rate)}</dd>
            <dt className="text-slate-500 dark:text-slate-400">Overall offer rate</dt>
            <dd className="text-right font-medium">{formatRate(rates.overall_offer_rate)}</dd>
          </dl>
        </Card>

        <Card title="Time to..." subtitle="Days from submission, median / average">
          <dl className="grid grid-cols-3 gap-y-3 text-sm">
            <dt className="col-span-2 text-slate-500 dark:text-slate-400">First response</dt>
            <dd className="text-right font-medium">
              {formatDuration(data.analytics.time_to_response_days.median)} / {formatDuration(data.analytics.time_to_response_days.average)}
            </dd>
            <dt className="col-span-2 text-slate-500 dark:text-slate-400">First interview</dt>
            <dd className="text-right font-medium">
              {formatDuration(data.analytics.time_to_interview_days.median)} / {formatDuration(data.analytics.time_to_interview_days.average)}
            </dd>
            <dt className="col-span-2 text-slate-500 dark:text-slate-400">First offer</dt>
            <dd className="text-right font-medium">
              {formatDuration(data.analytics.time_to_offer_days.median)} / {formatDuration(data.analytics.time_to_offer_days.average)}
            </dd>
          </dl>
        </Card>
      </div>

      <Card title="Upcoming" subtitle="Interviews, follow-ups, and deadlines -- read-only, nothing is ever sent automatically">
        {!calendar || calendar.length === 0 ? (
          <EmptyState message="Nothing upcoming." />
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {calendar.slice(0, 8).map((item, index) => (
              <li key={index} className="flex items-center justify-between py-2.5 text-sm">
                <span className="text-slate-700 dark:text-slate-300">{item.message}</span>
                <span className="text-xs text-slate-400 dark:text-slate-500">{new Date(item.date).toLocaleDateString()}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
