import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  acceptRecommendation,
  completeRecommendation,
  dismissRecommendation,
  generateRecommendations,
  listRecommendations,
} from '../api/recommendations'
import { useApi } from '../hooks/useApi'
import Card from '../components/Card'
import Button from '../components/Button'
import Badge, { StatusBadge } from '../components/Badge'
import ConfidenceBar from '../components/ConfidenceBar'
import { LoadingState, ErrorState, EmptyState } from '../components/AsyncState'
import type { RecommendationRead } from '../api/types'

const STATUS_FILTERS = ['new', 'viewed', 'accepted', 'dismissed', 'completed']

function RecommendationCard({ rec, onChange }: { rec: RecommendationRead; onChange: () => void }) {
  const [expanded, setExpanded] = useState(false)
  const [busy, setBusy] = useState(false)

  const act = async (fn: (id: number) => Promise<RecommendationRead>) => {
    setBusy(true)
    try {
      await fn(rec.id)
      onChange()
    } finally {
      setBusy(false)
    }
  }

  const relatedLink = rec.related_job_id
    ? { to: `/jobs/${rec.related_job_id}`, label: 'View job' }
    : rec.related_application_id
      ? { to: `/applications/${rec.related_application_id}`, label: 'View application' }
      : null

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 transition-colors duration-200 hover:bg-white/[0.05]">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <Badge color="purple">{rec.type.replace(/_/g, ' ')}</Badge>
            <StatusBadge status={rec.priority} />
            <StatusBadge status={rec.status} />
          </div>
          <h3 className="font-medium text-slate-100">{rec.title}</h3>
          <p className="mt-1 text-sm text-slate-300">{rec.description}</p>
          {rec.action && <p className="mt-2 text-sm font-medium text-violet-300">→ {rec.action}</p>}
        </div>
        <ConfidenceBar confidence={rec.confidence} reason={rec.confidence_reason} />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {relatedLink && (
          <Link to={relatedLink.to} className="text-xs font-medium text-violet-300 hover:text-violet-200 hover:underline">
            {relatedLink.label}
          </Link>
        )}
        <button onClick={() => setExpanded((e) => !e)} className="text-xs text-slate-500 hover:text-slate-300">
          {expanded ? 'Hide evidence' : 'Show evidence'}
        </button>
        <span className="text-xs text-slate-500" title={rec.confidence_reason}>
          {rec.confidence_reason}
        </span>
        <div className="ml-auto flex gap-2">
          {rec.status !== 'accepted' && (
            <Button variant="primary" disabled={busy} onClick={() => act(acceptRecommendation)}>
              Accept
            </Button>
          )}
          {rec.status !== 'completed' && (
            <Button variant="secondary" disabled={busy} onClick={() => act(completeRecommendation)}>
              Complete
            </Button>
          )}
          {rec.status !== 'dismissed' && (
            <Button variant="ghost" disabled={busy} onClick={() => act(dismissRecommendation)}>
              Dismiss
            </Button>
          )}
        </div>
      </div>

      {expanded && (
        <pre className="mt-3 max-h-64 overflow-auto rounded-lg border border-white/10 bg-black/30 p-3 text-xs text-slate-400">
          {JSON.stringify(rec.evidence, null, 2)}
        </pre>
      )}
    </div>
  )
}

export default function RecommendationsPage() {
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [generating, setGenerating] = useState(false)
  const { data, loading, error, refetch } = useApi(() => listRecommendations({ status: statusFilter || undefined }), [statusFilter])

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      await generateRecommendations()
      refetch()
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="gradient-text text-3xl font-bold tracking-tight">Recommendations</h1>
          <p className="mt-1 text-sm text-slate-400">
            Every recommendation carries evidence and a confidence score. Nothing here acts on its own -- you decide.
          </p>
        </div>
        <Button variant="primary" onClick={handleGenerate} disabled={generating}>
          {generating ? 'Generating…' : 'Generate recommendations'}
        </Button>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => setStatusFilter('')}
          className={`rounded-full px-3 py-1 text-xs font-medium transition-all duration-200 ${statusFilter === '' ? 'gradient-accent text-white shadow-[0_4px_16px_-4px_rgba(139,92,246,0.6)]' : 'bg-white/[0.06] text-slate-300 hover:bg-white/[0.1]'}`}
        >
          All
        </button>
        {STATUS_FILTERS.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition-all duration-200 ${statusFilter === s ? 'gradient-accent text-white shadow-[0_4px_16px_-4px_rgba(139,92,246,0.6)]' : 'bg-white/[0.06] text-slate-300 hover:bg-white/[0.1]'}`}
          >
            {s}
          </button>
        ))}
      </div>

      <Card>
        {loading && <LoadingState />}
        {error ? <ErrorState error={error} /> : null}
        {!loading && !error && (!data || data.items.length === 0) && (
          <EmptyState message="No recommendations yet -- click 'Generate recommendations' to analyze your current history." />
        )}
        {!loading && !error && data && data.items.length > 0 && (
          <div className="flex flex-col gap-3">
            {data.items.map((rec) => (
              <RecommendationCard key={rec.id} rec={rec} onChange={refetch} />
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
