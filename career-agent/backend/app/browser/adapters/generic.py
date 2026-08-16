"""GenericApplicationAdapter: works with ordinary HTML forms, no
platform-specific knowledge. The only adapter implemented in Step 5 --
see platform_detector.py for how a later step would register a
specialized one (GreenhouseAdapter, etc.) without touching this file.

This adapter is a thin sequencer: the actual logic (field detection,
mapping, filling, the submission gate) all lives in the standalone
browser/*.py modules, each independently testable. This file's job is
just to call them in the right order and persist the results.
"""

import logging
import re
from datetime import datetime, timezone

from playwright.async_api import Page
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.browser import field_mapper, file_uploader, form_detector, form_filler, page_analyzer, submission_guard
from app.browser.adapters.base import BaseApplicationAdapter
from app.browser.page_analyzer import PageAnalysis
from app.config import get_settings
from app.models.application import Application
from app.models.application_answer import ApplicationAnswer
from app.models.application_event import ApplicationEvent
from app.models.application_field import ApplicationField
from app.models.application_question import ApplicationQuestion
from app.models.enums import ApplicationEventType, ApplicationFieldStatus, ApplicationFieldType, ApplicationStatus
from app.services.profile_service import get_default_profile

logger = logging.getLogger("app.browser.adapters.generic")

SUBMIT_BUTTON_TEXTS = ("Submit Application", "Submit", "Apply", "Complete Application", "Finish", "Send Application")
CONFIRMATION_MARKERS = ("thank you", "application received", "successfully submitted", "application submitted", "confirmation")


def log_event(db: Session, application: Application, event_type: ApplicationEventType, description: str, metadata: dict | None = None) -> None:
    db.add(ApplicationEvent(
        application_id=application.id, event_type=event_type, description=description, event_metadata=metadata or {},
    ))
    db.commit()


