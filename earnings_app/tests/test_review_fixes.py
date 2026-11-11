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


@pytest.mark.django_db
def test_transition_rechecks_status_on_locked_row():
    from earnings_app.services import approve_earning, mark_paid, void_earning
    staff = baker.make(User, role='coach', is_active=True, is_staff=True)

    stale = make_row(status=EarningRow.STATUS_RELEASED)
    EarningRow.objects.filter(pk=stale.pk).update(status=EarningRow.STATUS_VOID)
    with pytest.raises(ValueError):
        approve_earning(stale, staff)

    stale = make_row(status=EarningRow.STATUS_APPROVED)
    EarningRow.objects.filter(pk=stale.pk).update(status=EarningRow.STATUS_VOID)
    with pytest.raises(ValueError):
        mark_paid(stale, staff, payout_ref='REF')

    stale = make_row(status=EarningRow.STATUS_APPROVED)
    EarningRow.objects.filter(pk=stale.pk).update(status=EarningRow.STATUS_PAID)
    with pytest.raises(ValueError):
        void_earning(stale, staff, reason='x')
    stale.refresh_from_db()
    assert stale.status == EarningRow.STATUS_PAID


def test_manual_payment_double_submit_and_bounds(staff_client):
    from earnings_app.models import ManualPaymentRecord
    coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    student = baker.make(User, role='student', is_active=True)
    url = reverse('earnings_panel:manuel_odeme')
    data = {'student_id': student.pk, 'coach_id': coach.pk, 'amount_tl': '3000',
            'coach_pool_tl': '2500', 'date': '2026-11-01', 'days': '30', 'note': 'havale'}

    assert staff_client.post(url, data).status_code == 302
    assert staff_client.post(url, data).status_code == 302
    assert ManualPaymentRecord.objects.count() == 1
    assert EarningRow.objects.filter(manual_record__isnull=False).count() == 1

    pool_over_amount = dict(data, amount_tl='1000', coach_pool_tl='2000', date='2026-11-02')
    assert staff_client.post(url, pool_over_amount).status_code == 200
    overflow = dict(data, amount_tl='99999999999', coach_pool_tl='1', date='2026-11-03')
    assert staff_client.post(url, overflow).status_code == 200
    assert ManualPaymentRecord.objects.count() == 1
