"""
Macro Syllabus Distribution Engine.

Distributes all remaining TYT/AYT topics across monthly buckets for a MacroPlan.
"Remaining" = all topics for the plan's sinav_tipi minus those the student has
already mastered via SM-2 (StudentTask.is_completed=True, repetition_count >= 2).

Two algorithms:
  - even              : topics distributed uniformly in subject order (higher question_count subjects first)
  - weighted_weakness : weak topics (from ExamTopicError aggregation) placed in the earliest buckets
"""

from datetime import date, timedelta
from math import ceil

from django.utils import timezone


TURKISH_MONTHS = [
    '', 'Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
    'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık',
]


def _month_label(d: date) -> str:
    return f'{TURKISH_MONTHS[d.month]} {d.year}'


def _first_of_month(d: date) -> date:
    return d.replace(day=1)


def _last_of_month(d: date) -> date:
    next_month = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month - timedelta(days=1)


def _build_month_windows(start: date, target: date) -> list[tuple[str, date, date]]:
    """Return list of (label, start_date, end_date) for each month from start → target."""
    windows = []
    current = _first_of_month(start)
    target_month = _first_of_month(target)
    while current <= target_month:
        label = _month_label(current)
        windows.append((label, current, _last_of_month(current)))
        next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
        current = next_month
    return windows


def _mastered_topic_ids(student) -> set:
    from exams_app.models import StudentTask
    return set(
        StudentTask.objects.filter(
            student=student,
            is_completed=True,
            repetition_count__gte=2,
        ).values_list('topic_id', flat=True)
    )


def _all_topics_for_plan(sinav_tipi: str):
    """Return Topics for the plan's exam type, ordered by subject importance then name."""
    from exams_app.models import Topic, Subject

    if sinav_tipi == 'BOTH':
        exam_types = ['TYT', 'AYT']
    else:
        exam_types = [sinav_tipi]

    return list(
        Topic.objects.filter(subject__exam_type__in=exam_types)
        .select_related('subject')
        .order_by('-subject__question_count', 'subject__name', 'sub_category', 'name')
    )


def _weakness_score_map(student) -> dict:
    """Return {topic_id: total_errors} from ExamTopicError for this student."""
    from django.db.models import Sum
    from exams_app.models import ExamTopicError

    rows = (
        ExamTopicError.objects
        .filter(exam__student=student)
        .values('topic_id')
        .annotate(errors=Sum('wrong_count') + Sum('blank_count'))
    )
    return {r['topic_id']: r['errors'] for r in rows}


def generate_macro_syllabus(plan) -> None:
    """
    (Re-)generates all MacroPlanBucket + MacroPlanTopic rows for the given plan.
    Safe to call multiple times — existing buckets are deleted before rebuilding.
    """
    from curriculum_app.models import MacroPlanBucket, MacroPlanTopic

    today = date.today()
    target = plan.target_date

    # ── 1. Build monthly windows ──────────────────────────────────────────────
    windows = _build_month_windows(today, target)
    if not windows:
        return

    n_months = len(windows)

    # ── 2. Gather topics and filter out mastered ones ──────────────────────────
    all_topics   = _all_topics_for_plan(plan.sinav_tipi)
    mastered_ids = _mastered_topic_ids(plan.student)
    remaining    = [t for t in all_topics if t.id not in mastered_ids]

    if not remaining:
        return

    # ── 3. Sort remaining by algorithm ────────────────────────────────────────
    if plan.algorithm == 'weighted_weakness':
        scores = _weakness_score_map(plan.student)
        # Topics with errors come first (descending error count), then unscored topics
        remaining.sort(key=lambda t: -scores.get(t.id, 0))

    # ── 4. Distribute into buckets ────────────────────────────────────────────
    per_bucket = ceil(len(remaining) / n_months)
    distribution: list[list] = []
    for i in range(n_months):
        chunk = remaining[i * per_bucket:(i + 1) * per_bucket]
        distribution.append(chunk)

    # ── 5. Persist ────────────────────────────────────────────────────────────
    # Delete existing buckets (cascades to MacroPlanTopic)
    plan.buckets.all().delete()

    for order, ((label, start, end), topics) in enumerate(zip(windows, distribution)):
        if not topics:
            continue
        bucket = MacroPlanBucket.objects.create(
            plan=plan, label=label, start_date=start, end_date=end, order=order,
        )
        MacroPlanTopic.objects.bulk_create([
            MacroPlanTopic(bucket=bucket, topic=t, order=j)
            for j, t in enumerate(topics)
        ])

    plan.regenerated_at = timezone.now()
    plan.save(update_fields=['regenerated_at'])
