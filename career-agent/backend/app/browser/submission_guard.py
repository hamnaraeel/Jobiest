"""The final safety gate (spec section 24).

No code path in this application may click a real submit button unless
`check_ready_for_submission()` reports ready AND
`Application.submission_approved` is True. This is checked twice by
design: once to compute the review's `ready_for_submission` flag (GET
.../review), and again immediately before the actual click inside
GenericApplicationAdapter.submit() -- defense in depth, so a stale review
object can never be the sole reason a real click happens.

`submission_approved` is set exactly one way: POST
/applications/{id}/approve-submission. Nothing else in this codebase ever
sets it.
"""

from dataclasses import dataclass, field

from app.models.application import Application
from app.models.application_field import ApplicationField
from app.models.cover_letter import CoverLetter
from app.models.cv_version import CVVersion
from app.models.enums import ApplicationFieldStatus, ApplicationMaterialStatus


@dataclass
class SubmissionCheck:
    ready: bool
    warnings: list[str] = field(default_factory=list)


def check_ready_for_submission(
    application: Application,
    fields: list[ApplicationField],
    cv_version: CVVersion | None,
    cover_letter: CoverLetter | None,
    requires_cover_letter: bool = False,
) -> SubmissionCheck:
    warnings: list[str] = []

    unresolved_required = [
        f for f in fields
        if f.required and f.status not in (ApplicationFieldStatus.FILLED, ApplicationFieldStatus.SKIPPED)
    ]
    if unresolved_required:
        names = ", ".join(f.label or f.field_identifier for f in unresolved_required[:5])
        warnings.append(f"{len(unresolved_required)} required field(s) are not resolved: {names}")

    needs_review = [
        f for f in fields
        if f.user_review_required and f.status not in (ApplicationFieldStatus.FILLED, ApplicationFieldStatus.SKIPPED)
    ]
    if needs_review:
        names = ", ".join(f.label or f.field_identifier for f in needs_review[:5])
        warnings.append(f"{len(needs_review)} field(s) still need user review: {names}")

    if cv_version is None:
        warnings.append("No CV is associated with this application.")
    elif cv_version.status != ApplicationMaterialStatus.APPROVED:
        warnings.append(f"CV status is '{cv_version.status.value}', not approved.")

    if requires_cover_letter:
        if cover_letter is None:
            warnings.append("This application requires a cover letter, but none is associated.")
        elif cover_letter.status != ApplicationMaterialStatus.APPROVED:
            warnings.append(f"Cover letter status is '{cover_letter.status.value}', not approved.")

    if not application.submission_approved:
        warnings.append("Explicit submission approval has not been given (POST /applications/{id}/approve-submission).")

    return SubmissionCheck(ready=not warnings, warnings=warnings)


def can_click_submit(check: SubmissionCheck, application: Application, dry_run: bool) -> tuple[bool, str]:
    """The literal gate immediately before a real click. Returns
    (allowed, reason_if_not_allowed)."""

    if dry_run:
        return False, "DRY_RUN is enabled -- submission is simulated, the real submit control is never clicked."
    if not application.submission_approved:
        return False, "Explicit submission approval has not been given."
    if not check.ready:
        return False, "Submission checks failed: " + "; ".join(check.warnings)
    return True, ""
