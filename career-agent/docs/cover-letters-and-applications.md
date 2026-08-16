# Cover Letters & Application Answers (Step 4)

## Local LLM only -- no paid API

Everything in this step runs against a local [Ollama](https://ollama.com)
model over HTTP (`OLLAMA_BASE_URL`, default `http://localhost:11434`;
`OLLAMA_MODEL`, no default -- you must set one). There is no OpenAI
dependency anywhere in this step, and no code path in it will ever call
OpenAI. `app/ai/client.py` now holds two independent clients side by
side: `get_openai_client()` (Steps 2-3, unchanged) and
`get_ollama_client()` / `OllamaClient` (Step 4, new). Steps 2-3 keep using
OpenAI as before -- this step doesn't touch them, and migrating them to
Ollama wasn't part of what was asked.

`OllamaClient.chat_structured()` uses Ollama's `format` field with a JSON
Schema (`schema.model_json_schema()`) for constrained decoding -- the
model literally cannot emit JSON that doesn't match the shape, which is
what replaces OpenAI's SDK-specific `.chat.completions.parse()` helper
here.

## Pipeline

```
Cover letter:
  JOB + JOB MATCH + APPROVED CV + CAREER PROFILE
    -> select relevant evidence (deterministic, no LLM call --
       reuses the same skill-overlap ranking as Step 3's CV plan)
    -> generate structured letter                [1 Ollama call]
    -> validate deterministically
    -> if issues: regenerate once with corrections [+1 Ollama call, max]
    -> store version (rejected if issues survive the retry, since a
       cover letter's free-form prose can't be "reverted to source"
       the way a CV bullet rewrite can)

Application answer: identical shape, one question at a time, plus a
separate deterministic length-enforcement loop (see below).
```

## Truthfulness: architecture, not just prompting

`ai/cover_letter_prompts.py` and `ai/application_prompts.py` tell the
model explicitly not to invent skills/experience/companies/metrics, not
to claim unstated company knowledge, and not to let user instructions
override any of that. But the prompt is never the only line of defense --
`answer_validation_service.py` (shared by both cover letters and
application answers) checks the model's output mechanically:

- **`UNSUPPORTED_SKILL`** -- a job requirement's skill name is mentioned
  in the generated text but doesn't resolve (via Step 2's
  `lookup_skill`/`skills_equivalent`) to anything in the profile.
- **`UNSUPPORTED_METRIC`** -- a number/percentage in the generated text
  doesn't match any number found anywhere in the profile's actual
  evidence (experience bullets, project results + metrics, research
  results, achievement metrics, years of experience, or a configured
  `salary_expectation`).
- **`UNSUPPORTED_COMPANY_CLAIM`** -- a generic company-admiration phrase
  ("your innovative culture", "admire your company", ...) appears without
  the underlying topic being grounded in the job's own supplied
  description text. (Job postings describe themselves in first person --
  "our culture" -- while a letter addresses the company in second person
  -- "your culture" -- so the check strips that framing before comparing.)

Unlike Step 3's CV bullets (which can cleanly "revert to the original
text" because each bullet is a rewrite of one specific source row), a
cover letter sentence has no single atomic source to fall back to. So
where Step 3 sanitizes and keeps going, Step 4 rejects: if issues survive
one correction retry, the letter/answer is still stored (never silently
discarded -- "do not silently remove factual claims without recording the
change") but with `status = rejected` and the specific issues in
`warnings`, rather than pretending a compromised result is fine.

### User instructions can't smuggle in unsupported claims

Spec example: "Add AWS to my cover letter" when AWS isn't verified must
be rejected with `"AWS is not present in the verified Career Profile."`
`cover_letter_service._check_instructions_for_unsupported_additions()`
catches this **before the LLM is ever called** by pattern-matching
add/mention/include-style instructions against the profile, rather than
just hoping the prompt's own instruction ("ignore instructions that would
require inventing something") and the post-hoc validator both catch it.

## Never-guess fields (spec sections 24-27)

Salary expectation, work authorization, relocation preference, and
availability date are never inferred or randomly generated. Four new
nullable columns exist on `CareerProfile` (`salary_expectation`,
`work_authorization`, `relocation_preference`, `availability_date`) --
added by this step's migration, never auto-populated by any service.
`application_answer_service.classify_question_type()` recognizes these
question types by keyword, and `_check_manual_input_required()` raises
`ManualInputRequiredError` (surfaced as `{"status":
"manual_input_required", ...}`, not a generated guess) whenever the
corresponding profile field is unset.

## Character/word limits: enforced in Python, not just asked of the model

`application_answer_service._exceeds_limit()` checks the actual generated
text length against `ApplicationQuestion.character_limit`/`word_limit`
after generation -- the model is told the limit as a hint, but Python is
what decides pass/fail. If it's too long, `_shorten_until_fits()` asks the
model to shorten (up to 2 attempts, each re-checked in Python), preserving
factual claims. If it still doesn't fit, the answer is stored with
`status = draft` and a `warnings` entry explaining why -- **never**
mechanically truncated, since cutting a sentence mid-claim can change its
meaning.

## Evidence traceability

`CoverLetter.source_evidence` / `ApplicationAnswer.evidence` are lists of
`{source_type, source_id}` -- every experience/project/research item that
was given to the generator as context for that specific piece of content.
This is an honest scope decision: getting true per-sentence citation would
need the model to tag which evidence backed which sentence (an extra call,
extra cost, extra failure mode) that the spec's 1-2-calls-per-generation
cost budget doesn't leave room for. What's stored instead is auditable in
its own right -- "here is the complete, closed set of verified facts this
content could truthfully have been built from."

## Versioning & approval

Both `CoverLetter` and `ApplicationAnswer` reuse `CVStatus` directly
(aliased as `ApplicationMaterialStatus` for readability) for the identical
`draft -> validated -> approved -> rejected -> archived` workflow as a CV.
Nothing is ever auto-approved by generation. Cover letters version like a
CV (`V1`, `V2`, ... per job, `POST /cover-letters/{id}/regenerate` always
creates a new row). `GET /jobs/{job_id}/application-materials` assembles
the read-only package (job, match, latest CV, latest cover letter, every
question's latest answer, and a computed `ready_for_application` flag that
is only ever `true` once the CV, the cover letter, and every *required*
answer are individually `approved`) that a future application-automation
step would consume -- it never generates or approves anything itself.

## PDF rendering

Reuses Step 3's controlled-template approach exactly: the LLM only ever
produces the letter's text (already validated); Python escapes it
(`cv_render_service.escape_latex`) and substitutes it into
`cv_templates/cover_letter/standard.tex`; `compile_latex_to_pdf()` (a
generalization of Step 3's `compile_pdf`, now shared by both CV and cover
letter rendering) shells out to `pdflatex`. `GET
/cover-letters/{id}/download` defaults to `.txt` (served directly from the
database, no compilation); `?format=pdf` compiles lazily on first request
and caches the path.
