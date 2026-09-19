import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.db import models
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView,
    PasswordResetView as DjangoPRView,
    PasswordResetConfirmView as DjangoPRConfirmView,
)
from django.views.generic import TemplateView
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from django.core.mail import EmailMultiAlternatives
from django_ratelimit.decorators import ratelimit

from .decorators import staff_required
from .forms import CoachRegistrationForm, EmailAuthenticationForm, InviteAcceptForm, InviteStudentForm, UserRegistrationForm
from .models import CoachAlert, CoachStudent, FeeTier, StudentAchievement, StudentInvite, User
from .services.billing import coach_billing_summary


def _reset_timeout_display():
    """Converts PASSWORD_RESET_TIMEOUT to a Turkish human-readable string."""
    secs = getattr(settings, 'PASSWORD_RESET_TIMEOUT', 3600)
    if secs >= 3600 and secs % 3600 == 0:
        return f'{secs // 3600} saat'
    return f'{secs // 60} dakika'


class CustomLoginView(LoginView):
    form_class = EmailAuthenticationForm
    template_name = 'auth/login.html'

    def form_valid(self, form):
        user = form.get_user()
        is_first_login = user.last_login is None
        response = super().form_valid(form)
        if user.is_coach and is_first_login:
            self.request.session['first_run'] = True
        return response

    def get_success_url(self):
        user = self.request.user
        if user.is_coach:
            return '/coach/'
        return '/student/'


class CustomPasswordResetView(DjangoPRView):
    template_name = 'auth/password_reset.html'
    email_template_name = 'emails/password_reset.txt'
    html_email_template_name = 'emails/password_reset.html'
    subject_template_name = 'emails/password_reset_subject.txt'
    success_url = '/auth/password-reset/done/'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['reset_timeout_display'] = _reset_timeout_display()
        return ctx

    def form_valid(self, form):
        email = form.cleaned_data['email'].lower().strip()
        cache_key = 'pwd_reset_' + hashlib.md5(email.encode()).hexdigest()
        timeout_display = _reset_timeout_display()
        if cache.get(cache_key):
            # Already sent recently — skip the email, flag session for UX message.
            # Cache key is set identically for real AND non-existent emails on the
            # first request, so this branch never leaks whether the address exists.
            self.request.session['pwd_reset_throttled'] = True
        else:
            cache.set(cache_key, 1, 1800)  # 30-minute window
            form.save(
                use_https=self.request.is_secure(),
                token_generator=self.token_generator,
                from_email=self.from_email,
                email_template_name=self.email_template_name,
                subject_template_name=self.subject_template_name,
                request=self.request,
                html_email_template_name=self.html_email_template_name,
                extra_email_context={'reset_timeout_display': timeout_display},
            )
            self.request.session.pop('pwd_reset_throttled', None)
        return HttpResponseRedirect(self.success_url)


class CustomPasswordResetDoneView(TemplateView):
    template_name = 'auth/password_reset_done.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['throttled'] = self.request.session.pop('pwd_reset_throttled', False)
        ctx['reset_timeout_display'] = _reset_timeout_display()
        return ctx


def _invalidate_other_sessions(request, user):
    """Delete all active DB sessions belonging to user except the current one.

    Django's session auth hash check would eventually reject the stale sessions
    on next request, but explicit deletion is immediate and leaves no DB clutter.
    """
    from django.contrib.sessions.models import Session
    from django.utils import timezone

    current_key = request.session.session_key
    victim_keys = []
    for session in Session.objects.filter(expire_date__gt=timezone.now()):
        if session.session_key == current_key:
            continue
        try:
            data = session.get_decoded()
            if str(data.get('_auth_user_id')) == str(user.pk):
                victim_keys.append(session.session_key)
        except Exception:
            pass
    if victim_keys:
        Session.objects.filter(session_key__in=victim_keys).delete()


class CustomPasswordResetConfirmView(DjangoPRConfirmView):
    template_name = 'auth/password_reset_confirm.html'
    success_url = '/auth/password-reset/complete/'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['reset_timeout_display'] = _reset_timeout_display()
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        _invalidate_other_sessions(self.request, self.user)
        return response


