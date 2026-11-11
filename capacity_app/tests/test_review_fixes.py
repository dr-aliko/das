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
