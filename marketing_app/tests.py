from unittest import mock

import pytest
from django.core import mail
from django.test import Client, override_settings
from model_bakery import baker

from marketing_app.models import CoachProfile, CoachRequest

FORM = {
    'full_name': 'Elif Yilmaz',
    'email': 'elif@example.com',
    'phone': '+90 555 000 00 00',
    'grade_level': '12',
    'track': 'sayisal',
}


@pytest.fixture
def public_coach(db):
    user = baker.make(
        'users_app.User', role='coach', is_active=True, is_approved=True,
        full_name='Test Koc', email='koc@example.com',
    )
    return CoachProfile.objects.create(user=user, slug='test-koc', is_public=True)


def _post(coach, **overrides):
    from django.utils.timezone import now
    data = {**FORM, 'target_exam_year': str(now().year), **overrides}
    return Client().post(f'/koclar/{coach.slug}/basvur/', data)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
def test_newline_in_name_does_not_break_request_email(public_coach):
    response = _post(public_coach, full_name='Elif\nBcc: victim@example.com')
    assert response.status_code == 200
    assert CoachRequest.objects.count() == 1
    assert len(mail.outbox) == 1
    assert '\n' not in mail.outbox[0].subject
    assert mail.outbox[0].to == ['koc@example.com']


def test_email_failure_is_logged_and_request_still_saved(public_coach, caplog):
    with mock.patch('marketing_app.views.send_mail', side_effect=OSError('smtp down')):
        response = _post(public_coach)
    assert response.status_code == 200
    assert response.context['submitted'] is True
    assert CoachRequest.objects.count() == 1
    assert 'coach request email failed' in caplog.text
