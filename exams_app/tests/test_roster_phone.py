"""
Tests for coach roster phone display.
"""
import pytest
from django.test import Client
from model_bakery import baker


# ── 1. Roster shows friendly format + tel link; omits when phone is empty ─────

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
    student_with = baker.make(
        'users_app.User',
        role='student',
        is_active=True,
        phone='+905551112233',
        coach=coach,
    )
    baker.make('users_app.CoachStudent', coach=coach, student=student_with, active=True)

    student_without = baker.make(
        'users_app.User',
        role='student',
        is_active=True,
        phone=None,
        coach=coach,
    )
    baker.make('users_app.CoachStudent', coach=coach, student=student_without, active=True)

    c = Client()
    c.force_login(coach)
    resp = c.get('/coach/')
    assert resp.status_code == 200
    html = resp.content.decode('utf-8')

    assert '0555 111 22 33' in html        # friendly display format
    assert 'tel:+905551112233' in html     # tel link with E164 number


# ── 2. A second coach's roster never shows the first coach's student's phone ──

@pytest.mark.django_db
def test_roster_second_coach_cannot_see_phone(settings):
    settings.SELF_PURCHASE_ENABLED = True

    coach1 = baker.make(
        'users_app.User', role='coach', is_active=True, is_approved=True, wordpress_post_id=1
    )
    coach2 = baker.make(
        'users_app.User', role='coach', is_active=True, is_approved=True, wordpress_post_id=2
    )
    student1 = baker.make(
        'users_app.User',
        role='student',
        is_active=True,
        phone='+905559876543',
        coach=coach1,
    )
    baker.make('users_app.CoachStudent', coach=coach1, student=student1, active=True)

    c2 = Client()
    c2.force_login(coach2)
    resp = c2.get('/coach/')
    assert resp.status_code == 200
    html = resp.content.decode('utf-8')

    assert '+905559876543' not in html
    assert '0555 987 65 43' not in html


# ── 3. Phone comes from the already-fetched User row; no extra query per student

@pytest.mark.django_db
def test_roster_phone_no_extra_queries(settings):
    """Query count must be identical whether the student has a phone or not."""
    settings.SELF_PURCHASE_ENABLED = True
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    coach_a = baker.make(
        'users_app.User', role='coach', is_active=True, is_approved=True, wordpress_post_id=10
    )
    coach_b = baker.make(
        'users_app.User', role='coach', is_active=True, is_approved=True, wordpress_post_id=11
    )

    s_with = baker.make(
        'users_app.User', role='student', is_active=True, phone='+905551234567', coach=coach_a
    )
    baker.make('users_app.CoachStudent', coach=coach_a, student=s_with, active=True)

    s_without = baker.make(
        'users_app.User', role='student', is_active=True, phone=None, coach=coach_b
    )
    baker.make('users_app.CoachStudent', coach=coach_b, student=s_without, active=True)

    c_a, c_b = Client(), Client()
    c_a.force_login(coach_a)
    c_b.force_login(coach_b)

    with CaptureQueriesContext(connection) as ctx_a:
        c_a.get('/coach/')
    with CaptureQueriesContext(connection) as ctx_b:
        c_b.get('/coach/')

    assert len(ctx_a.captured_queries) == len(ctx_b.captured_queries), (
        f'With phone: {len(ctx_a.captured_queries)} queries, '
        f'without phone: {len(ctx_b.captured_queries)} queries'
    )
