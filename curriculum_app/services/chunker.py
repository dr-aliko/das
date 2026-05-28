"""
Subject-balanced monthly interleaving.

Instead of dumping all topics from one subject into a bucket before moving to
the next (v1 behaviour), chunker interleaves subjects so each month contains
a mix. This prevents the "all TYT-Matematik in January, all Fizik in February"
problem.

Algorithm:
  1. Separate topics into per-subject buckets.
  2. Round-robin across subjects until the monthly topic quota is filled.
  3. Within each subject round, topics are taken in their sorted order.
"""
from __future__ import annotations

from math import ceil
from collections import defaultdict

from exams_app.models import Topic


def interleave_into_months(
    topics: list[Topic],
    n_months: int,
) -> list[list[Topic]]:
    """
    Returns a list of n_months sub-lists, each containing a balanced mix of
    subjects. Topics that don't fit are discarded (plan covers what it can).
    """
    if not topics or n_months <= 0:
        return [[] for _ in range(n_months)]

    per_month = ceil(len(topics) / n_months)

    # Group by subject, preserving input order within each group
    subject_queues: dict[int, list[Topic]] = defaultdict(list)
    subject_order: list[int] = []
    for t in topics:
        sid = t.subject_id
        if sid not in subject_queues:
            subject_order.append(sid)
        subject_queues[sid].append(t)

    months: list[list[Topic]] = [[] for _ in range(n_months)]

    for m in range(n_months):
        filled = 0
        # Round-robin across subjects
        for sid in subject_order:
            if filled >= per_month:
                break
            q = subject_queues[sid]
            if q:
                months[m].append(q.pop(0))
                filled += 1
        # Second pass to top up if some subjects ran out early
        for sid in subject_order:
            if filled >= per_month:
                break
            q = subject_queues[sid]
            if q:
                months[m].append(q.pop(0))
                filled += 1

    return months
