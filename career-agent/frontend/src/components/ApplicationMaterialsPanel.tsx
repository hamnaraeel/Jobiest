import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { approveCv, generateCv, getCv } from '../api/cvs'
import { approveCoverLetter, generateCoverLetter, getCoverLetter, regenerateCoverLetter } from '../api/coverLetters'
import { getApplicationMaterials } from '../api/materials'
import { applyToJob } from '../api/applications'
import { matchJob } from '../api/jobs'
import { useApi } from '../hooks/useApi'
import Card from './Card'
import Button from './Button'
import Badge from './Badge'
import { LoadingState, ErrorState } from './AsyncState'
import type { CoverLetterRead, CVVersionRead } from '../api/types'

function materialBadgeColor(status: string) {
  if (status === 'approved') return 'green' as const
  if (status === 'rejected') return 'red' as const
  if (status === 'validated') return 'blue' as const
  return 'slate' as const
}

/** Drives the full "parse -> customize CV -> write cover letter -> apply"
 * pipeline for one job. Used from both the job detail page (before an
 * application exists) and the application detail page (after) -- keyed
 * off job_id either way, since materials are generated per-job and an
 * Application just attaches whichever CV/cover-letter versions were
 * approved at the time it was created. */
export default function ApplicationMaterialsPanel({ jobId, existingApplicationId }: { jobId: number; existingApplicationId?: number }) {
  const navigate = useNavigate()
  const { data: materials, loading, error, refetch } = useApi(() => getApplicationMaterials(jobId), [jobId])

  const [cv, setCv] = useState<CVVersionRead | null>(null)
  const [coverLetter, setCoverLetter] = useState<CoverLetterRead | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [actionError, setActionError] = useState<unknown>(null)

  useEffect(() => {
    if (materials?.cv) getCv(materials.cv.id).then(setCv).catch(() => setCv(null))
    else setCv(null)
  }, [materials?.cv?.id])

  useEffect(() => {
    if (materials?.cover_letter) getCoverLetter(materials.cover_letter.id).then(setCoverLetter).catch(() => setCoverLetter(null))
    else setCoverLetter(null)
  }, [materials?.cover_letter?.id])

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label)
    setActionError(null)
    try {
      await fn()
      refetch()
    } catch (err) {
      setActionError(err)
    } finally {
      setBusy(null)
    }
  }

  // cv.generate requires the job to already have extracted requirements
  // ("analyzed") -- a job that only ever went through discovery, never
  // through the agent's search/rank pipeline, doesn't have those yet.
  // jobs.match auto-analyzes first if needed, so running it before
  // cv.generate makes "Generate CV" work from a job detail page directly
  // instead of surfacing a confusing "analyze it first" error.
  const handleGenerateCv = () => run('cv.generate', async () => {
    if (!materials?.match) await matchJob(jobId)
    return generateCv(jobId)
  })

  const handleApply = async () => {
    setBusy('apply')
    setActionError(null)
    try {
      const application = await applyToJob(jobId)
      navigate(`/applications/${application.id}`)
    } catch (err) {
      setActionError(err)
      setBusy(null)
    }
  }

  if (loading) return <LoadingState label="Loading application materials…" />
  if (error) return <ErrorState error={error} />
  if (!materials) return null

  const cvApproved = materials.cv?.status === 'approved'
  const cvReadyToApprove = materials.cv?.status === 'validated'
  const coverLetterApproved = materials.cover_letter?.status === 'approved'

  return (
    <Card
      title="Application materials"
      subtitle="Generated entirely from your Career Profile -- nothing invented, everything traceable back to a verified fact"
    >
      <div className="flex flex-col gap-5">
        {/* CV stage */}
        <div>
          <div className="mb-2 flex items-center justify-between">
            <h4 className="text-xs font-semibold uppercase text-slate-400">Tailored CV</h4>
            {materials.cv && <Badge color={materialBadgeColor(materials.cv.status)}>{materials.cv.status}</Badge>}
          </div>
          {!materials.cv && (
            <Button variant="primary" disabled={busy !== null} onClick={handleGenerateCv}>
              {busy === 'cv.generate' ? 'Generating…' : 'Generate CV'}
            </Button>
          )}
          {cv && (
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
              <p className="mb-2 text-sm leading-relaxed text-slate-300">{cv.summary}</p>
              <p className="mb-2 text-xs text-slate-500">
                {cv.skills.reduce((n, c) => n + c.skills.length, 0)} skills · {cv.experience.length} experience entries ·{' '}
                {cv.projects.length} projects
                {cv.match_score_after !== null ? ` · match ${cv.match_score_after}%` : ''}
              </p>
              {cv.warnings.length > 0 && (
                <ul className="mb-2 flex flex-col gap-1">
                  {cv.warnings.map((w, i) => (
                    <li key={i} className="flex gap-1.5 text-xs text-amber-300">
                      <span>⚠</span>
                      {w}
                    </li>
                  ))}
                </ul>
              )}
              <div className="flex flex-wrap gap-2">
                {cv.pdf_path && (
                  <a href={`/api/cvs/${cv.id}/preview`} target="_blank" rel="noreferrer">
                    <Button variant="secondary">Preview</Button>
                  </a>
                )}
                {cv.pdf_path && (
                  <a href={`/api/cvs/${cv.id}/download`} target="_blank" rel="noreferrer">
                    <Button variant="ghost">Download PDF</Button>
                  </a>
                )}
                {cvReadyToApprove && (
                  <Button variant="primary" disabled={busy !== null} onClick={() => run('cv.approve', () => approveCv(cv.id))}>
                    {busy === 'cv.approve' ? 'Approving…' : 'Approve CV'}
                  </Button>
                )}
                <Button variant="ghost" disabled={busy !== null} onClick={handleGenerateCv}>
                  {busy === 'cv.generate' ? 'Regenerating…' : 'Regenerate'}
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Cover letter stage */}
        <div>
          <div className="mb-2 flex items-center justify-between">
            <h4 className="text-xs font-semibold uppercase text-slate-400">Cover letter</h4>
            {materials.cover_letter && <Badge color={materialBadgeColor(materials.cover_letter.status)}>{materials.cover_letter.status}</Badge>}
          </div>
          {!materials.cover_letter && cvApproved && (
            <Button variant="primary" disabled={busy !== null} onClick={() => run('cl.generate', () => generateCoverLetter(jobId))}>
              {busy === 'cl.generate' ? 'Writing…' : 'Generate cover letter'}
            </Button>
          )}
          {!materials.cover_letter && !cvApproved && (
            <p className="text-sm text-slate-500">Approve the CV above first -- cover letters are written from the approved CV's content.</p>
          )}
          {coverLetter && (
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
              <p className="mb-2 whitespace-pre-line text-sm leading-relaxed text-slate-300">{coverLetter.content}</p>
              <p className="mb-2 text-xs text-slate-500">{coverLetter.word_count} words</p>
              {coverLetter.warnings.length > 0 && (
                <ul className="mb-2 flex flex-col gap-1">
                  {coverLetter.warnings.map((w, i) => (
                    <li key={i} className="flex gap-1.5 text-xs text-amber-300">
                      <span>⚠</span>
                      {w}
                    </li>
                  ))}
                </ul>
              )}
              <div className="flex flex-wrap gap-2">
                {!coverLetterApproved && (
                  <Button variant="primary" disabled={busy !== null} onClick={() => run('cl.approve', () => approveCoverLetter(coverLetter.id))}>
                    {busy === 'cl.approve' ? 'Approving…' : 'Approve'}
                  </Button>
                )}
                <Button
                  variant="ghost"
                  disabled={busy !== null}
                  onClick={() => run('cl.regenerate', () => regenerateCoverLetter(coverLetter.id))}
                >
                  {busy === 'cl.regenerate' ? 'Rewriting…' : 'Regenerate'}
                </Button>
              </div>
            </div>
          )}
        </div>

        {actionError ? <ErrorState error={actionError} /> : null}

        {/* Apply stage -- create_application attaches whichever CV/cover
            letter are APPROVED; anything less leaves them unattached, so
            the button stays disabled until both actually are. */}
        {!existingApplicationId && (
          <div className="border-t border-white/10 pt-4">
            <Button variant="primary" disabled={!cvApproved || !coverLetterApproved || busy !== null} onClick={handleApply}>
              {busy === 'apply' ? 'Creating application…' : 'Create application'}
            </Button>
            {(!cvApproved || !coverLetterApproved) && (materials.cv || materials.cover_letter) && (
              <p className="mt-2 text-xs text-slate-500">Approve both the CV and cover letter above before creating the application.</p>
            )}
          </div>
        )}
      </div>
    </Card>
  )
}
