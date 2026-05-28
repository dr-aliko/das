"""
Macro Syllabus Distribution Engine v2.

Replaces the simple sort+slice from engine.py with a doctrine-aware pipeline:
  1. Determine student segment (starter / mid / advanced)
  2. Determine time period (foundation / development / consolidation / sprint)
  3. Compute TYT/AYT balance ratio
  4. Gather and filter topics (prereq gating, yield deferral)
  5. Interleave subjects into monthly buckets (chunker)
  6. Create weekly activity mix buckets
  7. Run risk engine and persist PlanRiskAlert records

The old `generate_macro_syllabus` (engine.py) still works for plans whose
`algorithm` is 'even' or 'weighted_weakness' if called directly, but the
coach views will now call `generate_macro_syllabus_v2` by default.

Safe to re-run: existing buckets, week buckets, and risk alerts are deleted
before rebuilding.
"""
from __future__ import annotations

from datetime import date, timedelta

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
    windows = []
    current = _first_of_month(start)
    target_month = _first_of_month(target)
    while current <= target_month:
        windows.append((_month_label(current), current, _last_of_month(current)))
        next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
        current = next_month
    return windows


def _build_custom_windows(plan) -> list[tuple[str, date, date, str]]:
    """Returns [(label, start, end, kind), ...] sorted by start.
       kind ∈ {'TYT', 'AYT', 'BOTH'} — 'BOTH' when month falls in both ranges."""
    tyt_months: set[date] = set()
    ayt_months: set[date] = set()

    def _iter_months(start_d: date, end_d: date) -> list[date]:
        result = []
        cur = _first_of_month(start_d)
        end_m = _first_of_month(end_d)
        while cur <= end_m:
            result.append(cur)
            cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        return result

    if plan.tyt_start_date and plan.tyt_end_date:
        tyt_months = set(_iter_months(plan.tyt_start_date, plan.tyt_end_date))
    if plan.ayt_start_date and plan.ayt_end_date:
        ayt_months = set(_iter_months(plan.ayt_start_date, plan.ayt_end_date))

    all_months = sorted(tyt_months | ayt_months)
    windows = []
    for m in all_months:
        in_tyt = m in tyt_months
        in_ayt = m in ayt_months
        if in_tyt and in_ayt:
            kind = 'BOTH'
        elif in_tyt:
            kind = 'TYT'
        else:
            kind = 'AYT'
        windows.append((_month_label(m), m, _last_of_month(m), kind))
    return windows


def _mastered_topic_ids(student) -> set[int]:
    from exams_app.models import StudentTask
    return set(
        StudentTask.objects.filter(
            student=student, is_completed=True, repetition_count__gte=2,
        ).values_list('topic_id', flat=True)
    )


def _weakness_score_map(student) -> dict[int, float]:
    from django.db.models import Sum
    from exams_app.models import ExamTopicError
    rows = (
        ExamTopicError.objects.filter(exam__student=student)
        .values('topic_id')
        .annotate(errors=Sum('wrong_count') + Sum('blank_count'))
    )
    return {r['topic_id']: r['errors'] for r in rows}


def _all_topics_for_sinav(sinav_tipi: str):
    from exams_app.models import Topic
    exam_types = ['TYT', 'AYT'] if sinav_tipi == 'BOTH' else [sinav_tipi]
    return list(
        Topic.objects.filter(
            subject__exam_type__in=exam_types,
            subject__excluded_from_planning=False,
            excluded_from_planning=False,
        )
        .select_related('subject')
        .prefetch_related('depends_on')
        .order_by('-subject__question_count', 'subject__name', 'order_index', 'sub_category', 'name')
    )


def _coach_tyt_ratio_override(plan) -> float | None:
    from curriculum_app.models import PlanningRule
    try:
        rule = PlanningRule.objects.get(coach=plan.coach, rule_key='tyt_ratio')
        return float(rule.value)
    except (PlanningRule.DoesNotExist, ValueError):
        return None


def _coach_yield_threshold(plan) -> int:
    from curriculum_app.models import PlanningRule
    try:
        rule = PlanningRule.objects.get(coach=plan.coach, rule_key='yield_threshold')
        return int(rule.value)
    except (PlanningRule.DoesNotExist, ValueError):
        return 40


