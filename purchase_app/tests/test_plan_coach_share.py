"""
Tests that plan create/update correctly accept coach_share_tl (whole ₺ integer)
and store it as integer kuruş.
"""
import pytest
from django.test import Client

from model_bakery import baker
from users_app.models import User
from purchase_app.models import Plan


def make_staff():
    u = baker.make(User, role='coach', is_active=True, is_approved=True, is_staff=True)
    u.set_password('pw')
    u.save()
    return u


@pytest.mark.django_db
def test_plan_create_stores_coach_share_as_kurus():
    staff = make_staff()
    client = Client()
    client.force_login(staff)

    resp = client.post('/panel/satin-al/planlar/yeni/', {
        'name':           'Test Plan',
        'kind':           'one_time',
        'price_kurus':    319900,
        'coach_share_tl': '2500',
        'duration_days':  30,
        'active':         'on',
    })

    assert resp.status_code in (200, 302)
    plan = Plan.objects.filter(name='Test Plan').first()
    assert plan is not None
    assert plan.coach_share_kurus == 250_000


@pytest.mark.django_db
def test_plan_update_stores_coach_share_as_kurus():
    staff = make_staff()
    plan  = baker.make(Plan, name='Update Me', price_kurus=319900,
                       duration_days=30, active=True, coach_share_kurus=0)
    client = Client()
    client.force_login(staff)

    resp = client.post(f'/panel/satin-al/planlar/{plan.pk}/guncelle/', {
        'name':           'Update Me',
        'kind':           plan.kind,
        'price_kurus':    319900,
        'coach_share_tl': '2500',
        'duration_days':  30,
        'active':         'on',
    })

    assert resp.status_code in (200, 302)
    plan.refresh_from_db()
    assert plan.coach_share_kurus == 250_000


@pytest.mark.django_db
def test_plan_list_contains_coach_share_input():
    staff = make_staff()
    baker.make(Plan, name='Shown Plan', price_kurus=319900,
               duration_days=30, active=True, coach_share_kurus=250_000)
    client = Client()
    client.force_login(staff)

    resp = client.get('/panel/satin-al/planlar/')
    assert resp.status_code == 200
    content = resp.content.decode()
    assert 'coach_share_tl' in content
    assert '2500' in content
