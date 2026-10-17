import hashlib
import logging

from django.conf import settings
from django.core.cache import cache

_log = logging.getLogger(__name__)

# ── Checkout rate limiting ────────────────────────────────────────────────────
_CHECKOUT_WINDOW    = 900  # 15-minute fixed window
_CHECKOUT_IP_MAX    = 10
_CHECKOUT_EMAIL_MAX = 3


def _checkout_get_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '127.0.0.1')


def _checkout_cache_keys(email, ip):
    ip_hash    = hashlib.md5(ip.encode()).hexdigest()
    email_hash = hashlib.md5(email.lower().encode()).hexdigest()
    return f'checkout_ip_{ip_hash}', f'checkout_email_{email_hash}'


def is_checkout_rate_limited(email, ip):
    key_ip, key_email = _checkout_cache_keys(email, ip)
    return (
        (cache.get(key_ip)    or 0) >= _CHECKOUT_IP_MAX
        or (cache.get(key_email) or 0) >= _CHECKOUT_EMAIL_MAX
    )


def increment_checkout_counters(email, ip):
    key_ip, key_email = _checkout_cache_keys(email, ip)
    for key in (key_ip, key_email):
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, _CHECKOUT_WINDOW)


# ── Active provider ───────────────────────────────────────────────────────────

def get_provider():
    from .providers.sandbox import SandboxProvider
    from .providers.bank_transfer import BankTransferProvider

    if settings.DEBUG or getattr(settings, 'PAYMENT_SANDBOX', False):
        return SandboxProvider()

    iban   = getattr(settings, 'PURCHASE_IBAN', '').strip()
    holder = getattr(settings, 'PURCHASE_IBAN_HOLDER', '').strip()
    bank   = getattr(settings, 'PURCHASE_BANK_NAME', '').strip()
    if iban and holder and bank:
        return BankTransferProvider(iban=iban, holder=holder, bank_name=bank)

    raise RuntimeError('No payment provider configured.')


# ── Payment success handler ───────────────────────────────────────────────────

def on_payment_success(order):
    """
    Called inside a select_for_update transaction after provider confirms payment.
    Idempotent: re-processing a paid order is a no-op.
    Non-student or different-active-coach cases are marked needs_review.
    """
    from datetime import date, timedelta

    from django.contrib.auth import get_user_model
    from django.db import transaction
    from django_q.tasks import async_task

    from users_app.models import CoachStudent

    User = get_user_model()

    with transaction.atomic():
        from .models import Order
        order = Order.objects.select_for_update().get(pk=order.pk)

        if order.status == Order.STATUS_PAID:
            return  # idempotent

        # Look up existing user by email
        try:
            user = User.objects.select_for_update().get(email__iexact=order.email)
        except User.DoesNotExist:
            user = None

        # Non-student role: do not modify, mark needs_review
        if user is not None and not user.is_student:
            _mark_needs_review(
                order,
                f'email belongs to {user.role!r} (pk={user.pk}); human review required',
            )
            return

        # Create new student if not existing
        if user is None:
            user = User(
                email=order.email.lower(),
                full_name=order.full_name,
                role='student',
                is_active=True,
                is_approved=True,
            )
            user.set_unusable_password()
            user.save()
        else:
            # Re-activate existing student
            User.objects.filter(pk=user.pk).update(is_active=True, is_approved=True)

        order.student = user

        # Conflict: student already actively linked to a different coach
        conflicting = (
            CoachStudent.objects
            .filter(student=user, active=True)
            .exclude(coach=order.coach)
            .select_related('coach')
            .first()
        )
        if conflicting:
            _mark_needs_review(
                order,
                (
                    f'student (pk={user.pk}) is already actively linked to coach '
                    f'{conflicting.coach.full_name!r} (pk={conflicting.coach_id}); '
                    f'cannot silently create a second link'
                ),
            )
            order.save(update_fields=['student', 'notes', 'status', 'updated_at'])
            return

        # Create or extend CoachStudent link
        today = date.today()
        cs, created = CoachStudent.objects.get_or_create(
            coach=order.coach,
            student=user,
            defaults={
                'source': CoachStudent.SOURCE_VAGUS,
                'active': True,
                'next_payment_due': today + timedelta(days=order.plan.duration_days),
            },
        )
        if not created:
            base = max(cs.next_payment_due or today, today)
            cs.next_payment_due = base + timedelta(days=order.plan.duration_days)
            cs.active = True
            cs.deactivation_reason = None
            cs.save(update_fields=['next_payment_due', 'active', 'deactivation_reason'])

        # Mirror invite_register_view (users_app/views.py:512): set legacy User.coach FK.
        # Roster, task-create, GorevGrubu ownership all traverse this field.
        if user.coach_id != order.coach_id:
            User.objects.filter(pk=user.pk).update(coach=order.coach)
            user.coach_id = order.coach_id

        # Apply sinif/alan snapshot from order — never overwrite an existing value.
        profile_patch = {}
        if order.sinif and not user.sinif:
            profile_patch['sinif'] = order.sinif
        if order.alan and not user.alan:
            profile_patch['alan'] = order.alan
        if profile_patch:
            User.objects.filter(pk=user.pk).update(**profile_patch)

        order.status = Order.STATUS_PAID
        order.save(update_fields=['student', 'status', 'updated_at'])

        order_pk = order.pk
        transaction.on_commit(
            lambda: async_task('purchase_app.tasks.send_purchase_emails', order_pk)
        )


def _mark_needs_review(order, reason):
    order.status = order.STATUS_NEEDS_REVIEW
    order.notes  = reason
    order.save(update_fields=['status', 'notes', 'updated_at'])
    _log.warning('Order #%s needs_review: %s', order.pk, reason)

    from django.db import transaction
    from django_q.tasks import async_task
    order_pk = order.pk
    transaction.on_commit(
        lambda: async_task('purchase_app.tasks.notify_staff_needs_review', order_pk)
    )


# ── Stale order cleanup ───────────────────────────────────────────────────────

def cancel_stale_orders():
    """
    Cancel stale orders.
    Regular pending (sandbox/other): after 2 hours.
    Bank-transfer awaiting_transfer: after BANK_TRANSFER_EXPIRY_DAYS days (default 7).
    """
    from datetime import timedelta

    from django.utils import timezone

    from .models import Order

    cutoff_2h = timezone.now() - timedelta(hours=2)
    cancelled_regular = (
        Order.objects
        .filter(status=Order.STATUS_PENDING, created_at__lt=cutoff_2h)
        .update(status=Order.STATUS_CANCELLED)
    )

    expiry_days = getattr(settings, 'BANK_TRANSFER_EXPIRY_DAYS', 7)
    cutoff_transfer = timezone.now() - timedelta(days=expiry_days)
    cancelled_transfer = (
        Order.objects
        .filter(status=Order.STATUS_AWAITING_TRANSFER, created_at__lt=cutoff_transfer)
        .update(status=Order.STATUS_CANCELLED)
    )

    total = cancelled_regular + cancelled_transfer
    if total:
        _log.info('cancel_stale_orders: cancelled %d orders (%d regular, %d transfer)',
                  total, cancelled_regular, cancelled_transfer)
    return total
