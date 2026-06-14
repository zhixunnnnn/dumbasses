"""Divergence Index = how much the (normalized) raters disagree. This is the Trust Meter.

Higher spread = raters disagree more = lower trust. Requires >= 2 raters, else N.A.
(never fabricated). Keeps consensus / divergence / evidence as separate channels.
"""
from __future__ import annotations

from typing import Optional

from . import config
from .models import RaterPercentiles


def divergence_index(p: RaterPercentiles) -> Optional[float]:
    avail = p.available()
    if len(avail) < config.MIN_RATERS_FOR_DIVERGENCE:
        return None
    return round(max(avail) - min(avail), 2)
