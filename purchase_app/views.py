import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import ALAN_REQUIRED_GRADES, PurchaseForm
from .models import Order, Plan
from .services import (
    _checkout_get_ip,
    get_provider,
    increment_checkout_counters,
    is_checkout_rate_limited,
    on_payment_success,
)

_log = logging.getLogger(__name__)


def _purchase_enabled():
    return (
        getattr(settings, 'SELF_PURCHASE_ENABLED', False)
        and all([
            getattr(settings, 'LEGAL_TERMS_URL', ''),
            getattr(settings, 'LEGAL_DISTANCE_SALES_URL', ''),
            getattr(settings, 'LEGAL_PRIVACY_URL', ''),
        ])
    )


def _sandbox_on():
    return settings.DEBUG or getattr(settings, 'PAYMENT_SANDBOX', False)


def _coach_initials(full_name):
    parts = full_name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return full_name[:2].upper() if full_name else '?'


def _page_ctx(coach, plans, form, selected_plan_id=''):
    return {
        'coach':                  coach,
        'plans':                  plans,
        'form':                   form,
        'coach_initials':         _coach_initials(coach.full_name),
        'selected_plan_id':       selected_plan_id,
        'alan_required_grades':   sorted(ALAN_REQUIRED_GRADES),
        'legal_terms_url':          settings.LEGAL_TERMS_URL,
        'legal_distance_sales_url': settings.LEGAL_DISTANCE_SALES_URL,
        'legal_privacy_url':        settings.LEGAL_PRIVACY_URL,
    }


def purchase_page(request, wp_id):
    if not _purchase_enabled():
        raise Http404

    from django.contrib.auth import get_user_model
    User = get_user_model()

    try:
        coach = User.objects.get(
            wordpress_post_id=wp_id,
            role='coach',
            is_active=True,
            is_approved=True,
            wp_is_available=True,
        )
    except User.DoesNotExist:
        return render(request, 'purchase/unavailable.html', status=200)

    plans = Plan.objects.filter(active=True).order_by('price_kurus')
    if not plans.exists():
        raise Http404

    first = plans.first()
    form = PurchaseForm()
    return render(request, 'purchase/purchase_page.html',
                  _page_ctx(coach, plans, form, str(first.pk) if first else ''))


@require_POST
def checkout(request, wp_id):
    if not _purchase_enabled():
        raise Http404

    from django.contrib.auth import get_user_model
    User = get_user_model()

    try:
        coach = User.objects.get(
            wordpress_post_id=wp_id,
            role='coach',
            is_active=True,
            is_approved=True,
            wp_is_available=True,
        )
    except User.DoesNotExist:
        return render(request, 'purchase/unavailable.html', status=200)

    form = PurchaseForm(request.POST)
    plans = Plan.objects.filter(active=True).order_by('price_kurus')

    if not form.is_valid():
        return render(request, 'purchase/purchase_page.html',
                      _page_ctx(coach, plans, form, request.POST.get('plan', '')))

    email = form.cleaned_data['email'].lower().strip()
    ip    = _checkout_get_ip(request)

    if is_checkout_rate_limited(email, ip):
        form.add_error(None, 'Çok fazla istek gönderildi. Lütfen 15 dakika sonra tekrar deneyin.')
        return render(request, 'purchase/purchase_page.html',
                      _page_ctx(coach, plans, form, request.POST.get('plan', '')))

    increment_checkout_counters(email, ip)

    plan     = form.cleaned_data['plan']
    provider = get_provider()

    order = Order(
        email=email,
        coach=coach,
        plan=plan,
        amount_kurus=plan.price_kurus,
        full_name=form.cleaned_data['full_name'],
        phone=form.cleaned_data['phone'],
        sinif=form.cleaned_data.get('sinif', ''),
        alan=form.cleaned_data.get('alan', ''),
        guardian_name=form.cleaned_data.get('guardian_name', ''),
        guardian_phone=form.cleaned_data.get('guardian_phone', ''),
        provider=provider.name,
    )
    order.save()

    try:
        checkout_url = provider.create_checkout(order, request)
    except Exception:
        _log.exception('checkout: provider.create_checkout failed for order %s', order.pk)
        order.status = Order.STATUS_FAILED
        order.save(update_fields=['status', 'updated_at'])
        raise Http404

    return redirect(checkout_url)


