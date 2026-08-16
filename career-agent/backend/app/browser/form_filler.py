"""Fills mapped fields in the browser.

Only ever called on fields the caller has already decided are safe to
fill (GenericApplicationAdapter gates this on the configured
high-confidence threshold before calling here at all) -- this module
itself does not re-decide what's safe, it just performs the fill.

`locate_field()` re-resolves the element fresh on every call rather than
holding a handle across requests, since the page may have reloaded or
changed between when a field was detected and when it's actually filled.
"""

import logging

from playwright.async_api import Locator, Page

from app.models.application_field import ApplicationField
from app.models.enums import ApplicationFieldType

logger = logging.getLogger("app.browser.form_filler")


async def locate_field(page: Page, field: ApplicationField) -> Locator | None:
    if field.label:
        try:
            locator = page.get_by_label(field.label, exact=False)
            if await locator.count() > 0:
                return locator.first
        except Exception:
            pass
    for selector in (f'#{field.field_identifier}', f'[name="{field.field_identifier}"]'):
        try:
            locator = page.locator(selector)
            if await locator.count() > 0:
                return locator.first
        except Exception:
            continue
    return None


async def fill_field(page: Page, field: ApplicationField) -> bool:
    """Returns True if the field was actually filled in the browser."""

    locator = await locate_field(page, field)
    if locator is None:
        logger.warning("could not locate field '%s' (%s) to fill", field.label, field.field_identifier)
        return False

    value = field.proposed_value
    try:
        if field.field_type == ApplicationFieldType.SELECT:
            await locator.select_option(label=value)
        elif field.field_type == ApplicationFieldType.CHECKBOX:
            if str(value).strip().lower() in ("true", "yes", "checked", "1"):
                await locator.check()
            else:
                await locator.uncheck()
        elif field.field_type == ApplicationFieldType.RADIO:
            await locator.check()
        else:
            await locator.fill(value or "")
        return True
    except Exception as exc:
        logger.warning("failed to fill field '%s' (%s): %s", field.label, field.field_identifier, exc)
        return False
