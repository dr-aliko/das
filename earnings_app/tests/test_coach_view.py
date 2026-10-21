"""
Tests for the redesigned coach earnings view.
"""
import pytest
from datetime import date

from django.test import Client
from django.urls import reverse
from model_bakery import baker

from earnings_app.models import EarningRow
from users_app.models import User


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
