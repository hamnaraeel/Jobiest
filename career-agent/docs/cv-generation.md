# CV Customization, Versioning & PDF Generation (Step 3)

## Pipeline

```
JOB  +  JOB MATCH (Step 2)  +  CAREER PROFILE (Step 1, read-only)
  -> select relevant evidence (get_relevant_career_data, reused from Step 2)
  -> CV PLAN                                    [1 LLM call]
  -> CV CONTENT (summary/skills/bullet rewrites) [1 LLM call, retried once
                                                   if malformed or unsupported]
  -> deterministic validation -> sanitize unsupported claims
  -> assemble CVContent (education/certs/research/achievements copied
     verbatim from the profile -- never LLM-touched)
  -> render LaTeX (Python builds it; the LLM never sees or writes LaTeX)
  -> compile PDF (pdflatex)
  -> store CVVersion (+ CVSection ordering, + CVChange audit trail)
```

Two LLM calls total, same as Step 2's "extract, then explain" pattern: one
to decide **what** to include (`CV_PLAN_PROMPT_V1`), one to decide **how
to word it** (`CV_SUMMARY_PROMPT_V1` + `CV_BULLET_REWRITE_PROMPT_V1` +
`CV_SKILL_SELECTION_PROMPT_V1`, concatenated into a single system
message for that one call). `CV_PROJECT_SELECTION_PROMPT_V1`'s guidance is
folded into the planning call, since selecting *which* projects matter is
a planning decision, not a wording decision.

## Why hallucination can't slip through architecturally

The LLM is never asked to write a bullet from nothing. `CV_BULLET_REWRITE_PROMPT_V1`
only lets it *rewrite* an existing `ExperienceBullet` or `ProjectResult`,
and it must reference that row's real database id
(`RewrittenBullet.source_bullet_id`). That means a fabricated bullet isn't
a "did the AI lie" problem to detect after the fact -- it's a "this id
doesn't exist, or doesn't belong to the selected item" problem, which
`cv_validation_service.validate_bullets` catches mechanically, the same
way Step 2 never asks the LLM "do I match this job?".

Education, certifications, research, and achievements are **never passed
through the LLM for rewriting at all** -- they're copied verbatim from the
Career Profile straight into `CVContent`. There's no prompt for them in
`ai/cv_prompts.py` on purpose. This is why they need no separate
hallucination check: they *are* the verified source.

## Deterministic validation (`cv_validation_service.py`)

Runs on every generation, regardless of prompt quality:

- **`UNSUPPORTED_SKILL`** -- a skill name in the generated skill list
  doesn't resolve (via Step 2's `lookup_skill`/`skills_equivalent`) to
  anything in the profile. Stripped from the output.
- **`UNSUPPORTED_BULLET_SOURCE`** -- a rewritten bullet references a
  `source_bullet_id` that doesn't exist, or doesn't belong to the
  experience/project it claims to. Discarded.
- **`UNSUPPORTED_METRIC`** -- the rewrite contains a number/percentage not
  present in the original bullet (an `ExperienceBullet`'s text, or a
  `ProjectResult`'s `description` + `metric` combined -- both fields
  together count as that result's "original text", since a result's
  quantified achievement legitimately lives in `metric`, separate from
  `description`, per Step 1's design). Reverted to the original text.
- **`UNSUPPORTED_TECHNOLOGY`** -- the rewrite mentions a technology not in
  the original bullet AND not in that specific experience/project's
  technology list, checked against both the profile's own vocabulary and
  the job's requirement terms (so a wholly invented technology that
  appears nowhere else in the profile -- e.g. the job wants AWS and the
  profile has zero AWS mentions -- is still caught, not just technologies
  that happen to be verified elsewhere). Reverted to the original text.
- **`UNSUPPORTED_TECHNOLOGY_IN_SUMMARY`** -- the summary mentions a job
  requirement term the profile doesn't support. Can't be mechanically
  "reverted" (no single source row backs a summary), so if it survives one
  correction retry, the summary falls back to a deterministic template
  (`_fallback_summary`) built only from `plan.priority_skills`, which are
  themselves already filtered to verified skills.

If content still has issues after the correction retry, generation does
**not** fail outright -- the offending pieces are sanitized (stripped or
reverted, as above) and every remaining issue is recorded in
`CVVersion.warnings`. A CV with any warnings can never reach `validated`
status; it stays `draft`. This is a deliberate choice: refusing to ship
the whole CV over one bad bullet would waste two already-spent LLM calls
and the rest of the (correct) content -- sanitizing preserves the
verified-strengths-focused CV the spec explicitly allows ("may still be
optimized around other verified strengths") while never shipping the
specific unsupported claim.

## Match score before/after

Both use the *identical* deterministic Step 2 `compute_match()` -- called
once before generation (or read from the existing `JobMatch` if one
already exists) and once again after. If your profile data hasn't changed
between the two calls, they come out equal, and that's correct: tailoring
a CV's wording and selection doesn't retroactively add verified skills or
experience. A genuine increase only happens if you add or verify more
profile data between generating CVs for the same job -- which is real
signal, not a manufactured one.

## Versioning

`CVVersion.version_number` increments per job (`V1`, `V2`, `V3`, ...) --
generation always inserts a new row, never updates an existing one.
`DELETE /cvs/{id}` archives (`status = archived`) rather than deleting the
row or the PDF, matching "never delete old versions automatically."

## Status / approval workflow

`draft -> validated -> approved -> rejected -> archived`. Generation can
only ever produce `draft` or `validated` (validated only when zero
warnings survive and, if requested, the PDF actually compiled).
`PATCH /cvs/{id}/status` is the human-in-the-loop step -- nothing in this
codebase ever sets a CV to `approved` on its own. A future application
step is expected to only ever act on `status == approved`.

## LaTeX rendering (`cv_render_service.py`)

The LLM produces `CVContentOutput` (validated Pydantic data) and nothing
else. Python renders every section's LaTeX from that data via
`escape_latex()` (single-pass character substitution -- see the comment
in `cv_render_service.py` for why a sequential `.replace()` chain would
double-escape its own output), then substitutes exactly three pre-built
blocks (`{{NAME}}`, `{{CONTACT_LINE}}`, `{{BODY}}`) into
`cv_templates/ats/ml_engineer.tex`. There is no code path where raw LLM
output reaches `pdflatex`. See `cv_templates/README.md` for template
details.

`compile_pdf()` shells out to `pdflatex -halt-on-error`, confirms the PDF
exists and is non-empty, and returns the last 30 lines of the compilation
log on failure rather than a bare non-zero exit code. File paths are
resolved and checked against the configured storage root
(`PathSecurityError`) before any file is written.

## Example artifacts

`docs/examples/cv_example.json` and `docs/examples/cv_example.tex` are
real output from this pipeline (AI calls mocked, everything else --
profile data, planning logic, validation, rendering -- genuine), generated
against a profile with one verified skill, one experience with a bullet,
and one project with a quantified result. Notice every bullet in the JSON
carries `source_type`/`source_id`/`verified`.
