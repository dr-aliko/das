import logging

_log = logging.getLogger(__name__)


def _reset_timeout_display():
    from django.conf import settings
    secs = getattr(settings, 'PASSWORD_RESET_TIMEOUT', 3600)
    if secs >= 3600 and secs % 3600 == 0:
        return f'{secs // 3600} saat'
    return f'{secs // 60} dakika'


def send_purchase_verify_email(email, code, full_name):
    """Async task: send email verification code to purchase buyer."""
    from django.conf import settings
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string

    ctx = {
        'full_name':      full_name,
        'code':           code,
        'expiry_minutes': 10,
    }
    try:
        text_body = render_to_string('emails/purchase_verify_email.txt', ctx)
        html_body = render_to_string('emails/purchase_verify_email.html', ctx)
        msg = EmailMultiAlternatives(
            subject='Vagus doğrulama kodun',
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
            reply_to=['destek@vagus.tr'],
        )
        msg.attach_alternative(html_body, 'text/html')
        msg.send()
    except Exception:
        _log.exception('send_purchase_verify_email: failed for %s', email)


def send_purchase_emails(order_id):
    """Async task: send student set-password/welcome email, order confirm email, coach notify + push."""
    from django.conf import settings
    from django.contrib.auth.tokens import default_token_generator
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    from purchase_app.models import Order
    from users_app.services.notifications import send_push_notification

    try:
        order = Order.objects.select_related('student', 'coach', 'plan').get(pk=order_id)
    except Order.DoesNotExist:
        _log.warning('send_purchase_emails: order %s not found', order_id)
        return

    student = order.student
    if student is None:
        _log.warning('send_purchase_emails: order %s has no student', order_id)
        return

    # ── Student: welcome email only for new accounts (no usable password) ────
    if not student.has_usable_password():
        try:
            uid   = urlsafe_base64_encode(force_bytes(student.pk))
            token = default_token_generator.make_token(student)
            reset_path = f'/auth/password-reset/confirm/{uid}/{token}/'
            reset_link = f'{settings.APP_BASE_URL}{reset_path}'

            ctx = {
                'user':                  student,
                'reset_link':            reset_link,
                'reset_timeout_display': _reset_timeout_display(),
                'coach':                 order.coach,
                'plan':                  order.plan,
            }
            text_body = render_to_string('emails/purchase_student_welcome.txt', ctx)
            html_body = render_to_string('emails/purchase_student_welcome.html', ctx)
            msg = EmailMultiAlternatives(
                subject='Vagus — Hesabınız Hazır',
                body=text_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[student.email],
            )
            msg.attach_alternative(html_body, 'text/html')
            msg.send()
        except Exception:
            _log.exception('send_purchase_emails: student welcome email failed for order %s', order_id)

    # ── Order confirmation email (always sent) ────────────────────────────────
    try:
        from datetime import date, timedelta
        from users_app.models import CoachStudent

        cs = CoachStudent.objects.filter(coach=order.coach, student=student).first()
        if cs and cs.next_payment_due:
            valid_until = cs.next_payment_due
        else:
            valid_until = date.today() + timedelta(days=order.plan.duration_days)

        ctx = {
            'order':       order,
            'valid_until': valid_until,
        }
        text_body = render_to_string('emails/purchase_order_confirm.txt', ctx)
        html_body = render_to_string('emails/purchase_order_confirm.html', ctx)
        msg = EmailMultiAlternatives(
            subject='Vagus — Sipariş Onayı',
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[student.email],
            reply_to=['destek@vagus.tr'],
        )
        msg.attach_alternative(html_body, 'text/html')
        msg.send()
    except Exception:
        _log.exception('send_purchase_emails: order confirm email failed for order %s', order_id)

    # ── Coach: notification email ─────────────────────────────────────────────
    try:
        coach = order.coach
        student_url = f'{settings.APP_BASE_URL}/coach/student/{student.pk}/'
        ctx = {
            'coach':       coach,
            'student':     student,
            'order':       order,
            'student_url': student_url,
        }
        text_body = render_to_string('emails/purchase_coach_notify.txt', ctx)
        html_body = render_to_string('emails/purchase_coach_notify.html', ctx)
        msg = EmailMultiAlternatives(
            subject=f'Yeni öğrenci satın aldı — {student.full_name}',
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[coach.email],
            reply_to=['destek@vagus.tr'],
        )
        msg.attach_alternative(html_body, 'text/html')
        msg.send()
    except Exception:
        _log.exception('send_purchase_emails: coach email failed for order %s', order_id)

    # ── Coach: in-app Notification ────────────────────────────────────────────
    try:
        coach = order.coach
        send_push_notification(
            coach,
            title='Yeni öğrenci katıldı 🎉',
            body=f'{student.full_name} satın alma yaptı ve hesabı aktifleştirildi.',
            url=f'/coach/student/{student.pk}/',
        )
    except Exception:
        _log.exception('send_purchase_emails: coach notification failed for order %s', order_id)