def generate_macro_syllabus_v2(plan) -> None:
    """
    (Re-)generates MacroPlanBucket, MacroPlanTopic, MacroPlanWeekBucket, and
    PlanRiskAlert rows for the given plan. Existing rows are deleted first.
    Manual topic assignments (is_manual=True) are preserved across regenerations.
    Also caches the computed segment on plan.segment and marks status DRAFT.
    """
    from curriculum_app.models import MacroPlan, MacroPlanBucket, MacroPlanTopic
    from curriculum_app.services.segments import determine_segment
    from curriculum_app.services.period import determine_period
    from curriculum_app.services.balance import tyt_ratio
    from curriculum_app.services.topic_filter import filter_and_sort
    from curriculum_app.services.chunker import interleave_into_months
    from curriculum_app.services.weekly_mixer import create_week_buckets
    from curriculum_app.services.weekly_distributor import distribute_bucket_into_weeks
    from curriculum_app.services.risk_engine import assess_risks

    today = date.today()
    target = plan.target_date

    # ── 1. Context ─────────────────────────────────────────────────────────────
    segment = determine_segment(plan.student)
    period  = determine_period(plan.months_remaining)

    # ── 2. Month windows ───────────────────────────────────────────────────────
    if plan.planning_mode == MacroPlan.MODE_CUSTOM:
        has_tyt = bool(plan.tyt_start_date and plan.tyt_end_date)
        has_ayt = bool(plan.ayt_start_date and plan.ayt_end_date)
        if not has_tyt and not has_ayt:
            raise ValueError('Özel aralık modu seçildi ancak TYT veya AYT tarihleri girilmedi.')
        if has_tyt and plan.tyt_end_date <= plan.tyt_start_date:
            raise ValueError('TYT bitiş tarihi başlangıç tarihinden sonra olmalı.')
        if has_ayt and plan.ayt_end_date <= plan.ayt_start_date:
            raise ValueError('AYT bitiş tarihi başlangıç tarihinden sonra olmalı.')
        raw_windows = _build_custom_windows(plan)
        if not raw_windows:
            return
    else:
        raw_windows_plain = _build_month_windows(today, target)
        if not raw_windows_plain:
            return
        default_kind = plan.sinav_tipi if plan.sinav_tipi in ('TYT', 'AYT') else 'BOTH'
        raw_windows = [(label, start, end, default_kind) for (label, start, end) in raw_windows_plain]

    # ── 3. Topic gathering ─────────────────────────────────────────────────────
    all_topics   = _all_topics_for_sinav(plan.sinav_tipi)
    mastered_ids = _mastered_topic_ids(plan.student)

    # Exclude topics the coach marked as "Halledilmiş / Gerek Yok"
    skipped_ids = set(plan.skipped_topics.values_list('topic_id', flat=True))

    remaining = [t for t in all_topics if t.id not in mastered_ids and t.id not in skipped_ids]

    if not remaining:
        return

    # ── 3a. Snapshot manual assignments before deleting buckets ────────────────
    # manual_by_label: {bucket_label: [(topic_id, order), ...]}
    manual_by_label: dict[str, list[tuple[int, int]]] = {}
    manual_topic_ids: set[int] = set()
    for mpt in MacroPlanTopic.objects.filter(
        bucket__plan=plan, is_manual=True
    ).select_related('bucket', 'topic'):
        manual_by_label.setdefault(mpt.bucket.label, []).append((mpt.topic_id, mpt.order))
        manual_topic_ids.add(mpt.topic_id)

    # Exclude manually-placed topics from auto-distribution
    remaining = [t for t in remaining if t.id not in manual_topic_ids]

    # ── 4. Weakness map (always computed — used for sort, repair tagging, risk)
    scores = _weakness_score_map(plan.student)
    weakness_ids = {tid for tid, s in scores.items() if s >= 3}

    # ── 5. Weakness sort (weighted_weakness algorithm) ─────────────────────────
    if plan.algorithm == 'weighted_weakness':
        remaining.sort(key=lambda t: -scores.get(t.id, 0))

    # ── 6. Prerequisite gating + yield deferral ────────────────────────────────
    yield_threshold = _coach_yield_threshold(plan)
    remaining = filter_and_sort(remaining, mastered_ids, period, yield_threshold)

    # ── 7. Kind-aware distribution ─────────────────────────────────────────────
    ratio_override = _coach_tyt_ratio_override(plan)
    tyt_pool = [t for t in remaining if t.subject.exam_type == 'TYT']
    ayt_pool = [t for t in remaining if t.subject.exam_type == 'AYT']

    tyt_windows  = [w for w in raw_windows if w[3] in ('TYT', 'BOTH')]
    ayt_windows  = [w for w in raw_windows if w[3] in ('AYT', 'BOTH')]

    n_tyt_slots = len(tyt_windows) or 1
    n_ayt_slots = len(ayt_windows) or 1

    tyt_dist = interleave_into_months(tyt_pool, n_tyt_slots)
    ayt_dist = interleave_into_months(ayt_pool, n_ayt_slots)

    tyt_idx = ayt_idx = 0
    window_topics: dict[int, list] = {}

    for i, (label, start, end, kind) in enumerate(raw_windows):
        if kind == 'TYT':
            window_topics[i] = tyt_dist[tyt_idx] if tyt_idx < len(tyt_dist) else []
            tyt_idx += 1
        elif kind == 'AYT':
            window_topics[i] = ayt_dist[ayt_idx] if ayt_idx < len(ayt_dist) else []
            ayt_idx += 1
        else:  # BOTH — merge TYT+AYT slices, respecting ratio
            t_slice = tyt_dist[tyt_idx] if tyt_idx < len(tyt_dist) else []
            a_slice = ayt_dist[ayt_idx] if ayt_idx < len(ayt_dist) else []
            tyt_idx += 1
            ayt_idx += 1
            ratio = tyt_ratio(segment, period, ratio_override)
            combined = t_slice + a_slice
            tyt_n = round(len(combined) * ratio)
            window_topics[i] = (
                [x for x in combined if x.subject.exam_type == 'TYT'][:tyt_n]
                + [x for x in combined if x.subject.exam_type == 'AYT'][:len(combined) - tyt_n]
            )

    # ── 8. Build a topic-id lookup for re-inserting manual topics ──────────────
    topic_obj_map = {t.id: t for t in all_topics}

    # ── 9. Persist ─────────────────────────────────────────────────────────────
    plan.buckets.all().delete()

    window_label_index: dict[str, int] = {}  # label → bucket.pk (for fallback)
    for order, (label, start, end, kind) in enumerate(raw_windows):
        auto_topics = window_topics.get(order, [])
        manual_entries = manual_by_label.get(label, [])
        if not auto_topics and not manual_entries:
            continue
        bucket = MacroPlanBucket.objects.create(
            plan=plan, label=label, start_date=start, end_date=end,
            order=order, window_kind=kind,
        )
        window_label_index[label] = bucket.pk

        # Auto topics first
        MacroPlanTopic.objects.bulk_create([
            MacroPlanTopic(bucket=bucket, topic=t, order=j, is_manual=False)
            for j, t in enumerate(auto_topics)
        ])
        # Re-insert manual topics (preserve their order offset after auto topics)
        for topic_id, manual_order in manual_entries:
            topic_obj = topic_obj_map.get(topic_id)
            if not topic_obj:
                continue
            MacroPlanTopic.objects.get_or_create(
                bucket=bucket, topic=topic_obj,
                defaults={'order': manual_order, 'is_manual': True},
            )

        create_week_buckets(bucket, period, segment)
        distribute_bucket_into_weeks(bucket, weakness_ids, mastered_ids)

    # Manual topics whose original bucket label no longer exists → put them in
    # the first available bucket so they're not silently lost.
    orphaned_labels = set(manual_by_label) - set(window_label_index)
    if orphaned_labels and window_label_index:
        first_bucket_pk = next(iter(window_label_index.values()))
        for label in orphaned_labels:
            for topic_id, manual_order in manual_by_label[label]:
                topic_obj = topic_obj_map.get(topic_id)
                if not topic_obj:
                    continue
                MacroPlanTopic.objects.get_or_create(
                    bucket_id=first_bucket_pk, topic=topic_obj,
                    defaults={'order': manual_order, 'is_manual': True},
                )

    # ── 10. Update plan metadata ───────────────────────────────────────────────
    plan.segment = segment
    plan.regenerated_at = timezone.now()
    plan.save(update_fields=['segment', 'regenerated_at'])

    # ── 11. Risk assessment ────────────────────────────────────────────────────
    assess_risks(plan)


def create_empty_buckets(plan) -> None:
    """Create MacroPlanBucket rows for each month window without topic assignments.
    Used on first plan creation so the coach starts with an empty manual board."""
    from curriculum_app.models import MacroPlan, MacroPlanBucket

    today = date.today()
    target = plan.target_date

    if plan.planning_mode == MacroPlan.MODE_CUSTOM:
        raw_windows = _build_custom_windows(plan)
        if not raw_windows:
            return
    else:
        raw_windows_plain = _build_month_windows(today, target)
        if not raw_windows_plain:
            return
        default_kind = plan.sinav_tipi if plan.sinav_tipi in ('TYT', 'AYT') else 'BOTH'
        raw_windows = [(label, start, end, default_kind) for (label, start, end) in raw_windows_plain]

    for order, (label, start, end, kind) in enumerate(raw_windows):
        MacroPlanBucket.objects.create(
            plan=plan, label=label, start_date=start, end_date=end,
            order=order, window_kind=kind,
        )
