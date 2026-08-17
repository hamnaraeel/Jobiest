"""Confidence scoring shared by every analyzer in this package (spec
sections 38-40). Two flavors:

- `confidence_from_sample_size()` for statistical/historical
  observations (response rates, CV performance, ...) -- small-sample
  protected (spec section 39): fewer than SMALL_SAMPLE_THRESHOLD data
  points caps confidence low and says so explicitly, rather than
  reporting a misleadingly precise rate off a handful of applications.
- `confidence_from_completeness()` for single-item, non-statistical
  scores (a specific job's priority score) -- based on how much of the
  scoring input was actually available, not how many historical
  applications exist.

Never claims causation (spec section 40) -- that's enforced by callers
using "observed" language, not by this module, but every reason string
here is phrased as an observation ("based on N data points"), never a
causal claim.
"""

SMALL_SAMPLE_THRESHOLD = 10

# Confidence climbs from 0.5 at the small-sample threshold, gaining
# CONFIDENCE_SLOPE per additional data point, capped at MAX_CONFIDENCE.
CONFIDENCE_SLOPE = 0.015
MAX_CONFIDENCE = 0.95


def confidence_from_sample_size(n: int, max_confidence: float = MAX_CONFIDENCE) -> tuple[float, str]:
    """Returns (confidence, confidence_reason)."""

    if n <= 0:
        return 0.0, "No historical data available yet."

    if n < SMALL_SAMPLE_THRESHOLD:
        confidence = round(min(0.15 + n * 0.03, 0.45), 2)
        point_word = "data point" if n == 1 else "data points"
        return confidence, (
            f"Early signal only -- based on {n} {point_word}, fewer than the "
            f"{SMALL_SAMPLE_THRESHOLD} normally wanted for a reliable statistical read."
        )

    confidence = round(min(max_confidence, 0.5 + (n - SMALL_SAMPLE_THRESHOLD) * CONFIDENCE_SLOPE), 2)
    return confidence, f"Based on {n} historical data points."


def confidence_from_completeness(known: int, total: int) -> tuple[float, str]:
    """For scoring a single job/application where some inputs (salary,
    location, deadline, ...) may simply be unknown rather than
    statistically thin."""

    if total <= 0:
        return 0.0, "No scoring inputs were available."
    ratio = known / total
    confidence = round(0.3 + ratio * 0.65, 2)
    return confidence, f"{known}/{total} scoring inputs were available ({round(ratio * 100)}% complete)."
