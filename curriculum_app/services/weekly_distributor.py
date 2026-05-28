"""
Weekly distributor: assigns concrete topics to MacroPlanWeekBucket rows,
creating MacroPlanWeekTopic records with target hours, activity kind, and reason.

Called once per MacroPlanBucket after weekly_mixer has already created the
4 MacroPlanWeekBucket rows.

Algorithm
---------
1. Load all MacroPlanTopic rows for the bucket in order.
2. Determine default hours per topic (from expected_hours, falling back to
   priority-based defaults: 4h CORE/baglayici, 3h others, 2h OPTIONAL).
3. Tag each topic as 'repair' (in weakness set), 'revision' (mastered once),
   or 'new' (default).
4. Distribute topics round-robin into 4 week slots; keep subject interleaving.
5. In the LAST week, if capacity allows, inject one 'trial' row pointing to
   the highest-error topic in the bucket (so every month ends with a practice
   session).
"""
from __future__ import annotations

from math import ceil


def _default_hours(topic) -> int:
    if topic.expected_hours:
        return topic.expected_hours
    if topic.is_baglayici or topic.priority_tag == 'CORE':
        return 4
    if topic.priority_tag == 'OPTIONAL':
        return 2
    return 3


def _reason_text(topic, activity: str) -> str:
    if activity == 'repair':
        return 'Zayif konu onarimi'
    if activity == 'revision':
        return 'Spaced repetition'
    if topic.is_baglayici:
        return 'Baglayici konu — temel'
    return ''


def distribute_bucket_into_weeks(
    bucket,
    weakness_topic_ids: set[int],
    mastered_topic_ids: set[int],
) -> None:
    """
    Create MacroPlanWeekTopic rows for all 4 weeks of `bucket`.
    Deletes any existing rows first (safe to re-run).
    """
    from curriculum_app.models import MacroPlanWeekTopic

    week_buckets = list(bucket.weeks.order_by('week_index'))
    if not week_buckets:
        return

    plan_topics = list(
        bucket.topics.select_related('topic__subject').order_by('order')
    )
    if not plan_topics:
        return

    n_weeks = len(week_buckets)
    per_week = ceil(len(plan_topics) / n_weeks)

    # Delete existing rows for all weeks in this bucket
    for wb in week_buckets:
        MacroPlanWeekTopic.objects.filter(week=wb).delete()

    # Distribute round-robin across weeks
    week_assignments: list[list] = [[] for _ in range(n_weeks)]
    for i, pt in enumerate(plan_topics):
        week_assignments[i % n_weeks].append(pt.topic)

    # Persist
    trial_candidate = _pick_trial_topic(plan_topics, weakness_topic_ids)

    for w_idx, (wb, topics) in enumerate(zip(week_buckets, week_assignments)):
        rows = []
        for order, topic in enumerate(topics):
            if topic.id in weakness_topic_ids:
                activity = 'repair'
            elif topic.id in mastered_topic_ids:
                activity = 'revision'
            else:
                activity = 'new'
            rows.append(MacroPlanWeekTopic(
                week=wb,
                topic=topic,
                hours=_default_hours(topic),
                activity=activity,
                reason=_reason_text(topic, activity),
                order=order,
            ))

        # Last week: add a trial row if we have a candidate and it's not already there
        if w_idx == n_weeks - 1 and trial_candidate:
            if not any(r.topic_id == trial_candidate.id for r in rows):
                rows.append(MacroPlanWeekTopic(
                    week=wb,
                    topic=trial_candidate,
                    hours=2,
                    activity='trial',
                    reason='Karisik deneme analizi',
                    order=len(rows),
                ))

        MacroPlanWeekTopic.objects.bulk_create(rows, ignore_conflicts=True)


def _pick_trial_topic(plan_topics, weakness_topic_ids: set[int]):
    """Return the highest-error topic in this bucket, or the first topic if none."""
    for pt in plan_topics:
        if pt.topic_id in weakness_topic_ids:
            return pt.topic
    return plan_topics[0].topic if plan_topics else None
