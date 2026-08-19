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

const inputClass = 'glass-input rounded-lg px-3 py-1.5 text-sm transition-colors duration-200'

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
        <h1 className="gradient-text text-3xl font-bold tracking-tight">Applications</h1>
        <p className="mt-1 text-sm text-slate-400">{data ? `${data.total} applications` : 'Search and filter applications.'}</p>
      </div>

      <div className="flex flex-wrap gap-3">
        <input
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          placeholder="Filter by company…"
          className={inputClass}
        />
        <select value={status} onChange={(e) => setStatus(e.target.value)} className={inputClass}>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s} className="bg-[#160f2e]">
              {s === '' ? 'All statuses' : s.replace(/_/g, ' ')}
            </option>
          ))}
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value)} className={inputClass}>
          {SORT_OPTIONS.map((s) => (
            <option key={s.value} value={s.value} className="bg-[#160f2e]">
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
                <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="pb-2 font-medium">Application</th>
                  <th className="pb-2 font-medium">Status</th>
                  <th className="pb-2 font-medium">Priority</th>
                  <th className="pb-2 font-medium">Source</th>
                  <th className="pb-2 font-medium">Submitted</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.06]">
                {data.items.map((application) => (
                  <tr key={application.id} className="transition-colors duration-150 hover:bg-white/[0.04]">
                    <td className="py-2.5">
                      <Link to={`/applications/${application.id}`} className="font-medium text-violet-300 hover:text-violet-200 hover:underline">
                        Application #{application.id}
                      </Link>
                    </td>
                    <td className="py-2.5">
                      <StatusBadge status={application.status} />
                    </td>
                    <td className="py-2.5">
                      <StatusBadge status={application.priority} />
                    </td>
                    <td className="py-2.5 text-slate-300">{application.source ?? '—'}</td>
                    <td className="py-2.5 text-slate-400">
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
