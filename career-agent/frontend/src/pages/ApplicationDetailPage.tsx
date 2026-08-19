import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  addApplicationNote,
  archiveApplication,
  getApplication,
  getApplicationIntelligence,
  getApplicationInterviews,
  getApplicationNotes,
  getApplicationOffers,
  getApplicationTimeline,
  updateApplicationStatus,
} from '../api/applications'
import { useApi } from '../hooks/useApi'
import Card from '../components/Card'
import Button from '../components/Button'
import { StatusBadge } from '../components/Badge'
import { LoadingState, ErrorState, EmptyState } from '../components/AsyncState'
import type { ApplicationStatus } from '../api/types'

const STATUS_OPTIONS: ApplicationStatus[] = [
  'under_review', 'recruiter_contact', 'interview', 'technical_interview', 'final_interview',
  'offer', 'accepted', 'rejected', 'withdrawn', 'ghosted', 'closed',
]

const inputClass = 'glass-input rounded-lg px-3 py-1.5 text-sm transition-colors duration-200'

function QualityCheck({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className={ok ? 'text-emerald-400' : 'text-slate-600'}>{ok ? '✓' : '○'}</span>
      <span className={ok ? 'text-slate-200' : 'text-slate-500'}>{label}</span>
    </div>
  )
}

const ENTRY_ICON: Record<string, string> = {
  job: '📋', event: '⚙️', status_change: '🔄', note: '📝', interview: '🎤', followup: '⏰', offer: '🎉',
}

