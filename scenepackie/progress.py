"""Simple, cautious time estimates for long-running video jobs."""
from __future__ import annotations

import math


def estimate_remaining(elapsed: float, fraction: float) -> int | None:
    """Return approximate seconds left or None when there is too little data.

    A scan's pace can vary with video decoding and the number of faces, so the
    UI labels this a rough estimate, not a guaranteed completion time.
    """
    if not math.isfinite(elapsed) or not math.isfinite(fraction):
        return None
    if elapsed < 4 or fraction < 0.025 or fraction >= 1:
        return None
    return max(0, round(elapsed * (1 - fraction) / fraction))
