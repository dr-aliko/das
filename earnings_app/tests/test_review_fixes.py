import pytest
from datetime import date

from django.test import Client
from django.urls import reverse
from model_bakery import baker

from earnings_app.models import EarningRow
from users_app.models import User


@pytest.fixture
def staff_client(db):
    staff = baker.make(User, role='coach', is_active=True, is_staff=True)
    client = Client()
    client.force_login(staff)
    return client


def make_row(status=EarningRow.STATUS_RELEASED, student_name='Ali Veli', payout_ref=''):
    coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    student = baker.make(User, role='student', is_active=True, full_name=student_name)
    return baker.make(
        EarningRow,
        coach=coach, student=student,
        coverage_start=date(2024, 1, 1),
        coverage_end=date(2024, 1, 31),
        period_days=30, coach_days=30,
        pool_kurus=250_000, amount_kurus=250_000,
        status=status, payout_ref=payout_ref,
    )


def test_panel_export_csv_with_status_filter(staff_client):
    make_row(status=EarningRow.STATUS_RELEASED, student_name='Serbest Ogrenci')
    make_row(status=EarningRow.STATUS_PAID, student_name='Odenen Ogrenci')

    resp = staff_client.get(reverse('earnings_panel:export_csv'), {'status': 'paid'})

    assert resp.status_code == 200
    body = resp.content.decode('utf-8')
    assert 'Odenen Ogrenci' in body
    assert 'Serbest Ogrenci' not in body


def test_export_csv_neutralises_formula_cells(staff_client):
    row = make_row(status=EarningRow.STATUS_PAID,
                   student_name='=HYPERLINK("http://evil.example")', payout_ref='@ref')

    panel_body = staff_client.get(reverse('earnings_panel:export_csv')).content.decode('utf-8')
    assert '\'=HYPERLINK(' in panel_body
    assert ',=HYPERLINK(' not in panel_body
    assert "'@ref" in panel_body

    coach_client = Client()
    coach_client.force_login(row.coach)
    coach_body = coach_client.get(reverse('coach_kazanclar_export')).content.decode('utf-8')
    assert '\'=HYPERLINK(' in coach_body
    assert ',=HYPERLINK(' not in coach_body


def test_approve_ignores_foreign_referer(staff_client):
    row = make_row(status=EarningRow.STATUS_RELEASED)
    url = reverse('earnings_panel:approve', args=[row.pk])

    resp = staff_client.post(url, HTTP_REFERER='https://evil.example/x')
    assert resp.status_code == 302
    assert resp['Location'] == reverse('earnings_panel:list')

    row2 = make_row(status=EarningRow.STATUS_RELEASED)
    same_host = 'http://testserver/panel/kazanclar/?status=released'
    resp = staff_client.post(reverse('earnings_panel:approve', args=[row2.pk]), HTTP_REFERER=same_host)
    assert resp['Location'] == same_host
