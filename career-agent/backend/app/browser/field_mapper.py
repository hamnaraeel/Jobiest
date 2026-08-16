"""Maps detected fields to verified Career Profile data or previously
generated application answers -- or explicitly declines to map, which is
the correct outcome far more often than people expect.

Never guesses on sensitive/high-impact questions (spec sections 10-12):
work authorization, sponsorship, citizenship, security clearance,
criminal/legal declarations, disability, demographics, veteran status,
salary, relocation, availability, and notice period always come back
with confidence 0.0 and no proposed value, regardless of any text match
that would otherwise have been found -- these must always reach a human.
"""

import re
from dataclasses import dataclass

from app.browser.form_detector import DetectedField
from app.models.enums import ApplicationFieldType, ApplicationMaterialStatus
from app.models.profile import CareerProfile
from app.services.application_answer_service import classify_question_type

# Step 4's ApplicationQuestionType only needed salary/authorization/
# relocation/availability for its own answer-generation purposes. A
# browser form asks a wider range of sensitive questions, so this adds
# the categories Step 4 never needed.
EXTRA_SENSITIVE_KEYWORDS = (
    "citizen", "citizenship", "security clearance", "clearance",
    "criminal", "convicted", "felony", "misdemeanor", "background check",
    "disability", "disabled",
    "gender", "race", "ethnicity", "ethnic", "veteran", "military service",
    "sponsorship", "sponsor", "notice period",
)

_SENSITIVE_QUESTION_TYPES = {"salary", "authorization", "relocation", "availability"}

_PROFILE_FIELD_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bfirst\s*name\b", re.I), "first_name"),
    (re.compile(r"\blast\s*name\b|\bsurname\b", re.I), "last_name"),
    (re.compile(r"\bfull\s*name\b|^\s*name\s*$", re.I), "full_name"),
    (re.compile(r"\be-?mail\b", re.I), "email"),
    (re.compile(r"\bphone\b|\bmobile\b|\btelephone\b", re.I), "phone"),
    (re.compile(r"linkedin", re.I), "linkedin_url"),
    (re.compile(r"github", re.I), "github_url"),
    (re.compile(r"portfolio|personal\s*website", re.I), "portfolio_url"),
    (re.compile(r"\bcity\b", re.I), "city"),
    (re.compile(r"\bcountry\b", re.I), "country"),
]

HIGH_TEXT_MATCH_CONFIDENCE = 0.90
UNAPPROVED_MATCH_CONFIDENCE = 0.60
PROFILE_MATCH_CONFIDENCE = 0.97


@dataclass
class FieldMapping:
    mapped_source: str | None
    proposed_value: str | None
    confidence: float
    reason: str


def is_sensitive_label(label: str) -> bool:
    lowered = label.lower()
    if any(kw in lowered for kw in EXTRA_SENSITIVE_KEYWORDS):
        return True
    return classify_question_type(label).value in _SENSITIVE_QUESTION_TYPES


def _profile_value(profile: CareerProfile, key: str) -> str | None:
    if key == "first_name":
        parts = (profile.full_name or "").split()
        return parts[0] if parts else None
    if key == "last_name":
        parts = (profile.full_name or "").split()
        return parts[-1] if len(parts) > 1 else None
    value = getattr(profile, key, None)
    return str(value) if value else None


def _normalize_words(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    stopwords = {"a", "an", "the", "is", "are", "you", "your", "do", "did", "what", "why", "how", "to", "of", "for", "in", "on", "at", "this"}
    return {w for w in words if w not in stopwords and len(w) > 2}


def _best_question_match(label: str, answer_pairs: list[tuple]) -> tuple | None:
    label_words = _normalize_words(label)
    if not label_words:
        return None
    best_score, best = 0.0, None
    for question, answer in answer_pairs:
        question_words = _normalize_words(question.question)
        if not question_words:
            continue
        overlap = len(label_words & question_words)
        score = overlap / max(len(label_words), len(question_words))
        if score > best_score:
            best_score, best = score, (question, answer)
    return best if best_score >= 0.5 else None


def map_field(field: DetectedField, profile: CareerProfile | None, answer_pairs: list[tuple]) -> FieldMapping:
    label = field.label or field.field_identifier

    if is_sensitive_label(label):
        return FieldMapping(None, None, 0.0, "Sensitive/high-impact question -- always requires user review, never auto-answered.")

    if field.field_type == ApplicationFieldType.FILE:
        return FieldMapping(None, None, 0.0, "File upload -- handled by file_uploader.py, not field_mapper.py.")

    if profile is None:
        return FieldMapping(None, None, 0.0, "No career profile exists yet.")

    for pattern, profile_key in _PROFILE_FIELD_PATTERNS:
        if pattern.search(label):
            value = _profile_value(profile, profile_key)
            if value:
                return FieldMapping(f"profile.{profile_key}", value, PROFILE_MATCH_CONFIDENCE, f"Label matches '{profile_key}'.")
            return FieldMapping(None, None, 0.0, f"Looked like '{profile_key}' but the profile has no value for it.")

    if field.field_type in (ApplicationFieldType.TEXTAREA, ApplicationFieldType.TEXT):
        best = _best_question_match(label, answer_pairs)
        if best:
            question, answer = best
            approved = answer.status == ApplicationMaterialStatus.APPROVED
            confidence = HIGH_TEXT_MATCH_CONFIDENCE if approved else UNAPPROVED_MATCH_CONFIDENCE
            status_note = "an approved" if approved else f"a '{answer.status.value}' (not yet approved)"
            return FieldMapping(
                f"application_answer_{answer.id}", answer.answer, confidence,
                f"Matches {status_note} answer to: '{question.question}'.",
            )

    return FieldMapping(None, None, 0.0, "No confident mapping found.")
