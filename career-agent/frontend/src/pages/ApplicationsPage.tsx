import { useState } from 'react'
import { Link } from 'react-router-dom'
import { searchApplications } from '../api/applications'
import { useApi } from '../hooks/useApi'
import Card from '../components/Card'
import { StatusBadge } from '../components/Badge'
import { LoadingState, ErrorState, EmptyState } from '../components/AsyncState'

const STATUS_OPTIONS = [
  '', 'not_started', 'submitted', 'under_review', 'recruiter_contact', 'interview',
  'technical_interview', 'final_interview', 'offer', 'accepted', 'rejected', 'withdrawn', 'closed',
]
const SORT_OPTIONS = [
  { value: 'newest', label: 'Newest' },
  { value: 'oldest', label: 'Oldest' },
  { value: 'highest_match', label: 'Highest match' },
  { value: 'priority', label: 'Priority' },
  { value: 'latest_status_change', label: 'Latest status change' },
]

export default function ApplicationsPage() {
  const [company, setCompany] = useState('')
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState('newest')

  const { data, loading, error } = useApi(
    () => searchApplications({ company: company || undefined, status: status || undefined, sort, limit: 50 }),
    [company, status, sort],
  )

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-50">Applications</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{data ? `${data.total} applications` : 'Search and filter applications.'}</p>
      </div>

      <div className="flex flex-wrap gap-3">
        <input
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          placeholder="Filter by company…"
          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
        />
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s === '' ? 'All statuses' : s.replace(/_/g, ' ')}
            </option>
          ))}
        </select>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
        >
          {SORT_OPTIONS.map((s) => (
            <option key={s.value} value={s.value}>
              Sort: {s.label}
            </option>
          ))}
        </select>
      </div>

      <Card>
        {loading && <LoadingState />}
        {error ? <ErrorState error={error} /> : null}
        {!loading && !error && (!data || data.items.length === 0) && <EmptyState message="No applications match these filters." />}
        {!loading && !error && data && data.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400 dark:border-slate-800">
                  <th className="pb-2 font-medium">Application</th>
                  <th className="pb-2 font-medium">Status</th>
                  <th className="pb-2 font-medium">Priority</th>
                  <th className="pb-2 font-medium">Source</th>
                  <th className="pb-2 font-medium">Submitted</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {data.items.map((application) => (
                  <tr key={application.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <td className="py-2.5">
                      <Link to={`/applications/${application.id}`} className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                        Application #{application.id}
                      </Link>
                    </td>
                    <td className="py-2.5">
                      <StatusBadge status={application.status} />
                    </td>
                    <td className="py-2.5">
                      <StatusBadge status={application.priority} />
                    </td>
                    <td className="py-2.5 text-slate-600 dark:text-slate-300">{application.source ?? '—'}</td>
                    <td className="py-2.5 text-slate-500 dark:text-slate-400">
                      {application.submitted_at ? new Date(application.submitted_at).toLocaleDateString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
