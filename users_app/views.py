import json
from datetime import date, timedelta

from django.contrib import messages
from django.db import models
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from django.core.mail import EmailMultiAlternatives
from ratelimit.decorators import ratelimit

from .forms import CoachRegistrationForm, EmailAuthenticationForm, InviteAcceptForm, InviteStudentForm, UserRegistrationForm
from .models import CoachAlert, StudentAchievement, StudentInvite, User


class CustomLoginView(LoginView):
    form_class = EmailAuthenticationForm
    template_name = 'auth/login.html'

    def get_success_url(self):
        user = self.request.user
        if user.is_coach:
            return '/coach/'
        return '/student/'


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
    from django.urls import reverse
    from django.template.loader import render_to_string

    path = reverse('users_app:invite_register', args=[invite.token])
    invite_link = f'https://vagus.tr{path}'

    plain_text = (
        f'Vagus Platformuna Hoş Geldiniz!\n\n'
        f'Deneme analizlerinizi detaylı bir şekilde gerçekleştirmek, eksik konularınızı nokta atışı '
        f'tespit ederek netlerinizi artırmak için tasarlanan Vagus dünyasına davetlisiniz.\n\n'
        f'Hesabınızı aktifleştirmek ve sisteme giriş yapmak için lütfen aşağıdaki bağlantıya tıklayın:\n'
        f'{invite_link}\n\n'
        f'Önemli Not: Güvenliğiniz amacıyla bu aktivasyon bağlantısı tek kullanımlıktır.\n\n'
        f'Başarılar dileriz,\n'
        f'Vagus Ekibi'
    )
    html_body = render_to_string('emails/invite.html', {'invite_link': invite_link})

    email = EmailMultiAlternatives(
        subject='Vagus\'a Davetlisiniz - Hesap Aktivasyonu',
        body=plain_text,
        from_email=None,          # uses DEFAULT_FROM_EMAIL from settings
        to=[invite.email],
    )
    email.attach_alternative(html_body, 'text/html')
    email.send()


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

            invite.is_used = True
            invite.save(update_fields=['is_used'])

            login(request, user)
            messages.success(request, f'Hoş geldin, {user.full_name}!')
            return redirect('/student/')
    else:
        form = InviteAcceptForm(initial={'full_name': invite.full_name})

    return render(request, 'auth/invite_register.html', {'form': form, 'invite': invite})


def logout_view(request):
    logout(request)
    return redirect('/auth/login/')


def home_redirect(request):
    if not request.user.is_authenticated:
        return redirect('/auth/login/')
    if request.user.is_coach:
        return redirect('/coach/')
    return redirect('/student/')


# ── V2 shell stubs ────────────────────────────────────────────────────────────

@login_required
def yakinda_analiz(request):
    return render(request, 'student/stub_yakinda.html',
                  {'title': 'Analiz', 'back': '/student/'})


@login_required
def yakinda_profil(request):
    return render(request, 'student/stub_yakinda.html',
                  {'title': 'Profil', 'back': '/student/'})


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

    return render(request, 'profile/profile_v2.html', {
        'stats':         stats,
        'activity_week': activity_week,
        'all_badges':    all_badges,
        'v2_shell':      True,
    })


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