def send_bank_transfer_pending_email(order_id):
    """Async task: send buyer the bank-transfer 'ödeme bekleniyor' email."""
    from django.conf import settings
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string

    from purchase_app.models import Order

    try:
        order = Order.objects.select_related('plan').get(pk=order_id)
    except Order.DoesNotExist:
        _log.warning('send_bank_transfer_pending_email: order %s not found', order_id)
        return

    ctx = {
        'order':     order,
        'iban':      getattr(settings, 'PURCHASE_IBAN', ''),
        'holder':    getattr(settings, 'PURCHASE_IBAN_HOLDER', ''),
        'bank_name': getattr(settings, 'PURCHASE_BANK_NAME', ''),
    }
    try:
        text_body = render_to_string('emails/purchase_bank_transfer_pending.txt', ctx)
        html_body = render_to_string('emails/purchase_bank_transfer_pending.html', ctx)
        msg = EmailMultiAlternatives(
            subject='Vagus — Havale/EFT Bilgileri',
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[order.email],
            reply_to=['destek@vagus.tr'],
        )
        msg.attach_alternative(html_body, 'text/html')
        msg.send()
    except Exception:
        _log.exception('send_bank_transfer_pending_email: failed for order %s', order_id)


def notify_staff_new_transfer(order_id):
    """Async task: notify staff of a new bank-transfer order (PURCHASE_STAFF_NOTIFICATION_EMAIL)."""
    from django.conf import settings
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string

    from purchase_app.models import Order

    staff_email = getattr(settings, 'PURCHASE_STAFF_NOTIFICATION_EMAIL', '').strip()
    if not staff_email:
        return

    try:
        order = Order.objects.select_related('coach', 'plan').get(pk=order_id)
    except Order.DoesNotExist:
        _log.warning('notify_staff_new_transfer: order %s not found', order_id)
        return

    panel_url = f'{settings.APP_BASE_URL}/panel/satin-al/siparisler/{order.pk}/'
    ctx = {'order': order, 'panel_url': panel_url}
    try:
        text_body = render_to_string('emails/purchase_staff_new_transfer.txt', ctx)
        html_body = render_to_string('emails/purchase_staff_new_transfer.html', ctx)
        msg = EmailMultiAlternatives(
            subject=f'[Vagus] Yeni havale siparişi #{order.pk}',
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[staff_email],
        )
        msg.attach_alternative(html_body, 'text/html')
        msg.send()
    except Exception:
        _log.exception('notify_staff_new_transfer: failed for order %s', order_id)


def notify_staff_needs_review(order_id):
    """Async task: email staff when an order needs manual review."""
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.mail import EmailMessage

    from purchase_app.models import Order

    try:
        order = Order.objects.select_related('coach', 'plan').get(pk=order_id)
    except Order.DoesNotExist:
        return

    User = get_user_model()
    staff_emails = list(User.objects.filter(is_staff=True, is_active=True).values_list('email', flat=True))
    if not staff_emails:
        _log.warning('notify_staff_needs_review: no staff users found')
        return

    subject = f'[Vagus] Sipariş #{order.pk} inceleme gerekiyor'
    message = (
        f'Sipariş #{order.pk}\n'
        f'E-posta: {order.email}\n'
        f'Koç: {order.coach}\n'
        f'Plan: {order.plan}\n'
        f'Neden: {order.notes}\n\n'
        f'Panel: {settings.APP_BASE_URL}/panel/satin-al/siparisler/{order.pk}/'
    )
    try:
        msg = EmailMessage(subject, message, settings.DEFAULT_FROM_EMAIL, staff_emails)
        msg.send()
    except Exception:
        _log.exception('notify_staff_needs_review: email failed for order %s', order_id)


def cancel_stale_orders_task():
    """Wrapper called by django-q schedule."""
    from purchase_app.services import cancel_stale_orders
    return cancel_stale_orders()
