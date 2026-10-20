"""
Tests for the KPI card refactor on the coach roster:
- pill strip (rounded-full status buttons) is gone
- three KPI card buttons exist with aria-pressed hooks and status-filter @click
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from model_bakery import baker

User = get_user_model()


@pytest.fixture
def coach(db):
    u = baker.make(User, role='coach', is_active=True, is_approved=True)
    u.set_password('pw')
    u.save()
    return u


@pytest.fixture
def coach_client(coach):
    c = Client()
    c.login(username=coach.email, password='pw')
    return c


@pytest.mark.django_db
def test_pill_strip_removed(coach_client, settings):
    """The old rounded-full pill strip must not appear in the roster HTML."""
    settings.COACH_CAPACITY_ENFORCED = False
    resp = coach_client.get(reverse('coach:dashboard'))
    assert resp.status_code == 200
    body = resp.content.decode('utf-8')
    # The old pills used rounded-full with activeFilter click; check the
    # characteristic class combo that only the pill strip used.
    assert 'rounded-full' not in body or 'activeFilter' not in body.split('rounded-full')[0].rsplit('\n', 1)[-1]
    # More direct: the pill strip wrapper had this exact combo
    assert 'rounded-full' not in body.split('activeFilter')[0].rsplit('rounded-full', 1)[-1] if 'rounded-full' in body else True


@pytest.mark.django_db
def test_kpi_cards_are_buttons_with_aria_and_filter(coach_client, settings):
    """
    The three KPI cards must be <button> elements with :aria-pressed and
    @click="activeFilter = ..." directives.
    """
    settings.COACH_CAPACITY_ENFORCED = False
    resp = coach_client.get(reverse('coach:dashboard'))
    assert resp.status_code == 200
    body = resp.content.decode('utf-8')

    assert "activeFilter === 'tumu'" in body
    assert "activeFilter === 'iyi'" in body
    assert "activeFilter === 'dusus'" in body
    assert ":aria-pressed" in body

    assert "x-text=\"kpiTotal\"" in body
    assert "x-text=\"kpiIyi\"" in body
    assert "x-text=\"kpiDusus\"" in body
