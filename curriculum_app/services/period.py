"""
Time-period detection based on months remaining until exam.

Periods:
  foundation   — ≥ 8 months  → focus on baglayici and CORE topics
  development  — 4-7 months  → widen coverage, intro AYT
  consolidation — 2-3 months → revision-heavy, weak topic amplification
  sprint       — < 2 months  → high-yield only, no new heavy topics
"""
from __future__ import annotations


def determine_period(months_remaining: int) -> str:
    if months_remaining >= 8:
        return 'foundation'
    if months_remaining >= 4:
        return 'development'
    if months_remaining >= 2:
        return 'consolidation'
    return 'sprint'