def register_view(request):
    """Public registration — creates coach accounts pending admin approval."""
    if request.user.is_authenticated:
        return redirect('/')
    if request.method == 'POST':
        form = CoachRegistrationForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                email=form.cleaned_data['email'],
                full_name=form.cleaned_data['full_name'],
                role='coach',
                password=form.cleaned_data['password1'],
            )
            user.is_approved = False
            user.is_active = False   # blocked until admin approves
            user.save(update_fields=['is_approved', 'is_active'])
            return redirect('users_app:awaiting_approval')
    else:
        form = CoachRegistrationForm()
    return render(request, 'auth/register.html', {'form': form})


def awaiting_approval_view(request):
    return render(request, 'auth/awaiting_approval.html')


# ── Coach invite management ───────────────────────────────────────────────────

def _send_invite_email(invite, request):
    from django_q.tasks import async_task
    async_task('users_app.tasks.send_invite_email_task', invite.id)


@ratelimit(key='user_or_ip', rate='20/d', block=True)
def coach_invite_view(request):
    from users_app.decorators import coach_required
    # Apply decorator programmatically so the function can be referenced by name in urls.py
    if not request.user.is_authenticated or not request.user.is_coach:
        return redirect('users_app:login')
    if not request.user.is_approved:
        return redirect('users_app:awaiting_approval')

    invites = StudentInvite.objects.filter(coach=request.user).order_by('-created_at')
    form = InviteStudentForm()

    if request.method == 'POST':
        form = InviteStudentForm(request.POST)
        if form.is_valid():
            invite = StudentInvite.objects.create(
                coach=request.user,
                email=form.cleaned_data['email'],
                full_name=form.cleaned_data.get('full_name', ''),
                token=StudentInvite.generate_token(),
            )
            _send_invite_email(invite, request)
            messages.success(request, f'{invite.email} adresine davet gönderildi.')
            return redirect('users_app:coach_invites')

    invite_accepted = invites.filter(is_used=True).count()
    invite_pending  = invites.filter(is_used=False).count()
    return render(request, 'coach/invites.html', {
        'form': form,
        'invites': invites,
        'invite_accepted': invite_accepted,
        'invite_pending':  invite_pending,
        'invite_total':    invite_accepted + invite_pending,
    })


def revoke_invite(request, invite_id):
    """AJAX: coach revokes a pending invitation — deletes the record, invalidating the token."""
    from django.http import JsonResponse
    if not request.user.is_authenticated or not request.user.is_coach:
        return JsonResponse({'ok': False, 'error': 'Yetkisiz'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    try:
        invite = StudentInvite.objects.get(id=invite_id, coach=request.user, is_used=False)
    except StudentInvite.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Davet bulunamadı veya zaten kabul edildi.'}, status=404)
    invite.delete()
    return JsonResponse({'ok': True})


# ── Student invite acceptance ─────────────────────────────────────────────────

def invite_register_view(request, token):
    invite = StudentInvite.objects.filter(token=token, is_used=False).first()
    if not invite:
        from django.http import Http404
        raise Http404

    if request.method == 'POST':
        form = InviteAcceptForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                email=invite.email,
                full_name=form.cleaned_data['full_name'],
                role='student',
                password=form.cleaned_data['password1'],
            )
            user.coach = invite.coach
            user.is_approved = True
            user.is_active = True
            user.save(update_fields=['coach', 'is_approved', 'is_active'])

            source = (
                CoachStudent.SOURCE_VAGUS if invite.initiated_by_staff
                else CoachStudent.SOURCE_COACH
            )
            next_payment_due = None
            if invite.start_date:
                next_payment_due = invite.start_date + timedelta(days=30)
            CoachStudent.objects.get_or_create(
                coach=invite.coach,
                student=user,
                defaults={
                    'active': True,
                    'source': source,
                    'next_payment_due': next_payment_due,
                },
            )

            invite.is_used = True
            invite.save(update_fields=['is_used'])

            login(request, user)
            request.session['first_run'] = True
            messages.success(request, f'Hoş geldin, {user.full_name}!')
            return redirect('/student/')
    else:
        form = InviteAcceptForm(initial={'full_name': invite.full_name})

    return render(request, 'auth/invite_register.html', {'form': form, 'invite': invite})


def logout_view(request):
    logout(request)
    return redirect('/auth/login/')



# ──────────────────────────────────────────────
# Coaching Inbox — Alert API endpoints
# ──────────────────────────────────────────────

def _coach_inbox_context(coach):
    """Alerts visible in the inbox: not dismissed, not expired, sorted severity-first."""
    from datetime import date as _date
    return (
        CoachAlert.objects
        .filter(coach=coach, is_dismissed=False)
        .filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gte=_date.today()))
        .select_related('student')
        .order_by(
            models.Case(
                models.When(severity='critical', then=0),
                models.When(severity='warning',  then=1),
                models.When(severity='positive', then=2),
                default=3, output_field=models.IntegerField(),
            ),
            '-created_at',
        )
    )


