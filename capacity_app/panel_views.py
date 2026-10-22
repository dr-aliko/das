import logging
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from users_app.decorators import staff_required
from .models import CapacitySettings, CoachCapacityGrant, CoachCapacityOrder, GrantAdjustmentLog
from .services import (
    adjust_grant, create_manual_grant, get_capacity_status, mark_capacity_order_paid,
)

_log = logging.getLogger(__name__)
User = get_user_model()

_TAB = 'capacity'


def _tab_ctx():
    return {'active_tab': _TAB, 'active_section': _TAB}


@staff_required
def panel_capacity(request):
    from users_app.utils import filter_coaches_by_q
    q = request.GET.get('q', '').strip()
    coaches = list(
        User.objects.filter(role='coach', is_active=True)
        .order_by('full_name')
    )
    if q:
        coaches = filter_coaches_by_q(coaches, q)
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
        'q':            q,
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
@ratelimit(key='user', rate='20/m', method='POST', block=True)
def panel_capacity_settings(request):
    from .services import EXPLANATION_DEFAULT_TITLE, EXPLANATION_DEFAULT_BODY, parse_explanation_body
    cfg = CapacitySettings.get()
    error = None
    expl_error = None
    action = request.POST.get('action', 'save_price') if request.method == 'POST' else ''

    if request.method == 'POST':
        if action == 'save_price':
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

        elif action == 'save_explanation':
            title = request.POST.get('explanation_title', '').strip()
            body  = request.POST.get('explanation_body', '').strip()
            if not title:
                expl_error = 'Başlık boş bırakılamaz.'
            elif len(title) > 200:
                expl_error = f'Başlık en fazla 200 karakter olabilir (şu an {len(title)}).'
            elif len(body) > 1500:
                expl_error = f'Açıklama en fazla 1500 karakter olabilir (şu an {len(body)}).'
            else:
                raw_item_count = sum(
                    1 for line in body.splitlines()
                    if line.strip() and not line.strip().startswith('! ')
                )
                if raw_item_count > 8:
                    expl_error = f'En fazla 8 madde eklenebilir (şu an {raw_item_count}).'
                else:
                    cfg.explanation_title = title
                    cfg.explanation_body  = body
                    cfg.updated_by        = request.user
                    cfg.save()
                    return redirect('capacity_panel:settings')

        elif action == 'reset_explanation':
            cfg.explanation_title = EXPLANATION_DEFAULT_TITLE
            cfg.explanation_body  = EXPLANATION_DEFAULT_BODY
            cfg.updated_by        = request.user
            cfg.save()
            return redirect('capacity_panel:settings')

    form_expl_title = (
        request.POST.get('explanation_title', cfg.explanation_title)
        if expl_error else cfg.explanation_title
    )
    form_expl_body = (
        request.POST.get('explanation_body', cfg.explanation_body)
        if expl_error else cfg.explanation_body
    )

    return render(request, 'panel/capacity_settings.html', {
        **_tab_ctx(),
        'cfg':              cfg,
        'error':            error,
        'expl_error':       expl_error,
        'form_expl_title':  form_expl_title,
        'form_expl_body':   form_expl_body,
        'EXPLANATION_DEFAULT_BODY': EXPLANATION_DEFAULT_BODY,
    })


@staff_required
def panel_coach_grants(request, coach_pk):
    """Per-coach grant list and adjustment history."""
    coach = get_object_or_404(User, pk=coach_pk, role='coach')
    grants = (
        CoachCapacityGrant.objects
        .filter(coach=coach)
        .select_related('order')
        .order_by('-period_start', '-pk')
    )
    logs = (
        GrantAdjustmentLog.objects
        .filter(grant__coach=coach)
        .select_related('grant', 'adjusted_by')
        .order_by('-adjusted_at')
    )
    return render(request, 'panel/coach_grants.html', {
        **_tab_ctx(),
        'coach':      coach,
        'grants':     grants,
        'logs':       logs,
        'cap_status': get_capacity_status(coach),
        'today':      date.today(),
    })


@staff_required
@ratelimit(key='user', rate='20/m', method='POST', block=True)
def panel_grant_adjust(request, pk):
    """
    GET  ?action=reduce|end  — confirmation / entry form
    POST action=reduce|end   — execute the adjustment
    """
    grant = get_object_or_404(
        CoachCapacityGrant.objects.select_related('coach', 'order'), pk=pk
    )
    today = date.today()

    action = (
        request.GET.get('action') if request.method == 'GET'
        else request.POST.get('action', '')
    )
    if action not in ('reduce', 'end'):
        return redirect('capacity_panel:coach_grants', coach_pk=grant.coach_id)

    cap_status = get_capacity_status(grant.coach)
    error = None

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        notify = request.POST.get('notify') == 'on'

        if not reason:
            error = 'Neden belirtilmesi zorunludur.'
        elif action == 'reduce':
            try:
                new_slots = int(request.POST.get('new_slots', ''))
                if new_slots < 0 or new_slots >= grant.slots:
                    raise ValueError
            except (ValueError, TypeError):
                error = f'Yeni slot sayısı 0 ile {grant.slots - 1} arasında olmalıdır.'
            if not error:
                adjust_grant(grant.pk, 'reduce', new_slots, grant.period_end,
                             request.user, reason, notify)
                return redirect('capacity_panel:coach_grants', coach_pk=grant.coach_id)
        else:  # end
            adjust_grant(grant.pk, 'end', grant.slots, today,
                         request.user, reason, notify)
            return redirect('capacity_panel:coach_grants', coach_pk=grant.coach_id)

    # For preview: estimate free slots after change
    grant_active_slots = grant.slots if grant.is_active else 0
    if action == 'reduce':
        new_slots_default = max(0, grant.slots - 1)
        preview_delta = new_slots_default - grant_active_slots
    else:
        new_slots_default = None
        preview_delta = -grant_active_slots

    return render(request, 'panel/grant_adjust.html', {
        **_tab_ctx(),
        'grant':            grant,
        'action':           action,
        'cap_status':       cap_status,
        'today':            today,
        'error':            error,
        'is_paid_order':    grant.order is not None,
        'new_slots_default': new_slots_default,
        'preview_free':     cap_status['free'] + preview_delta,
        'post_action':      request.POST if request.method == 'POST' else None,
    })
