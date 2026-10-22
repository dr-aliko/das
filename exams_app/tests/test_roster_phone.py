"""
Tests for the coach roster WhatsApp phone pill.
"""
import pytest
from html.parser import HTMLParser
from django.test import Client
from model_bakery import baker


class _AnchorNestChecker(HTMLParser):
    """Tracks open <a> depth; records depth when each wa.me anchor starts."""
    def __init__(self):
        super().__init__()
        self._open = 0
        self.wa_depths = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href', '')
            if 'wa.me/' in href:
                self.wa_depths.append(self._open)
            self._open += 1

    def handle_endtag(self, tag):
        if tag == 'a':
            self._open = max(0, self._open - 1)


# ── 1. WA anchor is a sibling of the profile link, not nested inside it ───────

@pytest.mark.django_db
def test_roster_wa_link_not_nested_and_no_tel(settings):
    settings.SELF_PURCHASE_ENABLED = True

    coach = baker.make(
        'users_app.User',
        role='coach', is_active=True, is_approved=True, wordpress_post_id=1234,
    )
    student_with = baker.make(
        'users_app.User',
        role='student', is_active=True, phone='+905551112233', coach=coach,
    )
    baker.make('users_app.CoachStudent', coach=coach, student=student_with, active=True)
    student_without = baker.make(
        'users_app.User',
        role='student', is_active=True, phone=None, coach=coach,
    )
    baker.make('users_app.CoachStudent', coach=coach, student=student_without, active=True)

    c = Client()
    c.force_login(coach)
    resp = c.get('/coach/')
    assert resp.status_code == 200
    html = resp.content.decode('utf-8')

    # WA link present for the student who has a phone
    assert 'wa.me/905551112233' in html
    # No tel: links anywhere in the page
    assert 'tel:' not in html
    # WA anchor must not be nested inside another <a>
    checker = _AnchorNestChecker()
    checker.feed(html)
    assert checker.wa_depths, "expected at least one wa.me anchor in the page"
    assert all(d == 0 for d in checker.wa_depths), (
        f"wa.me anchor is nested inside another <a> (depths: {checker.wa_depths})"
    )
    # card view + list view = 2 occurrences for the one student with a phone
    assert html.count('wa.me/905551112233') == 2


# ── 2. Student without a phone renders no WA pill at all ──────────────────────

@pytest.mark.django_db
def test_roster_student_without_phone_shows_nothing(settings):
    settings.SELF_PURCHASE_ENABLED = True

    coach = baker.make(
        'users_app.User',
        role='coach', is_active=True, is_approved=True, wordpress_post_id=5678,
    )
    student = baker.make(
        'users_app.User',
        role='student', is_active=True, phone=None, coach=coach,
    )
    baker.make('users_app.CoachStudent', coach=coach, student=student, active=True)

    c = Client()
    c.force_login(coach)
    resp = c.get('/coach/')
    html = resp.content.decode('utf-8')

    assert 'wa.me/' not in html
    assert 'tel:' not in html
    assert 'href="https://wa.me/' not in html
