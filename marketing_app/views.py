from django.conf import settings
from django.core.mail import send_mail
from django.shortcuts import redirect, render, get_object_or_404

from .forms import CoachRequestForm
from .models import CoachProfile, CoachRequest, FAQItem, FeatureItem, PricingPlan, SiteSettings, Testimonial


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
            obj = form.save(commit=False)
            obj.coach_profile = coach
            obj.save()
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
    subject = f'Yeni Koç Talebi: {obj.full_name}'
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
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=True)


def about(request):
    return render(request, 'marketing/about.html', {'active_nav': 'about'})


def contact(request):
    return render(request, 'marketing/contact.html', {'active_nav': 'contact'})
