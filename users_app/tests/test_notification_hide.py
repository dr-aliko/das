import pytest
from django.urls import reverse
from model_bakery import baker

from users_app.models import Notification
from users_app.tasks import _notified_today


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def student(db):
    return baker.make('users_app.User', role='student', is_active=True)


@pytest.fixture
def other_student(db):
    return baker.make('users_app.User', role='student', is_active=True)


@pytest.fixture
def coach(db):
    return baker.make('users_app.User', role='coach', is_active=True)


def _notif(user, *, title='Test', is_read=False, hidden=False):
    return Notification.objects.create(
        user=user, title=title, body='body', url='', is_read=is_read, hidden_by_user=hidden,
    )


# ── Security: ownership ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_user_cannot_hide_another_users_notification(client, student, other_student):
    notif = _notif(other_student)
    client.force_login(student)
    url = reverse('notification_delete', kwargs={'pk': notif.pk})
    r = client.post(url)
    assert r.status_code == 404
    notif.refresh_from_db()
    assert notif.hidden_by_user is False


@pytest.mark.django_db
def test_user_can_hide_own_notification(client, student):
    notif = _notif(student)
    client.force_login(student)
    url = reverse('notification_delete', kwargs={'pk': notif.pk})
    r = client.post(url)
    assert r.status_code == 200
    notif.refresh_from_db()
    assert notif.hidden_by_user is True


# ── Hidden rows excluded from list and unread count ───────────────────────────

@pytest.mark.django_db
def test_hidden_notification_excluded_from_api_list(client, student):
    _notif(student, title='Visible')
    _notif(student, title='Hidden', hidden=True)
    client.force_login(student)
    r = client.get(reverse('student_notifications'))
    data = r.json()
    titles = [n['title'] for n in data['notifications']]
    assert 'Visible' in titles
    assert 'Hidden' not in titles


@pytest.mark.django_db
def test_hidden_unread_not_counted_in_badge(client, student):
    _notif(student, is_read=False)              # visible unread
    _notif(student, is_read=False, hidden=True)  # hidden unread — must not count
    client.force_login(student)
    r = client.get(reverse('student_notifications'))
    assert r.json()['unread_count'] == 1


# ── delete-all only affects caller ───────────────────────────────────────────

@pytest.mark.django_db
def test_delete_all_only_hides_callers_rows(client, student, other_student):
    mine = _notif(student)
    theirs = _notif(other_student)
    client.force_login(student)
    r = client.post(reverse('notifications_delete_all'))
    assert r.status_code == 200
    mine.refresh_from_db()
    theirs.refresh_from_db()
    assert mine.hidden_by_user is True
    assert theirs.hidden_by_user is False


# ── Dedup still fires on hidden rows ─────────────────────────────────────────

@pytest.mark.django_db
def test_dedup_sees_hidden_notification(student):
    """_notified_today must return True even if the notification was later hidden."""
    _notif(student, title='Görev Hatırlatıcı 📋', hidden=True)
    assert _notified_today(student, 'Görev Hatırlatıcı 📋') is True


# ── /notifications/ is a login-required redirect, not a 200 page ─────────────

@pytest.mark.django_db
def test_notifications_page_student_redirects(client, student):
    client.force_login(student)
    r = client.get(reverse('notifications_page'))
    assert r.status_code == 302


@pytest.mark.django_db
def test_notifications_page_coach_redirects(client, coach):
    client.force_login(coach)
    r = client.get(reverse('notifications_page'))
    assert r.status_code == 302


# ── Coach with real Notification rows can delete them ────────────────────────

@pytest.mark.django_db
def test_coach_can_delete_own_notification(client, coach):
    notif = _notif(coach)
    client.force_login(coach)
    r = client.post(reverse('notification_delete', kwargs={'pk': notif.pk}))
    assert r.status_code == 200
    notif.refresh_from_db()
    assert notif.hidden_by_user is True


@pytest.mark.django_db
def test_coach_api_returns_own_notifications(client, coach):
    _notif(coach, title='CoachNotif', is_read=False)
    client.force_login(coach)
    r = client.get(reverse('student_notifications'))
    data = r.json()
    assert data['ok'] is True
    assert any(n['title'] == 'CoachNotif' for n in data['notifications'])
    assert data['unread_count'] == 1


# ── Anonymous access: all views must redirect to login (302), never 500 ───────

_GET_URLS = [
    ('notifications_page', {}, {}),
    ('student_notifications', {}, {}),
]

_POST_URLS = [
    ('notification_delete', {'pk': 0}, {}),
    ('notifications_delete_all', {}, {}),
    ('notifications_mark_all_read', {}, {}),
    ('student_notification_read', {'pk': 0}, {}),
    ('student_notifications_mark_all', {}, {}),
]


@pytest.mark.django_db
@pytest.mark.parametrize('name,kwargs,data', _GET_URLS)
def test_anonymous_get_redirects_to_login(client, name, kwargs, data):
    r = client.get(reverse(name, kwargs=kwargs or None), data)
    assert r.status_code == 302
    assert 'login' in r['Location']


@pytest.mark.django_db
@pytest.mark.parametrize('name,kwargs,data', _POST_URLS)
def test_anonymous_post_redirects_to_login(client, name, kwargs, data):
    r = client.post(reverse(name, kwargs=kwargs or None), data)
    assert r.status_code == 302
    assert 'login' in r['Location']


# ── POST views must reject GET with 405, not 500 ─────────────────────────────

@pytest.mark.django_db
@pytest.mark.parametrize('name,kwargs', [
    ('notification_delete', {'pk': 1}),
    ('notifications_delete_all', {}),
    ('notifications_mark_all_read', {}),
    ('student_notification_read', {'pk': 1}),
    ('student_notifications_mark_all', {}),
])
def test_post_views_reject_get(client, student, name, kwargs):
    client.force_login(student)
    r = client.get(reverse(name, kwargs=kwargs or None))
    assert r.status_code == 405
