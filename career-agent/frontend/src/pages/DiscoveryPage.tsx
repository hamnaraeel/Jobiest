import { useState } from 'react'
import { listDiscoveryRuns, listDiscoverySources, runDiscovery } from '../api/discovery'
import { useApi } from '../hooks/useApi'
import Card from '../components/Card'
import Button from '../components/Button'
import Badge from '../components/Badge'
import { LoadingState, ErrorState, EmptyState } from '../components/AsyncState'
import type { DiscoveryRunRead } from '../api/types'

const SOURCE_LABELS: Record<string, string> = {
  greenhouse: 'Greenhouse',
  lever: 'Lever',
  remoteok: 'RemoteOK',
  weworkremotely: 'We Work Remotely',
  adzuna: 'Adzuna',
  usajobs: 'USAJobs',
}

function SourceCard({ source, configured, requiresApiKey, note }: { source: string; configured: boolean; requiresApiKey: boolean; note: string }) {
  return (
    <div className="rounded-lg border border-slate-100 p-3 dark:border-slate-800">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-slate-800 dark:text-slate-100">{SOURCE_LABELS[source] ?? source}</span>
        <Badge color={configured ? 'green' : requiresApiKey ? 'amber' : 'slate'}>
          {configured ? 'ready' : 'needs API key'}
        </Badge>
      </div>
      <p className="text-xs text-slate-500 dark:text-slate-400">{note}</p>
    </div>
  )
}

function ResultsBreakdown({ run }: { run: DiscoveryRunRead }) {
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {Object.entries(run.results).map(([source, result]) => (
        <div key={source} className="rounded-md border border-slate-100 p-2.5 text-sm dark:border-slate-800">
          <div className="mb-1 flex items-center justify-between">
            <span className="font-medium text-slate-700 dark:text-slate-200">{SOURCE_LABELS[source] ?? source}</span>
            {result.error ? <Badge color="red">error</Badge> : <Badge color="blue">{result.found} found</Badge>}
          </div>
          {result.error ? (
            <p className="text-xs text-rose-600 dark:text-rose-400">{result.error}</p>
          ) : result.note ? (
            <p className="text-xs text-slate-400">{result.note}</p>
          ) : (
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {result.created} new · {result.duplicate} already known
            </p>
          )}
        </div>
      ))}
    </div>
  )
}

export default function DiscoveryPage() {
  const { data: sources, loading: sourcesLoading, error: sourcesError } = useApi(listDiscoverySources)
  const { data: runsData, loading: runsLoading, error: runsError, refetch: refetchRuns } = useApi(() => listDiscoveryRuns({ limit: 10 }))

  const [running, setRunning] = useState(false)
  const [lastRun, setLastRun] = useState<DiscoveryRunRead | null>(null)
  const [runError, setRunError] = useState<unknown>(null)

  const handleRun = async () => {
    setRunning(true)
    setRunError(null)
    try {
      const run = await runDiscovery()
      setLastRun(run)
      refetchRuns()
    } catch (err) {
      setRunError(err)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-50">Discovery</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Searches public job sources using your target roles, locations, and companies (configured via
            your career profile and job-search goals) and stores new matches as jobs. LinkedIn and Indeed
            aren't included -- both prohibit automated scraping, so those stay a manual paste/URL flow on
            the Jobs page.
          </p>
        </div>
        <Button variant="primary" onClick={handleRun} disabled={running}>
          {running ? 'Running…' : 'Run discovery now'}
        </Button>
      </div>

      {runError ? <ErrorState error={runError} /> : null}

      {lastRun && (
        <Card title="Latest run" subtitle={`${lastRun.jobs_found} found · ${lastRun.jobs_created} new`}>
          <ResultsBreakdown run={lastRun} />
        </Card>
      )}

      <Card title="Sources">
        {sourcesLoading && <LoadingState />}
        {sourcesError ? <ErrorState error={sourcesError} /> : null}
        {sources && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {sources.map((s) => (
              <SourceCard key={s.source} source={s.source} configured={s.configured} requiresApiKey={s.requires_api_key} note={s.note} />
            ))}
          </div>
        )}
      </Card>

      <Card title="Run history">
        {runsLoading && <LoadingState />}
        {runsError ? <ErrorState error={runsError} /> : null}
        {!runsLoading && !runsError && (!runsData || runsData.items.length === 0) && (
          <EmptyState message="No discovery runs yet -- click 'Run discovery now' to search." />
        )}
        {runsData && runsData.items.length > 0 && (
          <ol className="flex flex-col gap-3">
            {runsData.items.map((run) => (
              <li key={run.id} className="rounded-md border border-slate-100 p-3 dark:border-slate-800">
                <div className="mb-2 flex items-center justify-between gap-2 text-sm">
                  <span className="font-medium text-slate-700 dark:text-slate-200">
                    {new Date(run.started_at).toLocaleString()}
                  </span>
                  <div className="flex items-center gap-2">
                    <Badge color={run.trigger === 'manual' ? 'blue' : 'purple'}>{run.trigger}</Badge>
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      {run.jobs_found} found · {run.jobs_created} new
                    </span>
                  </div>
                </div>
                <ResultsBreakdown run={run} />
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  )
}
