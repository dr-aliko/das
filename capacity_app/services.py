import logging
import secrets
from datetime import date, timedelta

from django.conf import settings
from django.db import transaction

_log = logging.getLogger(__name__)

# Unambiguous alphabet (same as purchase_app bank_transfer provider)
_REF_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'


def _generate_ref():
    return 'KC-' + ''.join(secrets.choice(_REF_ALPHABET) for _ in range(6))


def generate_unique_ref():
    """Generate a reference code that is unique across both order tables."""
    from purchase_app.models import Order
    from .models import CoachCapacityOrder
    while True:
        ref = _generate_ref()
        taken = (
            Order.objects.filter(provider_ref=ref).exists()
            or CoachCapacityOrder.objects.filter(ref_code=ref).exists()
        )
        if not taken:
            return ref


def is_own_student_source(source, student=None):
    """
    True if the source value counts as an 'own student' for capacity purposes.
    Rules:
      - source == 'coach' → own student
      - source == 'vagus' → NOT own student
      - source is None (NULL) → own student UNLESS the student has a paid purchase_app Order
    """
    if source == 'coach':
        return True
    if source == 'vagus':
        return False
    # NULL legacy link
    if student is not None:
        from purchase_app.models import Order
        return not Order.objects.filter(
            student=student, status=Order.STATUS_PAID
        ).exists()
    return True  # conservative: NULL with no student info → count as own


def get_capacity_status(coach):
    """
    Returns a dict:
      granted   — total slots from grants active today
      in_use    — active CoachStudent own-student links (excl. vagus-source)
      free      — granted - in_use  (may be negative for grandfathered overage)
      period_end — latest active grant end date, or None
    """
    from users_app.models import CoachStudent
    from .models import CoachCapacityGrant

    today = date.today()
    active_grants = CoachCapacityGrant.objects.filter(
        coach=coach,
        period_start__lte=today,
        period_end__gte=today,
    )
    granted = sum(g.slots for g in active_grants)
    period_end = active_grants.order_by('-period_end').values_list('period_end', flat=True).first()

    active_links = (
        CoachStudent.objects
        .filter(coach=coach, active=True)
        .exclude(source='vagus')
        .select_related('student')
    )
    in_use = 0
    for link in active_links:
        if is_own_student_source(link.source, link.student):
            in_use += 1

    return {
        'granted':    granted,
        'in_use':     in_use,
        'free':       granted - in_use,
        'period_end': period_end,
    }


def can_add_own_student(coach):
    """
    Returns (allowed: bool, error_msg: str|None).
    When COACH_CAPACITY_ENFORCED is False → always allowed.
    """
    if not getattr(settings, 'COACH_CAPACITY_ENFORCED', False):
        return True, None
    status = get_capacity_status(coach)
    if status['free'] > 0:
        return True, None
    return False, (
        'Kontenjanınız doldu. Yeni öğrenci ekleyebilmek için '
        '/coach/kontenjan/ adresinden kontenjan satın alabilirsiniz.'
    )


def create_capacity_order(coach, slots):
    """
    Create a CoachCapacityOrder in awaiting_transfer status with a unique ref code.
    Returns the order.
    """
    from .models import CapacitySettings, CoachCapacityOrder
    cfg = CapacitySettings.get()
    ref = generate_unique_ref()
    order = CoachCapacityOrder.objects.create(
        coach=coach,
        slots=slots,
        amount_kurus=cfg.per_slot_price_kurus * slots,
        per_slot_kurus=cfg.per_slot_price_kurus,
        status=CoachCapacityOrder.STATUS_AWAITING_TRANSFER,
        ref_code=ref,
    )
    return order


def mark_capacity_order_paid(order):
    """
    Atomically mark order as paid and create the grant. Idempotent.
    Returns (order, grant_created: bool).
    """
    from .models import CoachCapacityGrant, CoachCapacityOrder
    with transaction.atomic():
        order = CoachCapacityOrder.objects.select_for_update().get(pk=order.pk)
        if order.status == CoachCapacityOrder.STATUS_PAID:
            grant_created = not CoachCapacityGrant.objects.filter(order=order).exists()
            return order, grant_created

        if order.status not in (
            CoachCapacityOrder.STATUS_AWAITING_TRANSFER,
            CoachCapacityOrder.STATUS_PENDING,
        ):
            return order, False

        today = date.today()
        grant = CoachCapacityGrant.objects.create(
            coach=order.coach,
            order=order,
            slots=order.slots,
            period_start=today,
            period_end=today + timedelta(days=30),
        )
        order.status = CoachCapacityOrder.STATUS_PAID
        order.save(update_fields=['status', 'updated_at'])
        _log.info(
            'capacity: order pk=%s marked paid, grant pk=%s created for coach pk=%s',
            order.pk, grant.pk, order.coach_id,
        )
        return order, True


