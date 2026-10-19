"""
Confirm that a crash inside create_holding_earning (or the signal) never
rolls back the outer on_payment_success transaction that marked the order PAID.
"""
import pytest
from unittest.mock import patch

from model_bakery import baker

from purchase_app.models import Order, Plan
from purchase_app.services import on_payment_success
from users_app.models import User


def make_coach(**kw):
    return baker.make(User, role='coach', is_active=True, is_approved=True, **kw)


def make_plan(**kw):
    return baker.make(Plan, duration_days=30, active=True,
                      price_kurus=319_900, coach_share_kurus=250_000, **kw)


def make_pending_order(coach, plan, email='buyer@example.com'):
    return baker.make(
        Order,
        email=email,
        full_name='Test Buyer',
        coach=coach, plan=plan,
        amount_kurus=plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        provider_ref='sandbox-test-1',
    )


@pytest.mark.django_db
def test_order_stays_paid_when_create_holding_earning_raises():
    coach = make_coach()
    plan  = make_plan()
    order = make_pending_order(coach, plan)

    with patch('earnings_app.services.create_holding_earning',
               side_effect=Exception('forced failure')):
        on_payment_success(order)

    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_order_stays_paid_when_create_holding_earning_raises_db_error():
    """Even a database-level error inside the savepoint must not roll back PAID status."""
    from django.db import DatabaseError
    coach = make_coach()
    plan  = make_plan()
    order = make_pending_order(coach, plan, email='dbfail@example.com')

    with patch('earnings_app.services.create_holding_earning',
               side_effect=DatabaseError('simulated DB error')):
        on_payment_success(order)

    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID
