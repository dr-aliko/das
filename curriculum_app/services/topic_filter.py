"""
Topic filtering: prerequisite gating and yield-score deferral.

Rules:
1. Prerequisite gating — a topic whose depends_on set contains un-included
   topics is NOT ready unless all its prerequisites have been scheduled in
   an earlier (lower-order) bucket. In the initial pass we simply prefer
   topics whose prerequisites are already mastered or scheduled first.

2. Yield deferral — in 'sprint' period, topics with yield_score < threshold
   are deferred to the back of the list (they may fall off the end if time
   is short). Threshold default: 40 (override via coach PlanningRule).

3. OPTIONAL-tagged topics are always placed last regardless of yield.
"""
from __future__ import annotations

from exams_app.models import Topic


def filter_and_sort(
    topics: list[Topic],
    mastered_ids: set[int],
    period: str,
    yield_threshold: int = 40,
) -> list[Topic]:
    """
    Returns topics re-ordered so that:
      - prerequisite-ready topics come first
      - low-yield / OPTIONAL topics sink when in sprint
    """
    ready, not_ready, optional = [], [], []

    for t in topics:
        if t.priority_tag == Topic.PRIORITY_OPTIONAL:
            optional.append(t)
            continue
        # A topic is "ready" if all its depends_on topics are mastered
        prereq_ids = set(t.depends_on.values_list('id', flat=True))
        if prereq_ids.issubset(mastered_ids):
            ready.append(t)
        else:
            not_ready.append(t)

    if period == 'sprint':
        # In sprint, push low-yield ready topics below high-yield ones
        high = [t for t in ready if t.yield_score >= yield_threshold]
        low  = [t for t in ready if t.yield_score < yield_threshold]
        return high + low + not_ready + optional
    else:
        return ready + not_ready + optional
