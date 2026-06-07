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
