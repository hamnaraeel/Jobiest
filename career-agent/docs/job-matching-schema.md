# Job Ingestion, Analysis & Matching (Step 2)

## Pipeline

```
POST /jobs (url and/or description)
  -> fetch/clean, dedup, store Job                          [no AI]
POST /jobs/{id}/analyze
  -> 1 LLM call -> JobAnalysisResult -> JobRequirement rows  [needs OPENAI_API_KEY]
POST /jobs/{id}/match
  -> deterministic Python scoring against the career profile [no AI required]
  -> optional 2nd LLM call to phrase reasoning_summary        [falls back to a
                                                                template if no key]
```

`POST /jobs/{id}/match` calls analysis automatically if the job hasn't
been analyzed yet (`job.extracted_at is None`), so the whole pipeline runs
from one call. If it has already been analyzed, re-matching never makes
another extraction call.

## Entities

### Job (`jobs`)

Stores what was ingested and what the AI extracted. `raw_content` is the
original fetched HTML or pasted text; `description` is the cleaned text
actually sent to the LLM; `summary` and `keywords` are AI-extracted.
`canonical_url` and `description_hash` exist purely for deduplication
(see below). `duplicate_of_job_id` is a self-referential flag set after
analysis if another job with the same normalized (title, company,
location) already exists -- detection only, never a destructive merge.

`status` moves `discovered -> analyzed -> matched` automatically as the
pipeline runs. `shortlisted`/`skipped` are reserved for a later step's
user-driven actions (no endpoint sets them yet).

### JobRequirement (`job_requirements`)

One row per extracted requirement (a required skill, a preferred skill,
an experience requirement, an education requirement, a responsibility,
etc). `category` and `importance` drive both scoring weight and which
`evaluate_requirement` sub-function runs. `required` distinguishes must
have from nice to have -- see "Required vs preferred" below.

### JobMatch (`job_matches`)

One current row per job (`job_id` is unique) -- re-matching updates it in
place rather than growing a history table, which is what makes
`GET /jobs?min_score=...&recommendation=...` a plain join instead of a
"latest per job" query. Stores the full structured result: every
requirement's evaluation split into matched/partial/missing/unknown,
`critical_gaps`, `strengths`, `weaknesses`, and `reasoning_summary`.

## Deduplication

Two preventive checks run before a new `Job` row is ever created:

1. **Canonical URL match** -- `normalize_url()` lowercases the host,
   strips `www.`, trailing slash, and known tracking params
   (`utm_*`, `fbclid`, `ref`, ...), then sorts remaining query params. The
   same posting linked two different ways collapses to the same URL.
2. **Exact description-hash match** -- a SHA-256 of the cleaned text.
   Catches the same description pasted twice.

A third check runs **after** analysis, once title/company/location are
known: `find_possible_duplicate_by_identity` looks for another job with
the same normalized (title, company, location) and, if found, sets
`duplicate_of_job_id` -- flagged, not deleted, since collapsing two
independently-submitted rows automatically risks discarding data the user
explicitly provided.

## Required vs. preferred

The AI analysis prompt (`JOB_ANALYSIS_PROMPT_V1`) is explicit: a
requirement only goes in a `required_*` list if the posting states or
clearly implies it's mandatory. Soft language ("nice to have", "a plus",
"preferred", "bonus") always routes to the preferred list. This is
enforced again in code for education/certification requirements via
`_looks_preferred_language()` as a second check on top of the model's own
classification.

## Skill normalization

`normalize_skill()` lowercases, strips punctuation, and drops generic
suffix words (framework/library/language/platform/tool/toolkit), so
"PyTorch", "pytorch", and "PyTorch framework" all normalize to `pytorch`.
`skills_equivalent()` additionally checks a small, explicit alias table
(`SKILL_ALIAS_GROUPS`) for true synonyms (`k8s`/`kubernetes`,
`aws`/`amazon web services`, `hugging face transformers`/`transformers`,
...). There is no embedding-based fuzzy matching here deliberately --
every equivalence the system will claim is listed in one place and can be
read, audited, and explained. Unrelated tools (`Python`/`Java`,
`Docker`/`Kubernetes`, `PyTorch`/`TensorFlow`, `AWS`/`Azure`) are never
conflated.

