"""URL fetching and HTML-to-text cleaning for job postings.

Deliberately simple: plain HTTP GET, robots.txt respected, no
authentication bypass, no CAPTCHA handling, no JavaScript rendering. Pages
that need any of that are reported back as needing manual paste, not
worked around.
"""

import logging
import re
import urllib.robotparser as robotparser
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("app.job_parser")

USER_AGENT = "CareerAgentBot/0.1 (job ingestion for personal job-search assistant)"
REQUEST_TIMEOUT_SECONDS = 10
MIN_USABLE_TEXT_LENGTH = 200

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "ref", "referrer", "source", "trk", "trackingId",
}

NOISE_TAGS = ("script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg", "iframe")
NOISE_CLASS_KEYWORDS = ("cookie", "banner", "subscribe", "newsletter", "advertisement", "ad-", "consent", "popup")


def normalize_url(url: str) -> str:
    """Canonicalize a job URL for deduplication: lowercase host, strip
    www./trailing slash/tracking params, sort remaining query params."""

    parsed = urlparse(url.strip())
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/")
    query_pairs = sorted((k, v) for k, v in parse_qsl(parsed.query) if k not in TRACKING_PARAMS)
    return urlunparse(("https", netloc, path, "", urlencode(query_pairs), ""))


@dataclass
class FetchResult:
    ok: bool
    html: str | None = None
    status_code: int | None = None
    error: str | None = None


def _robots_allowed(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        rp = robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        # No reachable/parseable robots.txt -- default-allow, matching
        # standard crawler behavior for a missing robots.txt.
        return True


def fetch_job_url(url: str, timeout: float = REQUEST_TIMEOUT_SECONDS) -> FetchResult:
    normalized = normalize_url(url)

    if not _robots_allowed(normalized):
        logger.info("job url fetch blocked by robots.txt")
        return FetchResult(ok=False, error="Disallowed by robots.txt")

    try:
        response = requests.get(
            normalized, timeout=timeout, headers={"User-Agent": USER_AGENT}, allow_redirects=True
        )
    except requests.RequestException as exc:
        logger.info("job url fetch failed: %s", exc.__class__.__name__)
        return FetchResult(ok=False, error=str(exc))

    if response.status_code >= 400:
        return FetchResult(ok=False, status_code=response.status_code, error=f"HTTP {response.status_code}")

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        return FetchResult(ok=False, status_code=response.status_code, error=f"Unsupported content-type: {content_type}")

    return FetchResult(ok=True, html=response.text, status_code=response.status_code)


def clean_html_to_text(html: str) -> str | None:
    """Strip a job posting page down to its readable text. Returns None if
    the result looks too short to be a real job description (e.g. a
    JavaScript-only shell page that never got hydrated)."""

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()

    for tag in soup.find_all(True):
        identifiers = " ".join(filter(None, [tag.get("class") and " ".join(tag.get("class")), tag.get("id")])).lower()
        if any(keyword in identifiers for keyword in NOISE_CLASS_KEYWORDS):
            tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    if len(cleaned) < MIN_USABLE_TEXT_LENGTH:
        return None
    return cleaned


def clean_pasted_description(text: str) -> str:
    """Lighter cleaning for text the user pasted directly (already plain
    text, just normalize whitespace)."""

    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    cleaned = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()
