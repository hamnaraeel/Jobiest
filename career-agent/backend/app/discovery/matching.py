"""Keyword/company-token helpers shared by every discovery adapter."""

import re


def matches_keywords(text: str | None, keywords: list[str]) -> bool:
    """True if any keyword appears in text (case-insensitive substring).
    An empty keyword list matches everything -- callers that have no
    target_roles configured get an unfiltered feed rather than zero
    results."""

    if not keywords:
        return True
    if not text:
        return False
    haystack = text.lower()
    return any(keyword.lower().strip() in haystack for keyword in keywords if keyword.strip())


def company_to_board_token(company: str) -> str:
    """Greenhouse/Lever board tokens are the company name lowercased with
    everything but letters/digits stripped (e.g. "Notion Labs" -> "notionlabs").
    This is a best-effort guess, not a guarantee -- a 404 just means this
    particular company isn't on this particular ATS, which is expected
    and not treated as an error."""

    return re.sub(r"[^a-z0-9]", "", company.lower())