def coach_inbox_api(request):
    """GET — return JSON list of active inbox alerts for the logged-in coach."""
    if not (request.user.is_authenticated and request.user.is_coach):
        return JsonResponse({'ok': False}, status=403)
    SEVERITY_ICON = {'critical': '🔴', 'warning': '🟡', 'positive': '🟢'}
    alerts = []
    for a in _coach_inbox_context(request.user):
        alerts.append({
            'id':         a.id,
            'type':       a.alert_type,
            'severity':   a.severity,
            'icon':       SEVERITY_ICON.get(a.severity, ''),
            'title':      a.title,
            'detail':     a.detail,
            'student_id': a.student_id,
            'student_name': a.student.full_name,
            'student_initial': a.student.full_name[:1].upper(),
            'is_read':    a.is_read,
            'created_at': a.created_at.strftime('%d %b %Y'),
        })
    unread = sum(1 for a in alerts if not a['is_read'])
    return JsonResponse({'ok': True, 'alerts': alerts, 'unread': unread})


def alert_mark_read(request, alert_id):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    if not (request.user.is_authenticated and request.user.is_coach):
        return JsonResponse({'ok': False}, status=403)
    CoachAlert.objects.filter(id=alert_id, coach=request.user).update(is_read=True)
    return JsonResponse({'ok': True})


def alert_dismiss(request, alert_id):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    if not (request.user.is_authenticated and request.user.is_coach):
        return JsonResponse({'ok': False}, status=403)
    CoachAlert.objects.filter(id=alert_id, coach=request.user).update(is_dismissed=True, is_read=True)
    return JsonResponse({'ok': True})


def alert_mark_all_read(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    if not (request.user.is_authenticated and request.user.is_coach):
        return JsonResponse({'ok': False}, status=403)
    CoachAlert.objects.filter(coach=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'ok': True})


# ──────────────────────────────────────────────
# DAS-404/405/406 — Profile V2
# ──────────────────────────────────────────────

def _profile_streak(user):
    """Consecutive calendar days (ending today or yesterday) with at least one exam."""
    from exams_app.models import Exam
    dates = set(Exam.objects.filter(student=user).values_list('exam_date', flat=True))
    if not dates:
        return 0
    streak, day = 0, date.today()
    while day in dates:
        streak += 1
        day -= timedelta(days=1)
    if streak == 0:
        day = date.today() - timedelta(days=1)
        while day in dates:
            streak += 1
            day -= timedelta(days=1)
    return streak


@login_required
def activity_calendar_api(request):
    """
    AJAX endpoint returning activity data for a calendar month.
    ?offset=0  → current month
    ?offset=1  → previous month
    ?offset=N  → N months back
    Returns JSON: {month_label, year, month, first_weekday, total_days, active_days, offset}
    """
    import calendar as _cal
    from exams_app.models import Exam, StudentTask

    user = request.user
    if not (user.is_authenticated and user.is_student):
        return JsonResponse({'ok': False}, status=403)

    try:
        offset = max(0, int(request.GET.get('offset', 0)))
    except ValueError:
        offset = 0

    today = date.today()
    # Walk back 'offset' months from current month
    year, month = today.year, today.month
    for _ in range(offset):
        month -= 1
        if month == 0:
            month = 12
            year -= 1

    TR_MONTHS = ['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran',
                 'Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık']
    total_days = _cal.monthrange(year, month)[1]
    # Python weekday of the 1st (Mon=0 … Sun=6)
    first_weekday = date(year, month, 1).weekday()

    month_start = date(year, month, 1)
    month_end   = date(year, month, total_days)

    exam_dates = set(
        Exam.objects.filter(student=user, exam_date__gte=month_start, exam_date__lte=month_end)
        .values_list('exam_date', flat=True)
    )
    task_dates = set(
        StudentTask.objects.filter(
            student=user, is_completed=True,
            completed_at__date__gte=month_start, completed_at__date__lte=month_end
        ).values_list('completed_at__date', flat=True)
    )
    active_days = {d.day for d in (exam_dates | task_dates)}

    return JsonResponse({
        'ok':           True,
        'month_label':  f'{TR_MONTHS[month - 1]} {year}',
        'year':         year,
        'month':        month,
        'first_weekday': first_weekday,
        'total_days':   total_days,
        'active_days':  sorted(active_days),
        'offset':       offset,
        'has_next':     offset > 0,       # can navigate forward (toward present)
        'has_prev':     True,             # can always go further back
    })


