# Job-Search Tracking, Analytics & Follow-Up Management (Step 6)

## What this is, and what it isn't

Step 6 is the central source of truth for the whole job search: which
jobs you've looked at, which you shortlisted, what you applied with,
what happened afterward, and what's coming up. It **tracks and
organizes** -- it never submits or automates an application (that's
entirely Step 5's job) and never sends a message on your behalf (follow-up
reminders are shown, never sent).

## Reused vs. new

Nothing here duplicates Steps 1-5's models. `Job` (Step 2) and
`Application` (Step 5) gained a few new columns; four small tables
(`ApplicationStatusHistory`, `ApplicationFollowUp`, `Interview`, `Offer`)
plus two note tables (`ApplicationNote`, `JobNote`) are new. `JobMatch`
(Step 2) gained `score_components`/`algorithm_version` so the per-dimension
breakdown it already computed internally is now persisted, not just used
to derive the overall score.

| Model | Change |
|---|---|
| `Job` | + `priority`, `tags`, `deadline_source`, `external_job_id`; `status` enum extended (`preparing`, `ready_to_apply`, `applied`, `withdrawn`, `closed`, `rejected`, `archived`) |
| `Application` | + `priority`, `tags`, `source`, `archived`, `material_snapshot`; `status` enum extended with the full post-submission lifecycle |
| `JobMatch` | + `score_components` (per-dimension scores), `algorithm_version` |
| `ApplicationStatusHistory` | new -- append-only, one row per transition |
| `ApplicationFollowUp` | new |
| `Interview` | new |
| `Offer` | new |
| `ApplicationNote` / `JobNote` | new |

## Status: never overwritten, never silently regressed

`tracking_service.change_application_status()` is the only way
`Application.status` changes (besides Step 5's own confirmed-submission
path, which calls the same function with `source="system"`). Every call
appends an `ApplicationStatusHistory` row -- `submitted -> under_review ->
interview -> technical_interview -> rejected` all stay visible, in order,
forever.

The same principle applies to `Job.status`: `compute_match()` (Step 2)
runs every time a match score is (re)computed, including internally when
Step 3 reports a CV's before/after match score -- naively setting
`status = MATCHED` there would silently regress a job you'd already
manually shortlisted back to "matched". `_advance_status_to_matched()`
only ever moves a job's status *forward* along the normal pipeline
(`discovered -> analyzed -> matched -> shortlisted -> preparing ->
ready_to_apply -> applied`), never backward, and never touches a
terminal/user-decided status (`withdrawn`/`closed`/`rejected`/`archived`/`skipped`).

## The material snapshot

When Step 5 confirms a submission, `tracking_service.build_material_snapshot()`
freezes the CV content, cover letter content, match score, job
description, and application URL onto `Application.material_snapshot` --
once, never overwritten afterward. The job posting can change, the CV can
get a new version, but the record of what was actually submitted stays
accurate.

## Timeline

`GET /applications/{id}/timeline` merges everything with a timestamp into
one chronological view: the job's own discovered/analyzed/matched
moments (from its own `created_at`/`extracted_at`/`JobMatch.created_at`
-- Job has no separate event log of its own), every `ApplicationEvent`
Step 5 logged, every status transition, every note, interview, follow-up,
and offer.

## Follow-ups: suggested, never sent

`GET /applications/{id}/followups/suggested` returns
`submitted_at + DEFAULT_FOLLOWUP_DAYS` (default 7, configurable via
`.env`) as a suggestion only. Nothing is created until you explicitly
`POST /applications/{id}/followups`. Nothing ever emails or messages
anyone -- `GET /notifications/upcoming` and `GET /calendar/upcoming` are
read-only surfaces for you to act on.

## Duplicate detection: a warning, not a block

`GET /jobs/{id}/duplicates` checks canonical URL, exact URL, external job
ID, and company + normalized title against every other job, and returns
candidates. It never blocks or auto-merges anything -- you decide.

## Analytics: formulas

Every number below is a plain SQL aggregation or Python calculation --
never an LLM. `None` (not `0`) is returned whenever a rate's denominator
is zero, since "0%" and "not enough data yet" are different facts.

**Funnel** (`GET /analytics/overview`) -- discovered → shortlisted →
applied → responses → interviews → offers → accepted:
- `discovered` = every `Job` row.
- `shortlisted` = jobs whose status has reached `shortlisted` or later in
  the pipeline (see "Status" above) -- a *current-status* count, not a
  "was ever shortlisted" count, since only `Application` carries full
  history.
