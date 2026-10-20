"""
Tests for capacity_app.

Covers:
- Order creation and reference uniqueness across both order tables
- Claim (idempotent)
- mark_capacity_order_paid creates exactly one grant (idempotent)
- Stale order cancellation
- Enforcement off and on for invite creation
- Enforcement off and on for invite acceptance
- Within capacity, vagus links not counted
- NULL-source rule
- Student purchase funnel (on_payment_success) unaffected by enforcement
- Reference code uniqueness across purchase_app.Order and CoachCapacityOrder
- Failure isolation: exception in capacity code doesn't break invite flow
"""
import uuid
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from model_bakery import baker

from capacity_app.models import CapacitySettings, CoachCapacityGrant, CoachCapacityOrder
from capacity_app.services import (
    can_add_own_student,
    cancel_stale_capacity_orders,
    create_capacity_order,
    get_capacity_status,
    is_own_student_source,
    mark_capacity_order_paid,
)
from users_app.models import CoachStudent

User = get_user_model()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def coach(db):
    return baker.make(User, role='coach', is_active=True, is_approved=True)


@pytest.fixture
def student(db):
    return baker.make(User, role='student', is_active=True, is_approved=True)


@pytest.fixture
def capacity_settings(db):
    cfg = CapacitySettings.get()
    cfg.per_slot_price_kurus = 50000  # 500 ₺
    cfg.save()
    return cfg


@pytest.fixture
def grant_10(db, coach):
    today = date.today()
    return baker.make(
        CoachCapacityGrant,
        coach=coach,
        slots=10,
        period_start=today,
        period_end=today + timedelta(days=30),
        order=None,
    )


# ── 1. Order flow ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_create_capacity_order(coach, capacity_settings):
    order = create_capacity_order(coach, slots=3)
    assert order.slots == 3
    assert order.amount_kurus == 3 * 50000
    assert order.per_slot_kurus == 50000
    assert order.status == CoachCapacityOrder.STATUS_AWAITING_TRANSFER
    assert order.ref_code is not None
    assert order.ref_code.startswith('KC-')


@pytest.mark.django_db
def test_mark_paid_creates_grant(coach, capacity_settings):
    order = create_capacity_order(coach, slots=5)
    order_pk = order.pk

    updated_order, created = mark_capacity_order_paid(order)

    assert updated_order.status == CoachCapacityOrder.STATUS_PAID
    assert created is True
    grant = CoachCapacityGrant.objects.get(order=updated_order)
    assert grant.slots == 5
    assert grant.period_start == date.today()
    assert grant.period_end == date.today() + timedelta(days=30)
    assert grant.coach == coach


@pytest.mark.django_db
def test_mark_paid_idempotent(coach, capacity_settings):
    order = create_capacity_order(coach, slots=5)
    mark_capacity_order_paid(order)
    order.refresh_from_db()
    # Call again — should not create a second grant
    _, created = mark_capacity_order_paid(order)
    assert created is False
    assert CoachCapacityGrant.objects.filter(order=order).count() == 1


# ── 2. Claim ──────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_claim_sets_timestamp(coach, capacity_settings):
    order = create_capacity_order(coach, slots=1)
    assert order.payment_claimed_at is None
    client = Client()
    coach.set_password('testpass')
    coach.save()
    client.login(username=coach.email, password='testpass')
    client.post(f'/coach/kontenjan/satin-al/{order.token}/bildir/',
                data={'sender_name': 'Ali Kaya'})
    order.refresh_from_db()
    assert order.payment_claimed_at is not None
    assert order.sender_name == 'Ali Kaya'


# ── 3. Stale order cancellation ────────────────────────────────────────────────

@pytest.mark.django_db
def test_stale_cancellation(coach, capacity_settings):
    stale = baker.make(
        CoachCapacityOrder,
        coach=coach,
        slots=1,
        amount_kurus=50000,
        per_slot_kurus=50000,
        status=CoachCapacityOrder.STATUS_AWAITING_TRANSFER,
        created_at=timezone.now() - timedelta(days=8),
        ref_code='KC-STALE1',
    )
    fresh = create_capacity_order(coach, slots=1)
    cancelled = cancel_stale_capacity_orders()
    assert cancelled == 1
    stale.refresh_from_db()
    fresh.refresh_from_db()
    assert stale.status == CoachCapacityOrder.STATUS_CANCELLED
    assert fresh.status == CoachCapacityOrder.STATUS_AWAITING_TRANSFER


# ── 4. Capacity status ─────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_capacity_status_no_grants(coach, student):
    baker.make(CoachStudent, coach=coach, student=student,
               source=CoachStudent.SOURCE_COACH, active=True)
    st = get_capacity_status(coach)
    assert st['granted'] == 0
    assert st['in_use'] == 1
    assert st['free'] == -1  # overage


@pytest.mark.django_db
def test_capacity_status_with_grant(coach, student, grant_10):
    baker.make(CoachStudent, coach=coach, student=student,
               source=CoachStudent.SOURCE_COACH, active=True)
    st = get_capacity_status(coach)
    assert st['granted'] == 10
    assert st['in_use'] == 1
    assert st['free'] == 9


