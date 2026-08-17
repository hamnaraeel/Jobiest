"""The LLM layer (spec sections 41-44): turns already-computed,
deterministic evidence into a human-readable explanation. The LLM is
never given raw data to calculate from and never asked to produce a
number itself -- it only explains numbers/facts it's handed.

Pipeline (spec section 41):
    deterministic analytics -> structured evidence -> local LLM -> explanation -> VALIDATION

Validation (spec section 43) strips any sentence containing a number
that doesn't appear anywhere in the supplied evidence -- a deliberately
blunt, deterministic check: it can't verify semantic truth, but it
reliably catches the most common and most dangerous failure mode
(a fabricated statistic), which is exactly the failure mode this system
must never let through. If nothing survives, the caller's deterministic
fallback text (always already computed and always available) is used
instead -- the LLM is an enhancement, never a dependency.
"""

import logging
import re

from app.ai.client import OllamaClient
from app.ai.recommendation_outputs import ExplanationOutput
from app.ai.recommendation_prompts import RECOMMENDATION_EXPLANATION_PROMPT_V1

logger = logging.getLogger("app.intelligence.recommendation_explainer")

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _collect_evidence_numbers(value) -> set[str]:
    numbers: set[str] = set()

    def _walk(v):
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            numbers.add(str(v))
            numbers.add(str(round(v)))
            if 0 <= v <= 1:
                numbers.add(str(round(v * 100)))
        elif isinstance(v, dict):
            for item in v.values():
                _walk(item)
        elif isinstance(v, (list, tuple, set)):
            for item in v:
                _walk(item)
        elif isinstance(v, str):
            for match in _NUMBER_RE.findall(v):
                numbers.add(match)

    _walk(value)
    return numbers


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def validate_explanation(explanation: str, evidence: dict) -> tuple[str, list[str]]:
    """Returns (cleaned_explanation, discarded_sentences). A sentence is
    discarded if it contains any number not traceable to the evidence
    (spec sections 43-44) -- the fabricated-statistic failure mode this
    system must never let through unnoticed."""

    allowed_numbers = _collect_evidence_numbers(evidence)
    kept, discarded = [], []
    for sentence in _split_sentences(explanation):
        numbers_in_sentence = set(_NUMBER_RE.findall(sentence))
        if numbers_in_sentence - allowed_numbers:
            discarded.append(sentence)
        else:
            kept.append(sentence)
    return " ".join(kept), discarded


def explain(client: OllamaClient, evidence: dict, fallback: str) -> dict:
    """Returns {"explanation": str, "llm_used": bool, "discarded_sentences": list[str]}.
    Always returns something usable -- falls back to the deterministic
    `fallback` text (which callers already computed) if Ollama isn't
    configured/reachable, or if nothing in its output survives validation."""

    try:
        output: ExplanationOutput = client.chat_structured(RECOMMENDATION_EXPLANATION_PROMPT_V1, _evidence_to_prompt(evidence), ExplanationOutput)
    except Exception as exc:  # noqa: BLE001 -- any LLM failure falls back, never raises
        logger.warning("recommendation explanation LLM call failed, using deterministic fallback: %s", exc.__class__.__name__)
        return {"explanation": fallback, "llm_used": False, "discarded_sentences": []}

    cleaned, discarded = validate_explanation(output.explanation, evidence)
    if not cleaned.strip():
        return {"explanation": fallback, "llm_used": False, "discarded_sentences": discarded}
    return {"explanation": cleaned, "llm_used": True, "discarded_sentences": discarded}


def _evidence_to_prompt(evidence: dict) -> str:
    import json

    return f"Structured evidence:\n{json.dumps(evidence, default=str, indent=2)}"
