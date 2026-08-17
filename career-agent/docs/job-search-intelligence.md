# Job Search Intelligence, Optimization & Recommendations (Step 7)

## What this is, and what it isn't

Step 7 turns Steps 1-6's stored history into recommendations: which
jobs to prioritize, which skills to learn, which CV/source/role has
performed best, why rejections might be happening, and how to prepare
for an upcoming interview. It is an **advisory** layer -- every
recommendation is a suggestion the user can accept, dismiss, or ignore,
never an action taken on their behalf. Step 7 never applies to a job,
submits anything, edits the Career Profile, or contacts anyone; it only
recommends, and only the user decides (spec section 57).

Every recommendation carries four things, always:

- **WHAT** -- `title` (e.g. "Prioritize this job")
- **WHY** -- `description` (e.g. "Your profile matches 91% of the
  required skills")
- **EVIDENCE** -- `evidence`, the concrete numbers behind the claim
- **CONFIDENCE** -- `confidence` (0.0-1.0) + `confidence_reason`

## Reused vs. new

Nothing here recomputes what Steps 1-6 already computed. `app/intelligence/`
reads Job/JobMatch/Application/Interview/Offer/CVVersion and Step 6's own
`analytics_service` functions (promoted to public where reused:
`applications_with_relations`, `has_response`), and layers ranking,
gap-detection, and natural-language explanation on top. Two small,
genuinely new pieces of storage: the `Recommendation` model, and
`UserJobSearchGoal` (plus `Application.rejection_reason`/
`rejection_reason_custom`, only ever set by the user).

## The intelligence package

```
app/intelligence/
  confidence.py               Small-sample-protected confidence scoring (spec 38-40)
  job_prioritizer.py           Deterministic priority score + opportunity score (spec 6-10)
  skill_gap_analyzer.py        Demand/gap ranking: frequency x importance x relevance (spec 16-18)
  cv_analyzer.py                Profile-vs-CV gaps, job-vs-CV gaps, keyword coverage (spec 13-15)
  rejection_analyzer.py        Rejection pattern analysis (spec 19-21)
  career_insights.py           Company/source/role strategy, career direction, weekly review (spec 22-26, 33-34)
  application_analyzer.py      Per-job/per-application intelligence assembly (spec 32, 47)
  interview_analyzer.py        Interview prep context/output, question + answer generation (spec 27-31)
  recommendation_explainer.py  LLM explanation layer + output validation (spec 41-44)
```

`app/services/recommendation_engine.py` is the only place that writes
`Recommendation` rows -- every analyzer above only computes and returns
data. `app/services/goal_service.py` handles `UserJobSearchGoal` CRUD and
progress comparison.

## Confidence & small-sample protection

Two flavors (`app/intelligence/confidence.py`):

- **`confidence_from_sample_size(n)`** -- for historical/statistical
  observations. Below `SMALL_SAMPLE_THRESHOLD` (10) data points,
  confidence is capped low (max 0.45) and `confidence_reason` says so
  explicitly ("Early signal only..."). At or above 10, confidence climbs
  from 0.5 toward 0.95 as the sample grows (`n=32` gives ~0.83, matching
  spec section 38's own example).
- **`confidence_from_completeness(known, total)`** -- for a single job's
  priority score, based on how many of the scoring inputs were actually
  available (missing salary/location/deadline data lowers confidence
  without needing a large historical sample).

## Job prioritization (spec sections 6-10)

`job_prioritizer.compute_priority()` is a plain weighted sum, never an
LLM call. Default weights (`DEFAULT_PRIORITY_WEIGHTS`, overridable per
call, same pattern as `job_matching_service.DEFAULT_WEIGHTS`):

```
match_score               35%
required_skill_coverage   20%
role_preference            15%
experience_fit             10%
location_fit                5%
deadline                    5%
company_performance         5%
source_performance          5%
```

Each factor is only included if its input was actually available (e.g.
no salary means the salary-derived factor is simply omitted, not
guessed) -- the weighted average renormalizes over whatever factors were
actually scored, and `confidence_from_completeness()` reports how much
of the full input set that was. Every factor that *was* used produces a
human-readable reason string, and every unavailable/notable input (e.g.
"Salary unknown") becomes an explicit warning -- never silently dropped.

`compute_opportunity_score()` is a separate, smaller weighted score
(fit, company/source performance, profile strength) explicitly named
"Application Opportunity Score," never framed as a hiring probability --
it always carries a warning that competitive pressure (how many other
candidates, employer screening criteria) is unknown and not factored in
(spec section 10).

## Skill gaps (spec sections 16-18)

`skill_gap_analyzer.analyze_skill_gaps()` looks at every job with
extracted requirements (not just ones applied to -- this is about market
demand), counts skill-name frequency, and ranks by:

```
priority_score = demand_ratio x importance_score x relevance_score
```

- `demand_ratio` -- fraction of analyzed jobs requesting the skill.
- `importance_score` -- average of each requirement's importance
  (critical=1.0, high=0.75, medium=0.5, low=0.25).
- `relevance_score` -- fraction of that demand coming from jobs matching
  the user's configured target roles (1.0 if no target roles are
  configured, since relevance can't be discounted without a baseline).

`priority_score >= 0.5` is High, `>= 0.25` Medium, else Low. Skills the
Career Profile already has (matched via the same `skills_equivalent()`
fuzzy matching Step 2 uses) are marked `has_skill=True` and never
suggested as something to learn.

## CV analysis (spec sections 13-15)

`cv_analyzer.analyze_profile_vs_cv()` compares a CV version's stored
content against the Career Profile directly -- missing skills, missing
projects, missing achievements, and duplicate bullets (same text
appearing twice). Every "missing skill" suggestion is phrased as
*"Potential improvement: include X if it's relevant... it's in your
Career Profile but not on this CV"* -- never as an instruction to add an
unverified claim. Unsupported-claim detection isn't reimplemented here:
`CVVersion.warnings` (already computed deterministically by
`cv_validation_service` at generation time) is surfaced directly.

`cv_analyzer.analyze_job_cv_gap()` reuses `JobMatch`'s own matched/
partial/missing requirement lists for a specific job, and separately
computes keyword coverage (`Job.keywords` vs. words actually present in
the CV's bullets/skills/summary) -- a missing keyword is only flagged as
addable if a Career Profile skill actually supports it
(`supportable_missing_keywords`).

## Rejection & response patterns (spec sections 19-23)

`rejection_analyzer.analyze_rejections()` looks only at applications
with `status = rejected`, breaks down `Application.rejection_reason`
(user-recorded only -- `PATCH /applications/{id}/rejection-reason`), and
checks whether low match scores are overrepresented among them. Every
finding is phrased as "observed pattern," never a causal claim (spec
section 40) -- e.g. *"Consider focusing more heavily on roles with
stronger requirement alignment,"* never *"low match scores cause
rejection."*

`career_insights.company_strategy()` / `source_strategy()` /
`role_strategy()` pick the best-observed group by response rate, reusing
Step 6's `company_analytics()`/`source_analytics()`/`role_analytics()`
directly, wrapped with small-sample-protected confidence and cautious
phrasing ("Early signal... not enough historical data yet" below the
threshold).

## The LLM layer (spec sections 41-44)

The **only** two things the local Ollama model is used for in Step 7:

1. **Explaining already-computed evidence in natural language**
   (`recommendation_explainer.explain()`).
2. **Generating interview questions and draft answers**
   (`interview_analyzer.generate_questions()` /
   `generate_answer()`).

The LLM is never given raw rows to calculate a statistic from, and never
asked to produce a number itself. Pipeline:

```
deterministic analytics -> structured evidence (dict) -> local LLM -> explanation -> VALIDATION
```

**Validation** (`recommendation_explainer.validate_explanation()`):
splits the LLM's explanation into sentences, and discards any sentence
containing a number that doesn't appear anywhere in the supplied
evidence (including percentage-equivalents of fractions, e.g. `0.33` ->
also allows `"33"`). This is deliberately blunt -- it can't verify
semantic truth, but it reliably catches the single most dangerous
failure mode (a fabricated statistic). If nothing survives validation,
the caller's already-computed deterministic fallback text is used
instead -- the LLM is an enhancement, never a dependency; every
recommendation's `description` is always the deterministic text
regardless of whether the LLM explanation layer is invoked on top.

Interview-answer generation reuses Step 4's exact hallucination-check
validator (`answer_validation_service.validate_generated_text()`) --
the same "never invent a skill/metric/company claim" rule that already
governs cover letters and application answers. `validated: false` plus
`validation_issues` are returned to the caller rather than silently
serving a possibly-fabricated answer.

## Recommendations (spec sections 4-9, 45)

`recommendation_engine.generate_all()` runs every analyzer and
`_upsert()`s the results: a pending (`new`/`viewed`) recommendation of
the same type for the same job/application is updated in place on
regeneration rather than duplicated, while anything the user has already
acted on (`accepted`/`dismissed`/`completed`) is left untouched. Types:
`job_priority` (score >= 65), `job_skip` (score < 40 -- always phrased
as "low-priority," with an explicit note that the user can still choose
to apply), `skill_gap`, `cv_improvement`, `followup` (submitted
applications past their suggested follow-up date with none recorded
yet), `rejection_pattern`, `source_strategy`.

`GET/POST /intelligence/recommendations*` expose listing, fetching
(marks `new` -> `viewed`), and the accept/dismiss/complete feedback
loop (spec section 37) -- feedback is stored for future ranking
improvements, never used to silently modify the Career Profile.

## User goals (spec sections 35-36)

`UserJobSearchGoal` is single-user, like `CareerProfile` -- nothing is
assumed; `PUT /intelligence/goals` is the only way it's ever populated,
and only the fields actually supplied are changed (partial update,
`exclude_unset=True`). `GET /intelligence/goals/progress` compares
actual recent velocity against the configured goal and reports a
percentage, capped at 100 -- plain progress reporting, never phrased as
a shortfall or failure (spec section 36).

## Testing

`tests/test_intelligence.py` builds a synthetic dataset (spec section
63: 50 jobs, 30 shortlisted, 25 applications, 8 responses, 5 interviews,
2 offers, 3 CV versions, 4 sources, 5 roles, a real skill gap via AWS
never being in the profile, and 6 rejections with varying reasons) and
covers all 20 categories from spec section 62, including a direct test
that the LLM validator strips a fabricated statistic
(`test_llm_explanation_strips_fabricated_statistics`) and that an
interview answer claiming an unsupported skill is flagged, not silently
served (`test_interview_prep_answer_rejects_unsupported_claim`).
`tests/test_end_to_end.py` extends the Step 1-6 workflow test through
the full intelligence layer in one pass, printing the same
"AI JOB SEARCH INTELLIGENCE" summary shape as spec section 64's example.
