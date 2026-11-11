import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from model_bakery import baker

from capacity_app.models import CoachCapacityOrder

User = get_user_model()


@pytest.mark.django_db
def test_order_detail_confirm_escapes_coach_name():
    staff = baker.make(User, role='staff', is_active=True, is_staff=True)
    coach = baker.make(User, role='coach', is_active=True, is_approved=True,
                       full_name="x');alert(1);//")
    order = baker.make(
        CoachCapacityOrder,
        coach=coach, slots=1, amount_kurus=10_000, per_slot_kurus=10_000,
        status=CoachCapacityOrder.STATUS_AWAITING_TRANSFER, ref_code='KC-TEST01',
    )
    client = Client()
    client.force_login(staff)

    html = client.get(reverse('capacity_panel:order_detail', args=[order.pk])).content.decode('utf-8')

    confirm_line = next(line for line in html.splitlines() if 'return confirm(' in line)
    assert '&#x27;);alert(1)' not in confirm_line
    assert '\\u0027' in confirm_line


@pytest.fixture
def staff_client(db):
    staff = baker.make(User, role='staff', is_active=True, is_staff=True)
    client = Client()
    client.force_login(staff)
    return client


@pytest.fixture
def coach(db):
    return baker.make(User, role='coach', is_active=True, is_approved=True)


@pytest.mark.django_db
def test_repeated_capacity_purchase_reuses_open_order(coach):
    from capacity_app.models import CapacitySettings
    cfg = CapacitySettings.get()
    cfg.per_slot_price_kurus = 50_000
    cfg.save()
    client = Client()
    client.force_login(coach)

    first = client.post(reverse('capacity:page'), {'slots': '2'})
    second = client.post(reverse('capacity:page'), {'slots': '2'})

    assert first.status_code == second.status_code == 302
    assert first['Location'] == second['Location']
    assert CoachCapacityOrder.objects.filter(coach=coach).count() == 1


@pytest.mark.django_db
def test_panel_cancel_never_overwrites_paid_orders(staff_client, coach):
    from capacity_app.models import CoachStudentRenewalOrder
    from users_app.models import CoachStudent
    paid = baker.make(CoachCapacityOrder, coach=coach, slots=1, amount_kurus=10_000,
                      per_slot_kurus=10_000, status=CoachCapacityOrder.STATUS_PAID,
                      ref_code='KC-PAID01')
    student = baker.make(User, role='student', is_active=True)
    link = baker.make(CoachStudent, coach=coach, student=student, active=True, source='coach')
    paid_renewal = baker.make(CoachStudentRenewalOrder, coach_student=link, amount_kurus=10_000,
                              per_student_kurus=10_000, ref_code='KC-PAID02',
                              status=CoachStudentRenewalOrder.STATUS_PAID)
    open_renewal = baker.make(CoachStudentRenewalOrder, coach_student=link, amount_kurus=10_000,
                              per_student_kurus=10_000, ref_code='KC-OPEN03',
                              status=CoachStudentRenewalOrder.STATUS_AWAITING_TRANSFER)

    staff_client.post(reverse('capacity_panel:order_cancel', args=[paid.pk]))
    staff_client.post(reverse('capacity_panel:renewal_cancel', args=[paid_renewal.pk]))
    staff_client.post(reverse('capacity_panel:renewal_cancel', args=[open_renewal.pk]))

    paid.refresh_from_db()
    paid_renewal.refresh_from_db()
    open_renewal.refresh_from_db()
    assert paid.status == CoachCapacityOrder.STATUS_PAID
    assert paid_renewal.status == CoachStudentRenewalOrder.STATUS_PAID
    assert open_renewal.status == CoachStudentRenewalOrder.STATUS_CANCELLED


@pytest.mark.django_db
def test_manual_grant_double_submit_creates_one_grant(staff_client, coach):
    from capacity_app.models import CoachCapacityGrant
    url = reverse('capacity_panel:grant_create')

    staff_client.post(url, {'coach_id': coach.pk, 'slots': '4'})
    staff_client.post(url, {'coach_id': coach.pk, 'slots': '4'})

    assert CoachCapacityGrant.objects.filter(coach=coach).count() == 1


@pytest.mark.django_db
def test_credit_grant_is_bounded_and_double_submit_safe(staff_client, coach):
    from capacity_app.models import CoachCreditLedger
    url = reverse('capacity_panel:coach_credits', kwargs={'coach_pk': coach.pk})

    too_many = staff_client.post(url, {'action': 'grant', 'n': '99999999999', 'notes': 'x'})
    assert too_many.status_code == 200
    too_negative = staff_client.post(url, {'action': 'adjust', 'delta': '-5000', 'notes': 'x'})
    assert too_negative.status_code == 200
    assert not CoachCreditLedger.objects.filter(coach=coach).exists()

    staff_client.post(url, {'action': 'grant', 'n': '5', 'notes': 'hediye'})
    staff_client.post(url, {'action': 'grant', 'n': '5', 'notes': 'hediye'})
    assert CoachCreditLedger.objects.filter(coach=coach).count() == 1


@pytest.mark.django_db
def test_renewal_start_twice_keeps_one_open_order(coach):
    from capacity_app.models import CapacitySettings, CoachStudentRenewalOrder
    from users_app.models import CoachStudent
    cfg = CapacitySettings.get()
    cfg.per_slot_price_kurus = 50_000
    cfg.save()
    student = baker.make(User, role='student', is_active=True)
    link = baker.make(CoachStudent, coach=coach, student=student, active=True, source='coach')
    client = Client()
    client.force_login(coach)
    url = reverse('capacity:renewal_start', args=[link.pk])

    first = client.post(url)
    second = client.post(url)

    assert first['Location'] == second['Location']
    assert CoachStudentRenewalOrder.objects.filter(coach_student=link).count() == 1
