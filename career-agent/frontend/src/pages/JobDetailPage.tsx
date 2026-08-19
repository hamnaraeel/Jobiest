import { useParams, Link } from 'react-router-dom'
import { archiveJob, getJob, getJobIntelligence } from '../api/jobs'
import { useApi } from '../hooks/useApi'
import Card from '../components/Card'
import Button from '../components/Button'
import Badge, { StatusBadge } from '../components/Badge'
import ConfidenceBar from '../components/ConfidenceBar'
import { LoadingState, ErrorState } from '../components/AsyncState'

function ScorePanel({
  title,
  score,
  reasons,
  warnings,
  confidence,
  confidenceReason,
}: {
  title: string
  score: number
  reasons: string[]
  warnings: string[]
  confidence?: number
  confidenceReason?: string
}) {
  return (
    <Card title={title}>
      <div className="mb-3 flex items-baseline gap-2">
        <span className="gradient-text text-3xl font-bold">{score}</span>
        <span className="text-sm text-slate-500">/ 100</span>
        {confidence !== undefined && <ConfidenceBar confidence={confidence} reason={confidenceReason} />}
      </div>
      {reasons.length > 0 && (
        <ul className="mb-2 flex flex-col gap-1">
          {reasons.map((r, i) => (
            <li key={i} className="flex gap-2 text-sm text-slate-300">
              <span className="text-emerald-400">✓</span>
              {r}
            </li>
          ))}
        </ul>
      )}
      {warnings.length > 0 && (
        <ul className="flex flex-col gap-1 border-t border-white/10 pt-2">
          {warnings.map((w, i) => (
            <li key={i} className="flex gap-2 text-sm text-amber-300">
              <span>⚠</span>
              {w}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

export default function JobDetailPage() {
  const { jobId } = useParams()
  const id = Number(jobId)
  const { data: job, loading: jobLoading, error: jobError, refetch } = useApi(() => getJob(id), [id])
  const { data: intel, loading: intelLoading, error: intelError } = useApi(() => getJobIntelligence(id), [id])

  if (jobLoading) return <LoadingState label="Loading job…" />
  if (jobError) return <ErrorState error={jobError} />
  if (!job) return null

  const matchAnalysis = intel?.match_analysis as { matched?: string[]; partial?: string[]; missing?: string[]; overall_score?: number } | undefined

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <StatusBadge status={job.status} />
            <StatusBadge status={job.priority} />
          </div>
          <h1 className="gradient-text text-2xl font-bold tracking-tight">{job.title ?? 'Untitled role'}</h1>
          <p className="mt-1 text-sm text-slate-400">
            {job.company ?? 'Unknown company'} {job.location ? `· ${job.location}` : ''}
          </p>
        </div>
        <div className="flex gap-2">
          {job.url && (
            <a href={job.url} target="_blank" rel="noreferrer">
              <Button variant="secondary">View posting</Button>
            </a>
          )}
          <Button
            variant="ghost"
            onClick={async () => {
              await archiveJob(id)
              refetch()
            }}
          >
            Archive
          </Button>
        </div>
      </div>

      {job.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {job.tags.map((tag) => (
            <Badge key={tag} color="blue">
              {tag}
            </Badge>
          ))}
        </div>
      )}

      {intelLoading && <LoadingState label="Loading intelligence…" />}
      {intelError ? <ErrorState error={intelError} /> : null}
      {intel && (
        <>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <ScorePanel
              title="Priority score"
              score={intel.priority.score}
              reasons={intel.priority.reasons}
              warnings={intel.priority.warnings}
              confidence={intel.priority.confidence}
              confidenceReason={intel.priority.confidence_reason}
            />
            <ScorePanel
              title="Application opportunity score"
              score={intel.opportunity.score}
              reasons={intel.opportunity.reasons}
              warnings={intel.opportunity.warnings}
            />
          </div>

          {matchAnalysis && (
            <Card title="Requirement match" subtitle={matchAnalysis.overall_score !== undefined ? `Overall: ${matchAnalysis.overall_score}%` : undefined}>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div>
                  <h4 className="mb-1.5 text-xs font-semibold uppercase text-emerald-400">Matched</h4>
                  <ul className="flex flex-col gap-1 text-sm text-slate-300">
                    {(matchAnalysis.matched ?? []).map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h4 className="mb-1.5 text-xs font-semibold uppercase text-amber-400">Partial</h4>
                  <ul className="flex flex-col gap-1 text-sm text-slate-300">
                    {(matchAnalysis.partial ?? []).map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h4 className="mb-1.5 text-xs font-semibold uppercase text-rose-400">Missing</h4>
                  <ul className="flex flex-col gap-1 text-sm text-slate-300">
                    {(matchAnalysis.missing ?? []).map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </Card>
          )}

          {intel.cv_recommendations.length > 0 && (
            <Card title="CV recommendations" subtitle="Only ever suggests what your Career Profile already supports">
              <ul className="flex flex-col gap-2 text-sm text-slate-300">
                {intel.cv_recommendations.map((rec, i) => (
                  <li key={i}>{rec}</li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}

      {job.description && (
        <Card title="Job description">
          <p className="whitespace-pre-line text-sm text-slate-300">{job.description}</p>
        </Card>
      )}

      <div>
        <Link to="/jobs" className="text-sm text-violet-300 hover:text-violet-200 hover:underline">
          ← Back to jobs
        </Link>
      </div>
    </div>
  )
}