@login_required
def profil_view(request):
    """DAS-404/405: Profile page with KPI stats, streak, badges, and 7-day heatmap."""
    from exams_app.models import Exam, StudentTask
    user = request.user

    exam_qs = Exam.objects.filter(student=user).prefetch_related('results')
    total_exams = exam_qs.count()

    best_net = 0.0
    for exam in exam_qs:
        net = sum(float(r.net_score) for r in exam.results.all())
        if net > best_net:
            best_net = net

    # Use cached streak fields (updated by streak_engine on each qualifying action)
    current_streak = user.current_streak if user.is_student else 0
    longest_streak = user.longest_streak if user.is_student else 0

    stats = {
        'total_exams':     total_exams,
        'best_net':        round(best_net, 1),
        'streak':          current_streak,
        'longest_streak':  longest_streak,
    }

    # 7-day activity heatmap (last 7 calendar days including today)
    activity_week = []
    if user.is_student:
        today = date.today()
        exam_dates = set(
            Exam.objects.filter(student=user, exam_date__gte=today - timedelta(days=6))
            .values_list('exam_date', flat=True)
        )
        task_dates = set(
            StudentTask.objects.filter(student=user, is_completed=True,
                                       completed_at__date__gte=today - timedelta(days=6))
            .values_list('completed_at__date', flat=True)
        )
        active_dates = exam_dates | task_dates
        activity_week = [
            {'date': today - timedelta(days=6 - i), 'active': (today - timedelta(days=6 - i)) in active_dates}
            for i in range(7)
        ]

    # Badges
    if user.is_student:
        unlocked_qs = StudentAchievement.objects.filter(student=user).order_by('-awarded_at')
        unlocked_map = {a.badge_key: a.awarded_at for a in unlocked_qs}
        all_badges = [
            {
                'key':        key,
                'label':      label,
                'icon':       StudentAchievement.BADGE_META.get(key, {}).get('icon', '🏅'),
                'hint':       StudentAchievement.BADGE_META.get(key, {}).get('hint', ''),
                'unlocked':   key in unlocked_map,
                'awarded_at': unlocked_map.get(key),
            }
            for key, label in StudentAchievement.BADGE_CHOICES
        ]
    else:
        all_badges = []

    # Sınav Hedefi auto-calculation from sinif
    target_year = None
    if user.is_student and user.sinif:
        from datetime import date as _date
        current_year = _date.today().year
        sinif_offset = {'9': 3, '10': 2, '11': 1, '12': 0, 'mezun': 0}.get(user.sinif)
        if sinif_offset is not None:
            target_year = current_year + sinif_offset + 1  # +1: next YKS cycle

    has_completed_placement = False
    if user.is_student:
        from exams_app.models import StudentExamAttempt
        has_completed_placement = StudentExamAttempt.objects.filter(
            student=user, is_completed=True, exam__is_active=True
        ).exists()

    return render(request, 'profile/profile_v2.html', {
        'stats':                   stats,
        'activity_week':           activity_week,
        'all_badges':              all_badges,
        'target_year':             target_year,
        'alan_choices':            User.ALAN_CHOICES,
        'sinif_choices':           User.SINIF_CHOICES,
        'has_completed_placement': has_completed_placement,
        'v2_shell':                True,
        'shell_hide_fab':          True,
    })


@login_required
@require_http_methods(['POST'])
def alan_sinif_save(request):
    """Save alan (field of study) and/or sinif (grade) for the logged-in student."""
    if not request.user.is_student:
        return JsonResponse({'ok': False, 'error': 'not a student'}, status=403)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'ok': False, 'error': 'invalid JSON'}, status=400)

    valid_alan  = {k for k, _ in User.ALAN_CHOICES}
    valid_sinif = {k for k, _ in User.SINIF_CHOICES}

    fields_to_save = []
    if 'alan' in data:
        val = data['alan']
        if val not in valid_alan and val != '':
            return JsonResponse({'ok': False, 'error': 'invalid alan'}, status=400)
        request.user.alan = val
        fields_to_save.append('alan')
    if 'sinif' in data:
        val = data['sinif']
        if val not in valid_sinif and val != '':
            return JsonResponse({'ok': False, 'error': 'invalid sinif'}, status=400)
        request.user.sinif = val
        fields_to_save.append('sinif')

    if fields_to_save:
        request.user.save(update_fields=fields_to_save)

    # Return updated target_year so frontend can update without reload
    from datetime import date as _date
    sinif = request.user.sinif
    target_year = None
    if sinif:
        sinif_offset = {'9': 3, '10': 2, '11': 1, '12': 0, 'mezun': 0}.get(sinif)
        if sinif_offset is not None:
            target_year = _date.today().year + sinif_offset + 1

    return JsonResponse({'ok': True, 'target_year': target_year})


