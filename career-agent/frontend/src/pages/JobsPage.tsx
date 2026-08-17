import { useState } from 'react'
import { Link } from 'react-router-dom'
import { searchJobs } from '../api/jobs'
import { useApi } from '../hooks/useApi'
import Card from '../components/Card'
import { StatusBadge } from '../components/Badge'
import { LoadingState, ErrorState, EmptyState } from '../components/AsyncState'

const STATUS_OPTIONS = ['', 'discovered', 'analyzed', 'matched', 'shortlisted', 'preparing', 'ready_to_apply', 'applied', 'archived']
const SORT_OPTIONS = [
  { value: 'newest', label: 'Newest' },
  { value: 'oldest', label: 'Oldest' },
  { value: 'highest_match', label: 'Highest match' },
  { value: 'deadline', label: 'Deadline' },
  { value: 'priority', label: 'Priority' },
]

export default function JobsPage() {
  const [company, setCompany] = useState('')
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState('newest')

  const { data, loading, error } = useApi(
    () => searchJobs({ company: company || undefined, status: status || undefined, sort, limit: 50 }),
    [company, status, sort],
  )

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-50">Jobs</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{data ? `${data.total} jobs` : 'Search and filter jobs.'}</p>
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
        {!loading && !error && (!data || data.items.length === 0) && <EmptyState message="No jobs match these filters." />}
        {!loading && !error && data && data.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400 dark:border-slate-800">
                  <th className="pb-2 font-medium">Title</th>
                  <th className="pb-2 font-medium">Company</th>
                  <th className="pb-2 font-medium">Status</th>
                  <th className="pb-2 font-medium">Priority</th>
                  <th className="pb-2 font-medium">Deadline</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {data.items.map((job) => (
                  <tr key={job.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <td className="py-2.5">
                      <Link to={`/jobs/${job.id}`} className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                        {job.title ?? 'Untitled'}
                      </Link>
                    </td>
                    <td className="py-2.5 text-slate-600 dark:text-slate-300">{job.company ?? '—'}</td>
                    <td className="py-2.5">
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="py-2.5">
                      <StatusBadge status={job.priority} />
                    </td>
                    <td className="py-2.5 text-slate-500 dark:text-slate-400">
                      {job.application_deadline ? new Date(job.application_deadline).toLocaleDateString() : '—'}
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