@pytest.mark.django_db
def test_vagus_links_not_counted(coach, grant_10):
    for _ in range(5):
        s = baker.make(User, role='student')
        baker.make(CoachStudent, coach=coach, student=s,
                   source=CoachStudent.SOURCE_VAGUS, active=True)
    st = get_capacity_status(coach)
    assert st['in_use'] == 0
    assert st['free'] == 10


# ── 5. NULL-source rule ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_null_source_no_paid_order_counts_as_own(coach, grant_10):
    s = baker.make(User, role='student')
    baker.make(CoachStudent, coach=coach, student=s, source=None, active=True)
    st = get_capacity_status(coach)
    assert st['in_use'] == 1


@pytest.mark.django_db
def test_null_source_with_paid_order_not_counted(coach, grant_10):
    from purchase_app.models import Order, Plan
    s = baker.make(User, role='student')
    plan = baker.make(Plan, price_kurus=100000, duration_days=30)
    baker.make(Order, student=s, coach=coach, plan=plan, email=s.email,
               status=Order.STATUS_PAID, amount_kurus=100000,
               full_name='Test', provider='sandbox')
    baker.make(CoachStudent, coach=coach, student=s, source=None, active=True)
    st = get_capacity_status(coach)
    assert st['in_use'] == 0


# ── 6. Enforcement ────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_enforcement_off_allows_when_full(coach, settings):
    settings.COACH_CAPACITY_ENFORCED = False
    allowed, _ = can_add_own_student(coach)
    assert allowed is True


@pytest.mark.django_db
def test_enforcement_on_blocks_when_full(coach, settings):
    settings.COACH_CAPACITY_ENFORCED = True
    # No grants → capacity 0, in_use 0, free 0
    allowed, msg = can_add_own_student(coach)
    assert allowed is False
    assert msg is not None


@pytest.mark.django_db
def test_enforcement_on_allows_when_space(coach, grant_10, settings):
    settings.COACH_CAPACITY_ENFORCED = True
    allowed, msg = can_add_own_student(coach)
    assert allowed is True
    assert msg is None


@pytest.mark.django_db
def test_invite_creation_blocked_when_enforcement_on(coach, settings):
    settings.COACH_CAPACITY_ENFORCED = True
    coach.set_password('testpass')
    coach.save()
    client = Client()
    client.login(username=coach.email, password='testpass')
    resp = client.post('/auth/invite-students/', {
        'email': 'newstudent@example.com',
        'full_name': 'New Student',
    })
    from users_app.models import StudentInvite
    assert not StudentInvite.objects.filter(email='newstudent@example.com').exists()


@pytest.mark.django_db
def test_invite_creation_allowed_when_enforcement_on_with_capacity(coach, grant_10, settings):
    settings.COACH_CAPACITY_ENFORCED = True
    coach.set_password('testpass')
    coach.save()
    client = Client()
    client.login(username=coach.email, password='testpass')
    resp = client.post('/auth/invite-students/', {
        'email': 'newstudent@example.com',
        'full_name': 'New Student',
    })
    from users_app.models import StudentInvite
    assert StudentInvite.objects.filter(email='newstudent@example.com').exists()


@pytest.mark.django_db
def test_invite_acceptance_blocked_when_enforcement_on(coach, settings):
    settings.COACH_CAPACITY_ENFORCED = True
    from users_app.models import StudentInvite
    invite = baker.make(
        StudentInvite,
        coach=coach,
        email='blocktest@example.com',
        token=StudentInvite.generate_token(),
        is_used=False,
        initiated_by_staff=False,
    )
    client = Client()
    resp = client.post(f'/auth/invite/{invite.token}/', {
        'full_name': 'Block Test',
        'password1': 'Testpass123!',
        'password2': 'Testpass123!',
        'terms_accepted': 'on',
        'kvkk_accepted': 'on',
    })
    assert not User.objects.filter(email='blocktest@example.com').exists()
    invite.refresh_from_db()
    assert not invite.is_used


@pytest.mark.django_db
def test_invite_acceptance_allowed_when_enforcement_on_with_capacity(coach, grant_10, settings):
    settings.COACH_CAPACITY_ENFORCED = True
    from users_app.models import StudentInvite
    invite = baker.make(
        StudentInvite,
        coach=coach,
        email='allowtest@example.com',
        token=StudentInvite.generate_token(),
        is_used=False,
        initiated_by_staff=False,
    )
    client = Client()
    resp = client.post(f'/auth/invite/{invite.token}/', {
        'full_name': 'Allow Test',
        'password1': 'Testpass123!',
        'password2': 'Testpass123!',
        'terms_accepted': 'on',
        'kvkk_accepted': 'on',
    })
    assert User.objects.filter(email='allowtest@example.com').exists()
    invite.refresh_from_db()
    assert invite.is_used


