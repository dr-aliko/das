import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import CoachCapacityOrder
from .services import (
    cancel_stale_capacity_orders,
    create_capacity_order,
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
        'status':          status,
        'orders':          orders,
        'cfg':             cfg,
        'error':           error,
        'enforcement_on':  _enforcement_on(),
    })


@_coach_required
def capacity_order_instructions(request, order_token):
    order = get_object_or_404(CoachCapacityOrder, token=order_token, coach=request.user)
    return render(request, 'capacity/capacity_order_instructions.html', {
        'order':   order,
        'claimed': order.payment_claimed_at is not None,
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

    return redirect('capacity:order_instructions', order_token=str(order_token))


def _enforcement_on():
    from django.conf import settings
    return getattr(settings, 'COACH_CAPACITY_ENFORCED', False)
