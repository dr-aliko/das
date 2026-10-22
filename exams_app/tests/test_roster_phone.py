"""
Tests for coach roster phone column and student profile phone accordion.
"""
import pytest
from django.test import Client
from model_bakery import baker


# ── 1. Roster renders and shows student phone ─────────────────────────────────

@pytest.mark.django_db
def test_roster_renders_student_phone(settings):
    settings.SELF_PURCHASE_ENABLED = True

    coach = baker.make(
        'users_app.User',
        role='coach',
        is_active=True,
        is_approved=True,
        wordpress_post_id=1234,
    )
    student = baker.make(
        'users_app.User',
        role='student',
        is_active=True,
        phone='+905551112233',
        coach=coach,
    )
    baker.make(
        'users_app.CoachStudent',
        coach=coach,
        student=student,
        active=True,
    )

    c = Client()
    c.force_login(coach)
    resp = c.get('/coach/')
    assert resp.status_code == 200
    assert '+905551112233' in resp.content.decode('utf-8')


# ── 2. Profile accordion: form when no phone, read-only when phone set ─────────

@pytest.mark.django_db
def test_profile_accordion_conditional_phone(db):
    # Student without phone: form input must be present
    student_no_phone = baker.make(
        'users_app.User',
        role='student',
        is_active=True,
        phone=None,
    )
    c = Client()
    c.force_login(student_no_phone)
    resp = c.get('/profil/')
    assert resp.status_code == 200
    content = resp.content.decode('utf-8')
    assert 'name="phone"' in content
    assert 'Kişisel Bilgiler' in content

    # Student with phone: form input must be absent, phone text present
    student_with_phone = baker.make(
        'users_app.User',
        role='student',
        is_active=True,
        phone='+905559876543',
    )
    c2 = Client()
    c2.force_login(student_with_phone)
    resp2 = c2.get('/profil/')
    assert resp2.status_code == 200
    content2 = resp2.content.decode('utf-8')
    assert 'name="phone"' not in content2
    assert '05559876543' in content2