@login_required
@require_http_methods(['POST'])
def theme_save(request):
    """DAS-406: Async theme preference update — updates DB + returns new class."""
    try:
        data  = json.loads(request.body)
        theme = data.get('theme', '')
    except (json.JSONDecodeError, AttributeError):
        theme = request.POST.get('theme', '')

    if theme not in ('auto', 'light', 'dark'):
        return JsonResponse({'ok': False, 'error': 'invalid theme'}, status=400)

    request.user.theme = theme
    request.user.save(update_fields=['theme'])
    return JsonResponse({'ok': True, 'theme': theme, 'html_class': f'das-theme-{theme}'})


@login_required
def profil_ayarlar(request):
    """Settings page — legal, feedback, WhatsApp, notifications."""
    from django.conf import settings as djsettings
    return render(request, 'profile/settings.html', {
        'v2_shell': True,
        'shell_hide_fab': True,
        'vapid_public_key': djsettings.VAPID_PUBLIC_KEY,
    })


@login_required
@require_http_methods(['POST'])
def geri_bildirim_gonder(request):
    """Accept feedback form submission and email it to support."""
    from django.utils import timezone

    tip     = request.POST.get('tip', '').strip()
    mesaj   = request.POST.get('mesaj', '').strip()
    ua      = request.POST.get('user_agent', '')
    screen  = request.POST.get('screen_info', '')

    if not mesaj:
        return JsonResponse({'ok': False, 'error': 'Mesaj boş olamaz.'}, status=400)

    user = request.user
    ip   = (request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or request.META.get('REMOTE_ADDR', ''))
    zaman = timezone.now().strftime('%Y-%m-%d %H:%M UTC')

    tip_labels = {'hata': 'Hata Bildirimi', 'oneri': 'Öneri', 'soru': 'Soru'}
    tip_label  = tip_labels.get(tip, tip or 'Genel')

    subject = f'[Vagus Geri Bildirim] {tip_label} — {user.full_name}'
    body = (
        f"Tür: {tip_label}\n"
        f"Kullanıcı: {user.full_name} ({user.email}) | Rol: {user.role} | ID: {user.id}\n\n"
        f"Mesaj:\n{mesaj}\n\n"
        f"--- Teknik Bilgiler ---\n"
        f"Tarih: {zaman}\nIP: {ip}\nTarayıcı: {ua}\nEkran: {screen}"
    )

    email_msg = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email='Vagus <noreply@vagus.tr>',
        to=['info@vagus.tr', 'kayaa3413@gmail.com'],
        reply_to=[user.email],
    )
    gorsel = request.FILES.get('gorsel')
    if gorsel:
        _ALLOWED_MIME = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
        _MAX_SIZE = 5 * 1024 * 1024  # 5 MB

        if gorsel.size > _MAX_SIZE:
            return JsonResponse({'ok': False, 'error': 'Görsel 5 MB\'dan büyük olamaz.'}, status=400)
        if gorsel.content_type not in _ALLOWED_MIME:
            return JsonResponse({'ok': False, 'error': 'Yalnızca JPEG, PNG, WebP veya GIF yükleyebilirsiniz.'}, status=400)
        try:
            from PIL import Image
            img = Image.open(gorsel)
            img.verify()
            gorsel.seek(0)
        except Exception:
            return JsonResponse({'ok': False, 'error': 'Geçersiz görsel dosyası.'}, status=400)

        email_msg.attach(gorsel.name, gorsel.read(), gorsel.content_type)

    try:
        email_msg.send()
    except Exception:
        return JsonResponse({'ok': False, 'error': 'E-posta gönderilemedi. Lütfen daha sonra tekrar deneyin.'}, status=500)

    return JsonResponse({'ok': True})


# ── Web Push subscription management ─────────────────────────────────────────