## Match status definitions

| Status    | Meaning                                                        |
|-----------|-----------------------------------------------------------------|
| `matched` | Clearly supported by *verified* career information.             |
| `partial` | Evidence exists but doesn't fully confirm it (e.g. an unverified skill, a related-but-not-exact degree). |
| `missing` | The profile was checked and does not demonstrate this.          |
| `unknown` | There isn't enough information to say either way.                |

`unknown` is never converted to `matched`. Two categories are **always**
`unknown`, unconditionally: `work_authorization` and `language` -- the
Step 1 profile schema has no field for either, so evaluating them would
mean guessing, which the whole system exists to prevent. Soft skills
default toward `unknown` rather than `missing` on silence, since they are
inherently hard to verify from structured data.

## Scoring (deterministic, not LLM-judged)

`compute_match()` in `app/services/job_matching_service.py` computes a
weighted sum of eight components, each 0.0-1.0:

| Component            | Weight | What it measures |
|-----------------------|--------|-------------------|
| `required_skills`     | 30%    | Avg. status score of required `technical_skill` requirements |
| `experience`          | 20%    | Years-required vs. `profile.years_of_experience`, or text overlap if no year figure was extracted |
| `technical_alignment` | 15%    | Overlap between the job's extracted `keywords` and everything in the profile's skill index |
| `projects`             | 10%    | Fraction of required skills whose evidence specifically traces to a Project |
| `education`           | 10%    | Avg. status score of `education` requirements |
| `research`             | 5%     | Fraction of required skills whose evidence specifically traces to Research |
| `preferred_skills`    | 5%     | Avg. status score of preferred `technical_skill` requirements |
| `other_requirements`  | 5%     | Avg. status score of everything else (soft skill, certification, responsibility, location, work authorization, language, other) |

`matched=1.0, partial=0.5, unknown=0.5, missing=0.0` per requirement; a
component with zero applicable requirements defaults to `1.0` (nothing to
fail). Weights and recommendation thresholds
(`DEFAULT_WEIGHTS`, `DEFAULT_RECOMMENDATION_THRESHOLDS` in
`job_matching_service.py`) are plain dicts passed as optional arguments to
`compute_match()`, so they're trivial to override in code or tests.

`score_to_recommendation()`: `>= 75` -> `apply`, `>= 60` -> `maybe`,
else `skip`. This score is explicitly an internal alignment score against
the stored profile -- never presented as an ATS score or a hiring
probability.

## Critical requirement override

If any requirement with `importance = critical` evaluates to `missing`,
`critical_gaps` is populated and the recommendation is forced to `skip`
**regardless of the numerical score**. `importance = critical` is set
automatically when requirement text contains phrases like "must have",
"mandatory", or "security clearance", or unconditionally for every
`work_authorization` requirement (though those are always `unknown`, not
`missing`, so they don't trigger this override by themselves -- only a
category that can actually resolve to `missing`, like a required
certification, can).

## RAG readiness

`get_relevant_career_data(db, profile_id)` is the single function that
assembles a `ProfileContext` from the database. Everything downstream
(`evaluate_requirement`, scoring) only talks to that dataclass, never to
the database directly. That's the seam: a later step can replace this
function's body with an embedding similarity search (using the
`embedding` columns already reserved on Step 1's models) without touching
any matching or scoring logic.

## Cost control

One LLM call per analysis (`call_job_analysis`), validated against
`JobAnalysisResult` -- never trusted as free text. One optional LLM call
per match, only to phrase `reasoning_summary`; if it fails or no API key
is configured, `compute_match()` falls back to a deterministic
templated summary instead of raising. The score itself never involves an
LLM call.
