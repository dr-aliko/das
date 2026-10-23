import logging
import secrets
from datetime import date, timedelta

from django.conf import settings
from django.db import transaction

_log = logging.getLogger(__name__)

EXPLANATION_DEFAULT_TITLE = 'Kontenjan nasıl çalışır?'

EXPLANATION_DEFAULT_BODY = (
    "Kendi öğrencileriniz: Kontenjan, Vagus'ta aynı anda takip edebileceğiniz kendi "
    "öğrenci sayınızdır — yani kendiniz davet ettiğiniz öğrenciler.\n"
    "30 günlük dönem: Dönemler 30 gün sürer; ayrılan öğrencinin slotu serbest kalır "
    "ve yeniden kullanılabilir.\n"
    "Vagus öğrencileri: Vagus'un size atadığı öğrenciler kontenjanınızdan sayılmaz.\n"
    "Dönem sonu: Dönem sona erdiğinde mevcut öğrencileriniz etkilenmez; yenileme "
    "yapana kadar yalnızca yeni öğrenci ekleme kısıtlanır."
)


def parse_explanation_body(body):
    """
    Parse explanation body text into structured items.
    Returns {'items': [{'title': str, 'text': str}], 'note': str|None}
    Line formats:
      "Title: text"  → {'title': 'Title', 'text': 'text'}
      "plain"        → {'title': '', 'text': 'plain'}
      "! note text"  → note field (last occurrence wins)
    At most 8 items returned (note lines don't count).
    """
    items = []
    note = None
    for raw in (body or '').splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('! '):
            note = line[2:].strip()
        elif ':' in line:
            idx = line.index(':')
            items.append({'title': line[:idx].strip(), 'text': line[idx + 1:].strip()})
        else:
            items.append({'title': '', 'text': line})
    return {'items': items[:8], 'note': note}

# Unambiguous alphabet (same as purchase_app bank_transfer provider)
_REF_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'


def _generate_ref():
    return 'KC-' + ''.join(secrets.choice(_REF_ALPHABET) for _ in range(6))