@login_required
@require_http_methods(['POST'])
def push_subscribe(request):
    """Save or reactivate a browser push subscription for the current user."""
    from .models import PushSubscription
    try:
        data     = json.loads(request.body)
        endpoint = data.get('endpoint', '').strip()
        keys     = data.get('keys', {})
        p256dh   = keys.get('p256dh', '').strip()
        auth_key = keys.get('auth', '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    if not (endpoint and p256dh and auth_key):
        return JsonResponse({'ok': False, 'error': 'Missing fields'}, status=400)

    PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            'user':      request.user,
            'p256dh':    p256dh,
            'auth':      auth_key,
            'is_active': True,
        },
    )
    return JsonResponse({'ok': True})


@login_required
@require_http_methods(['POST'])
def push_unsubscribe(request):
    """Deactivate a push subscription (called when user turns off notifications)."""
    from .models import PushSubscription
    try:
        data     = json.loads(request.body)
        endpoint = data.get('endpoint', '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    if endpoint:
        PushSubscription.objects.filter(user=request.user, endpoint=endpoint).update(is_active=False)
    else:
        PushSubscription.objects.filter(user=request.user).update(is_active=False)

    return JsonResponse({'ok': True})


@login_required
@require_http_methods(['POST'])
def push_test(request):
    """Send a real test push notification to all active subscriptions of the logged-in user."""
    from .services.notifications import send_push_notification
    from django.conf import settings as djsettings

    if not djsettings.VAPID_PRIVATE_KEY:
        return JsonResponse({'ok': False, 'error': 'VAPID not configured'}, status=500)

    sent, failed = send_push_notification(
        request.user,
        title='Vagus Test Bildirimi',
        body='Bildirimler çalışıyor! Harika.',
        url='/profil/ayarlar/',
    )

    if sent == 0 and failed == 0:
        return JsonResponse({'ok': False, 'error': 'No active subscriptions found'}, status=404)

    return JsonResponse({'ok': True, 'sent': sent, 'failed': failed})


def _rel_time_tr(dt):
    from django.utils import timezone
    diff = timezone.now() - dt
    secs = int(diff.total_seconds())
    if secs < 60:
        return 'Az önce'
    mins = secs // 60
    if mins < 60:
        return f'{mins} dakika önce'
    hours = mins // 60
    if hours < 24:
        return f'{hours} saat önce'
    days = hours // 24
    if days == 1:
        return 'Dün'
    if days < 30:
        return f'{days} gün önce'
    return dt.strftime('%d.%m.%Y')


@login_required
@require_http_methods(['GET'])
def student_notifications_api(request):
    from .models import Notification
    if not request.user.is_student:
        return JsonResponse({'ok': False}, status=403)
    qs = Notification.objects.filter(user=request.user).order_by('-created_at')[:50]
    notifications = [
        {
            'id': n.id,
            'title': n.title,
            'body': n.body,
            'url': n.url,
            'is_read': n.is_read,
            'time': _rel_time_tr(n.created_at),
        }
        for n in qs
    ]
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({'ok': True, 'notifications': notifications, 'unread_count': unread_count})


@login_required
@require_http_methods(['POST'])
def student_notification_read(request, pk):
    from .models import Notification
    if not request.user.is_student:
        return JsonResponse({'ok': False}, status=403)
    Notification.objects.filter(user=request.user, pk=pk).update(is_read=True)
    return JsonResponse({'ok': True})


@login_required
@require_http_methods(['POST'])
def student_notification_mark_all_read(request):
    from .models import Notification
    if not request.user.is_student:
        return JsonResponse({'ok': False}, status=403)
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'ok': True})


# ── Coach billing view ────────────────────────────────────────────────────────

@login_required
def coach_billing_view(request):
    if not request.user.is_coach:
        return redirect('/')
    summary = coach_billing_summary(request.user)
    return render(request, 'coach/odeme.html', {'summary': summary})


def _tier_add_defaults(tiers):
    """Return (next_order, next_min) as pre-fill suggestions for the add-tier form."""
    if not tiers:
        return 1, 1
    next_order = max(t.order for t in tiers) + 1
    non_null_maxes = [t.max_students for t in tiers if t.max_students is not None]
    next_min = max(non_null_maxes) + 1 if non_null_maxes else max(t.min_students for t in tiers) + 1
    return next_order, next_min


def _fee_tier_sections():
    sections = []
    for source_val, source_label in (('vagus', 'Vagus'), ('coach', 'Koç')):
        tiers = list(FeeTier.objects.filter(source=source_val).order_by('order'))
        next_order, next_min = _tier_add_defaults(tiers)
        sections.append((source_val, source_label, tiers, next_order, next_min))
    return sections