export default function ApplicationDetailPage() {
  const { applicationId } = useParams()
  const id = Number(applicationId)

  const { data: application, loading: appLoading, error: appError, refetch: refetchApp } = useApi(() => getApplication(id), [id])
  const { data: intel } = useApi(() => getApplicationIntelligence(id), [id])
  const { data: timeline, refetch: refetchTimeline } = useApi(() => getApplicationTimeline(id), [id])
  const { data: interviews } = useApi(() => getApplicationInterviews(id), [id])
  const { data: offers } = useApi(() => getApplicationOffers(id), [id])
  const { data: notes, refetch: refetchNotes } = useApi(() => getApplicationNotes(id), [id])

  const [statusChoice, setStatusChoice] = useState('')
  const [statusReason, setStatusReason] = useState('')
  const [updatingStatus, setUpdatingStatus] = useState(false)
  const [noteText, setNoteText] = useState('')
  const [addingNote, setAddingNote] = useState(false)

  if (appLoading) return <LoadingState label="Loading application…" />
  if (appError) return <ErrorState error={appError} />
  if (!application) return null

  const handleStatusUpdate = async () => {
    if (!statusChoice) return
    setUpdatingStatus(true)
    try {
      await updateApplicationStatus(id, statusChoice, statusReason || undefined)
      setStatusChoice('')
      setStatusReason('')
      refetchApp()
      refetchTimeline()
    } finally {
      setUpdatingStatus(false)
    }
  }

  const handleAddNote = async () => {
    if (!noteText.trim()) return
    setAddingNote(true)
    try {
      await addApplicationNote(id, noteText.trim())
      setNoteText('')
      refetchNotes()
      refetchTimeline()
    } finally {
      setAddingNote(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <StatusBadge status={application.status} />
            <StatusBadge status={application.priority} />
            {application.archived && <StatusBadge status="archived" />}
          </div>
          <h1 className="gradient-text text-2xl font-bold tracking-tight">Application #{application.id}</h1>
          <p className="mt-1 text-sm text-slate-400">
            {application.source ?? 'Unknown source'}
            {application.submitted_at ? ` · submitted ${new Date(application.submitted_at).toLocaleDateString()}` : ''}
          </p>
        </div>
        <div className="flex gap-2">
          <Link to={`/jobs/${application.job_id}`}>
            <Button variant="secondary">View job</Button>
          </Link>
          <Button
            variant="ghost"
            onClick={async () => {
              await archiveApplication(id)
              refetchApp()
            }}
          >
            Archive
          </Button>
        </div>
      </div>

      {intel && (
        <Card title="Readiness" subtitle={`${Math.round(intel.quality.score * 100)}% complete`}>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <QualityCheck label="Match computed" ok={intel.quality.match_complete} />
            <QualityCheck label="CV approved" ok={intel.quality.cv_approved} />
            <QualityCheck label="Cover letter approved" ok={intel.quality.cover_letter_approved} />
            <QualityCheck label="Required fields complete" ok={intel.quality.questions_complete} />
          </div>
          {intel.followup_recommendation && (
            <p className="mt-3 border-t border-white/10 pt-3 text-sm text-violet-300">
              {intel.followup_recommendation}
            </p>
          )}
        </Card>
      )}

      <Card title="Update status" subtitle="Every change is recorded, never overwritten">
        <div className="flex flex-wrap items-end gap-3">
          <select value={statusChoice} onChange={(e) => setStatusChoice(e.target.value)} className={inputClass}>
            <option value="" className="bg-[#160f2e]">Choose new status…</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s} className="bg-[#160f2e]">
                {s.replace(/_/g, ' ')}
              </option>
            ))}
          </select>
          <input
            value={statusReason}
            onChange={(e) => setStatusReason(e.target.value)}
            placeholder="Reason (optional)…"
            className={`min-w-[220px] flex-1 ${inputClass}`}
          />
          <Button variant="primary" disabled={!statusChoice || updatingStatus} onClick={handleStatusUpdate}>
            Update
          </Button>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Timeline">
          {!timeline || timeline.entries.length === 0 ? (
            <EmptyState message="No timeline events yet." />
          ) : (
            <ol className="flex flex-col gap-3">
              {timeline.entries.map((entry, i) => (
                <li key={i} className="flex gap-3 text-sm">
                  <span className="shrink-0">{ENTRY_ICON[entry.entry_type] ?? '•'}</span>
                  <div>
                    <p className="text-slate-200">{entry.description}</p>
                    <p className="text-xs text-slate-500">{new Date(entry.timestamp).toLocaleString()}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>

        <div className="flex flex-col gap-6">
          <Card title="Interviews">
            {!interviews || interviews.length === 0 ? (
              <EmptyState message="No interviews recorded yet." />
            ) : (
              <ul className="flex flex-col gap-2">
                {interviews.map((iv) => (
                  <li key={iv.id} className="rounded-lg border border-white/10 bg-white/[0.03] p-2.5 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium capitalize text-slate-200">{iv.type.replace(/_/g, ' ')}</span>
                      <StatusBadge status={iv.status} />
                    </div>
                    {iv.scheduled_at && <p className="mt-1 text-xs text-slate-400">{new Date(iv.scheduled_at).toLocaleString()}</p>}
                    {iv.interviewer && <p className="text-xs text-slate-500">with {iv.interviewer}</p>}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Offers">
            {!offers || offers.length === 0 ? (
              <EmptyState message="No offers recorded yet." />
            ) : (
              <ul className="flex flex-col gap-2">
                {offers.map((offer) => (
                  <li key={offer.id} className="rounded-lg border border-white/10 bg-white/[0.03] p-2.5 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-slate-200">{offer.role ?? 'Role'}</span>
                      <StatusBadge status={offer.status} />
                    </div>
                    {offer.salary && (
                      <p className="mt-1 text-xs text-slate-400">
                        {offer.salary.toLocaleString()} {offer.currency}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      {intel?.interview_preparation && (
        <Card title="Interview preparation context" subtitle="Assembled from the job description, CV, and matched skills -- no invented content">
          <pre className="max-h-64 overflow-auto rounded-lg border border-white/10 bg-black/30 p-3 text-xs text-slate-400">
            {JSON.stringify(intel.interview_preparation, null, 2)}
          </pre>
        </Card>
      )}

      <Card title="Notes">
        <div className="mb-3 flex gap-2">
          <input
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            placeholder="Add a note…"
            className={`flex-1 ${inputClass}`}
            onKeyDown={(e) => e.key === 'Enter' && handleAddNote()}
          />
          <Button variant="primary" disabled={addingNote || !noteText.trim()} onClick={handleAddNote}>
            Add
          </Button>
        </div>
        {!notes || notes.length === 0 ? (
          <EmptyState message="No notes yet." />
        ) : (
          <ul className="flex flex-col gap-2">
            {notes.map((note) => (
              <li key={note.id} className="rounded-lg border border-white/10 bg-white/[0.03] p-2.5 text-sm">
                <p className="text-slate-200">{note.content}</p>
                <p className="mt-1 text-xs text-slate-500">{new Date(note.created_at).toLocaleString()}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <div>
        <Link to="/applications" className="text-sm text-violet-300 hover:text-violet-200 hover:underline">
          ← Back to applications
        </Link>
      </div>
    </div>
  )
}
