"""Divergence Index = how much the (normalized) raters disagree. This is the Trust Meter.

Higher spread = raters disagree more = lower trust. Needs at least
MIN_RATERS_FOR_DIVERGENCE contributing raters; below that the number does not exist and is
N.A. (a genuine data absence, not a policy choice).

WHICH raters contribute is the policy choice, and it is config.ALLOW_ILLUSTRATIVE_FALLBACK:

  * on  (prototype default) — every available channel contributes, and the figure ships a
    provenance label. A "mixed" spread is exactly Keppel's old 87.8: a real MSCI letter
    against a seeded S&P. It is shown, but it is never shown as if it were measured.
  * off (strict) — only REAL channels contribute, and the spread is additionally N.A.
    below MIN_REAL_RATERS_FOR_DIVERGENCE.

Keeps consensus / divergence / evidence as separate channels.
"""
from __future__ import annotations

from typing import Optional

from . import config
from .models import RaterPercentiles


def divergence_index(p: RaterPercentiles) -> Optional[float]:
    values = p.contributing_values()
    if len(values) < config.MIN_RATERS_FOR_DIVERGENCE:
        return None
    if (not config.ALLOW_ILLUSTRATIVE_FALLBACK
            and len(values) < config.MIN_REAL_RATERS_FOR_DIVERGENCE):
        return None
    return round(max(values) - min(values), 2)
