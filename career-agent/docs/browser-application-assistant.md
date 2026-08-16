# Browser-Based Job Application Assistant (Step 5)

## What this is, and what it deliberately is not

This step drives a real browser (Playwright) to help fill out an online
job application form -- detecting fields, mapping them to verified Career
Profile data or previously-approved Step 4 answers, uploading approved
CV/cover-letter PDFs, and (only with explicit permission) clicking the
real submit button. It is an **assisted** workflow, not an autonomous
one: nothing gets submitted without a human looking at it first.

## The two non-negotiable safety guarantees

1. **`DRY_RUN=true` by default.** As long as this is true, `submit()`
   never clicks the real submit control -- it always simulates. Nothing
   about the review state or approval status changes this; it's checked
   first, unconditionally, in `submission_guard.can_click_submit()`.
2. **Explicit approval is the only thing that can enable a real click,
   and even that isn't enough by itself.** `Application.submission_approved`
   starts `false` and can only ever become `true` via one call:
   `POST /applications/{id}/approve-submission`. A real click additionally
   requires `DRY_RUN=false` *and* every required field resolved *and* an
   approved CV on file -- `submission_guard.check_ready_for_submission()`
   computes readiness, and `can_click_submit()` is the literal gate
   checked a second time, immediately before the click, inside
   `GenericApplicationAdapter.submit()`. A stale review page can never be
   the sole reason a real click happens.

Setting `DRY_RUN=false` and calling approve-submission are two
independent, deliberate actions. Neither one alone is enough.

## What gets a click, and what it looks like when it stops early

`submit()` always returns a result -- it never leaves the caller
guessing:

- Blocked by DRY_RUN or missing approval: `{"submitted": false, "dry_run":
  ..., "reason": "..."}`.
- Clicked, but the resulting page shows no recognizable confirmation
  text: `{"submitted": false, "reason": "Could not confirm submission
  succeeded."}` -- the agent never assumes success just because a click
  happened and the page changed. A URL change alone isn't treated as
  proof either (a "next page" navigation looks the same to the browser as
  a real submission).
