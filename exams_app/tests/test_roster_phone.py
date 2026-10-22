"""
Tests for the coach roster WhatsApp/call phone pill.
"""
import pytest
from django.test import Client
from model_bakery import baker


# ── 1. wa.me + tel links present; nothing rendered for student without phone ──

@pytest.mark.django_db
def test_roster_phone_pill_links(settings):
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

    # wa.me link uses digits-only international number (no +)
    assert 'wa.me/905551112233' in html
    # tel link for the call button
    assert 'tel:+905551112233' in html
    # friendly display text
    assert '0555 111 22 33' in html
    # student without phone: none of the above appears for them
    # (the page renders without errors; counts confirm only one student's phone)
    assert html.count('wa.me/') == 2   # card view + list view, same student


# ── 2. Old muted inline markup is gone ────────────────────────────────────────

@pytest.mark.django_db
def test_roster_old_muted_phone_markup_absent(settings):
    settings.SELF_PURCHASE_ENABLED = True

    coach = baker.make(
        'users_app.User',
        role='coach',
        is_active=True,
        is_approved=True,
        wordpress_post_id=5678,
    )
    student = baker.make(
        'users_app.User',
        role='student',
        is_active=True,
        phone='+905559998877',
        coach=coach,
    )
    baker.make('users_app.CoachStudent', coach=coach, student=student, active=True)

    c = Client()
    c.force_login(coach)
    resp = c.get('/coach/')
    html = resp.content.decode('utf-8')

    # Old pattern: muted inline text appended after a "·" separator in the grade line
    assert ' · 0555' not in html
    # Old pattern: muted span with display:block inline style (the previous implementation)
    assert 'display:block;margin-top:2px' not in html
    # New design is present: wa.me button
    assert 'wa.me/905559998877' in html
