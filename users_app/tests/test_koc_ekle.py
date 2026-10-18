"""
Tests for the staff-only "Koç Ekle" (add coach) panel feature.

Covers:
- Coach account creation + exactly one email sent
- Duplicate email refused for any role
- Anonymous and non-staff users rejected (403 / redirect)
- Resend works only for coaches without a password
- A new coach can set a password and log in via the reset link
"""
import pytest
from django.test import Client
from django.urls import reverse
from model_bakery import baker

from users_app.models import User


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def staff_user(db):
    return baker.make('users_app.User', role='coach', is_active=True, is_staff=True)


@pytest.fixture
def staff_client(staff_user):
    c = Client()
    c.force_login(staff_user)
    return c


@pytest.fixture
def anon_client():
    return Client()


@pytest.fixture
def plain_coach(db):
    return baker.make('users_app.User', role='coach', is_active=True, is_staff=False)


@pytest.fixture
def plain_client(plain_coach):
    c = Client()
    c.force_login(plain_coach)
    return c


# ── helpers ───────────────────────────────────────────────────────────────────

def _create_url():
    return reverse('panel_koc_ekle')


def _resend_url(coach_id):
    return reverse('panel_koc_davet_resend', args=[coach_id])


def _post_preview(client, full_name, email):
    return client.post(_create_url(), {'action': 'preview', 'full_name': full_name, 'email': email})


def _post_create(client, full_name, email):
    return client.post(_create_url(), {'action': 'create', 'full_name': full_name, 'email': email})


# ── access control ────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_anonymous_get_redirects(anon_client):
    response = anon_client.get(_create_url())
    assert response.status_code in (302, 301)


@pytest.mark.django_db
def test_non_staff_get_redirects(plain_client):
    response = plain_client.get(_create_url())
    assert response.status_code in (302, 301)


@pytest.mark.django_db
def test_staff_get_returns_200(staff_client):
    response = staff_client.get(_create_url())
    assert response.status_code == 200


@pytest.mark.django_db
def test_anonymous_post_redirects(anon_client):
    response = _post_create(anon_client, 'Test', 'test@example.com')
    assert response.status_code in (302, 301)


@pytest.mark.django_db
def test_non_staff_post_redirects(plain_client):
    response = _post_create(plain_client, 'Test', 'test@example.com')
    assert response.status_code in (302, 301)


# ── coach creation ────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_creates_coach_account(staff_client, mailoutbox):
    response = _post_create(staff_client, 'Ahmet Yılmaz', 'ahmet@example.com')
    assert response.status_code == 302
    coach = User.objects.get(email='ahmet@example.com')
    assert coach.role == 'coach'
    assert coach.is_active is True
    assert coach.is_approved is True
    assert not coach.has_usable_password()
    assert coach.email_verified is False


@pytest.mark.django_db
def test_creates_coach_sends_exactly_one_email(staff_client, mailoutbox):
    _post_create(staff_client, 'Mehmet Kaya', 'mehmet@example.com')
    assert len(mailoutbox) == 1
    mail = mailoutbox[0]
    assert 'mehmet@example.com' in mail.to
    assert 'noreply@vagus.tr' in mail.from_email
    assert 'destek@vagus.tr' in (mail.reply_to or [])
    assert 'Şifrenizi Belirleyin' in mail.subject


@pytest.mark.django_db
def test_email_contains_reset_link(staff_client, mailoutbox):
    _post_create(staff_client, 'Ali Demir', 'ali@example.com')
    assert len(mailoutbox) == 1
    body = mailoutbox[0].body
    assert '/auth/password-reset/confirm/' in body


# ── duplicate email guard ─────────────────────────────────────────────────────

@pytest.mark.django_db
def test_existing_coach_email_refused(staff_client, mailoutbox):
    baker.make('users_app.User', email='coach@example.com', role='coach')
    response = _post_create(staff_client, 'Başka Koç', 'coach@example.com')
    assert response.status_code == 200
    assert User.objects.filter(email='coach@example.com').count() == 1
    assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_existing_student_email_refused(staff_client, mailoutbox):
    baker.make('users_app.User', email='student@example.com', role='student')
    response = _post_create(staff_client, 'Yeni Koç', 'student@example.com')
    assert response.status_code == 200
    assert User.objects.filter(email='student@example.com').count() == 1
    assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_existing_account_not_modified(staff_client):
    original = baker.make('users_app.User', email='existing@example.com', role='student',
                          full_name='Orijinal İsim', is_approved=False)
    _post_create(staff_client, 'Farklı İsim', 'existing@example.com')
    original.refresh_from_db()
    assert original.full_name == 'Orijinal İsim'
    assert original.role == 'student'
    assert original.is_approved is False


# ── resend invite ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_resend_works_for_coach_without_password(staff_client, mailoutbox):
    coach = User.objects.create_user(email='nopass@example.com', full_name='Koç', role='coach', password=None)
    coach.is_active = True
    coach.is_approved = True
    coach.save(update_fields=['is_active', 'is_approved'])

    response = staff_client.post(_resend_url(coach.pk))
    assert response.status_code == 302
    assert len(mailoutbox) == 1
    assert 'nopass@example.com' in mailoutbox[0].to


@pytest.mark.django_db
def test_resend_refused_for_coach_with_password(staff_client, mailoutbox):
    coach = User.objects.create_user(email='haspass@example.com', full_name='Koç', role='coach',
                                     password='strong-password-123')
    coach.is_active = True
    coach.is_approved = True
    coach.save(update_fields=['is_active', 'is_approved'])

    response = staff_client.post(_resend_url(coach.pk))
    assert response.status_code == 302
    assert len(mailoutbox) == 0


