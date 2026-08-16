"""Playwright lifecycle management.

A real browser session has to stay alive across several separate HTTP
requests (start-browser -> analyze-page -> fill -> review -> submit).
Sessions live in an in-process registry keyed by application_id --
appropriate for a local-first, single-user tool; no Redis or multi-worker
complexity needed.

Uses Playwright's async API to match FastAPI's async route handlers
directly. A persistent browser profile (BROWSER_PROFILE_DIR) lets the
user log in to a site once, manually, and stay logged in across runs --
this module never automates credential entry (see spec section 3).
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

from app.config import get_settings

logger = logging.getLogger("app.browser.manager")


class BrowserLaunchError(RuntimeError):
    pass


@dataclass
class BrowserSession:
    application_id: int
    playwright: Playwright
    context: BrowserContext
    page: Page


_active_sessions: dict[int, BrowserSession] = {}


def _profile_dir() -> Path:
    settings = get_settings()
    path = (Path(__file__).resolve().parents[3] / "backend" / settings.browser_profile_dir).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sessions_dir(application_id: int) -> Path:
    settings = get_settings()
    path = (Path(__file__).resolve().parents[3] / "backend" / settings.application_sessions_dir / str(application_id)).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


async def start_session(application_id: int) -> BrowserSession:
    existing = _active_sessions.get(application_id)
    if existing:
        return existing

    settings = get_settings()
    playwright = await async_playwright().start()
    browser_type = getattr(playwright, settings.browser_type, None)
    if browser_type is None:
        await playwright.stop()
        raise BrowserLaunchError(f"Unknown BROWSER_TYPE '{settings.browser_type}'. Use chromium, firefox, or webkit.")

    try:
        context = await browser_type.launch_persistent_context(str(_profile_dir()), headless=settings.browser_headless)
    except Exception as exc:
        await playwright.stop()
        raise BrowserLaunchError(f"Failed to launch {settings.browser_type}: {exc}") from exc

    page = context.pages[0] if context.pages else await context.new_page()
    session = BrowserSession(application_id=application_id, playwright=playwright, context=context, page=page)
    _active_sessions[application_id] = session
    logger.info(
        "browser session started application_id=%s browser=%s headless=%s",
        application_id, settings.browser_type, settings.browser_headless,
    )
    return session


def get_session(application_id: int) -> BrowserSession | None:
    return _active_sessions.get(application_id)


async def close_session(application_id: int) -> None:
    session = _active_sessions.pop(application_id, None)
    if session is None:
        return
    try:
        await session.context.close()
    finally:
        await session.playwright.stop()
    logger.info("browser session closed application_id=%s", application_id)


async def take_screenshot(application_id: int, name: str) -> str | None:
    """No-op unless BROWSER_SCREENSHOTS=true. Never exposed publicly --
    see docs/browser-application-assistant.md for the privacy rules."""

    settings = get_settings()
    if not settings.browser_screenshots:
        return None
    session = get_session(application_id)
    if session is None:
        return None
    path = _sessions_dir(application_id) / f"{name}.png"
    await session.page.screenshot(path=str(path))
    return str(path)
