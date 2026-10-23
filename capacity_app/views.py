import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import CoachCapacityOrder
from .services import (
    cancel_stale_capacity_orders,
    create_capacity_order,
    generate_unique_ref,
    get_capacity_status,
    mark_capacity_order_paid,
)

_log = logging.getLogger(__name__)

_CLAIM_WINDOW = 600
_CLAIM_MAX = 5


def _coach_required(view_fn):
    """Decorator: must be authenticated coach."""
    from functools import wraps
    from django.contrib.auth.decorators import login_required

    @wraps(view_fn)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_coach:
            return redirect('/')
        if not request.user.is_approved:
            return redirect('users_app:awaiting_approval')
        return view_fn(request, *args, **kwargs)
    return wrapper


def _claim_rate_limited(order_token):
    from django.core.cache import cache
    key = f'cap_claim_rl_{order_token}'
    count = cache.get(key) or 0
    if count >= _CLAIM_MAX:
        return True
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, _CLAIM_WINDOW)
    return False


@_coach_required
def capacity_page(request):
    from .models import CapacitySettings

    coach = request.user
    status = get_capacity_status(coach)
    orders = CoachCapacityOrder.objects.filter(coach=coach).order_by('-created_at')[:20]
    cfg = CapacitySettings.get()
    error = None

    if request.method == 'POST':
        slots_str = request.POST.get('slots', '').strip()
        try:
            slots = int(slots_str)
            if slots < 1 or slots > 50:
                raise ValueError
        except (ValueError, TypeError):
            error = 'Geçerli bir slot sayısı girin (1–50).'
        else:
            if cfg.per_slot_price_kurus == 0:
                error = 'Fiyatlandırma henüz yapılandırılmamış. Lütfen yönetici ile iletişime geçin.'
            else:
                order = create_capacity_order(coach, slots)
                return redirect('capacity:order_instructions', order_token=str(order.token))

    return render(request, 'capacity/capacity_page.html', {
        'status':               status,
        'orders':               orders,
        'cfg':                  cfg,
        'error':                error,
        'enforcement_on':       _enforcement_on(),
        'per_student_periods':  getattr(settings, 'COACH_PER_STUDENT_PERIODS', False),
    })


@_coach_required
def capacity_order_instructions(request, order_token):
    order = get_object_or_404(CoachCapacityOrder, token=order_token, coach=request.user)
    iban = getattr(settings, 'PURCHASE_IBAN', '')
    return render(request, 'capacity/capacity_order_instructions.html', {
        'order':                order,
        'claimed':              order.payment_claimed_at is not None,
        'iban':                 iban,
        'iban_grouped':         _group_iban(iban) if iban else '',
        'holder':               getattr(settings, 'PURCHASE_IBAN_HOLDER', ''),
        'bank_name':            getattr(settings, 'PURCHASE_BANK_NAME', ''),
        'per_student_periods':  getattr(settings, 'COACH_PER_STUDENT_PERIODS', False),
    })


@require_POST
@_coach_required
def capacity_order_claim(request, order_token):
    """Coach notifies that bank transfer was completed."""
    order = get_object_or_404(CoachCapacityOrder, token=order_token, coach=request.user)

    if order.status != CoachCapacityOrder.STATUS_AWAITING_TRANSFER:
        return redirect('capacity:order_instructions', order_token=str(order_token))

    if _claim_rate_limited(str(order_token)):
        return redirect('capacity:order_instructions', order_token=str(order_token))

    sender_name = request.POST.get('sender_name', '').strip()[:80]
    is_first = order.payment_claimed_at is None

    CoachCapacityOrder.objects.filter(pk=order.pk).update(
        payment_claimed_at=timezone.now(),
        sender_name=sender_name,
    )

    if is_first:
        _log.info('capacity: order %s claimed by coach %s', order.pk, request.user.pk)
        from users_app.panel_badges import invalidate_panel_badges
        transaction.on_commit(lambda: invalidate_panel_badges('pbadge:transfers_c'))

    return redirect('capacity:order_instructions', order_token=str(order_token))


def _enforcement_on():
    return getattr(settings, 'COACH_CAPACITY_ENFORCED', False)


def _group_iban(iban):
    s = iban.replace(' ', '')
    return ' '.join(s[i:i + 4] for i in range(0, len(s), 4))


@require_POST
@_coach_required
def renewal_start(request, cs_pk):
    from .models import CapacitySettings, CoachStudentRenewalOrder
    from users_app.models import CoachStudent

    cs = get_object_or_404(CoachStudent, pk=cs_pk, coach=request.user, active=True, source=CoachStudent.SOURCE_COACH)
    cfg = CapacitySettings.get()
    if cfg.per_slot_price_kurus == 0:
        messages.error(request, 'Fiyat belirlenmemiş.')
        return redirect('users_app:coach_invites')

    open_order = CoachStudentRenewalOrder.objects.filter(
        coach_student=cs, status=CoachStudentRenewalOrder.STATUS_AWAITING_TRANSFER
    ).first()
    if open_order is None:
        open_order = CoachStudentRenewalOrder.objects.create(
            coach_student=cs,
            amount_kurus=cfg.per_slot_price_kurus,
            per_student_kurus=cfg.per_slot_price_kurus,
            ref_code=generate_unique_ref(),
        )
    return redirect('capacity:renewal_instructions', order_token=str(open_order.token))


@_coach_required
def renewal_instructions(request, order_token):
    from .models import CoachStudentRenewalOrder
    order = get_object_or_404(
        CoachStudentRenewalOrder.objects.select_related('coach_student__coach', 'coach_student__student'),
        token=order_token,
        coach_student__coach=request.user,
    )
    iban = getattr(settings, 'PURCHASE_IBAN', '')
    return render(request, 'capacity/renewal_order_instructions.html', {
        'order':        order,
        'iban':         iban,
        'iban_grouped': _group_iban(iban) if iban else '',
        'holder':       getattr(settings, 'PURCHASE_IBAN_HOLDER', ''),
        'bank_name':    getattr(settings, 'PURCHASE_BANK_NAME', ''),
        'claimed':      order.payment_claimed_at is not None,
    })


@require_POST
@_coach_required
def renewal_claim(request, order_token):
    from .models import CoachStudentRenewalOrder
    order = get_object_or_404(
        CoachStudentRenewalOrder,
        token=order_token,
        coach_student__coach=request.user,
    )
    if order.status != CoachStudentRenewalOrder.STATUS_AWAITING_TRANSFER:
        return redirect('capacity:renewal_instructions', order_token=str(order_token))
    sender_name = request.POST.get('sender_name', '').strip()[:80]
    if order.payment_claimed_at is None:
        CoachStudentRenewalOrder.objects.filter(pk=order.pk).update(
            payment_claimed_at=timezone.now(),
            sender_name=sender_name,
        )
        from users_app.panel_badges import invalidate_panel_badges
        transaction.on_commit(lambda: invalidate_panel_badges('pbadge:renewals_claimed'))
    return redirect('capacity:renewal_instructions', order_token=str(order_token))
