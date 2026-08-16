"""BaseApplicationAdapter: the interface every platform-specific adapter
must implement (generic HTML forms today; Greenhouse/Lever/Workday/etc.
later).

Every adapter shares the SAME submission guard, approval gate, credential
restrictions, CAPTCHA handling, and sensitive-question rules (spec
section 33) -- those live in submission_guard.py / page_analyzer.py /
field_mapper.py, which every adapter calls into rather than
reimplementing. No adapter may bypass them.
"""

from abc import ABC, abstractmethod

from playwright.async_api import Page
from sqlalchemy.orm import Session

from app.browser.page_analyzer import PageAnalysis
from app.models.application import Application
from app.models.application_field import ApplicationField


class BaseApplicationAdapter(ABC):
    platform_name: str = "unknown"

    @staticmethod
    @abstractmethod
    def detect(url: str) -> bool:
        """Whether this adapter should handle the given application URL."""

    @abstractmethod
    async def open(self, page: Page, application: Application) -> None:
        """Navigate the browser to application.application_url."""

    @abstractmethod
    async def analyze_page(self, page: Page, db: Session, application: Application) -> PageAnalysis:
        """Detect + persist ApplicationField rows for the current page."""

    @abstractmethod
    async def fill_fields(self, page: Page, db: Session, application: Application) -> list[ApplicationField]:
        """Fill only the fields safe to fill automatically."""

    @abstractmethod
    async def upload_files(self, page: Page, db: Session, application: Application) -> list[ApplicationField]:
        """Upload the approved CV/cover letter to any detected file fields."""

    @abstractmethod
    def prepare_review(self, db: Session, application: Application) -> dict:
        """Build the pre-submission review object (spec section 25)."""

    @abstractmethod
    async def submit(self, page: Page, db: Session, application: Application) -> dict:
        """Click the real submit control -- only if submission_guard allows it."""
