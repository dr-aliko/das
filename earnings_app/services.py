import logging
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

_log = logging.getLogger(__name__)


def compute_split(student_id, coverage_start, coverage_end, pool_kurus):
    """
    Pro-rata split of pool_kurus across coaches for [coverage_start, coverage_end).

    Returns list of dicts: {coach_id, days, amount_kurus, gap_fallback}.
    Remainder from floor-division is added to the last segment only when
    all period days are covered (no gap). Gap days are paid to nobody.
    """
    from users_app.models import CoachStudent, CoachStudentInterval

    period_days = (coverage_end - coverage_start).days
    if period_days <= 0 or pool_kurus <= 0:
        return []

    intervals = list(
        CoachStudentInterval.objects
        .filter(
            student_id=student_id,
            started_at__date__lt=coverage_end,
        )
        .filter(
            Q(ended_at__isnull=True) |
            Q(ended_at__date__gt=coverage_start)
        )
        .order_by('started_at')
    )

    from django.utils.timezone import localtime

    segments = []
    for iv in intervals:
        seg_start = max(localtime(iv.started_at).date(), coverage_start)
        seg_end = coverage_end if iv.ended_at is None else min(localtime(iv.ended_at).date(), coverage_end)
        days = (seg_end - seg_start).days
        if days > 0:
            segments.append({'coach_id': iv.coach_id, 'days': days})

    if not segments:
        link = CoachStudent.objects.filter(student_id=student_id, active=True).first()
        if link is None:
            return []
        return [{'coach_id': link.coach_id, 'days': period_days,
                 'amount_kurus': (pool_kurus // 100) * 100, 'gap_fallback': True}]

    for s in segments:
        s['amount_kurus'] = (pool_kurus * s['days'] // period_days // 100) * 100
        s['gap_fallback'] = False

    return segments


def create_holding_earning(order):
    """
    Create a single held EarningRow when an Order is paid.
    Idempotent — no-op if a row already exists for this order.
    Skipped if plan.coach_share_kurus == 0 or student is unset.
    """
    from .models import EarningRow

    if not order.student_id:
        return
    if order.plan.coach_share_kurus <= 0:
        return
    if EarningRow.objects.filter(order=order).exists():
        return

    today = date.today()

    prev = (
        EarningRow.objects
        .filter(
            student_id=order.student_id,
            status__in=[
                EarningRow.STATUS_HELD,
                EarningRow.STATUS_RELEASED,
                EarningRow.STATUS_APPROVED,
                EarningRow.STATUS_PAID,
            ],
        )
        .order_by('-coverage_end')
        .first()
    )

    coverage_start = prev.coverage_end if (prev and prev.coverage_end > today) else today
    coverage_end = coverage_start + timedelta(days=order.plan.duration_days)

    EarningRow.objects.create(
        order=order,
        coach=order.coach,
        student=order.student,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        period_days=order.plan.duration_days,
        coach_days=0,
        pool_kurus=order.plan.coach_share_kurus,
        amount_kurus=0,
        kind=EarningRow.KIND_EARNING,
        status=EarningRow.STATUS_HELD,
    )


def create_earning_for_manual_record(manual_record):
    """Create a held EarningRow for a ManualPaymentRecord. Idempotent."""
    from .models import EarningRow

    if EarningRow.objects.filter(manual_record=manual_record).exists():
        return

    coverage_end = manual_record.date + timedelta(days=manual_record.days)

    EarningRow.objects.create(
        manual_record=manual_record,
        coach=manual_record.coach,
        student=manual_record.student,
        coverage_start=manual_record.date,
        coverage_end=coverage_end,
        period_days=manual_record.days,
        coach_days=0,
        pool_kurus=manual_record.coach_pool_kurus,
        amount_kurus=0,
        kind=EarningRow.KIND_EARNING,
        status=EarningRow.STATUS_HELD,
    )


def _release_one(row):
    """Compute split for a held row and set it to released."""
    from .models import EarningRow

    splits = compute_split(
        row.student_id, row.coverage_start, row.coverage_end, row.pool_kurus
    )

    if not splits:
        row.status = EarningRow.STATUS_VOID
        row.void_reason = 'no_coach_found'
        row.voided_at = timezone.now()
        row.save(update_fields=['status', 'void_reason', 'voided_at'])
        return

    shared = dict(
        order_id=row.order_id,
        manual_record_id=row.manual_record_id,
        student_id=row.student_id,
        coverage_start=row.coverage_start,
        coverage_end=row.coverage_end,
        period_days=row.period_days,
        pool_kurus=row.pool_kurus,
        kind=row.kind,
    )

    if len(splits) == 1:
        s = splits[0]
        row.coach_id = s['coach_id']
        row.coach_days = s['days']
        row.amount_kurus = s['amount_kurus']
        row.gap_fallback = s['gap_fallback']
        row.status = EarningRow.STATUS_RELEASED
        row.save(update_fields=[
            'coach_id', 'coach_days', 'amount_kurus', 'gap_fallback', 'status',
        ])
    else:
        row.delete()
        EarningRow.objects.bulk_create([
            EarningRow(
                **shared,
                coach_id=s['coach_id'],
                coach_days=s['days'],
                amount_kurus=s['amount_kurus'],
                gap_fallback=s['gap_fallback'],
                status=EarningRow.STATUS_RELEASED,
            )
            for s in splits
        ])


def release_held_earnings(today=None):
    """
    Process all held EarningRows whose coverage has ended.
    Idempotent; uses select_for_update with skip_locked.
    Returns total count of rows processed.
    """
    from .models import EarningRow

    if today is None:
        today = date.today()

    processed = 0
    while True:
        with transaction.atomic():
            batch = list(
                EarningRow.objects
                .select_for_update(skip_locked=True)
                .filter(status=EarningRow.STATUS_HELD, coverage_end__lte=today)
                [:100]
            )
            if not batch:
                break
            for row in batch:
                _release_one(row)
                processed += 1

    _log.info('release_held_earnings: processed %d rows', processed)
    return processed


def void_order_earnings(order_id, reason='order_cancelled', actor=None):
    """
    Void all open (held / released / approved) EarningRows for an order.
    Paid rows are never touched.
    """
    from .models import EarningRow

    EarningRow.objects.filter(
        order_id=order_id,
        status__in=[EarningRow.STATUS_HELD, EarningRow.STATUS_RELEASED, EarningRow.STATUS_APPROVED],
    ).update(
        status=EarningRow.STATUS_VOID,
        void_reason=reason,
        voided_at=timezone.now(),
        voided_by=actor,
    )


def approve_earning(row, actor):
    """released → approved."""
    from .models import EarningRow
    if row.status != EarningRow.STATUS_RELEASED:
        raise ValueError('Yalnızca serbest satırlar onaylanabilir.')
    row.status = EarningRow.STATUS_APPROVED
    row.approved_at = timezone.now()
    row.approved_by = actor
    row.save(update_fields=['status', 'approved_at', 'approved_by'])


def mark_paid(row, actor, payout_ref=''):
    """approved → paid (immutable after this)."""
    from .models import EarningRow
    if row.status != EarningRow.STATUS_APPROVED:
        raise ValueError('Yalnızca onaylanmış satırlar ödendi olarak işaretlenebilir.')
    row.status = EarningRow.STATUS_PAID
    row.paid_at = timezone.now()
    row.paid_by = actor
    row.payout_ref = payout_ref or ''
    row.save(update_fields=['status', 'paid_at', 'paid_by', 'payout_ref'])


def void_earning(row, actor, reason=''):
    """Void a single non-paid earning row."""
    from .models import EarningRow
    if row.status == EarningRow.STATUS_PAID:
        raise ValueError('Ödenmiş satırlar iptal edilemez.')
    row.status = EarningRow.STATUS_VOID
    row.voided_at = timezone.now()
    row.voided_by = actor
    row.void_reason = reason
    row.save(update_fields=['status', 'voided_at', 'voided_by', 'void_reason'])
