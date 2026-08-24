import { useRef, useState } from 'react'
import { confirmResumeImport, getProfile, listResumeImports, rejectResumeImport, uploadResume } from '../api/profile'
import { useApi } from '../hooks/useApi'
import { ApiError } from '../api/client'
import Card from '../components/Card'
import Button from '../components/Button'
import Badge from '../components/Badge'
import { LoadingState, ErrorState, EmptyState } from '../components/AsyncState'
import type { ResumeImportRead } from '../api/types'

function isNotFound(error: unknown) {
  return error instanceof ApiError && error.status === 404
}

function parsedCounts(data: Record<string, unknown>) {
  const listLen = (key: string) => (Array.isArray(data[key]) ? (data[key] as unknown[]).length : 0)
  return {
    skills: listLen('skills'),
    experience: listLen('experience'),
    education: listLen('education'),
    projects: listLen('projects'),
    certifications: listLen('certifications'),
  }
}

function ResumeImportCard({ item, onChanged }: { item: ResumeImportRead; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const counts = parsedCounts(item.parsed_data)
  const name = typeof item.parsed_data.full_name === 'string' ? item.parsed_data.full_name : item.filename

  const handleConfirm = async () => {
    setBusy(true)
    setError(null)
    try {
      await confirmResumeImport(item.id)
      onChanged()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  const handleReject = async () => {
    setBusy(true)
    setError(null)
    try {
      await rejectResumeImport(item.id)
      onChanged()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3.5">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-slate-100">{name}</p>
          <p className="text-xs text-slate-500">{item.filename}</p>
        </div>
        <Badge color="amber">pending review</Badge>
      </div>
      <p className="mb-3 text-xs text-slate-400">
        {counts.skills} skills · {counts.experience} experience · {counts.education} education · {counts.projects} projects ·{' '}
        {counts.certifications} certifications
      </p>
      {item.warnings.length > 0 && (
        <ul className="mb-3 flex flex-col gap-1">
          {item.warnings.map((w, i) => (
            <li key={i} className="flex gap-2 text-xs text-amber-300">
              <span>⚠</span>
              {w}
            </li>
          ))}
        </ul>
      )}
      {error ? <ErrorState error={error} /> : null}
      <div className="flex gap-2">
        <Button variant="primary" onClick={handleConfirm} disabled={busy}>
          {busy ? 'Working…' : 'Confirm into profile'}
        </Button>
        <Button variant="danger" onClick={handleReject} disabled={busy}>
          Reject
        </Button>
      </div>
    </div>
  )
}

export default function ProfilePage() {
  const { data: profile, loading: profileLoading, error: profileError, refetch: refetchProfile } = useApi(getProfile)
  const { data: importsData, loading: importsLoading, error: importsError, refetch: refetchImports } = useApi(listResumeImports)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<unknown>(null)

  const handleFileChosen = async (file: File) => {
    setUploading(true)
    setUploadError(null)
    try {
      await uploadResume(file)
      refetchImports()
    } catch (err) {
      setUploadError(err)
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleChanged = () => {
    refetchImports()
    refetchProfile()
  }

  const pendingImports = importsData?.items.filter((i) => i.status === 'pending_review') ?? []

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="gradient-text text-3xl font-bold tracking-tight">Profile</h1>
        <p className="mt-1 text-sm text-slate-400">
          Your Career Profile is the source of truth every generated CV, cover letter, and match score is grounded
          in. Upload a resume to extract skills, experience, and education for review -- nothing is written until you
          confirm it.
        </p>
      </div>

      <Card
        title="Upload resume"
        subtitle="PDF, .txt, or .md. AI-extracted facts land here as a pending review, never written directly."
      >
        <div className="flex items-center gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.txt,.md"
            disabled={uploading}
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) handleFileChosen(file)
            }}
            className="flex-1 cursor-pointer rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-300 file:mr-3 file:cursor-pointer file:rounded-md file:border-0 file:bg-white/[0.08] file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-slate-100 hover:file:bg-white/[0.14]"
          />
          {uploading && <span className="shrink-0 text-sm text-slate-400">Parsing…</span>}
        </div>
        {uploadError ? (
          <div className="mt-3">
            <ErrorState error={uploadError} />
          </div>
        ) : null}
      </Card>

      {(importsLoading || pendingImports.length > 0 || Boolean(importsError)) && (
        <Card title="Pending review" subtitle="Confirm to write these into your Career Profile, or reject to discard.">
          {importsLoading && <LoadingState />}
          {importsError ? <ErrorState error={importsError} /> : null}
          {!importsLoading && !importsError && pendingImports.length === 0 && (
            <EmptyState message="Nothing pending -- uploads you confirm or reject disappear from this list." />
          )}
          {pendingImports.length > 0 && (
            <div className="flex flex-col gap-3">
              {pendingImports.map((item) => (
                <ResumeImportCard key={item.id} item={item} onChanged={handleChanged} />
              ))}
            </div>
          )}
        </Card>
      )}

      <Card title="Career Profile">
        {profileLoading && <LoadingState />}
        {profileError && !isNotFound(profileError) ? <ErrorState error={profileError} /> : null}
        {isNotFound(profileError) && (
          <EmptyState message="No profile yet -- upload a resume above and confirm it to create one." />
        )}
        {profile && (
          <div className="flex flex-col gap-4">
            <div>
              <h3 className="text-lg font-semibold text-slate-50">{profile.full_name}</h3>
              <p className="text-sm text-slate-400">{profile.professional_title}</p>
            </div>
            <div className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
              <p className="text-slate-300">
                <span className="text-slate-500">Email </span>
                {profile.email}
              </p>
              {profile.phone && (
                <p className="text-slate-300">
                  <span className="text-slate-500">Phone </span>
                  {profile.phone}
                </p>
              )}
              {(profile.city || profile.country) && (
                <p className="text-slate-300">
                  <span className="text-slate-500">Location </span>
                  {[profile.city, profile.country].filter(Boolean).join(', ')}
                </p>
              )}
              {profile.years_of_experience !== null && (
                <p className="text-slate-300">
                  <span className="text-slate-500">Experience </span>
                  {profile.years_of_experience} years
                </p>
              )}
              {profile.linkedin_url && (
                <p className="truncate text-slate-300">
                  <span className="text-slate-500">LinkedIn </span>
                  <a href={profile.linkedin_url} target="_blank" rel="noreferrer" className="text-indigo-300 hover:underline">
                    {profile.linkedin_url}
                  </a>
                </p>
              )}
              {profile.github_url && (
                <p className="truncate text-slate-300">
                  <span className="text-slate-500">GitHub </span>
                  <a href={profile.github_url} target="_blank" rel="noreferrer" className="text-indigo-300 hover:underline">
                    {profile.github_url}
                  </a>
                </p>
              )}
            </div>
            {profile.target_roles.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {profile.target_roles.map((role) => (
                  <Badge key={role} color="blue">
                    {role}
                  </Badge>
                ))}
              </div>
            )}
            {profile.current_summary && <p className="text-sm leading-relaxed text-slate-300">{profile.current_summary}</p>}
          </div>
        )}
      </Card>
    </div>
  )
}