def sandbox_pay(request, order_token):
    """Fake payment page. Staff + sandbox only."""
    if not _sandbox_on() or not request.user.is_authenticated or not request.user.is_staff:
        raise Http404

    order = get_object_or_404(Order, token=order_token, status=Order.STATUS_PENDING)
    return render(request, 'purchase/sandbox_pay.html', {'order': order})


@require_POST
def sandbox_confirm(request, order_token):
    """Staff confirms sandbox payment."""
    if not _sandbox_on() or not request.user.is_authenticated or not request.user.is_staff:
        raise Http404

    order = get_object_or_404(Order, token=order_token, status=Order.STATUS_PENDING)
    on_payment_success(order)
    order.refresh_from_db()
    return redirect('purchase:success', order_token=str(order.token))


def success(request, order_token):
    """Thank-you page. Shows minimal data; token is unguessable UUID."""
    if not _purchase_enabled():
        raise Http404

    order = get_object_or_404(Order, token=order_token)
    return render(request, 'purchase/success.html', {
        'order':  order,
        'status': order.status,
    })


# ── Staff panel ───────────────────────────────────────────────────────────────

from users_app.decorators import staff_required


@staff_required
def panel_orders(request):
    orders = (
        Order.objects
        .select_related('coach', 'student', 'plan')
        .order_by('-created_at')
    )
    status_filter = request.GET.get('status', '')
    if status_filter:
        orders = orders.filter(status=status_filter)
    return render(request, 'panel/purchase_orders.html', {
        'orders':         orders,
        'status_choices': Order.STATUS_CHOICES,
        'status_filter':  status_filter,
    })


@staff_required
def panel_order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.select_related('coach', 'student', 'plan'),
        pk=pk,
    )
    return render(request, 'panel/purchase_order_detail.html', {'order': order})


@staff_required
def panel_plans(request):
    plans = Plan.objects.order_by('kind', 'price_kurus')
    return render(request, 'panel/purchase_plans.html', {'plans': plans})


@staff_required
@require_POST
def panel_plan_create(request):
    name          = request.POST.get('name', '').strip()
    kind          = request.POST.get('kind', Plan.KIND_ONE_TIME)
    price_kurus   = request.POST.get('price_kurus', '').strip()
    duration_days = request.POST.get('duration_days', '').strip()
    active        = request.POST.get('active') == 'on'

    errors = []
    if not name:
        errors.append('Ad zorunludur.')
    try:
        price_kurus_int = int(price_kurus)
        if price_kurus_int <= 0:
            raise ValueError
    except (ValueError, TypeError):
        errors.append('Geçerli bir fiyat girin (kuruş cinsinden, pozitif tam sayı).')
        price_kurus_int = None
    try:
        duration_days_int = int(duration_days)
        if duration_days_int <= 0:
            raise ValueError
    except (ValueError, TypeError):
        errors.append('Geçerli bir süre girin (pozitif tam sayı gün).')
        duration_days_int = None

    if not errors:
        Plan.objects.create(
            name=name,
            kind=kind,
            price_kurus=price_kurus_int,
            duration_days=duration_days_int,
            active=active,
        )

    plans = Plan.objects.order_by('kind', 'price_kurus')
    return render(request, 'panel/purchase_plans.html', {
        'plans': plans,
        'errors': errors,
    })


@staff_required
@require_POST
def panel_plan_update(request, pk):
    plan = get_object_or_404(Plan, pk=pk)
    name          = request.POST.get('name', '').strip()
    kind          = request.POST.get('kind', plan.kind)
    price_kurus   = request.POST.get('price_kurus', '').strip()
    duration_days = request.POST.get('duration_days', '').strip()
    active        = request.POST.get('active') == 'on'

    errors = []
    if not name:
        errors.append('Ad zorunludur.')
    try:
        price_kurus_int = int(price_kurus)
        if price_kurus_int <= 0:
            raise ValueError
    except (ValueError, TypeError):
        errors.append('Geçerli bir fiyat girin.')
        price_kurus_int = None
    try:
        duration_days_int = int(duration_days)
        if duration_days_int <= 0:
            raise ValueError
    except (ValueError, TypeError):
        errors.append('Geçerli bir süre girin.')
        duration_days_int = None

    if not errors:
        plan.name          = name
        plan.kind          = kind
        plan.price_kurus   = price_kurus_int
        plan.duration_days = duration_days_int
        plan.active        = active
        plan.save()

    plans = Plan.objects.order_by('kind', 'price_kurus')
    return render(request, 'panel/purchase_plans.html', {
        'plans':  plans,
        'errors': errors,
    })