# ── password set flow ─────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_new_coach_can_set_password_and_login(staff_client, client, mailoutbox):
    _post_create(staff_client, 'Zeynep Çelik', 'zeynep@example.com')
    assert len(mailoutbox) == 1

    body = mailoutbox[0].body
    import re
    match = re.search(r'/auth/password-reset/confirm/([^/]+)/([^/\s]+)/', body)
    assert match, f'Reset link not found in email body: {body[:300]}'
    uidb64, token = match.group(1), match.group(2)

    confirm_url = reverse('users_app:password_reset_confirm', kwargs={'uidb64': uidb64, 'token': token})
    resp = client.get(confirm_url, follow=True)
    assert resp.status_code == 200

    post_url = resp.redirect_chain[-1][0] if resp.redirect_chain else confirm_url
    resp2 = client.post(post_url, {'new_password1': 'VagusTest123!', 'new_password2': 'VagusTest123!'})
    assert resp2.status_code in (200, 302)

    coach = User.objects.get(email='zeynep@example.com')
    assert coach.has_usable_password()
    assert coach.check_password('VagusTest123!')


# ── coach deletion ────────────────────────────────────────────────────────────

def _make_no_pw_coach(db, email='todel@example.com'):
    coach = User.objects.create_user(email=email, full_name='Silinecek Koç', role='coach', password=None)
    coach.is_active = True
    coach.is_approved = True
    coach.save(update_fields=['is_active', 'is_approved'])
    return coach


def _sil_get(client, coach_id):
    """GET the confirm page for deletion (PRG step 1)."""
    return client.get(reverse('panel_koc_sil', args=[coach_id]))


def _sil_delete(client, coach_id, follow=False):
    """POST to execute deletion (PRG step 2)."""
    return client.post(reverse('panel_koc_sil', args=[coach_id]), follow=follow)


@pytest.mark.django_db
def test_delete_allowed_case(staff_client, db):
    coach = _make_no_pw_coach(db)
    coach_pk = coach.pk

    resp = _sil_get(staff_client, coach_pk)
    assert resp.status_code == 200
    assert 'koc_sil_onayla' in resp.templates[0].name

    resp2 = _sil_delete(staff_client, coach_pk)
    assert resp2.status_code == 302
    assert not User.objects.filter(pk=coach_pk).exists()


@pytest.mark.django_db
def test_delete_refused_coach_has_student(staff_client, db):
    from users_app.models import CoachStudent
    coach = _make_no_pw_coach(db)
    student = baker.make('users_app.User', role='student', is_active=True)
    CoachStudent.objects.create(coach=coach, student=student, active=True)

    resp = _sil_get(staff_client, coach.pk)
    assert resp.status_code == 302
    assert User.objects.filter(pk=coach.pk).exists()


@pytest.mark.django_db
def test_delete_refused_coach_has_password(staff_client, db):
    coach = User.objects.create_user(email='withpw@example.com', full_name='Koç', role='coach',
                                     password='SomePassword1!')
    coach.is_active = True
    coach.is_approved = True
    coach.save(update_fields=['is_active', 'is_approved'])

    resp = _sil_get(staff_client, coach.pk)
    assert resp.status_code == 302
    assert User.objects.filter(pk=coach.pk).exists()


@pytest.mark.django_db
def test_delete_non_staff_rejected(plain_client, db):
    coach = _make_no_pw_coach(db)
    resp = _sil_get(plain_client, coach.pk)
    assert resp.status_code in (302, 301)
    assert User.objects.filter(pk=coach.pk).exists()


@pytest.mark.django_db
def test_delete_wrong_role_redirects_gracefully(staff_client, db):
    """Attempting to delete a non-coach user must redirect, not 404."""
    student = baker.make('users_app.User', role='student', is_active=True)
    resp = _sil_delete(staff_client, student.pk)
    assert resp.status_code == 302
    assert User.objects.filter(pk=student.pk).exists()


# ── follow-redirect tests (assert final page is 200) ─────────────────────────

@pytest.mark.django_db
def test_delete_success_lands_on_list_page(staff_client, db):
    coach = _make_no_pw_coach(db, email='followdel@example.com')
    resp = _sil_delete(staff_client, coach.pk, follow=True)
    assert resp.status_code == 200
    assert resp.redirect_chain[-1][0].endswith('/panel/koc-ekle/')
    assert not User.objects.filter(email='followdel@example.com').exists()


@pytest.mark.django_db
def test_delete_refused_lands_on_list_page(staff_client, db):
    from users_app.models import CoachStudent
    coach = _make_no_pw_coach(db, email='followref@example.com')
    student = baker.make('users_app.User', role='student', is_active=True)
    CoachStudent.objects.create(coach=coach, student=student, active=True)

    resp = _sil_get(staff_client, coach.pk)
    assert resp.status_code == 302
    final = staff_client.get(resp['Location'])
    assert final.status_code == 200
    assert User.objects.filter(email='followref@example.com').exists()


@pytest.mark.django_db
def test_delete_already_deleted_id_harmless(staff_client, db):
    """A second request for a coach that was already deleted must not 404."""
    coach = _make_no_pw_coach(db, email='gone@example.com')
    coach_pk = coach.pk
    coach.delete()

    resp = _sil_get(staff_client, coach_pk)
    assert resp.status_code == 302

    final = staff_client.get(resp['Location'], follow=True)
    assert final.status_code == 200
