from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse


def send_invite_email_task(invite_id):
    from users_app.models import StudentInvite
    invite = StudentInvite.objects.get(id=invite_id)

    path = reverse('users_app:invite_register', args=[invite.token])
    invite_link = f'{settings.APP_BASE_URL}{path}'

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
        subject="Vagus'a Davetlisiniz - Hesap Aktivasyonu",
        body=plain_text,
        from_email=None,
        to=[invite.email],
    )
    email.attach_alternative(html_body, 'text/html')
    email.send()


MOTIVATIONAL_MESSAGES = [
    ("Bugün bir adım daha at! 💪", "Küçük adımlar büyük başarılar getirir, hadi başlayalım."),
    ("Az kaldı! 🚀", "Bugünkü görevlerine göz atmayı unutma."),
    ("Sen yapabilirsin! ✨", "Düzenli çalışma, kalıcı başarı demektir."),
    ("Hazır mısın? 📚", "Bugün de biraz zaman ayırıp ilerleme kaydedelim."),
    ("Devam et! 🔥", "Her gün biraz daha güçleniyorsun."),
    ("Tutarlılık kazandırır.", "Bugün de programına bir göz at."),
    ("Hedefine bir adım daha yaklaş.", "Bugünkü görevlerini tamamlamaya ne dersin?"),
    ("Çalışmaya devam! 📖", "Bugün küçük bir ilerleme bile fark yaratır."),
    ("Zihnini bugün de besle.", "Programındaki görevlere bir göz at."),
    ("Başarı, küçük alışkanlıklardan doğar.", "Bugünü de değerlendirelim mi?"),
    ("Bugün kendine zaman ayır.", "Az bir çalışma bile fark yaratır."),
    ("Disiplin, motivasyondan daha güçlüdür.", "Bugünkü görevlerine bakmaya ne dersin?"),
    ("Potansiyelini göster! 🌟", "Bugün de bir adım at."),
    ("Sınava bir gün daha yaklaştın.", "Bugünkü çalışmanı ihmal etme."),
]


def generate_all_coach_alerts():
    from django.contrib.auth import get_user_model
    from users_app.services.alert_engine import generate_alerts_for_coach

    User = get_user_model()
    coaches = User.objects.filter(role='coach', is_active=True)
    total_created = total_updated = 0
    for coach in coaches:
        created, updated = generate_alerts_for_coach(coach)
        total_created += created
        total_updated += updated
    return total_created, total_updated


def send_task_deadline_reminders():
    """Scheduled daily at 09:00 Istanbul (cron='0 9 * * *' in local time)."""
    from django.contrib.auth import get_user_model
    from django.utils.timezone import localdate
    from tasks_app.models import GorevGrubu
    from users_app.services.notifications import send_push_notification

    User = get_user_model()
    today = localdate()

    students = User.objects.filter(
        role='student',
        is_active=True,
        push_subscriptions__is_active=True,
    ).distinct()

    total_sent = 0
    for student in students:
        pending_count = GorevGrubu.objects.filter(
            student=student,
            tarih=today,
            is_completed=False,
            is_hidden_by_student=False,
        ).count()

        if pending_count == 0:
            continue

        sent, _ = send_push_notification(
            student,
            title='Görev Hatırlatıcı 📋',
            body=f'Bugün {pending_count} görevin var, unutma!',
            url='/student/tasks/',
        )
        total_sent += sent

    return total_sent


def send_konu_review_reminders():
    """Scheduled daily at 08:00 Istanbul (cron='0 8 * * *' in local time)."""
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from konu_takip_app.models import StudentSubjectSrSetting, StudentTopicProgress
    from users_app.services.notifications import send_push_notification

    User = get_user_model()
    now = timezone.now()

    students = User.objects.filter(
        role='student',
        is_active=True,
        push_subscriptions__is_active=True,
    ).distinct()

    total_sent = 0
    for student in students:
        # SR is opt-in: only count reviews for subjects explicitly enabled for this student
        enabled_subjects = set(
            StudentSubjectSrSetting.objects
            .filter(student=student, sr_enabled=True)
            .values_list('subject_id', flat=True)
        )
        if not enabled_subjects:
            continue
        due_count = (
            StudentTopicProgress.objects
            .filter(student=student, finished=True, next_review_at__lte=now,
                    topic__subject_id__in=enabled_subjects)
            .count()
        )

        if due_count == 0:
            continue

        body = f'{due_count} konunun tekrar zamanı geldi! Konu Takip\'te hazır bekliyorlar.'
        sent, _ = send_push_notification(
            student,
            title='Konu Tekrar Zamanı 📚',
            body=body,
            url='/student/konu-takip/',
        )
        total_sent += sent

    return total_sent


def send_motivational_notifications():
    """Scheduled daily at 19:00 Istanbul (cron='0 19 * * *' in local time)."""
    import random
    from django.contrib.auth import get_user_model
    from django.utils.timezone import localdate
    from tasks_app.models import GorevGrubu
    from users_app.services.notifications import send_push_notification

    User = get_user_model()
    today = localdate()

    students = User.objects.filter(
        role='student',
        is_active=True,
        push_subscriptions__is_active=True,
    ).distinct()

    total_sent = 0
    for student in students:
        today_tasks = GorevGrubu.objects.filter(
            student=student,
            tarih=today,
            is_hidden_by_student=False,
        )
        if today_tasks.exists() and not today_tasks.filter(is_completed=False).exists():
            # All of today's tasks are done — skip the "get to work" nudge
            continue

        title, body = random.choice(MOTIVATIONAL_MESSAGES)
        sent, _ = send_push_notification(student, title=title, body=body)
        total_sent += sent

    return total_sent
