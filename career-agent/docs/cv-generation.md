# CV Customization, Versioning & PDF Generation (Step 3)

## Pipeline

```
JOB  +  JOB MATCH (Step 2)  +  CAREER PROFILE (Step 1, read-only)
  -> read the full profile (get_relevant_career_data, reused from Step 2)
  -> CV PLAN (framing only)                     [1 LLM call]
  -> SUMMARY                                    [1 LLM call, retried once
                                                   if malformed or unsupported]
  -> deterministic skill reordering (no LLM)
  -> assemble CVContent from the profile, verbatim
  -> BULLET REWRITE, per bullet, validated      [1 LLM call]
  -> render LaTeX (Python builds it; the LLM never sees or writes LaTeX)
  -> compile PDF (pdflatex)
  -> store CVVersion (+ CVSection ordering, + CVChange audit trail)
```

Three LLM calls total: one to decide how to **frame** the candidate
(`CV_PLAN_PROMPT_V1`), one to write the **summary**
(`CV_SUMMARY_PROMPT_V1`), and one to **reword the candidate's existing
bullets** toward the job description (`CV_BULLET_REWRITE_PROMPT_V1`).

## What tailoring does and does not change

Three different rules apply to three kinds of content, and the difference
is the whole design:

- **Inclusion is never AI-decided.** Every experience, project, bullet,
  research item, education entry, certification, achievement, and skill on
  the profile appears on every generated CV. There is no prompt, and no
  schema field, for "which of these is relevant enough" -- see
  `assemble_cv_content()` and `_master_skill_categories()`. A CV is never
  shorter because a model judged something unimportant.
- **Skill emphasis is tailored deterministically.** `_reorder_skills_for_job()`
  promotes skills and categories matching the job's requirements toward the
  top with a stable sort. Nothing is added, removed, or renamed, and no LLM
  is involved.
- **Wording is AI-tailored.** The summary is written per job, and each
  existing bullet is rewritten per job to lead with impact and to use the
  job description's terminology.

## Why hallucination can't slip through architecturally

The LLM is never asked to write a bullet from nothing -- only to reword one
the candidate already wrote, and only within limits a machine can check.
`rewrite_bullets_for_job()` keys the rewrite request by positional ids it
mints itself (`e0b1`, `p2b0`), so structurally the model *cannot* add a
bullet, drop one, reorder them, or move one between roles: ids it invents
are never looked up, and ids it fails to return keep their original text.

What remains is the risk that a rewrite of a real bullet says something the
original didn't, and that is checked deterministically by
`validate_bullet_rewrite()` rather than trusted to the prompt. Because a
bullet always has exactly one source row, a failed check needs no
judgement call about how to repair it: **the rewrite is discarded and the
candidate's stored text ships instead.** The worst case of the entire
rewrite step -- a broken model, an unreachable API, malformed output,
wholesale fabrication -- is the untailored, verbatim CV.

Education, certifications, research, and achievements are **never passed
through the LLM at all**. There is no prompt for them in `ai/cv_prompts.py`
on purpose: they are copied verbatim from the Career Profile straight into
`CVContent`, so they need no hallucination check -- they *are* the verified
source.

## Deterministic validation (`cv_validation_service.py`)

Runs on every generation, regardless of prompt quality.

Per rewritten bullet, checked against the bullet it came from. Any of
these reverts that one bullet to its original text and is logged, not
surfaced as a `CVVersion` warning -- a reverted bullet means the CV shipped
the candidate's own words, which is not a defect to flag:

- **`NEW_METRIC_IN_BULLET`** -- the rewrite contains a number or percentage
  the original bullet does not.
- **`NEW_TECHNOLOGY_IN_BULLET`** -- the rewrite names a technology the
  original bullet does not, checked against the candidate's own skills
  *and* the job's requirement terms. Both halves matter: a term the
  candidate genuinely has elsewhere is still false in a bullet that never
  mentioned it, and a term only the job asked for is exactly what a
  keyword-matching model is tempted to insert.
- **`BULLET_REWRITE_PADDED`** -- the rewrite exceeds the original's word
  count by more than 50%. This is the check that catches unsupported
  *scope* ("a service" becoming "a distributed system serving millions"),
  which contains neither a new number nor a new technology name and would
  otherwise pass.
- **`EMPTY_BULLET_REWRITE`** -- the rewrite is blank.

Dropping a detail the original had is deliberately *not* an error. The
constraint is one-directional: a rewrite may say less than the original,
never more.

For the summary:

- **`UNSUPPORTED_TECHNOLOGY_IN_SUMMARY`** -- the summary mentions a job
  requirement term the profile doesn't support. Unlike a bullet this can't
  be mechanically reverted (no single source row backs a summary), so if it
  survives one correction retry the summary falls back to a deterministic
  template (`_fallback_summary`) built only from `plan.priority_skills`,
  which are themselves already filtered to verified skills.

A summary issue that survives the retry is recorded in `CVVersion.warnings`,
and a CV with any warnings can never reach `validated` status -- it stays
`draft`. Generation does not fail outright: refusing to ship the whole CV
over one sentence would waste the other two LLM calls and the rest of the
correct content.

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

The LLM produces validated Pydantic data (`CVContentOutput`,
`CVBulletRewriteOutput`) and nothing else -- it is never shown a template
and never asked for LaTeX. Python renders every section's LaTeX from that
data via
`escape_latex()` (single-pass character substitution -- see the comment
in `cv_render_service.py` for why a sequential `.replace()` chain would
double-escape its own output), then substitutes exactly two pre-built
blocks (`{{HEADER_BLOCK}}`, `{{BODY}}`) into
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
