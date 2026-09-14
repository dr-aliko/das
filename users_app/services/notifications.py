import json

from django.conf import settings


def send_push_notification(user, title, body, url=None):
    """Send a push notification to all active subscriptions for a user.

    Returns (sent_count, failed_count). Automatically deactivates
    subscriptions that return 404/410 (expired or unregistered).
    Always creates an in-app Notification row regardless of push delivery outcome.
    """
    from users_app.models import PushSubscription, Notification
    from pywebpush import webpush, WebPushException

    Notification.objects.create(user=user, title=title, body=body, url=url or '')

    if not settings.VAPID_PRIVATE_KEY:
        return 0, 0

    subs = PushSubscription.objects.filter(user=user, is_active=True)
    if not subs.exists():
        return 0, 0

    payload_dict = {'title': title, 'body': body}
    if url:
        payload_dict['url'] = url
    payload = json.dumps(payload_dict)

    sent, failed = 0, 0
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={'sub': f'mailto:{settings.VAPID_ADMIN_EMAIL}'},
            )
            sent += 1
        except WebPushException as exc:
            if exc.response is not None and exc.response.status_code in (404, 410):
                sub.is_active = False
                sub.save(update_fields=['is_active'])
            failed += 1

    return sent, failed
