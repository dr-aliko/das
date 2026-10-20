import logging
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from users_app.decorators import staff_required
from .models import CapacitySettings, CoachCapacityGrant, CoachCapacityOrder
from .services import create_manual_grant, get_capacity_status, mark_capacity_order_paid

_log = logging.getLogger(__name__)
User = get_user_model()

_TAB = 'capacity'


def _tab_ctx():
    return {'active_tab': _TAB}


@staff_required
def panel_capacity(request):
    coaches = (
        User.objects.filter(role='coach', is_active=True)
        .order_by('full_name')
    )
    today = date.today()
    rows = []
    for coach in coaches:
        st = get_capacity_status(coach)
        latest_grant = (
            CoachCapacityGrant.objects
            .filter(coach=coach, period_end__gte=today)
            .order_by('-period_end')
            .first()
        )
        pending_order = (
            CoachCapacityOrder.objects
            .filter(
                coach=coach,
                status__in=[CoachCapacityOrder.STATUS_AWAITING_TRANSFER,
                            CoachCapacityOrder.STATUS_PENDING],
            )
            .order_by('-created_at')
            .first()
        )
        rows.append({
            'coach':         coach,
            'in_use':        st['in_use'],
            'granted':       st['granted'],
            'free':          st['free'],
            'period_end':    st['period_end'],
            'pending_order': pending_order,
        })

    cfg = CapacitySettings.get()
    return render(request, 'panel/capacity.html', {
        **_tab_ctx(),
        'rows':         rows,
        'cfg':          cfg,
        'orders':       CoachCapacityOrder.objects.select_related('coach').order_by('-created_at')[:100],
        'coaches_all':  User.objects.filter(role='coach', is_active=True).order_by('full_name'),
    })


@staff_required
def panel_capacity_order_detail(request, pk):
    order = get_object_or_404(
        CoachCapacityOrder.objects.select_related('coach'),
        pk=pk,
    )
    grant = CoachCapacityGrant.objects.filter(order=order).first()
    return render(request, 'panel/capacity_order_detail.html', {
        **_tab_ctx(),
        'order': order,
        'grant': grant,
    })


@staff_required
@require_POST
def panel_capacity_order_mark_paid(request, pk):
    order = get_object_or_404(CoachCapacityOrder, pk=pk)
    mark_capacity_order_paid(order)
    return redirect('capacity_panel:order_detail', pk=pk)


@staff_required
@require_POST
def panel_capacity_order_cancel(request, pk):
    order = get_object_or_404(CoachCapacityOrder, pk=pk)
    if order.status in (
        CoachCapacityOrder.STATUS_PENDING,
        CoachCapacityOrder.STATUS_AWAITING_TRANSFER,
    ):
        order.status = CoachCapacityOrder.STATUS_CANCELLED
        order.save(update_fields=['status', 'updated_at'])
    return redirect('capacity_panel:order_detail', pk=pk)


@staff_required
@require_POST
def panel_capacity_grant_create(request):
    """Manual staff comp grant."""
    coach_id  = request.POST.get('coach_id', '').strip()
    slots_str = request.POST.get('slots', '').strip()
    errors = []

    try:
        coach = User.objects.get(pk=coach_id, role='coach', is_active=True)
    except (User.DoesNotExist, ValueError):
        errors.append('Geçersiz koç seçimi.')
        coach = None

    try:
        slots = int(slots_str)
        if slots < 1 or slots > 200:
            raise ValueError
    except (ValueError, TypeError):
        errors.append('Geçerli bir slot sayısı girin (1–200).')
        slots = None

    if not errors and coach and slots:
        create_manual_grant(coach, slots, request.user)

    return redirect('capacity_panel:overview')


@staff_required
def panel_capacity_settings(request):
    cfg = CapacitySettings.get()
    error = None
    if request.method == 'POST':
        tl_str = request.POST.get('per_slot_price_tl', '').strip()
        try:
            tl = int(tl_str)
            if tl < 0:
                raise ValueError
        except (ValueError, TypeError):
            error = 'Geçerli bir tutar girin (0 veya pozitif tam sayı TL).'
        else:
            cfg.per_slot_price_kurus = tl * 100
            cfg.save()
            return redirect('capacity_panel:overview')

    return render(request, 'panel/capacity_settings.html', {
        **_tab_ctx(),
        'cfg': cfg,
        'error': error,
    })