- `applied` = applications with `submitted_at` set (robust to the status
  changing afterward).
- `responses` = applications with an `ApplicationStatusHistory` entry
  into `under_review`, `recruiter_contact`, `interview`,
  `technical_interview`, `final_interview`, `offer`, `accepted`, or
  `rejected` (a rejection is still a response; `ghosted`/`withdrawn`/
  `closed`/`failed` are not).
- `interviews` / `offers` = applications with at least one `Interview` /
  `Offer` row.
- `accepted` = `Offer` rows with `status = accepted`.

**Conversion rates** (`GET /analytics/overview`):
```
shortlist_rate      = shortlisted / discovered
application_rate    = applied / shortlisted
response_rate       = responses / applied
interview_rate      = interviews / applied
offer_rate          = offers / interviews
overall_offer_rate  = offers / applied
```

**Time-to-response/interview/offer** (`GET /analytics/overview`): for
each application, the gap in days between `submitted_at` and its first
qualifying event (first response-status transition / first interview's
`scheduled_at` or `created_at` / first offer's `created_at`). Average,
median, min, max, and count over all applications that have that event.

**Status breakdown** (`GET /analytics/status`): count of applications
per current `status`.

**Company / role / source** (`GET /analytics/companies` /
`/analytics/roles` / `/analytics/sources`): grouped by `Job.company` /
`Job.title` / `Application.source`. Each group reports applications,
interviews, offers, response rate, and average match score.

**Skill demand + gap** (`GET /analytics/skills`): counts how often each
`skill_name` appears in the technical-skill requirements of jobs you've
actually applied to, and separately lists which of those skills aren't
matched (via the same `skills_equivalent()` fuzzy matching Step 2 uses)
by anything in your Career Profile -- reported as a "potential gap," a
plain observation, never an instruction, and the profile is never
modified automatically.

**Match-score buckets** (`GET /analytics/match-scores`): applications and
interviews grouped into 90-100 / 80-89 / 70-79 / 60-69 / 0-59, to see
whether a higher match score is actually correlating with better
outcomes for you.

**CV / cover-letter version performance** (`GET /analytics/cv-versions`):
applications/interviews/offers per CV version and per cover-letter
version, labeled `"{version_name} [#{id}]"` -- the id suffix matters,
since two different versions can share the same name (e.g. two
applications to similarly-titled roles at the same company, given
`cv_customization_service`'s `"{title} - {company} - V{n}"` naming).
Always described as "observed application performance," never a causal
claim.

**Weekly / monthly** (`GET /analytics/weekly`, `/analytics/monthly`):
jobs discovered/shortlisted, applications, responses, interviews, offers
within the given (or current) calendar week/month.

## Readiness

`GET /applications/{id}/readiness` reuses Step 5's own
`submission_guard.check_ready_for_submission()` (the same check the
actual submit button is gated on) and additionally reports each
individual check (`job_valid`, `cv_approved`, `cover_letter_approved`,
`required_answers_complete`, `application_url_valid`) as a named boolean.

## Export & backup

`GET /applications/export?format=csv|json` exports non-archived
applications (company, role, URLs, status, priority, match score,
submitted date, CV/cover-letter version, latest interview/offer status,
notes) by default; `include_archived=true` includes archived ones too.

`python -m app.cli backup` (run from `career-agent/backend/`) writes a
full `pg_dump` plus a non-secret settings snapshot to
`data/backups/{UTC timestamp}/`. `DATABASE_URL` and `OPENAI_API_KEY` are
never included. The browser profile (cookies/session state) is excluded
unless you pass `--include-browser-profile`.

## Timezones

All timestamps are stored timezone-aware, in UTC (`TimestampMixin`,
`ApplicationStatusHistory.created_at`, etc.) -- never naive datetimes.
`ApplicationFollowUp.due_date`/`Job.application_deadline` are plain
calendar dates (no time component), since a due date is a day the user
picked, not a specific instant.

## Testing

`tests/test_tracking.py` builds a realistic synthetic dataset (20 jobs,
10 shortlisted, 8 applications, 3 responses, 2 interviews, 1 offer,
matching the shape used throughout this doc's examples) and verifies
every analytics formula above against hand-computed expected values, plus
status history, timeline ordering, cascading deletes, timezone-awareness,
search/sort/filter, archiving, and export. `tests/test_end_to_end.py`
drives the complete Step 1 → Step 6 workflow through the real API (mocked
AI clients, real Playwright against the local Step 5 fixture, real
submission with explicit approval) and checks the final state matches
what actually happened at every step.