def generate_unique_ref():
    """Generate a reference code unique across Order, CoachCapacityOrder, and CoachStudentRenewalOrder."""
    from purchase_app.models import Order
    from .models import CoachCapacityOrder, CoachStudentRenewalOrder
    while True:
        ref = _generate_ref()
        taken = (
            Order.objects.filter(provider_ref=ref).exists()
            or CoachCapacityOrder.objects.filter(ref_code=ref).exists()
            or CoachStudentRenewalOrder.objects.filter(ref_code=ref).exists()
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

    When COACH_PER_STUDENT_PERIODS=True: credit-based check.
    When COACH_PER_STUDENT_PERIODS=False: old capacity-enforcement check (unchanged).
    """
    if getattr(settings, 'COACH_PER_STUDENT_PERIODS', False):
        avail = available_credits(coach)
        if avail > 0:
            return True, None
        bal = credit_balance(coach)
        if bal <= 0:
            msg = 'Davet hakkınız yok. Yeni öğrenci ekleyebilmek için davet hakkı satın alın.'
        else:
            pending = pending_invite_count(coach)
            msg = f'{pending} davet bekliyor, hakların ayrıldı. Davet hakkınız kalmadı.'
        return False, msg

    if not getattr(settings, 'COACH_CAPACITY_ENFORCED', False):
        return True, None
    status = get_capacity_status(coach)
    if status['free'] > 0:
        return True, None
    if status['granted'] == 0:
        msg = 'Kontenjanınız yok. Yeni öğrenci ekleyebilmek için kontenjan satın alın.'
    else:
        msg = 'Kontenjanınız doldu. Yeni öğrenci ekleyebilmek için kontenjan satın alın.'
    return False, msg


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

    When COACH_PER_STUDENT_PERIODS=True: credits a ledger entry instead of a grant.
    When COACH_PER_STUDENT_PERIODS=False: old grant path (unchanged).
    """
    from .models import CoachCapacityGrant, CoachCapacityOrder
    per_student = getattr(settings, 'COACH_PER_STUDENT_PERIODS', False)

    with transaction.atomic():
        order = CoachCapacityOrder.objects.select_for_update().get(pk=order.pk)

        if per_student:
            from .models import CoachCreditLedger
            if order.status == CoachCapacityOrder.STATUS_PAID:
                return order, False

            if order.status not in (
                CoachCapacityOrder.STATUS_AWAITING_TRANSFER,
                CoachCapacityOrder.STATUS_PENDING,
            ):
                return order, False

            order.status = CoachCapacityOrder.STATUS_PAID
            order.save(update_fields=['status', 'updated_at'])

            already = CoachCreditLedger.objects.filter(
                order=order,
                reason=CoachCreditLedger.REASON_PURCHASE_APPROVED,
            ).exists()
            if not already:
                grant_credits(order.coach, order.slots, CoachCreditLedger.REASON_PURCHASE_APPROVED, order=order)
                _log.info(
                    'capacity: order pk=%s marked paid, %d credits granted for coach pk=%s',
                    order.pk, order.slots, order.coach_id,
                )
            return order, True

        # flag=False: original grant path
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


# ── Per-student period credit ledger ─────────────────────────────────────────

class InsufficientCredits(Exception):
    """Raised when consume_credit_for_invite finds the coach's raw balance at zero or below."""


def credit_balance(coach):
    """Sum of all delta values in the ledger for this coach (0 if no entries)."""
    from django.db.models import Sum
    from .models import CoachCreditLedger
    return CoachCreditLedger.objects.filter(coach=coach).aggregate(
        total=Sum('delta')
    )['total'] or 0


def pending_invite_count(coach):
    """Count of unused, non-staff-initiated invites for this coach (credits already earmarked)."""
    from users_app.models import StudentInvite
    return StudentInvite.objects.filter(
        coach=coach,
        is_used=False,
        initiated_by_staff=False,
    ).count()


def available_credits(coach):
    """Credits available to consume: raw balance minus already-pending invite count."""
    return credit_balance(coach) - pending_invite_count(coach)


def grant_credits(coach, n, reason, order=None, staff=None, notes=''):
    """Create a positive credit ledger entry for a coach."""
    from .models import CoachCreditLedger
    return CoachCreditLedger.objects.create(
        coach=coach,
        delta=n,
        reason=reason,
        order=order,
        created_by=staff,
        notes=notes,
    )


def consume_credit_for_invite(coach, invite, coach_student):
    """
    Atomically consume one credit when a coach invite is accepted.

    Idempotent: if this invite already consumed a credit, the existing entry is
    returned without creating a second one.

    Raises InsufficientCredits when the raw balance is zero or would go negative
    (consuming 1 from a balance of 0 would yield -1 < 0).

    Locking: the coach's User row is locked with SELECT FOR UPDATE before the
    balance is summed so that concurrent calls cannot both see a positive balance
    and both consume.  PostgreSQL does not allow FOR UPDATE on aggregate queries,
    which is why the lock is taken on the User row instead.
    """
    from django.contrib.auth import get_user_model
    from django.db.models import Sum
    from .models import CoachCreditLedger

    User = get_user_model()

    with transaction.atomic():
        User.objects.select_for_update().get(pk=coach.pk)

        existing = CoachCreditLedger.objects.filter(
            invite=invite,
            reason=CoachCreditLedger.REASON_CONSUMED_INVITE,
        ).first()
        if existing:
            return existing

        balance = CoachCreditLedger.objects.filter(coach=coach).aggregate(
            total=Sum('delta')
        )['total'] or 0

        if balance <= 0:
            raise InsufficientCredits(
                f'Coach pk={coach.pk} has no available credits (balance={balance}).'
            )

        return CoachCreditLedger.objects.create(
            coach=coach,
            delta=-1,
            reason=CoachCreditLedger.REASON_CONSUMED_INVITE,
            invite=invite,
            coach_student=coach_student,
        )


def adjust_credits_staff(coach, delta, staff, notes=''):
    """
    Staff-initiated signed credit adjustment.  May drive the balance negative.
    delta: positive = grant credits, negative = revoke credits.
    """
    from .models import CoachCreditLedger
    return CoachCreditLedger.objects.create(
        coach=coach,
        delta=delta,
        reason=CoachCreditLedger.REASON_STAFF_ADJUSTMENT,
        created_by=staff,
        notes=notes,
    )


def mark_renewal_order_paid(order, staff):
    """
    Atomically mark a CoachStudentRenewalOrder as paid and extend the student's period.
    Idempotent: if already PAID or CANCELLED, returns (order, False).
    Returns (order, True) when the period was extended.

    new_end = max(cs.next_payment_due or today, today) + timedelta(days=30)
    """
    from django.utils import timezone as _tz
    from .models import CoachStudentRenewalOrder
    from users_app.models import CoachStudent, Notification

    with transaction.atomic():
        order = CoachStudentRenewalOrder.objects.select_for_update().get(pk=order.pk)
        cs = CoachStudent.objects.select_for_update().get(pk=order.coach_student_id)

        if order.status in (
            CoachStudentRenewalOrder.STATUS_PAID,
            CoachStudentRenewalOrder.STATUS_CANCELLED,
        ):
            return order, False

        today = _tz.localdate()
        current_due = cs.next_payment_due or today
        base = max(current_due, today)
        new_end = base + timedelta(days=30)

        cs.next_payment_due = new_end
        cs.save(update_fields=['next_payment_due'])

        order.status = CoachStudentRenewalOrder.STATUS_PAID
        order.save(update_fields=['status', 'updated_at'])

        Notification.objects.create(
            user=cs.coach,
            title='Öğrenci süresi uzatıldı',
            body=(
                f'{cs.student.full_name} için 30 günlük süre uzatıldı. '
                f'Yeni son tarih: {cs.next_payment_due.strftime("%d.%m.%Y")}'
            ),
            url='/auth/invite-students/',
        )

        _log.info(
            'renewal: order pk=%s marked paid by staff pk=%s; '
            'coach_student pk=%s new_end=%s',
            order.pk, getattr(staff, 'pk', None), cs.pk, new_end,
        )
        return order, True


# ── Per-student wording defaults ──────────────────────────────────────────────

EXPLANATION_DEFAULT_TITLE_PER_STUDENT = 'Davet hakkı nasıl çalışır?'

EXPLANATION_DEFAULT_BODY_PER_STUDENT = (
    "Her kabul edilen davet bir hak tüketir: Bir öğrenci davetinizi kabul ettiğinde "
    "bir davet hakkı kullanılır; hak süresi dolmaz.\n"
    "30 günlük dönem: Her öğrenci, daveti kabul ettiği günden itibaren 30 günlük "
    "bireysel bir dönem başlar. Dönem sonunda öğrencinin süresi yenilenmesi gerekir.\n"
    "Bitiş uyarısı: Bir öğrencinin dönemi bitmeden 5 gün önce bildirim alırsınız.\n"
    "Süre dolunca: Süresi biten öğrencinin programı, yenileme yapılana kadar "
    "davetler sayfasından düzenlenemez.\n"
    "Öğrenci kaldırma: Öğrenciyi kaldırmak kullanılan davet hakkını iade etmez."
)


def notify_expiring_student_periods():
    """
    Notify each coach once per OWN student whose period ends in exactly 5 days.

    Runs only when COACH_PER_STUDENT_PERIODS=True.
    Idempotent: uses the Notification.url field as an idempotency key so that
    re-running the task on the same day does not create duplicate notifications.
    Returns the number of new notifications sent.
    """
    from django.conf import settings
    if not getattr(settings, 'COACH_PER_STUDENT_PERIODS', False):
        return 0

    from django.utils import timezone as _tz
    from users_app.models import CoachStudent, Notification

    today = _tz.localdate()
    target_due = today + timedelta(days=5)

    links = (
        CoachStudent.objects
        .filter(active=True, next_payment_due=target_due)
        .select_related('coach', 'student')
        .exclude(source='vagus')
    )

    count = 0
    for cs in links:
        if not is_own_student_source(cs.source, cs.student):
            continue
        reminder_url = f'/auth/invite-students/?reminder={cs.student_id}-{target_due}'
        if Notification.objects.filter(user=cs.coach, url=reminder_url).exists():
            continue
        Notification.objects.create(
            user=cs.coach,
            title='Öğrenci süresi bitiyor',
            body=(
                f'{cs.student.full_name} adlı öğrencinizin 30 günlük süresi '
                f'{target_due.strftime("%d.%m.%Y")} tarihinde sona eriyor. '
                f'Süreyi uzatmak için davetler sayfasını ziyaret edin.'
            ),
            url=reminder_url,
        )
        count += 1
    if count:
        _log.info('renewal: sent %d expiry reminders (5 days ahead)', count)
    return count


def set_student_period_staff(cs, new_end_date, staff, notes):
    """
    Staff adjusts a student's period end date.
    Writes a delta=0 ledger row with the old→new date info and returns the entry.
    """
    from .models import CoachCreditLedger
    old_date = cs.next_payment_due
    cs.next_payment_due = new_end_date
    cs.save(update_fields=['next_payment_due'])
    entry = CoachCreditLedger.objects.create(
        coach=cs.coach,
        delta=0,
        reason=CoachCreditLedger.REASON_STAFF_ADJUSTMENT,
        coach_student=cs,
        created_by=staff,
        notes=f'Süre değiştirildi: {old_date} → {new_end_date}. {notes}',
    )
    _log.info(
        'renewal: staff pk=%s set period for coach_student pk=%s: %s → %s',
        getattr(staff, 'pk', None), cs.pk, old_date, new_end_date,
    )
    return entry
