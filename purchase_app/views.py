import logging
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
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
from . import verification

from users_app.views import (
    _login_get_ip,
    _login_cache_keys,
    _LOGIN_WINDOW,
    _PAIR_MAX_FAILURES,
    _IP_MAX_FAILURES,
    _LOGIN_RATE_MSG,
)

_log = logging.getLogger(__name__)

_PURCHASE_STEPS = ['Bilgiler', 'Doğrulama', 'Ödeme']


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


def _sandbox_test_emails():
    raw = getattr(settings, 'SANDBOX_TEST_EMAILS', '')
    if not raw:
        return set()
    return {e.strip().lower() for e in raw.split(',') if e.strip()}


def _coach_initials(full_name):
    parts = full_name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return full_name[:2].upper() if full_name else '?'


def _get_coach(wp_id):
    """Return coach user or None."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        return User.objects.get(
            wordpress_post_id=wp_id,
            role='coach',
            is_active=True,
            is_approved=True,
            wp_is_available=True,
        )
    except User.DoesNotExist:
        return None


def _base_ctx(coach, plans, selected_plan_id='', purchase_step=1,
              is_logged_in_student=False, mod='', login_error='',
              login_email_hint='', skip_verify=False):
    return {
        'coach':                    coach,
        'plans':                    plans,
        'coach_initials':           _coach_initials(coach.full_name),
        'selected_plan_id':         str(selected_plan_id),
        'alan_required_grades':     sorted(ALAN_REQUIRED_GRADES),
        'legal_terms_url':          getattr(settings, 'LEGAL_TERMS_URL', ''),
        'legal_distance_sales_url': getattr(settings, 'LEGAL_DISTANCE_SALES_URL', ''),
        'legal_privacy_url':        getattr(settings, 'LEGAL_PRIVACY_URL', ''),
        'purchase_step':            purchase_step,
        'purchase_steps':           _PURCHASE_STEPS,
        'is_logged_in_student':     is_logged_in_student,
        'mod':                      mod,
        'login_error':              login_error,
        'login_email_hint':         login_email_hint,
        'skip_verify':              skip_verify,
    }


def _mask_email(email):
    """al***@example.com"""
    try:
        local, domain = email.split('@', 1)
        return local[:2] + '***@' + domain
    except Exception:
        return '***'


def _safe_next(next_param, wp_id):
    """Validate next redirect; must start with /satin-al/ or fallback."""
    if next_param and next_param.startswith('/satin-al/'):
        return next_param
    return f'/satin-al/{wp_id}/'


# ── Step 1 ────────────────────────────────────────────────────────────────────

def step1(request, wp_id):
    if not _purchase_enabled():
        raise Http404

    from django.contrib.auth import get_user_model
    User = get_user_model()

    coach = _get_coach(wp_id)
    if coach is None:
        return render(request, 'purchase/unavailable.html', status=200)

    user = request.user
    is_logged_in_student = user.is_authenticated and user.is_student

    # Logged-in coach or staff → friendly block (before plans check so no 404)
    if user.is_authenticated and not user.is_student:
        return render(request, 'purchase/not_for_you.html', {
            'coach': coach,
            'coach_initials': _coach_initials(coach.full_name),
        })

    plans = Plan.objects.filter(active=True).order_by('price_kurus')
    if not plans.exists():
        raise Http404

    # ── Login tab POST (?mod=giris) ───────────────────────────────────────────
    if request.method == 'POST' and request.GET.get('mod') == 'giris':
        return _handle_login_post(request, wp_id, coach, plans)

    # ── Logged-in student ─────────────────────────────────────────────────────
    if is_logged_in_student:
        if request.method == 'GET':
            session_data = request.session.get('purchase_step1', {})
            initial = {
                'sinif': session_data.get('sinif', user.sinif or ''),
                'alan':  session_data.get('alan',  user.alan  or ''),
                'plan':  session_data.get('plan_id', str(plans.first().pk) if plans.exists() else ''),
            }
            form = PurchaseForm(initial=initial)
            ctx = _base_ctx(coach, plans,
                            selected_plan_id=initial['plan'],
                            is_logged_in_student=True,
                            skip_verify=True)
            ctx['form'] = form
            return render(request, 'purchase/purchase_page.html', ctx)

        # POST for logged-in student — inject email from authenticated user
        post_data = request.POST.copy()
        post_data['email'] = user.email
        form = PurchaseForm(post_data)
        if not form.is_valid():
            ctx = _base_ctx(coach, plans,
                            selected_plan_id=request.POST.get('plan', ''),
                            is_logged_in_student=True,
                            skip_verify=True)
            ctx['form'] = form
            return render(request, 'purchase/purchase_page.html', ctx)

        email = user.email.lower().strip()

        # Conflict check: active CoachStudent to a different coach
        from users_app.models import CoachStudent
        conflict = (
            CoachStudent.objects
            .filter(student=user, active=True)
            .exclude(coach=coach)
            .first()
        )
        if conflict:
            ctx = _base_ctx(coach, plans,
                            selected_plan_id=request.POST.get('plan', ''),
                            is_logged_in_student=True,
                            skip_verify=True)
            ctx['form'] = form
            ctx['purchase_block_msg'] = (
                f'Bu hesap zaten {conflict.coach.full_name} koçuna bağlı. '
                'Farklı bir koçtan satın alma yapılamaz.'
            )
            return render(request, 'purchase/purchase_page.html', ctx)

        # Store in session, mark verified
        plan = form.cleaned_data['plan']
        request.session['purchase_step1'] = {
            'email':          email,
            'full_name':      form.cleaned_data['full_name'],
            'phone':          form.cleaned_data['phone'],
            'sinif':          form.cleaned_data.get('sinif', ''),
            'alan':           form.cleaned_data.get('alan', ''),
            'plan_id':        str(plan.pk),
            'guardian_name':  form.cleaned_data.get('guardian_name', ''),
            'guardian_phone': form.cleaned_data.get('guardian_phone', ''),
        }
        request.session['purchase_verified_email'] = email
        return redirect('purchase:payment', wp_id=wp_id)

    # ── Anonymous ─────────────────────────────────────────────────────────────
    mod = request.GET.get('mod', '')
    login_email_hint = request.session.pop('purchase_login_email_hint', '')

    if request.method == 'GET':
        session_data = request.session.get('purchase_step1', {})
        verified_email = request.session.get('purchase_verified_email', '')
        if session_data and not verified_email:
            initial = {
                'full_name': session_data.get('full_name', ''),
                'email':     session_data.get('email', ''),
                'phone':     session_data.get('phone', ''),
                'sinif':     session_data.get('sinif', ''),
                'alan':      session_data.get('alan', ''),
                'plan':      session_data.get('plan_id', ''),
            }
            form = PurchaseForm(initial=initial)
            selected = session_data.get('plan_id', str(plans.first().pk) if plans.exists() else '')
        else:
            form = PurchaseForm()
            selected = str(plans.first().pk) if plans.exists() else ''
        ctx = _base_ctx(coach, plans, selected_plan_id=selected,
                        mod=mod, login_email_hint=login_email_hint)
        ctx['form'] = form
        return render(request, 'purchase/purchase_page.html', ctx)

    # Anonymous POST
    form = PurchaseForm(request.POST)
    if not form.is_valid():
        ctx = _base_ctx(coach, plans,
                        selected_plan_id=request.POST.get('plan', ''),
                        mod=mod)
        ctx['form'] = form
        return render(request, 'purchase/purchase_page.html', ctx)

    email = form.cleaned_data['email'].lower().strip()
    ip = _checkout_get_ip(request)

    if is_checkout_rate_limited(email, ip):
        form.add_error(None, 'Çok fazla istek gönderildi. Lütfen 15 dakika sonra tekrar deneyin.')
        ctx = _base_ctx(coach, plans,
                        selected_plan_id=request.POST.get('plan', ''),
                        mod=mod)
        ctx['form'] = form
        return render(request, 'purchase/purchase_page.html', ctx)

    increment_checkout_counters(email, ip)

    plan = form.cleaned_data['plan']
    request.session['purchase_step1'] = {
        'email':          email,
        'full_name':      form.cleaned_data['full_name'],
        'phone':          form.cleaned_data['phone'],
        'sinif':          form.cleaned_data.get('sinif', ''),
        'alan':           form.cleaned_data.get('alan', ''),
        'plan_id':        str(plan.pk),
        'guardian_name':  form.cleaned_data.get('guardian_name', ''),
        'guardian_phone': form.cleaned_data.get('guardian_phone', ''),
    }

    # Issue verification code and send email
    from django_q.tasks import async_task
    code = verification.issue_code(request.session.session_key, email)
    full_name = form.cleaned_data['full_name']
    async_task('purchase_app.tasks.send_purchase_verify_email', email, code, full_name)

    return redirect('purchase:verify', wp_id=wp_id)


def _handle_login_post(request, wp_id, coach, plans):
    """Handle login tab POST for anonymous users who already have an account."""
    from django.contrib.auth import get_user_model
    User = get_user_model()

    email = request.POST.get('login_email', '').strip().lower()
    password = request.POST.get('login_password', '').strip()
    mod = 'giris'
    login_email_hint = email

    ip = _login_get_ip(request)
    pair_key, ip_key = _login_cache_keys(email, ip)

    pair_failures = cache.get(pair_key) or 0
    ip_failures   = cache.get(ip_key)   or 0

    if pair_failures >= _PAIR_MAX_FAILURES or ip_failures >= _IP_MAX_FAILURES:
        ctx = _base_ctx(coach, plans, mod=mod,
                        login_error=_LOGIN_RATE_MSG,
                        login_email_hint=login_email_hint)
        ctx['form'] = PurchaseForm()
        return render(request, 'purchase/purchase_page.html', ctx)

    user = authenticate(request, username=email, password=password)

    if user is None or not user.is_active:
        # Increment brute-force counters
        for key in (pair_key, ip_key):
            try:
                cache.incr(key)
            except ValueError:
                cache.set(key, 1, _LOGIN_WINDOW)
        ctx = _base_ctx(coach, plans, mod=mod,
                        login_error='E-posta veya şifre hatalı.',
                        login_email_hint=login_email_hint)
        ctx['form'] = PurchaseForm()
        return render(request, 'purchase/purchase_page.html', ctx)

    if not user.is_student:
        # Non-student login attempt — reject
        ctx = _base_ctx(coach, plans, mod=mod,
                        login_error='Bu giriş yalnızca öğrenci hesapları içindir.',
                        login_email_hint=login_email_hint)
        ctx['form'] = PurchaseForm()
        return render(request, 'purchase/purchase_page.html', ctx)

    # Success — reset counters
    cache.delete(pair_key)

    auth_login(request, user)
    next_param = request.POST.get('next', '')
    return redirect(_safe_next(next_param, wp_id))


# ── Step 2: Verify ────────────────────────────────────────────────────────────

def step2_verify(request, wp_id):
    if not _purchase_enabled():
        raise Http404

    if 'purchase_step1' not in request.session:
        return redirect('purchase:page', wp_id=wp_id)

    coach = _get_coach(wp_id)
    if coach is None:
        return render(request, 'purchase/unavailable.html', status=200)

    step1_data = request.session['purchase_step1']
    email = step1_data.get('email', '')
    session_key = request.session.session_key

    can_resend_now = verification.can_resend(session_key, email)
    masked = _mask_email(email)

    if request.method == 'GET':
        return render(request, 'purchase/step2_verify.html', {
            'coach':          coach,
            'coach_initials': _coach_initials(coach.full_name),
            'purchase_step':  2,
            'purchase_steps': _PURCHASE_STEPS,
            'email':          email,
            'masked_email':   masked,
            'can_resend':     can_resend_now,
            'wp_id':          wp_id,
        })

    # POST — verify code
    submitted = request.POST.get('code', '').strip()
    result = verification.verify(session_key, email, submitted)

    if result == verification.OK:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        existing = User.objects.filter(email__iexact=email).first()

        if existing is not None:
            if existing.is_student:
                request.session['purchase_login_email_hint'] = email
                return render(request, 'purchase/step2_verify.html', {
                    'coach':                 coach,
                    'coach_initials':        _coach_initials(coach.full_name),
                    'purchase_step':         2,
                    'purchase_steps':        _PURCHASE_STEPS,
                    'email':                 email,
                    'masked_email':          masked,
                    'can_resend':            can_resend_now,
                    'wp_id':                 wp_id,
                    'account_exists_student': True,
                })
            else:
                return render(request, 'purchase/step2_verify.html', {
                    'coach':               coach,
                    'coach_initials':      _coach_initials(coach.full_name),
                    'purchase_step':       2,
                    'purchase_steps':      _PURCHASE_STEPS,
                    'email':               email,
                    'masked_email':        masked,
                    'can_resend':          can_resend_now,
                    'wp_id':               wp_id,
                    'account_exists_other': True,
                })

        # No existing account — proceed to step 3
        request.session['purchase_verified_email'] = email
        return redirect('purchase:payment', wp_id=wp_id)

    error_map = {
        verification.WRONG:        'Kod hatalı. Lütfen tekrar deneyin.',
        verification.NO_CODE:      'Kodun süresi doldu veya geçersiz. Yeni bir kod isteyin.',
        verification.MAX_ATTEMPTS: 'Çok fazla yanlış deneme. Lütfen yeni bir kod isteyin.',
    }
    return render(request, 'purchase/step2_verify.html', {
        'coach':          coach,
        'coach_initials': _coach_initials(coach.full_name),
        'purchase_step':  2,
        'purchase_steps': _PURCHASE_STEPS,
        'email':          email,
        'masked_email':   masked,
        'can_resend':     can_resend_now,
        'wp_id':          wp_id,
        'verify_error':   error_map.get(result, 'Doğrulama başarısız.'),
    })


# ── Step 2: Resend ────────────────────────────────────────────────────────────

@require_POST
def step2_resend(request, wp_id):
    if not _purchase_enabled():
        raise Http404

    if 'purchase_step1' not in request.session:
        return redirect('purchase:page', wp_id=wp_id)

    step1_data = request.session['purchase_step1']
    email = step1_data.get('email', '')
    session_key = request.session.session_key

    if not verification.can_resend(session_key, email):
        return redirect(f'/satin-al/{wp_id}/dogrula/?resend_blocked=1')

    from django_q.tasks import async_task
    code = verification.issue_code(session_key, email)
    verification.record_resend(session_key, email)
    full_name = step1_data.get('full_name', '')
    async_task('purchase_app.tasks.send_purchase_verify_email', email, code, full_name)

    return redirect('purchase:verify', wp_id=wp_id)


# ── Step 3: Payment ───────────────────────────────────────────────────────────

def step3_payment(request, wp_id):
    if not _purchase_enabled():
        raise Http404

    coach = _get_coach(wp_id)
    if coach is None:
        return render(request, 'purchase/unavailable.html', status=200)

    # Session guards
    step1_data     = request.session.get('purchase_step1')
    verified_email = request.session.get('purchase_verified_email', '')

    user = request.user
    is_logged_in_student = user.is_authenticated and user.is_student

    if not step1_data:
        return redirect('purchase:page', wp_id=wp_id)

    if is_logged_in_student:
        if verified_email.lower() != user.email.lower():
            return redirect('purchase:page', wp_id=wp_id)
    else:
        step1_email = step1_data.get('email', '')
        if not verified_email or verified_email.lower() != step1_email.lower():
            return redirect('purchase:page', wp_id=wp_id)

    try:
        plan = Plan.objects.get(pk=step1_data['plan_id'], active=True)
    except (Plan.DoesNotExist, KeyError):
        return redirect('purchase:page', wp_id=wp_id)

    email     = step1_data['email']
    full_name = step1_data['full_name']
    skip_verify = is_logged_in_student

    if request.method == 'GET':
        valid_until = date.today() + timedelta(days=plan.duration_days)
        return render(request, 'purchase/step3_payment.html', {
            'coach':          coach,
            'coach_initials': _coach_initials(coach.full_name),
            'plan':           plan,
            'amount_display': plan.price_display,
            'email':          email,
            'full_name':      full_name,
            'duration_days':  plan.duration_days,
            'valid_until':    valid_until,
            'purchase_step':  3,
            'purchase_steps': _PURCHASE_STEPS,
            'skip_verify':    skip_verify,
            'wp_id':          wp_id,
        })

    # POST — create order and redirect to payment provider
    provider = get_provider()

    order = Order(
        email=email,
        coach=coach,
        plan=plan,
        amount_kurus=plan.price_kurus,
        full_name=full_name,
        phone=step1_data.get('phone', ''),
        sinif=step1_data.get('sinif', ''),
        alan=step1_data.get('alan', ''),
        guardian_name=step1_data.get('guardian_name', ''),
        guardian_phone=step1_data.get('guardian_phone', ''),
        provider=provider.name,
    )
    if is_logged_in_student:
        order.student = user
    order.save()

    try:
        checkout_url = provider.create_checkout(order, request)
    except Exception:
        _log.exception('step3_payment: provider.create_checkout failed for order %s', order.pk)
        order.status = Order.STATUS_FAILED
        order.save(update_fields=['status', 'updated_at'])
        raise Http404

    return redirect(checkout_url)


# ── Sandbox ───────────────────────────────────────────────────────────────────

def sandbox_pay(request, order_token):
    """Sandbox payment page. Staff always; buyers via SANDBOX_TEST_EMAILS."""
    if not _sandbox_on():
        raise Http404
    order = get_object_or_404(Order, token=order_token, status=Order.STATUS_PENDING)
    is_staff = request.user.is_authenticated and request.user.is_staff
    if not is_staff and order.email.lower() not in _sandbox_test_emails():
        raise Http404
    return render(request, 'purchase/sandbox_pay.html', {'order': order})


@require_POST
def sandbox_confirm(request, order_token):
    """Sandbox payment confirm. Staff always; buyers via SANDBOX_TEST_EMAILS."""
    if not _sandbox_on():
        raise Http404
    order = get_object_or_404(Order, token=order_token, status=Order.STATUS_PENDING)
    is_staff = request.user.is_authenticated and request.user.is_staff
    if not is_staff and order.email.lower() not in _sandbox_test_emails():
        raise Http404
    on_payment_success(order)
    order.refresh_from_db()
    return redirect('purchase:success', order_token=str(order.token))


def success(request, order_token):
    """Thank-you page."""
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