# ── Staff panel — billing management ─────────────────────────────────────────

@staff_required
def panel_billing_view(request):
    coach_filter_id = None
    raw = request.GET.get('coach_id', '').strip()
    if raw:
        try:
            coach_filter_id = int(raw)
        except ValueError:
            pass

    qs = (
        CoachStudent.objects
        .filter(student__is_active=True)  # include active=False rows for audit history
        .select_related('coach', 'student')
        .order_by('coach__full_name', 'student__full_name')
    )
    if coach_filter_id:
        qs = qs.filter(coach_id=coach_filter_id)

    today = date.today()
    unclassified = []  # only active + unclassified (triage queue)
    coaches_map = {}
    active_link_count = 0

    for link in qs:
        days = (link.next_payment_due - today).days if (link.next_payment_due and link.active) else None
        row = {'link': link, 'days': days, 'inactive': not link.active}
        if link.active:
            active_link_count += 1
            if link.source is None:
                unclassified.append(row)
        cid = link.coach_id
        if cid not in coaches_map:
            coaches_map[cid] = {'coach': link.coach, 'rows': [], 'removed_count': 0}
        coaches_map[cid]['rows'].append(row)
        if not link.active:
            coaches_map[cid]['removed_count'] += 1

    all_coaches = list(
        User.objects.filter(role='coach', is_active=True).order_by('full_name')
    )

    coaches_list = list(coaches_map.values())
    for group in coaches_list:
        group['summary'] = coach_billing_summary(group['coach'])

    return render(request, 'panel/odeme.html', {
        'unclassified': unclassified,
        'coaches': coaches_list,
        'total_links': active_link_count,
        'unclassified_count': len(unclassified),
        'all_coaches': all_coaches,
        'coach_filter_id': coach_filter_id or '',
        'active_tab': 'classification',
        'fee_tier_sections': _fee_tier_sections(),
    })


@staff_required
@require_http_methods(['POST'])
def panel_billing_update(request, pk):
    try:
        data = json.loads(request.body)
        link = CoachStudent.objects.get(pk=pk)
        source_val = data.get('source', '')
        link.source = source_val if source_val in ('vagus', 'coach') else None
        due_str = data.get('next_payment_due', '').strip()
        if due_str:
            from datetime import datetime as _dt
            link.next_payment_due = _dt.strptime(due_str, '%Y-%m-%d').date()
        else:
            link.next_payment_due = None
        link.save(update_fields=['source', 'next_payment_due'])
        return JsonResponse({'ok': True})
    except CoachStudent.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'not found'}, status=404)
    except (ValueError, json.JSONDecodeError) as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


@staff_required
def panel_odemeler_view(request):
    coaches = User.objects.filter(role='coach', is_active=True).order_by('full_name')
    rows = []
    for coach in coaches:
        s = coach_billing_summary(coach)
        rows.append({
            'coach': coach,
            'vagus_count': s['vagus_count'],
            'coach_count': s['coach_count'],
            'vagus_fee': s['vagus_fee'],
            'coach_fee': s['coach_fee'],
            'total_fee': s['total_fee'],
            'vagus_fee_undefined': s['vagus_fee_undefined'],
            'coach_fee_undefined': s['coach_fee_undefined'],
            'unclassified_count': s['unclassified_count'],
        })
    rows.sort(key=lambda r: (r['total_fee'] is None, -(r['total_fee'] or 0)))
    grand_total = sum((r['total_fee'] for r in rows if r['total_fee'] is not None), Decimal('0'))
    return render(request, 'panel/odemeler.html', {
        'rows': rows,
        'grand_total': grand_total,
        'active_tab': 'payments',
    })