class GenericApplicationAdapter(BaseApplicationAdapter):
    platform_name = "generic"

    @staticmethod
    def detect(url: str) -> bool:
        return True  # fallback adapter -- always matches

    async def open(self, page: Page, application: Application) -> None:
        await page.goto(application.application_url, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass  # some pages poll/stream and never go fully idle -- not fatal

    async def analyze_page(self, page: Page, db: Session, application: Application) -> PageAnalysis:
        analysis = await page_analyzer.analyze_page(page)

        if analysis.captcha_detected:
            application.status = ApplicationStatus.BLOCKED
            db.commit()
            log_event(
                db, application, ApplicationEventType.BLOCKED,
                f"CAPTCHA/anti-bot challenge detected ({analysis.captcha_indicator}). Human action required -- "
                f"complete it manually in the browser, then call analyze-page again.",
            )
            return analysis

        if analysis.login_required:
            application.status = ApplicationStatus.NEEDS_USER_INPUT
            db.commit()
            log_event(
                db, application, ApplicationEventType.USER_INPUT_REQUIRED,
                "Login required. Please log in manually in the browser window, then call analyze-page again.",
            )
            return analysis

        log_event(db, application, ApplicationEventType.PAGE_LOADED, f"Page loaded: {analysis.title} ({analysis.url})")

        detected = await form_detector.detect_fields(page)
        profile = get_default_profile(db)
        questions = db.execute(select(ApplicationQuestion).where(ApplicationQuestion.job_id == application.job_id)).scalars().all()

        answer_pairs = []
        for question in questions:
            latest = db.execute(
                select(ApplicationAnswer).where(ApplicationAnswer.question_id == question.id)
                .order_by(ApplicationAnswer.id.desc()).limit(1)
            ).scalar_one_or_none()
            if latest:
                answer_pairs.append((question, latest))

        settings = get_settings()
        for det in detected:
            existing = db.execute(
                select(ApplicationField).where(
                    ApplicationField.application_id == application.id,
                    ApplicationField.field_identifier == det.field_identifier,
                    ApplicationField.page_url == analysis.url,
                )
            ).scalar_one_or_none()
            if existing:
                continue

            mapping = field_mapper.map_field(det, profile, answer_pairs)
            field_row = ApplicationField(
                application_id=application.id, field_identifier=det.field_identifier, label=det.label,
                field_type=det.field_type, page_url=analysis.url, required=det.required,
                detected_value=det.current_value, mapped_source=mapping.mapped_source,
                proposed_value=mapping.proposed_value, confidence=mapping.confidence,
                status=ApplicationFieldStatus.MAPPED if mapping.mapped_source else ApplicationFieldStatus.DETECTED,
                user_review_required=mapping.confidence < settings.field_confidence_high,
            )
            db.add(field_row)
            db.flush()
            log_event(
                db, application, ApplicationEventType.FIELD_DETECTED,
                f"Detected field '{det.label or det.field_identifier}' ({det.field_type.value}): {mapping.reason}",
                {"field_id": field_row.id, "confidence": mapping.confidence},
            )
            if det.field_type in (ApplicationFieldType.TEXTAREA,) and mapping.mapped_source is None:
                log_event(db, application, ApplicationEventType.QUESTION_DETECTED, f"Question detected with no approved answer: '{det.label}'")

        db.commit()
        return analysis

    async def fill_fields(self, page: Page, db: Session, application: Application) -> list[ApplicationField]:
        settings = get_settings()
        candidates = db.execute(
            select(ApplicationField).where(
                ApplicationField.application_id == application.id,
                ApplicationField.status == ApplicationFieldStatus.MAPPED,
            )
        ).scalars().all()

        filled: list[ApplicationField] = []
        for field_row in candidates:
            if field_row.field_type == ApplicationFieldType.FILE:
                continue  # file_uploader's job

            if field_row.confidence is None or field_row.confidence < settings.field_confidence_high:
                field_row.status = ApplicationFieldStatus.NEEDS_REVIEW
                field_row.user_review_required = True
                continue

            success = await form_filler.fill_field(page, field_row)
            if success:
                field_row.status = ApplicationFieldStatus.FILLED
                field_row.final_value = field_row.proposed_value
                filled.append(field_row)
                log_event(
                    db, application, ApplicationEventType.FIELD_FILLED,
                    f"Filled '{field_row.label or field_row.field_identifier}' from {field_row.mapped_source}",
                    {"field_id": field_row.id},
                )
            else:
                field_row.status = ApplicationFieldStatus.NEEDS_REVIEW
                field_row.user_review_required = True

        db.commit()
        return filled

    async def upload_files(self, page: Page, db: Session, application: Application) -> list[ApplicationField]:
        uploaded: list[ApplicationField] = []
        file_fields = db.execute(
            select(ApplicationField).where(
                ApplicationField.application_id == application.id,
                ApplicationField.field_type == ApplicationFieldType.FILE,
                ApplicationField.status.in_([ApplicationFieldStatus.DETECTED, ApplicationFieldStatus.MAPPED]),
            )
        ).scalars().all()

        for field_row in file_fields:
            label = (field_row.label or "").lower()
            try:
                if "cover" in label:
                    path = file_uploader.resolve_cover_letter_pdf_path(db, application.cover_letter)
                    source = f"cover_letter_{application.cover_letter_id}"
                elif "resume" in label or "cv" in label:
                    path = file_uploader.resolve_cv_pdf_path(db, application.cv_version)
                    source = f"cv_version_{application.cv_version_id}"
                else:
                    field_row.status = ApplicationFieldStatus.NEEDS_REVIEW
                    field_row.user_review_required = True
                    continue
            except file_uploader.UnapprovedMaterialError as exc:
                field_row.status = ApplicationFieldStatus.NEEDS_REVIEW
                field_row.user_review_required = True
                log_event(db, application, ApplicationEventType.BLOCKED, f"Could not upload for field '{field_row.label}': {exc}")
                continue

            locator = await form_filler.locate_field(page, field_row)
            if locator is None:
                field_row.status = ApplicationFieldStatus.NEEDS_REVIEW
                field_row.user_review_required = True
                continue

            await file_uploader.upload_file(locator, path)
            field_row.status = ApplicationFieldStatus.FILLED
            field_row.final_value = path
            field_row.mapped_source = source
            uploaded.append(field_row)
            log_event(db, application, ApplicationEventType.FILE_UPLOADED, f"Uploaded {source} to '{field_row.label}'", {"field_id": field_row.id, "path": path})

        db.commit()
        return uploaded

    def prepare_review(self, db: Session, application: Application) -> dict:
        fields = db.execute(select(ApplicationField).where(ApplicationField.application_id == application.id)).scalars().all()
        check = submission_guard.check_ready_for_submission(application, fields, application.cv_version, application.cover_letter)

        log_event(db, application, ApplicationEventType.REVIEW_READY, "Review generated.", {"ready": check.ready})
        if check.ready and application.status != ApplicationStatus.SUBMITTED:
            application.status = ApplicationStatus.READY_FOR_REVIEW
            db.commit()

        return {"fields": fields, "ready_for_submission": check.ready, "warnings": check.warnings}

    async def submit(self, page: Page, db: Session, application: Application) -> dict:
        settings = get_settings()
        fields = db.execute(select(ApplicationField).where(ApplicationField.application_id == application.id)).scalars().all()
        check = submission_guard.check_ready_for_submission(application, fields, application.cv_version, application.cover_letter)
        allowed, reason = submission_guard.can_click_submit(check, application, settings.dry_run)

        if not allowed:
            log_event(db, application, ApplicationEventType.BLOCKED, f"Submission blocked: {reason}")
            return {"submitted": False, "dry_run": settings.dry_run, "reason": reason}

        application.status = ApplicationStatus.SUBMITTING
        db.commit()
        log_event(db, application, ApplicationEventType.SUBMISSION_STARTED, "Clicking the final submit control.")

        submit_locator = await self._find_submit_button(page)
        if submit_locator is None:
            application.status = ApplicationStatus.FAILED
            db.commit()
            log_event(db, application, ApplicationEventType.SUBMISSION_FAILED, "Could not identify the final submit control.")
            return {"submitted": False, "reason": "Could not identify the final submit control."}

        before_url = page.url
        button_text = (await submit_locator.inner_text()).strip() if await submit_locator.count() else ""
        await submit_locator.click()
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        confirmed, reference = await self._detect_confirmation(page, before_url)
        if confirmed:
            application.status = ApplicationStatus.SUBMITTED
            application.submitted_at = datetime.now(timezone.utc)
            application.confirmation_reference = reference
            db.commit()
            log_event(
                db, application, ApplicationEventType.SUBMISSION_COMPLETED, "Submission confirmed.",
                {"reference": reference, "url": page.url, "button_text": button_text},
            )
            return {"submitted": True, "confirmation_reference": reference}

        application.status = ApplicationStatus.FAILED
        db.commit()
        log_event(
            db, application, ApplicationEventType.SUBMISSION_FAILED,
            "Clicked submit but could not confirm success -- reporting failure rather than assuming it worked.",
            {"url": page.url, "button_text": button_text},
        )
        return {"submitted": False, "reason": "Could not confirm submission succeeded."}

    async def _find_submit_button(self, page: Page):
        for text in SUBMIT_BUTTON_TEXTS:
            locator = page.get_by_role("button", name=text, exact=False)
            if await locator.count() > 0:
                return locator.first
        locator = page.locator('button[type="submit"], input[type="submit"]')
        if await locator.count() > 0:
            return locator.first
        return None

    async def _detect_confirmation(self, page: Page, before_url: str) -> tuple[bool, str | None]:
        # url_changed alone is not a reliable confirmation signal (e.g. a
        # "next page" navigation also changes the URL without submitting
        # anything) -- it's recorded for the event log, but confirmation
        # itself requires an explicit success/confirmation marker in the
        # resulting page's text.
        url_changed = page.url != before_url
        body_text = ""
        try:
            body_text = (await page.inner_text("body")).lower()
        except Exception:
            pass

        text_confirmed = any(marker in body_text for marker in CONFIRMATION_MARKERS)

        # Requires an explicit ":" or "#" separator (with at most one
        # in-between word, e.g. "confirmation reference: X") and at least
        # one digit in the captured token -- otherwise a phrase like
        # "confirmation reference: TEST-123" would greedily capture the
        # word "reference" itself as the reference value, since it also
        # matches [A-Za-z0-9-]{4,}.
        reference = None
        match = re.search(
            r"(?:reference|confirmation)(?:\s+\w+)?\s*[:#]\s*([A-Za-z0-9\-]*\d[A-Za-z0-9\-]*)",
            body_text, re.IGNORECASE,
        )
        if match:
            reference = match.group(1)

        logger.info("submission confirmation check: url_changed=%s text_confirmed=%s", url_changed, text_confirmed)
        return text_confirmed, reference
