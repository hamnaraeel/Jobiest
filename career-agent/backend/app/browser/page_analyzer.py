"""Analyzes the current page for CAPTCHA/anti-bot challenges and
login-required states. Both must STOP the agent -- never be bypassed
(spec sections 22-23). Detection is heuristic and deliberately
conservative: a false positive just means an unnecessary pause for the
user, which is safe; a false negative would mean attempting to automate
past a control that must not be automated past, which is not."""

import logging
from dataclasses import dataclass

from playwright.async_api import Page

logger = logging.getLogger("app.browser.page_analyzer")

CAPTCHA_TEXT_INDICATORS = (
    "captcha", "recaptcha", "hcaptcha", "are you a robot", "verify you are human",
    "human verification", "bot verification", "unusual traffic",
    "prove you're not a robot", "checking your browser",
)

CAPTCHA_DOM_SELECTORS = (
    'iframe[src*="recaptcha"]', 'iframe[src*="hcaptcha"]',
    '.g-recaptcha', '#cf-challenge-running', '[data-sitekey]',
)

LOGIN_TEXT_INDICATORS = ("sign in", "log in", "login", "create an account", "forgot password")


@dataclass
class PageAnalysis:
    url: str
    title: str
    captcha_detected: bool = False
    captcha_indicator: str | None = None
    login_required: bool = False
    has_password_field: bool = False


async def analyze_page(page: Page) -> PageAnalysis:
    url = page.url
    title = await page.title()

    body_text = ""
    try:
        body_text = (await page.inner_text("body")).lower()
    except Exception:
        logger.warning("could not read page body text for %s", url)

    captcha_indicator = next((kw for kw in CAPTCHA_TEXT_INDICATORS if kw in body_text), None)
    if captcha_indicator is None:
        for selector in CAPTCHA_DOM_SELECTORS:
            try:
                if await page.query_selector(selector):
                    captcha_indicator = selector
                    break
            except Exception:
                continue

    has_password_field = False
    try:
        has_password_field = (await page.query_selector('input[type="password"]')) is not None
    except Exception:
        pass

    login_keyword_hit = any(kw in body_text for kw in LOGIN_TEXT_INDICATORS)
    login_required = has_password_field and login_keyword_hit

    return PageAnalysis(
        url=url, title=title,
        captcha_detected=captcha_indicator is not None, captcha_indicator=captcha_indicator,
        login_required=login_required, has_password_field=has_password_field,
    )
