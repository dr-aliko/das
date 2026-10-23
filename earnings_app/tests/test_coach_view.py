"""
Tests for the redesigned coach earnings view.
"""
import pytest
from datetime import date, timedelta

from django.test import Client
from django.urls import reverse
from django.utils.timezone import make_aware
from model_bakery import baker

from earnings_app.models import EarningRow
from users_app.models import CoachStudentInterval, User


def make_coach(**kw):
    return baker.make(User, role='coach', is_active=True, is_approved=True, **kw)


def make_student(**kw):
    return baker.make(User, role='student', is_active=True, **kw)


def make_row(coach, student, status=EarningRow.STATUS_RELEASED, **kw):
    defaults = dict(
        coverage_start=date(2024, 1, 1),
        coverage_end=date(2024, 2, 1),
        period_days=31,
        coach_days=31,
        pool_kurus=250_000,
        amount_kurus=250_000,
    )
    defaults.update(kw)
    return baker.make(EarningRow, coach=coach, student=student, status=status, **defaults)


@pytest.mark.django_db
def test_held_row_shows_en_fazla_never_zero():
    """
    Held row must render 'En fazla X ₺' (pool value).
    'Bu ay' tile must not include the held pool.
    """
    coach   = make_coach()
    student = make_student()
    make_row(coach, student, status=EarningRow.STATUS_HELD,
             pool_kurus=250_000, amount_kurus=0)

    c = Client()
    c.force_login(coach)
    response = c.get(reverse('coach_kazanclar'))
    assert response.status_code == 200

    ctx = response.context
    held_rows = [r for r in ctx['rows'] if r['status'] == 'held']
    assert held_rows, 'expected held row in context'
    assert held_rows[0]['pool_display'] == '2.500 ₺'
    assert held_rows[0]['amount_display'] == ''  # no raw amount for held

    # Bu ay tile is 0 — held pool never included
    assert ctx['tile_this_month'] == '0 ₺'

    content = response.content.decode()
    assert 'En fazla' in content
    assert '2.500' in content


@pytest.mark.django_db
def test_coach_a_page_excludes_coach_b_data():
    """
    Coach A's page must not contain coach B's student names.
    No 'pool_kurus', 'amount_kurus', or 'vagus_share' field names in HTML.
    """
    coach_a  = make_coach()
    coach_b  = make_coach()
    student_a = make_student(full_name='Ali Deneme')
    student_b = make_student(full_name='Zeynep Gizlidir')

    make_row(coach_a, student_a, status=EarningRow.STATUS_RELEASED,
             pool_kurus=300_000, amount_kurus=300_000)
    make_row(coach_b, student_b, status=EarningRow.STATUS_RELEASED,
             pool_kurus=400_000, amount_kurus=400_000)

    c = Client()
    c.force_login(coach_a)
    response = c.get(reverse('coach_kazanclar'))
    assert response.status_code == 200

    content = response.content.decode()
    assert 'Zeynep Gizlidir' not in content
    assert 'pool_kurus'   not in content
    assert 'amount_kurus' not in content
    assert 'vagus_share'  not in content

    # Coach A's own student should be present
    assert 'Ali Deneme' in content


@pytest.mark.django_db
def test_filter_counts_match_data():
    """count_tumu/bekleyen/hazir/odenen in context must match the actual row breakdown."""
    coach   = make_coach()
    student = make_student()

    make_row(coach, student, status=EarningRow.STATUS_HELD)
    make_row(coach, student, status=EarningRow.STATUS_RELEASED)
    make_row(coach, student, status=EarningRow.STATUS_APPROVED)
    make_row(coach, student, status=EarningRow.STATUS_PAID)
    make_row(coach, student, status=EarningRow.STATUS_VOID)

    c = Client()
    c.force_login(coach)
    response = c.get(reverse('coach_kazanclar'))
    assert response.status_code == 200

    ctx = response.context
    assert ctx['count_tumu']     == 5   # all rows including void
    assert ctx['count_bekleyen'] == 1   # held only
    assert ctx['count_hazir']    == 2   # released + approved
    assert ctx['count_odenen']   == 1   # paid only


def _make_interval(coach, student, started_days_ago, ended_days_ago=None):
    from datetime import datetime
    today = date.today()
    started = make_aware(datetime.combine(today - timedelta(days=started_days_ago), datetime.min.time()))
    ended = None
    if ended_days_ago is not None:
        ended = make_aware(datetime.combine(today - timedelta(days=ended_days_ago), datetime.min.time()))
    return baker.make(CoachStudentInterval, coach=coach, student=student,
                      started_at=started, ended_at=ended)


@pytest.mark.django_db
def test_progress_bar_started_today_shows_1():
    """Period started today: live_days = 1 and bar width non-empty in HTML."""
    today = date.today()
    coach   = make_coach()
    student = make_student()
    make_row(coach, student, status=EarningRow.STATUS_HELD,
             coverage_start=today, coverage_end=today + timedelta(days=30),
             period_days=30, coach_days=0, pool_kurus=300_000, amount_kurus=0)
    _make_interval(coach, student, started_days_ago=0)

    c = Client()
    c.force_login(coach)
    response = c.get(reverse('coach_kazanclar'))
    assert response.status_code == 200

    held = [r for r in response.context['rows'] if r['status'] == 'held']
    assert held, 'expected held row'
    assert held[0]['coach_days'] == 1

    content = response.content.decode()
    # Bar must not be width:0% — minimum 3% is applied for held rows with N≥1
    assert '"coach_days": 1' in content or 'coach_days' in content
    assert 'width:0%' not in content


@pytest.mark.django_db
def test_progress_bar_started_yesterday_shows_2():
    """Period started yesterday: live_days = 2."""
    today = date.today()
    coach   = make_coach()
    student = make_student()
    make_row(coach, student, status=EarningRow.STATUS_HELD,
             coverage_start=today - timedelta(days=1),
             coverage_end=today + timedelta(days=29),
             period_days=30, coach_days=0, pool_kurus=300_000, amount_kurus=0)
    _make_interval(coach, student, started_days_ago=1)

    c = Client()
    c.force_login(coach)
    response = c.get(reverse('coach_kazanclar'))
    assert response.status_code == 200

    held = [r for r in response.context['rows'] if r['status'] == 'held']
    assert held, 'expected held row'
    assert held[0]['coach_days'] == 2


@pytest.mark.django_db
def test_progress_bar_mid_period_coach_change_clips_to_interval():
    """
    Coverage started 10 days ago; this coach's interval started 5 days ago.
    live_days must be 6 (today + 5 previous days), not 11.
    """
    today = date.today()
    coach   = make_coach()
    student = make_student()
    make_row(coach, student, status=EarningRow.STATUS_HELD,
             coverage_start=today - timedelta(days=10),
             coverage_end=today + timedelta(days=20),
             period_days=30, coach_days=0, pool_kurus=300_000, amount_kurus=0)
    _make_interval(coach, student, started_days_ago=5)

    c = Client()
    c.force_login(coach)
    response = c.get(reverse('coach_kazanclar'))
    assert response.status_code == 200

    held = [r for r in response.context['rows'] if r['status'] == 'held']
    assert held, 'expected held row'
    assert held[0]['coach_days'] == 6