@staff_required
def panel_davetler_view(request):
    coaches = User.objects.filter(role='coach', is_active=True).order_by('full_name')
    error = None
    success = None

    if request.method == 'POST':
        email     = request.POST.get('email', '').strip().lower()
        full_name = request.POST.get('full_name', '').strip()
        coach_id  = request.POST.get('coach_id', '').strip()
        start_date_str = request.POST.get('start_date', '').strip()

        if not email:
            error = 'E-posta adresi zorunludur.'
        elif User.objects.filter(email=email).exists():
            error = 'Bu e-posta zaten kayıtlı bir kullanıcıya ait.'
        elif StudentInvite.objects.filter(email=email, is_used=False).exists():
            error = 'Bu e-postaya zaten bekleyen bir davet gönderilmiş.'
        elif not coach_id:
            error = 'Koç seçimi zorunludur.'
        else:
            try:
                coach = User.objects.get(pk=coach_id, role='coach', is_active=True)
            except User.DoesNotExist:
                error = 'Geçersiz koç seçimi.'
            else:
                from datetime import datetime as _dt
                start_date = None
                if start_date_str:
                    try:
                        start_date = _dt.strptime(start_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        error = 'Geçersiz başlama tarihi.'

                if not error:
                    invite = StudentInvite.objects.create(
                        coach=coach,
                        email=email,
                        full_name=full_name,
                        token=StudentInvite.generate_token(),
                        initiated_by_staff=True,
                        start_date=start_date,
                    )
                    _send_invite_email(invite, request)
                    success = f'{email} adresine davet gönderildi.'

    pending = (
        StudentInvite.objects
        .filter(initiated_by_staff=True, is_used=False)
        .select_related('coach')
        .order_by('-created_at')
    )
    return render(request, 'panel/davetler.html', {
        'coaches': coaches,
        'pending': pending,
        'error': error,
        'success': success,
        'active_tab': 'invites',
    })


@staff_required
def panel_ogrenciler_view(request):
    from django.db.models import Prefetch
    coaches = (
        User.objects.filter(role='coach', is_active=True)
        .prefetch_related(
            Prefetch(
                'coach_student_links',
                queryset=CoachStudent.objects.filter(active=True)
                    .select_related('student')
                    .order_by('student__full_name'),
                to_attr='active_links',
            )
        )
        .order_by('full_name')
    )
    return render(request, 'panel/ogrenciler.html', {
        'coaches': coaches,
        'active_tab': 'students',
    })


@staff_required
@require_http_methods(['POST'])
def panel_student_unlink(request, coach_id, student_id):
    coach   = get_object_or_404(User, pk=coach_id, role='coach')
    student = get_object_or_404(User, pk=student_id, role='student')
    CoachStudent.objects.filter(coach=coach, student=student).update(active=False)
    if student.coach_id == coach.id:
        student.coach = None
        student.save(update_fields=['coach'])
    return JsonResponse({'ok': True})


# ── Staff panel — fee tier CRUD ───────────────────────────────────────────────

def _apply_tier_fields(tier, data):
    """Set fields on a FeeTier from parsed JSON dict. Returns error string or None."""
    try:
        tier.min_students = int(data['min_students'])
        max_s = data.get('max_students', '')
        tier.max_students = int(max_s) if str(max_s).strip() else None
        tier.monthly_fee_try = data['monthly_fee_try']
        tier.order = int(data['order'])
    except (KeyError, ValueError, TypeError) as e:
        return f'Geçersiz alan: {e}'
    return None


@staff_required
@require_http_methods(['POST'])
def panel_fee_tier_add(request):
    try:
        data = json.loads(request.body)
        source = data.get('source', '')
        if source not in ('vagus', 'coach'):
            return JsonResponse({'ok': False, 'error': 'Geçersiz kaynak'}, status=400)
        tier = FeeTier(source=source)
        err = _apply_tier_fields(tier, data)
        if err:
            return JsonResponse({'ok': False, 'error': err}, status=400)
        from django.core.exceptions import ValidationError
        try:
            tier.full_clean()
        except ValidationError as e:
            return JsonResponse({'ok': False, 'error': ' '.join(e.messages)}, status=400)
        tier.save()
        return JsonResponse({'ok': True, 'id': tier.pk})
    except json.JSONDecodeError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


@staff_required
@require_http_methods(['POST'])
def panel_fee_tier_update(request, pk):
    try:
        data = json.loads(request.body)
        tier = FeeTier.objects.get(pk=pk)
        err = _apply_tier_fields(tier, data)
        if err:
            return JsonResponse({'ok': False, 'error': err}, status=400)
        from django.core.exceptions import ValidationError
        try:
            tier.full_clean()
        except ValidationError as e:
            return JsonResponse({'ok': False, 'error': ' '.join(e.messages)}, status=400)
        tier.save()
        return JsonResponse({'ok': True})
    except FeeTier.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'not found'}, status=404)
    except json.JSONDecodeError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


@staff_required
@require_http_methods(['POST'])
def panel_fee_tier_delete(request, pk):
    try:
        FeeTier.objects.filter(pk=pk).delete()
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)