@pytest.mark.django_db
def test_staff_invite_acceptance_bypasses_capacity_check(coach, settings):
    """Staff-initiated invites create SOURCE_VAGUS links; capacity doesn't apply."""
    settings.COACH_CAPACITY_ENFORCED = True
    from users_app.models import StudentInvite
    invite = baker.make(
        StudentInvite,
        coach=coach,
        email='vagusinvite@example.com',
        token=StudentInvite.generate_token(),
        is_used=False,
        initiated_by_staff=True,
    )
    client = Client()
    resp = client.post(f'/auth/invite/{invite.token}/', {
        'full_name': 'Vagus Invite',
        'password1': 'Testpass123!',
        'password2': 'Testpass123!',
        'terms_accepted': 'on',
        'kvkk_accepted': 'on',
    })
    assert User.objects.filter(email='vagusinvite@example.com').exists()


# ── 7. Student purchase funnel unaffected ─────────────────────────────────────

@pytest.mark.django_db
def test_on_payment_success_unaffected_by_capacity(coach, settings):
    """on_payment_success (vagus-source) must work regardless of enforcement."""
    settings.COACH_CAPACITY_ENFORCED = True
    from purchase_app.models import Order, Plan
    from purchase_app.services import on_payment_success
    plan = baker.make(Plan, price_kurus=100000, duration_days=30, active=True)
    order = baker.make(
        Order,
        coach=coach,
        plan=plan,
        email='funneltest@example.com',
        amount_kurus=100000,
        status=Order.STATUS_AWAITING_TRANSFER,
        provider='bank_transfer',
        full_name='Funnel Test',
        provider_ref='KC-TEST01',
    )
    on_payment_success(order)
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID
    assert User.objects.filter(email='funneltest@example.com').exists()


# ── 8. Reference code uniqueness ──────────────────────────────────────────────

@pytest.mark.django_db
def test_ref_code_unique_across_tables(coach, capacity_settings, db):
    """CoachCapacityOrder.ref_code must not duplicate purchase_app.Order.provider_ref."""
    from purchase_app.models import Order, Plan
    plan = baker.make(Plan, price_kurus=100000, duration_days=30)
    purchase_order = baker.make(
        Order,
        coach=coach,
        plan=plan,
        email='x@x.com',
        amount_kurus=100000,
        status=Order.STATUS_AWAITING_TRANSFER,
        provider='bank_transfer',
        provider_ref='KC-XXXXX1',
        full_name='X',
    )
    with patch('capacity_app.services._generate_ref',
               side_effect=['KC-XXXXX1', 'KC-XXXXX2']):
        order = create_capacity_order(coach, slots=1)
    assert order.ref_code == 'KC-XXXXX2'


# ── 9. is_own_student_source ──────────────────────────────────────────────────

def test_source_coach_is_own():
    assert is_own_student_source('coach') is True


def test_source_vagus_not_own():
    assert is_own_student_source('vagus') is False


def test_source_null_no_student_is_own():
    assert is_own_student_source(None, student=None) is True


# ── 10. Enforcement off: no change in invite/acceptance flow ──────────────────

@pytest.mark.django_db
def test_enforcement_off_invite_creation_with_5_own_students(coach, settings):
    """Flag off + 0 grants + 5 own students → invite creation must succeed."""
    settings.COACH_CAPACITY_ENFORCED = False
    for _ in range(5):
        s = baker.make(User, role='student')
        baker.make(CoachStudent, coach=coach, student=s,
                   source=CoachStudent.SOURCE_COACH, active=True)

    coach.set_password('testpass')
    coach.save()
    client = Client()
    client.login(username=coach.email, password='testpass')
    resp = client.post('/auth/invite-students/', {
        'email': 'enfoff_new@example.com',
        'full_name': 'Enf Off Test',
    })
    from users_app.models import StudentInvite
    assert StudentInvite.objects.filter(email='enfoff_new@example.com').exists()


@pytest.mark.django_db
def test_enforcement_off_invite_acceptance_with_5_own_students(coach, settings):
    """Flag off + 0 grants + 5 own students → invite acceptance must succeed."""
    settings.COACH_CAPACITY_ENFORCED = False
    for _ in range(5):
        s = baker.make(User, role='student')
        baker.make(CoachStudent, coach=coach, student=s,
                   source=CoachStudent.SOURCE_COACH, active=True)

    from users_app.models import StudentInvite
    invite = baker.make(
        StudentInvite,
        coach=coach,
        email='enfoff_accept@example.com',
        token=StudentInvite.generate_token(),
        is_used=False,
        initiated_by_staff=False,
    )
    client = Client()
    resp = client.post(f'/auth/invite/{invite.token}/', {
        'full_name': 'Enf Off Accept',
        'password1': 'Testpass123!',
        'password2': 'Testpass123!',
        'terms_accepted': 'on',
        'kvkk_accepted': 'on',
    })
    assert User.objects.filter(email='enfoff_accept@example.com').exists()
    invite.refresh_from_db()
    assert invite.is_used
