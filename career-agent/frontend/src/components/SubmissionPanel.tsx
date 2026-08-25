import { useState } from 'react'
import {
  analyzeApplicationPage,
  approveApplicationSubmission,
  cancelApplication,
  fillApplication,
  getApplicationReview,
  pauseApplication,
  resumeApplication,
  startBrowser,
  submitApplication,
} from '../api/applications'
import Card from './Card'
import Button from './Button'
import { StatusBadge } from './Badge'
import { ErrorState } from './AsyncState'
import type { ApplicationRead, ApplicationReviewResponse, FillResultResponse, PageAnalysisResponse, SubmitResultResponse } from '../api/types'

const ACTIVE_STATUSES = ['browser_open', 'filling', 'needs_user_input', 'ready_for_review', 'approved_for_submission']

/** Drives Step 5's browser-assisted submission flow (start -> analyze ->
 * fill -> review -> approve -> submit). Every one of these calls a real
 * backend endpoint that opens/drives an actual local browser window --
 * this panel is the same gated flow the API always enforced, just made
 * clickable. A real submit still requires DRY_RUN disabled AND the
 * explicit approve-submission step below; nothing here bypasses that. */
export default function SubmissionPanel({ application, onChanged }: { application: ApplicationRead; onChanged: () => void }) {
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [pageInfo, setPageInfo] = useState<PageAnalysisResponse | null>(null)
  const [fillResult, setFillResult] = useState<FillResultResponse | null>(null)
  const [review, setReview] = useState<ApplicationReviewResponse | null>(null)
  const [submitResult, setSubmitResult] = useState<SubmitResultResponse | null>(null)

  const run = async <T,>(label: string, fn: () => Promise<T>, onSuccess?: (result: T) => void) => {
    setBusy(label)
    setError(null)
    try {
      const result = await fn()
      onSuccess?.(result)
      onChanged()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(null)
    }
  }

  if (!application.cv_version_id || !application.cover_letter_id) {
    return (
      <Card title="Submission" subtitle="Browser-assisted fill and submit">
        <p className="text-sm text-slate-500">
          This application has no approved CV/cover letter attached yet -- generate and approve materials above first.
        </p>
      </Card>
    )
  }

  return (
    <Card title="Submission" subtitle="Browser-assisted fill and submit -- a real submit still requires DRY_RUN off and your explicit approval">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={application.status} />
          {application.application_url && (
            <a href={application.application_url} target="_blank" rel="noreferrer" className="text-xs text-indigo-300 hover:underline">
              {application.application_url}
            </a>
          )}
        </div>

        {error ? <ErrorState error={error} /> : null}

        <div className="flex flex-wrap gap-2">
          {application.status === 'not_started' && (
            <Button variant="primary" disabled={busy !== null} onClick={() => run('start', () => startBrowser(application.id))}>
              {busy === 'start' ? 'Opening browser…' : 'Start browser'}
            </Button>
          )}

          {ACTIVE_STATUSES.includes(application.status) && (
            <>
              <Button
                variant="secondary"
                disabled={busy !== null}
                onClick={() => run('analyze', () => analyzeApplicationPage(application.id), setPageInfo)}
              >
                {busy === 'analyze' ? 'Analyzing…' : 'Analyze page'}
              </Button>
              <Button variant="secondary" disabled={busy !== null} onClick={() => run('fill', () => fillApplication(application.id), setFillResult)}>
                {busy === 'fill' ? 'Filling…' : 'Fill fields'}
              </Button>
              <Button
                variant="secondary"
                disabled={busy !== null}
                onClick={() => run('review', () => getApplicationReview(application.id), setReview)}
              >
                {busy === 'review' ? 'Loading…' : 'Review fields'}
              </Button>
              <Button variant="ghost" disabled={busy !== null} onClick={() => run('pause', () => pauseApplication(application.id))}>
                Pause
              </Button>
              <Button variant="danger" disabled={busy !== null} onClick={() => run('cancel', () => cancelApplication(application.id))}>
                Cancel
              </Button>
            </>
          )}

          {application.status === 'needs_user_input' && (
            <Button variant="secondary" disabled={busy !== null} onClick={() => run('resume', () => resumeApplication(application.id))}>
              Resume
            </Button>
          )}

          {review?.ready_for_submission && application.status !== 'approved_for_submission' && (
            <Button
              variant="primary"
              disabled={busy !== null}
              onClick={() => run('approve', () => approveApplicationSubmission(application.id))}
            >
              {busy === 'approve' ? 'Approving…' : 'Approve submission'}
            </Button>
          )}

          {application.status === 'approved_for_submission' && (
            <Button variant="primary" disabled={busy !== null} onClick={() => run('submit', () => submitApplication(application.id), setSubmitResult)}>
              {busy === 'submit' ? 'Submitting…' : 'Submit'}
            </Button>
          )}
        </div>

        {pageInfo && (
          <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-sm">
            <p className="text-slate-300">{pageInfo.title}</p>
            {pageInfo.captcha_detected && <p className="mt-1 text-amber-300">⚠ CAPTCHA detected ({pageInfo.captcha_indicator}) -- needs manual handling.</p>}
            {pageInfo.login_required && <p className="mt-1 text-amber-300">⚠ Login required on this page.</p>}
          </div>
        )}

        {fillResult && (
          <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-sm text-slate-300">
            {fillResult.filled.length} filled · {fillResult.uploaded.length} uploaded · {fillResult.needs_user_input.length} need your input
          </div>
        )}

        {review && (
          <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
            <p className="mb-2 text-sm text-slate-300">
              {review.ready_for_submission ? 'Ready for submission.' : 'Not ready for submission yet.'}
            </p>
            {review.warnings.length > 0 && (
              <ul className="mb-2 flex flex-col gap-1">
                {review.warnings.map((w, i) => (
                  <li key={i} className="text-xs text-amber-300">
                    ⚠ {w}
                  </li>
                ))}
              </ul>
            )}
            {review.fields.length > 0 && (
              <ul className="flex flex-col gap-1">
                {review.fields.map((f) => (
                  <li key={f.id} className="flex items-center justify-between text-xs text-slate-400">
                    <span>{f.label ?? f.field_identifier}</span>
                    <span className={f.user_review_required ? 'text-amber-300' : 'text-slate-500'}>{f.status}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {submitResult && (
          <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-sm">
            {submitResult.dry_run ? (
              <p className="text-amber-300">Dry run -- nothing was actually submitted. {submitResult.reason}</p>
            ) : submitResult.submitted ? (
              <p className="text-emerald-300">Submitted. {submitResult.confirmation_reference}</p>
            ) : (
              <p className="text-rose-300">Not submitted. {submitResult.reason}</p>
            )}
          </div>
        )}
      </div>
    </Card>
  )
}
