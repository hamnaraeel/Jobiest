"""Detects form fields on the current page.

Does not depend solely on CSS selectors (spec section 18): a field's
identity comes from whatever combination of label/aria-label/placeholder/
name/id the page actually provides. `field_identifier` is what's
persisted to the database for cross-request identification; the actual
element is re-located at fill time (see form_filler.py) rather than
holding a live handle across requests, since a page may have reloaded or
changed between an analyze-page call and a later fill call.
"""

from dataclasses import dataclass, field as dc_field

from playwright.async_api import Page

from app.models.enums import ApplicationFieldType

_INPUT_TYPE_MAP = {
    "email": ApplicationFieldType.EMAIL,
    "tel": ApplicationFieldType.PHONE,
    "number": ApplicationFieldType.NUMBER,
    "date": ApplicationFieldType.DATE,
    "url": ApplicationFieldType.URL,
    "file": ApplicationFieldType.FILE,
    "checkbox": ApplicationFieldType.CHECKBOX,
    "radio": ApplicationFieldType.RADIO,
}

_SKIP_INPUT_TYPES = {"submit", "button", "hidden", "reset", "image"}


@dataclass
class DetectedField:
    field_identifier: str
    label: str | None
    field_type: ApplicationFieldType
    required: bool
    current_value: str | None = None
    options: list[str] = dc_field(default_factory=list)


async def detect_fields(page: Page) -> list[DetectedField]:
    detected: list[DetectedField] = []
    elements = await page.query_selector_all("input, textarea, select")

    for index, el in enumerate(elements):
        tag = (await el.evaluate("el => el.tagName")).lower()
        input_type = "text"
        if tag == "input":
            input_type = (await el.get_attribute("type") or "text").lower()
        elif tag == "textarea":
            input_type = "textarea"
        elif tag == "select":
            input_type = "select"

        if input_type in _SKIP_INPUT_TYPES:
            continue

        name = await el.get_attribute("name")
        el_id = await el.get_attribute("id")
        placeholder = await el.get_attribute("placeholder")
        aria_label = await el.get_attribute("aria-label")
        required_attr = await el.get_attribute("required")
        aria_required = await el.get_attribute("aria-required")

        label_text = await _resolve_label(page, el, el_id)
        identifier = name or el_id or f"{tag}_{input_type}_{index}"

        if input_type in _INPUT_TYPE_MAP:
            field_type = _INPUT_TYPE_MAP[input_type]
        elif tag == "textarea":
            field_type = ApplicationFieldType.TEXTAREA
        elif tag == "select":
            field_type = ApplicationFieldType.SELECT
        else:
            field_type = ApplicationFieldType.TEXT

        options: list[str] = []
        if tag == "select":
            for opt in await el.query_selector_all("option"):
                text = (await opt.inner_text()).strip()
                if text:
                    options.append(text)

        current_value = None
        if input_type in ("checkbox", "radio"):
            current_value = "checked" if await el.is_checked() else "unchecked"
        elif tag != "select":
            try:
                current_value = await el.input_value()
            except Exception:
                current_value = None

        detected.append(DetectedField(
            field_identifier=identifier,
            label=label_text or aria_label or placeholder,
            field_type=field_type,
            required=required_attr is not None or aria_required == "true",
            current_value=current_value,
            options=options,
        ))

    return detected


async def _resolve_label(page: Page, el, el_id: str | None) -> str | None:
    if el_id:
        try:
            label_el = await page.query_selector(f'label[for="{el_id}"]')
            if label_el:
                text = (await label_el.inner_text()).strip()
                if text:
                    return text
        except Exception:
            pass
    try:
        text = await el.evaluate("el => { const l = el.closest('label'); return l ? l.innerText : null; }")
        if text:
            return text.strip()
    except Exception:
        pass
    return None
