import hashlib
import logging

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.shortcuts import redirect, render, get_object_or_404

from .forms import CoachRequestForm
from users_app.utils import client_ip

from .models import CoachProfile, CoachRequest, FAQItem, FeatureItem, PricingPlan, SiteSettings, Testimonial

logger = logging.getLogger(__name__)

_REQUEST_IP_MAX = 10
_REQUEST_IP_WINDOW = 60 * 60
_REQUEST_EMAIL_MAX = 3
_REQUEST_EMAIL_WINDOW = 60 * 60 * 24
_REQUEST_LIMIT_MSG = 'Çok fazla başvuru gönderildi. Lütfen daha sonra tekrar deneyin.'


def _request_limit_keys(email, ip):
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()
    email_hash = hashlib.sha256(email.strip().lower().encode()).hexdigest()
    return f'coachreq_ip_{ip_hash}', f'coachreq_email_{email_hash}'


def _coach_request_limited(email, ip):
    try:
        key_ip, key_email = _request_limit_keys(email, ip)
        return (
            (cache.get(key_ip) or 0) >= _REQUEST_IP_MAX
            or (cache.get(key_email) or 0) >= _REQUEST_EMAIL_MAX
        )
    except Exception:
        logger.warning('coach request rate-limit check failed; allowing the request', exc_info=True)
        return False


def _count_coach_request(email, ip):
    try:
        key_ip, key_email = _request_limit_keys(email, ip)
        cache.set(key_ip, (cache.get(key_ip) or 0) + 1, _REQUEST_IP_WINDOW)
        cache.set(key_email, (cache.get(key_email) or 0) + 1, _REQUEST_EMAIL_WINDOW)
    except Exception:
        logger.warning('coach request rate-limit bookkeeping failed', exc_info=True)


def home(request):
    if request.user.is_authenticated:
        if request.user.is_coach:
            return redirect('/coach/')
        return redirect('/student/')
    ctx = {
        'active_nav': 'home',
        'feature_items': FeatureItem.objects.filter(is_published=True, show_on_home=True),
        'testimonials': Testimonial.objects.filter(is_published=True),
        'coaches': CoachProfile.objects.filter(is_public=True).select_related('user'),
    }
    return render(request, 'marketing/home.html', ctx)


def features(request):
    ctx = {
        'active_nav': 'features',
        'feature_items': FeatureItem.objects.filter(is_published=True),
    }
    return render(request, 'marketing/features.html', ctx)


def pricing(request):
    plans = PricingPlan.objects.filter(is_published=True).prefetch_related('features')
    student_faqs = FAQItem.objects.filter(is_published=True, category='student')
    parent_faqs = FAQItem.objects.filter(is_published=True, category='parent')
    ctx = {
        'active_nav': 'pricing',
        'plans': plans,
        'student_faqs': student_faqs,
        'parent_faqs': parent_faqs,
    }
    return render(request, 'marketing/pricing.html', ctx)


def coach_list(request):
    coaches = CoachProfile.objects.filter(is_public=True).select_related('user')
    ctx = {
        'active_nav': 'coaches',
        'coaches': coaches,
    }
    return render(request, 'marketing/coach_list.html', ctx)


def coach_detail(request, slug):
    coach = get_object_or_404(CoachProfile, slug=slug, is_public=True)
    ctx = {
        'active_nav': 'coaches',
        'coach': coach,
    }
    return render(request, 'marketing/coach_detail.html', ctx)


def coach_request(request, slug):
    coach = get_object_or_404(CoachProfile, slug=slug, is_public=True)
    if request.method == 'POST':
        form = CoachRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            ip = client_ip(request)
            if _coach_request_limited(email, ip):
                form.add_error(None, _REQUEST_LIMIT_MSG)
                return render(request, 'marketing/coach_request.html', {
                    'active_nav': 'coaches',
                    'coach': coach,
                    'form': form,
                    'submitted': False,
                }, status=429)
            obj = form.save(commit=False)
            obj.coach_profile = coach
            obj.save()
            _count_coach_request(email, ip)
            _send_coach_request_email(obj, coach)
            return render(request, 'marketing/coach_request.html', {
                'active_nav': 'coaches',
                'coach': coach,
                'submitted': True,
            })
    else:
        form = CoachRequestForm()
    return render(request, 'marketing/coach_request.html', {
        'active_nav': 'coaches',
        'coach': coach,
        'form': form,
        'submitted': False,
    })


def _send_coach_request_email(obj, coach):
    recipient = coach.user.email or settings.DEFAULT_FROM_EMAIL
    subject = f'Yeni Koç Talebi: {" ".join(obj.full_name.split())}'
    body = (
        f'Merhaba {coach.get_display_name()},\n\n'
        f'Yeni bir görüşme talebi aldınız.\n\n'
        f'Öğrenci Bilgileri\n'
        f'─────────────────\n'
        f'Ad Soyad        : {obj.full_name}\n'
        f'E-posta         : {obj.email}\n'
        f'Telefon         : {obj.phone}\n'
        f'Sınıf           : {obj.get_grade_level_display()}\n'
        f'Hedef Sınav Yılı: {obj.target_exam_year}\n'
        f'Alan            : {obj.get_track_display()}\n\n'
        f'Not\n'
        f'───\n'
        f'{obj.note or "—"}\n\n'
        f'Veli Bilgileri\n'
        f'──────────────\n'
        f'Veli Adı    : {obj.parent_name or "—"}\n'
        f'Veli Telefon: {obj.parent_phone or "—"}\n\n'
        f'Talep Tarihi: {obj.created_at.strftime("%d.%m.%Y %H:%M")}\n\n'
        f'Talebi Vagus admin panelinden de görüntüleyebilirsiniz.'
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient])
    except Exception:
        logger.exception('coach request email failed (request_id=%s)', obj.pk)


def about(request):
    return render(request, 'marketing/about.html', {'active_nav': 'about'})


def contact(request):
    return render(request, 'marketing/contact.html', {'active_nav': 'contact'})
