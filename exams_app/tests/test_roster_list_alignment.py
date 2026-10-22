"""
Regression: list-view rows must have identical action-slot and stat-column markup
for both Vagus-assigned and own students so columns stay aligned.
"""
import pytest
from django.test import Client
from model_bakery import baker


@pytest.mark.django_db
def test_list_view_action_slot_and_stats_consistent(settings):
    settings.SELF_PURCHASE_ENABLED = True

    coach = baker.make(
        'users_app.User',
        role='coach', is_active=True, is_approved=True, wordpress_post_id=9001,
    )
    vagus_student = baker.make('users_app.User', role='student', is_active=True, coach=coach)
    baker.make('users_app.CoachStudent', coach=coach, student=vagus_student, active=True, source='vagus')
    own_student = baker.make('users_app.User', role='student', is_active=True, coach=coach)
    baker.make('users_app.CoachStudent', coach=coach, student=own_student, active=True, source='coach')

    c = Client()
    c.force_login(coach)
    html = c.get('/coach/').content.decode()

    # Both rows (one per student) carry the action slot — button for own, placeholder for vagus.
    # Search for the attribute value, not the CSS class selector (which also contains the token).
    slot_elements = html.count('class="roster-action-slot')
    assert slot_elements == 2, (
        f"Expected one roster-action-slot element per student row; found {slot_elements}"
    )
    # Both rows carry the fixed-width stat container
    assert html.count('roster-stats') == 2, (
        "Expected one roster-stats container per student row; "
        f"found {html.count('roster-stats')}"
    )