- Clicked and confirmed (a marker like "thank you" / "application
  submitted" / "application received" appears in the resulting page):
  `{"submitted": true, "confirmation_reference": ...}`, and
  `Application.status` becomes `submitted`.

## No credentials, ever

`browser_manager.py` never automates a login form. If `page_analyzer.py`
detects a login page (a password field plus sign-in/log-in text) or a
CAPTCHA/anti-bot challenge (reCAPTCHA/hCaptcha markers, "verify you are
human" text, Cloudflare challenge selectors), the adapter stops and sets
the application to `needs_user_input` or `blocked` -- the user completes
that step by hand in the real, visible browser window (`BROWSER_HEADLESS`
defaults to `false` for exactly this reason), then calls `analyze-page`
again to continue. Detection is deliberately conservative: a false
positive just costs an unnecessary pause, which is safe; a false negative
would mean automating past something that must never be automated past,
which isn't.

`browser_manager` does persist a Chromium user-data directory
(`BROWSER_PROFILE_DIR`) across runs -- that's what lets a manual login
survive between sessions. It's populated by the browser itself (cookies,
local storage), never written to by this codebase, and is gitignored
(see `data/browser_profile/README.md`).

## Field detection, mapping, and confidence

`form_detector.py` walks every `input`/`textarea`/`select` on the page
and records a field's identity from whatever the page actually exposes
(label, `aria-label`, placeholder, `name`, `id`) -- never a synthesized
index-based CSS selector, and never a live element handle held across
requests (a page can reload or change between `analyze-page` and `fill`,
so `form_filler.locate_field()` always re-resolves the element fresh).

`field_mapper.py` then decides, per field:

- **Sensitive/high-impact questions never get a proposed value at all**
  (confidence `0.0`, regardless of any text match that would otherwise
  have been found): salary, work authorization/sponsorship/citizenship,
  security clearance, criminal/legal history, disability, demographic
  questions, veteran status, relocation, availability, notice period.
  These always require a human.
- A label matching a verified Career Profile field (name, email, phone,
  LinkedIn, GitHub, portfolio, city, country) maps at confidence `0.97`.
- A label matching a **Step 4 `ApplicationAnswer`** by word overlap maps
  at `0.90` if that answer is `approved`, or `0.60` if it exists but isn't
  approved yet -- reusing Step 4's answers and its `generate_answer()`
  service rather than building a second answer-generation system.
- Anything else maps at `0.0` and is left for the user.

Only fields at or above `FIELD_CONFIDENCE_HIGH` (default `0.90`) are
auto-filled by `fill_fields()`; everything else is marked
`user_review_required` and surfaced in `GET /applications/{id}/review`
for `POST /applications/{id}/fields/{field_id}/input`. A provided value
is stored against that one application's field only -- it never writes
back to the Career Profile automatically.

## File uploads

`file_uploader.py` resolves a file input to the CV/cover-letter PDF only
if the associated `CVVersion`/`CoverLetter` row's `status` is
`approved` -- a draft, rejected, or unvalidated version is refused
(`UnapprovedMaterialError`), not silently skipped. If an approved
version doesn't have a compiled PDF on disk yet, it's compiled lazily
(same pattern as Step 4's cover-letter PDFs).

## Architecture

```
POST /jobs/{id}/apply
  -> application_service.create_application()
     (duplicate-attempt detection unless force=true; defaults to the
     job's own URL and the latest APPROVED cv/cover letter)

POST /applications/{id}/start-browser
  -> browser_manager.start_session() (real Playwright, launch_persistent_context)
  -> platform_detector.get_adapter(application.platform).open()

POST /applications/{id}/analyze-page
  -> page_analyzer (CAPTCHA/login check -- stops here if either trips)
  -> form_detector.detect_fields() + field_mapper.map_field()
  -> persists ApplicationField rows, logs ApplicationEvent rows

POST /applications/{id}/fill
  -> form_filler (fills only >= FIELD_CONFIDENCE_HIGH fields)
  -> file_uploader (approved materials only)

GET /applications/{id}/review
  -> submission_guard.check_ready_for_submission()

POST /applications/{id}/approve-submission
  -> the only place Application.submission_approved becomes true

POST /applications/{id}/submit
  -> submission_guard.can_click_submit() checked again, immediately
     before any real click
```

A real browser has to stay alive across these separate, stateless HTTP
requests, so sessions live in an in-process registry keyed by
`application_id` (`browser_manager._active_sessions`) rather than
external session storage -- appropriate for a local-first, single-user
tool. Because every session launches against the same persistent profile
directory, only one browser session can be open at a time; closing one
(`POST /applications/{id}/cancel`, or finishing a submission) is required
before starting the next.

Only `GenericApplicationAdapter` (plain HTML forms, no platform-specific
knowledge) is implemented. `platform_detector.py` identifies the ATS by
hostname (Greenhouse/Lever/Workday/LinkedIn/Indeed/generic company site)
purely so a future step can register a specialized adapter for one of
them via `register_adapter()` without touching anything else --
`get_adapter()` already falls back to the generic adapter for every
platform today, including all of the ones it can detect.

## Testing

Nothing in the test suite touches a real job site. `tests/fixtures/`
holds local, self-contained HTML pages (a full form with every field
type Step 5 needs to handle; a CAPTCHA-marker page; a login-required
page; a page whose submit handler deliberately shows no confirmation
text) that real Playwright Chromium loads via `file://` URLs. This
exercises the actual detection/mapping/filling/confirmation-detection
logic against a real DOM and a real browser, not mocked `Page` objects,
while staying entirely local and repeatable. See
`tests/test_browser_application.py` (field mapping, the submission gate,
platform detection, duplicate detection, approval/pause/resume -- no
browser needed) and `tests/test_browser_application_e2e.py` (the full
API-driven workflow against the fixtures, including the DRY_RUN-blocks-
submission and explicit-approval-enables-submission proofs).
