"""
Weekly activity mix generator.

Creates MacroPlanWeekBucket rows for each MacroPlanBucket, distributing
new-topic / revision / trial percentages based on period and segment.

Mix presets (pct_new_topic, pct_revision, pct_trial):
  foundation   starter   : 70 / 20 / 10
  foundation   mid       : 65 / 25 / 10
  foundation   advanced  : 60 / 25 / 15
  development  *         : 55 / 30 / 15
  consolidation*         : 40 / 40 / 20
  sprint       *         : 30 / 45 / 25
"""
from __future__ import annotations

from curriculum_app.models import MacroPlanBucket, MacroPlanWeekBucket

_MIX_TABLE: dict[tuple[str, str], tuple[int, int, int]] = {
    ('foundation',    'starter'):  (70, 20, 10),
    ('foundation',    'mid'):      (65, 25, 10),
    ('foundation',    'advanced'): (60, 25, 15),
    ('development',   'starter'):  (55, 30, 15),
    ('development',   'mid'):      (55, 30, 15),
    ('development',   'advanced'): (50, 30, 20),
    ('consolidation', 'starter'):  (45, 40, 15),
    ('consolidation', 'mid'):      (40, 40, 20),
    ('consolidation', 'advanced'): (35, 40, 25),
    ('sprint',        'starter'):  (35, 45, 20),
    ('sprint',        'mid'):      (30, 45, 25),
    ('sprint',        'advanced'): (25, 50, 25),
}
_DEFAULT_MIX = (55, 30, 15)


def create_week_buckets(bucket: MacroPlanBucket, period: str, segment: str) -> None:
    """
    Delete existing week buckets for `bucket` and create 4 new ones (weeks 0-3).
    All 4 weeks in a month receive the same mix (monthly granularity is sufficient
    for long-range planning; coaches can manually adjust later).
    """
    MacroPlanWeekBucket.objects.filter(bucket=bucket).delete()
    new_topic, revision, trial = _MIX_TABLE.get((period, segment), _DEFAULT_MIX)
    MacroPlanWeekBucket.objects.bulk_create([
        MacroPlanWeekBucket(
            bucket=bucket,
            week_index=w,
            pct_new_topic=new_topic,
            pct_revision=revision,
            pct_trial=trial,
        )
        for w in range(4)
    ])
