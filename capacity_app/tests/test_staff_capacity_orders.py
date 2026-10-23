"""
Staff-side capacity order management guards.

Covers:
- Orders table shows inline 'Ödeme alındı' button only for claimed orders
- transfers_capacity badge counts only claimed (payment_claimed_at set) orders
- Approving twice with COACH_PER_STUDENT_PERIODS=True creates one ledger entry, no grant
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker

from capacity_app.models import CoachCapacityGrant, CoachCapacityOrder, CoachCreditLedger

User = get_user_model()


@pytest.fixture
def staff(db):
    u = baker.make(User, role='staff', is_active=True, is_staff=True)
    u.set_password('pass')
    u.save()
    return u


@pytest.fixture
def coach(db):
    return baker.make(User, role='coach', is_active=True, is_approved=True)


@pytest.fixture
def staff_client(staff):
    c = Client()
    c.login(username=staff.email, password='pass')
    return c


@pytest.mark.django_db
def test_orders_table_approve_button_only_for_claimed(staff_client, coach):
    """Inline 'Ödeme alındı' POST form appears only for claimed orders."""
    claimed = baker.make(
        CoachCapacityOrder,
        coach=coach, slots=3,
        status=CoachCapacityOrder.STATUS_AWAITING_TRANSFER,
        payment_claimed_at=timezone.now(),
    )
    unclaimed = baker.make(
        CoachCapacityOrder,
        coach=coach, slots=2,
        status=CoachCapacityOrder.STATUS_AWAITING_TRANSFER,
        payment_claimed_at=None,
    )
    resp = staff_client.get(reverse('capacity_panel:overview'))
    assert resp.status_code == 200
    body = resp.content.decode('utf-8')

    claimed_url = reverse('capacity_panel:order_mark_paid', kwargs={'pk': claimed.pk})
    unclaimed_url = reverse('capacity_panel:order_mark_paid', kwargs={'pk': unclaimed.pk})
    assert claimed_url in body, 'approve action missing for claimed order'
    assert unclaimed_url not in body, 'approve action must not appear for unclaimed order'


@pytest.mark.django_db
def test_badge_counts_only_claimed_capacity_orders(db):
    """transfers_capacity badge counts claimed orders only; unclaimed awaiting orders are excluded."""
    from users_app.panel_badges import all_badges
    coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    baker.make(
        CoachCapacityOrder, coach=coach, slots=1,
        status=CoachCapacityOrder.STATUS_AWAITING_TRANSFER,
        payment_claimed_at=timezone.now(),
    )
    baker.make(
        CoachCapacityOrder, coach=coach, slots=1,
        status=CoachCapacityOrder.STATUS_AWAITING_TRANSFER,
        payment_claimed_at=None,
    )
    badges = all_badges()
    assert badges['transfers_capacity'] == 1, (
        f'Expected 1 (claimed only), got {badges["transfers_capacity"]}'
    )


@pytest.mark.django_db
def test_double_approve_per_student_credits_once_no_grant(settings):
    """With COACH_PER_STUDENT_PERIODS=True, approving twice creates one ledger row and no grant."""
    settings.COACH_PER_STUDENT_PERIODS = True
    from capacity_app.services import mark_capacity_order_paid

    coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    order = baker.make(
        CoachCapacityOrder,
        coach=coach, slots=3,
        status=CoachCapacityOrder.STATUS_AWAITING_TRANSFER,
        payment_claimed_at=timezone.now(),
    )

    _, created1 = mark_capacity_order_paid(order)
    _, created2 = mark_capacity_order_paid(order)

    assert created1 is True
    assert created2 is False

    ledger_rows = CoachCreditLedger.objects.filter(
        coach=coach,
        reason=CoachCreditLedger.REASON_PURCHASE_APPROVED,
        order=order,
    )
    assert ledger_rows.count() == 1
    assert ledger_rows.first().delta == 3
    assert not CoachCapacityGrant.objects.filter(order=order).exists()
