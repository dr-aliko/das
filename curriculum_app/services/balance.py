"""
TYT / AYT topic count balancing.

Returns the fraction (0.0–1.0) of the plan's total topic slots that should
be allocated to TYT topics, based on sinav_tipi, segment, and period.

Rationale (doctrine):
  - TYT is mandatory for all YKS students and gates AYT usefulness.
  - Starters should nail TYT first (higher TYT ratio).
  - Advanced students closer to exam can shift toward AYT.
  - Sprint period → max TYT protection.
"""
from __future__ import annotations

# (segment, period) → TYT ratio
_RATIO_TABLE: dict[tuple[str, str], float] = {
    ('starter',  'foundation'):    0.70,
    ('starter',  'development'):   0.50,
    ('starter',  'consolidation'): 0.35,
    ('starter',  'sprint'):        0.25,
    ('mid',      'foundation'):    0.55,
    ('mid',      'development'):   0.40,
    ('mid',      'consolidation'): 0.30,
    ('mid',      'sprint'):        0.20,
    ('advanced', 'foundation'):    0.40,
    ('advanced', 'development'):   0.30,
    ('advanced', 'consolidation'): 0.20,
    ('advanced', 'sprint'):        0.15,
}

_DEFAULT_RATIO = 0.65


def tyt_ratio(segment: str, period: str, coach_override: float | None = None) -> float:
    if coach_override is not None:
        return max(0.0, min(1.0, coach_override))
    return _RATIO_TABLE.get((segment, period), _DEFAULT_RATIO)
