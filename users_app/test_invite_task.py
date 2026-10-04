from django.core import mail
from django.test import TestCase, override_settings
from model_bakery import baker

from users_app.tasks import send_invite_email_task


class SendInviteEmailTaskTests(TestCase):

    def test_missing_invite_returns_cleanly(self):
        with self.assertLogs('users_app.tasks', level='WARNING') as log:
            send_invite_email_task(999999)
        self.assertTrue(any('999999' in m for m in log.output))

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_existing_invite_sends_email(self):
        coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
        invite = baker.make(
            'users_app.StudentInvite',
            coach=coach,
            email='invite@example.com',
            token='testtoken_abc123',
        )
        send_invite_email_task(invite.id)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(invite.email, mail.outbox[0].to)