def create_manual_grant(coach, slots, staff):
    """Staff comp: create a grant not tied to any order."""
    from .models import CoachCapacityGrant
    today = date.today()
    grant = CoachCapacityGrant.objects.create(
        coach=coach,
        order=None,
        slots=slots,
        period_start=today,
        period_end=today + timedelta(days=30),
    )
    _log.info(
        'capacity: manual grant pk=%s created for coach pk=%s by staff pk=%s',
        grant.pk, coach.pk, staff.pk,
    )
    return grant


def cancel_stale_capacity_orders():
    """Cancel capacity orders that have been awaiting transfer for too long (7 days)."""
    from django.utils import timezone
    from .models import CoachCapacityOrder
    cutoff = timezone.now() - timedelta(days=7)
    cancelled = (
        CoachCapacityOrder.objects
        .filter(
            status=CoachCapacityOrder.STATUS_AWAITING_TRANSFER,
            created_at__lt=cutoff,
            payment_claimed_at__isnull=True,
        )
        .update(status=CoachCapacityOrder.STATUS_CANCELLED)
    )
    if cancelled:
        _log.info('capacity: cancelled %d stale orders', cancelled)
    return cancelled


def notify_expiring_grants():
    """Send a notification to coaches whose grants expire in exactly 5 days."""
    from django.utils import timezone
    from users_app.models import Notification
    from .models import CoachCapacityGrant

    today = date.today()
    target_end = today + timedelta(days=5)
    expiring = CoachCapacityGrant.objects.filter(period_end=target_end).select_related('coach')
    count = 0
    for grant in expiring:
        Notification.objects.create(
            user=grant.coach,
            title='Kontenjan bitiyor',
            body=(
                f'{grant.slots} slotluk kontenjanınız {grant.period_end.strftime("%d.%m.%Y")} '
                f'tarihinde sona eriyor. Yenilemek için kontenjan sayfasını ziyaret edin.'
            ),
            url='/coach/kontenjan/',
        )
        count += 1
    if count:
        _log.info('capacity: sent %d expiry notifications (5 days ahead)', count)
    return count


def adjust_grant(grant_pk, action, new_slots, new_period_end, staff, reason, notify=True):
    """
    Atomically reduce a grant's slots or bring forward its end date.
    Idempotent: if the grant is already at (new_slots, new_period_end), returns None.
    Returns the GrantAdjustmentLog created, or None on no-op.
    """
    from .models import CoachCapacityGrant, GrantAdjustmentLog
    with transaction.atomic():
        grant = CoachCapacityGrant.objects.select_for_update().get(pk=grant_pk)

        if grant.slots == new_slots and grant.period_end == new_period_end:
            return None  # already at target — idempotent no-op

        old_slots      = grant.slots
        old_period_end = grant.period_end

        grant.slots      = new_slots
        grant.period_end = new_period_end
        grant.save(update_fields=['slots', 'period_end'])

        log = GrantAdjustmentLog.objects.create(
            grant=grant,
            adjusted_by=staff,
            action=action,
            reason=reason,
            old_slots=old_slots,
            new_slots=new_slots,
            old_period_end=old_period_end,
            new_period_end=new_period_end,
        )

        if notify:
            from users_app.models import Notification
            Notification.objects.create(
                user=grant.coach,
                title='Kontenjanınız güncellendi',
                body='Kontenjanınız personel tarafından güncellendi. Detaylar için kontenjan sayfanızı ziyaret edin.',
                url='/coach/kontenjan/',
            )

        _log.info(
            'capacity: grant pk=%s adjusted by staff pk=%s — action=%s '
            'old_slots=%s new_slots=%s old_end=%s new_end=%s',
            grant.pk, staff.pk, action, old_slots, new_slots, old_period_end, new_period_end,
        )
        return log
