"""
Tests for the bank_transfer provider and related flows.
"""
import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from model_bakery import baker

from purchase_app.models import Order, Plan
from purchase_app.services import cancel_stale_orders, on_payment_success

User = get_user_model()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def coach(db):
    return baker.make(
        'users_app.User',
        role='coach',
        is_active=True,
        is_approved=True,
        wp_is_available=True,
        wordpress_post_id=6666,
    )


@pytest.fixture
def active_plan(db):
    return baker.make(
        'purchase_app.Plan',
        name='BT Test Plan',
        kind=Plan.KIND_ONE_TIME,
        price_kurus=199900,
        duration_days=30,
        active=True,
    )


@pytest.fixture
def bt_settings(settings):
    settings.SELF_PURCHASE_ENABLED = True
    settings.LEGAL_TERMS_URL = 'https://example.com/terms'
    settings.LEGAL_DISTANCE_SALES_URL = 'https://example.com/ds'
    settings.LEGAL_PRIVACY_URL = 'https://example.com/kvkk'
    settings.PAYMENT_SANDBOX = False
    settings.DEBUG = False
    settings.PURCHASE_IBAN = 'TR330006100519786457841326'
    settings.PURCHASE_IBAN_HOLDER = 'Vagus Teknoloji A.Ş.'
    settings.PURCHASE_BANK_NAME = 'Garanti BBVA'
    return settings


@pytest.fixture
def awaiting_order(db, coach, active_plan):
    return baker.make(
        'purchase_app.Order',
        email='buyer@example.com',
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_AWAITING_TRANSFER,
        provider='bank_transfer',
        provider_ref='VAGUS-999',
        full_name='Test Buyer',
    )


# ── 0. Settings-level regression: IBAN from settings reaches _purchase_enabled ─

@pytest.mark.django_db
def test_iban_in_settings_makes_page_reachable(coach, active_plan, client, settings):
    """Regression: PURCHASE_IBAN etc. must be read from settings, not os.environ."""
    settings.SELF_PURCHASE_ENABLED = True
    settings.LEGAL_TERMS_URL = 'https://example.com/terms'
    settings.LEGAL_DISTANCE_SALES_URL = 'https://example.com/ds'
    settings.LEGAL_PRIVACY_URL = 'https://example.com/kvkk'
    settings.PAYMENT_SANDBOX = False
    settings.DEBUG = False
    settings.PURCHASE_IBAN = 'TR330006100519786457841326'
    settings.PURCHASE_IBAN_HOLDER = 'Vagus Teknoloji A.Ş.'
    settings.PURCHASE_BANK_NAME = 'Garanti BBVA'
    resp = client.get(f'/satin-al/{coach.wordpress_post_id}/')
    assert resp.status_code == 200, (
        'Purchase page must return 200 when IBAN settings are set; '
        f'got {resp.status_code} — IBAN is likely read from env not settings'
    )


@pytest.mark.django_db
def test_iban_in_settings_shown_on_instructions_page(awaiting_order, settings):
    """IBAN from settings must appear on the bank-transfer instructions page."""
    settings.PURCHASE_IBAN = 'TR330006100519786457841326'
    settings.PURCHASE_IBAN_HOLDER = 'Vagus Teknoloji A.Ş.'
    settings.PURCHASE_BANK_NAME = 'Garanti BBVA'
    c = Client()
    resp = c.get(f'/satin-al/havale/{awaiting_order.token}/')
    assert resp.status_code == 200
    assert b'TR330006100519786457841326' in resp.content


# ── 1. Empty IBAN blocks the purchase flow ────────────────────────────────────

@pytest.mark.django_db
def test_empty_iban_blocks_step1(coach, client, settings):
    settings.SELF_PURCHASE_ENABLED = True
    settings.LEGAL_TERMS_URL = 'https://example.com/terms'
    settings.LEGAL_DISTANCE_SALES_URL = 'https://example.com/ds'
    settings.LEGAL_PRIVACY_URL = 'https://example.com/kvkk'
    settings.PAYMENT_SANDBOX = False
    settings.DEBUG = False
    settings.PURCHASE_IBAN = ''
    settings.PURCHASE_IBAN_HOLDER = 'Holder'
    settings.PURCHASE_BANK_NAME = 'Bank'
    resp = client.get(f'/satin-al/{coach.wordpress_post_id}/')
    assert resp.status_code == 404


@pytest.mark.django_db
def test_all_iban_fields_required(coach, client, settings):
    settings.SELF_PURCHASE_ENABLED = True
    settings.LEGAL_TERMS_URL = 'https://example.com/terms'
    settings.LEGAL_DISTANCE_SALES_URL = 'https://example.com/ds'
    settings.LEGAL_PRIVACY_URL = 'https://example.com/kvkk'
    settings.PAYMENT_SANDBOX = False
    settings.DEBUG = False
    settings.PURCHASE_IBAN = 'TR330006100519786457841326'
    settings.PURCHASE_IBAN_HOLDER = ''          # missing holder
    settings.PURCHASE_BANK_NAME = 'Garanti BBVA'
    resp = client.get(f'/satin-al/{coach.wordpress_post_id}/')
    assert resp.status_code == 404


# ── 2. Reference code shown on instructions page ──────────────────────────────

@pytest.mark.django_db
def test_bank_transfer_instructions_shows_reference(awaiting_order):
    c = Client()
    resp = c.get(f'/satin-al/havale/{awaiting_order.token}/')
    assert resp.status_code == 200
    assert b'VAGUS-999' in resp.content


@pytest.mark.django_db
def test_bank_transfer_instructions_shows_iban(awaiting_order, bt_settings):
    c = Client()
    resp = c.get(f'/satin-al/havale/{awaiting_order.token}/')
    assert resp.status_code == 200
    assert b'TR330006100519786457841326' in resp.content


# ── 3. No anonymous/non-staff way to mark paid ────────────────────────────────

@pytest.mark.django_db
def test_mark_paid_anonymous_redirects(awaiting_order):
    c = Client()
    resp = c.post(f'/panel/satin-al/siparisler/{awaiting_order.pk}/odeme-alindi/')
    # Redirected to login (staff_required decorator)
    assert resp.status_code in (302, 403)
    if resp.status_code == 302:
        assert 'login' in resp['Location'] or 'auth' in resp['Location']


@pytest.mark.django_db
def test_mark_paid_non_staff_returns_redirect(awaiting_order):
    student = baker.make('users_app.User', role='student', is_active=True, is_staff=False)
    c = Client()
    c.force_login(student)
    resp = c.post(f'/panel/satin-al/siparisler/{awaiting_order.pk}/odeme-alindi/')
    assert resp.status_code in (302, 403)
    # Must not have changed the order status
    awaiting_order.refresh_from_db()
    assert awaiting_order.status == Order.STATUS_AWAITING_TRANSFER


# ── 4. Staff mark_paid creates account and activates student ─────────────────

@pytest.mark.django_db(transaction=True)
def test_staff_mark_paid_creates_student(awaiting_order):
    from users_app.models import CoachStudent

    staff = baker.make('users_app.User', role='coach', is_active=True, is_staff=True)
    c = Client()
    c.force_login(staff)

    with patch('django_q.tasks.async_task'):
        resp = c.post(
            f'/panel/satin-al/siparisler/{awaiting_order.pk}/odeme-alindi/',
            follow=False,
        )

    assert resp.status_code == 302
    awaiting_order.refresh_from_db()
    assert awaiting_order.status == Order.STATUS_PAID
    assert User.objects.filter(email='buyer@example.com', role='student').exists()
    assert CoachStudent.objects.filter(
        coach=awaiting_order.coach,
        student__email='buyer@example.com',
    ).exists()


# ── 5. Paid twice creates exactly one CoachStudent link and one email task ────

@pytest.mark.django_db(transaction=True)
def test_staff_mark_paid_twice_one_link_one_email(awaiting_order):
    from users_app.models import CoachStudent

    staff = baker.make('users_app.User', role='coach', is_active=True, is_staff=True)
    c = Client()
    c.force_login(staff)

    with patch('django_q.tasks.async_task') as mock_at:
        c.post(f'/panel/satin-al/siparisler/{awaiting_order.pk}/odeme-alindi/')
        c.post(f'/panel/satin-al/siparisler/{awaiting_order.pk}/odeme-alindi/')

    student = User.objects.filter(email='buyer@example.com').first()
    assert student is not None

    cs_count = CoachStudent.objects.filter(
        coach=awaiting_order.coach, student=student
    ).count()
    assert cs_count == 1, 'CoachStudent must not be duplicated'

    email_tasks = [
        call.args[0] for call in mock_at.call_args_list
        if call.args[0] == 'purchase_app.tasks.send_purchase_emails'
    ]
    assert len(email_tasks) == 1, 'send_purchase_emails must be dispatched exactly once'


# ── 6. Stale rule: awaiting_transfer NOT cancelled at 2 hours ────────────────

@pytest.mark.django_db
def test_awaiting_transfer_not_cancelled_at_2h(awaiting_order):
    from django.utils import timezone

    Order.objects.filter(pk=awaiting_order.pk).update(
        created_at=timezone.now() - timezone.timedelta(hours=3)
    )
    cancel_stale_orders()
    awaiting_order.refresh_from_db()
    assert awaiting_order.status == Order.STATUS_AWAITING_TRANSFER


# ── 7. Stale rule: awaiting_transfer IS cancelled after 7 days ───────────────

@pytest.mark.django_db
def test_awaiting_transfer_cancelled_after_7_days(awaiting_order, settings):
    from django.utils import timezone

    settings.BANK_TRANSFER_EXPIRY_DAYS = 7
    Order.objects.filter(pk=awaiting_order.pk).update(
        created_at=timezone.now() - timezone.timedelta(days=8)
    )
    count = cancel_stale_orders()
    assert count >= 1
    awaiting_order.refresh_from_db()
    assert awaiting_order.status == Order.STATUS_CANCELLED


# ── 8. Regular pending still cancelled at 2 hours ────────────────────────────

@pytest.mark.django_db
def test_regular_pending_still_cancelled_at_2h(coach, active_plan):
    from django.utils import timezone

    order = baker.make(
        'purchase_app.Order',
        email='sandbox@example.com',
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        provider_ref=f'sandbox-{uuid.uuid4()}',
        full_name='Sandbox User',
    )
    Order.objects.filter(pk=order.pk).update(
        created_at=timezone.now() - timezone.timedelta(hours=3)
    )
    cancel_stale_orders()
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELLED


# ── 9. Staff can mark expired (cancelled) bank-transfer order as paid ─────────

@pytest.mark.django_db(transaction=True)
def test_staff_can_mark_expired_transfer_paid(awaiting_order):
    from django.utils import timezone

    Order.objects.filter(pk=awaiting_order.pk).update(
        status=Order.STATUS_CANCELLED,
        created_at=timezone.now() - timezone.timedelta(days=8),
    )
    awaiting_order.refresh_from_db()

    staff = baker.make('users_app.User', role='coach', is_active=True, is_staff=True)
    c = Client()
    c.force_login(staff)

    with patch('django_q.tasks.async_task'):
        resp = c.post(
            f'/panel/satin-al/siparisler/{awaiting_order.pk}/odeme-alindi/',
            follow=False,
        )

    assert resp.status_code == 302
    awaiting_order.refresh_from_db()
    assert awaiting_order.status == Order.STATUS_PAID


# ── 10. Claim: does not activate account ──────────────────────────────────────

@pytest.mark.django_db
def test_claim_does_not_activate_account(awaiting_order):
    from django.contrib.auth import get_user_model
    User = get_user_model()

    with patch('django_q.tasks.async_task'):
        resp = Client().post(
            f'/satin-al/havale/{awaiting_order.token}/bildir/',
            {'sender_name': 'Test User'},
        )

    assert resp.status_code == 302
    awaiting_order.refresh_from_db()
    assert awaiting_order.status == Order.STATUS_AWAITING_TRANSFER
    assert not User.objects.filter(email=awaiting_order.email).exists()


# ── 11. Claim: staff email sent exactly once for two presses ─────────────────

@pytest.mark.django_db
def test_claim_staff_email_sent_once(awaiting_order):
    c = Client()
    with patch('django_q.tasks.async_task') as mock_at:
        c.post(f'/satin-al/havale/{awaiting_order.token}/bildir/', {'sender_name': 'A'})
        c.post(f'/satin-al/havale/{awaiting_order.token}/bildir/', {'sender_name': 'B'})

    claimed_tasks = [
        call.args[0] for call in mock_at.call_args_list
        if call.args[0] == 'purchase_app.tasks.notify_staff_payment_claimed'
    ]
    assert len(claimed_tasks) == 1, 'notify_staff_payment_claimed must be called exactly once'


# ── 12. Claim: anonymous with valid token redirects (succeeds) ───────────────

@pytest.mark.django_db
def test_claim_valid_token_anonymous_succeeds(awaiting_order):
    with patch('django_q.tasks.async_task'):
        resp = Client().post(
            f'/satin-al/havale/{awaiting_order.token}/bildir/', {}
        )
    assert resp.status_code == 302


# ── 13. Claim: wrong token returns 404 ───────────────────────────────────────

@pytest.mark.django_db
def test_claim_wrong_token_returns_404(db):
    import uuid
    resp = Client().post(f'/satin-al/havale/{uuid.uuid4()}/bildir/', {})
    assert resp.status_code == 404


# ── 14. Claim: paid order silently ignored ────────────────────────────────────

@pytest.mark.django_db
def test_claim_after_paid_silently_ignored(awaiting_order):
    Order.objects.filter(pk=awaiting_order.pk).update(status=Order.STATUS_PAID)
    resp = Client().post(
        f'/satin-al/havale/{awaiting_order.token}/bildir/', {}
    )
    assert resp.status_code == 302
    awaiting_order.refresh_from_db()
    assert awaiting_order.status == Order.STATUS_PAID
    assert awaiting_order.payment_claimed_at is None


# ── 15. Claim: cancelled order silently ignored ───────────────────────────────

@pytest.mark.django_db
def test_claim_after_cancelled_silently_ignored(awaiting_order):
    Order.objects.filter(pk=awaiting_order.pk).update(status=Order.STATUS_CANCELLED)
    resp = Client().post(
        f'/satin-al/havale/{awaiting_order.token}/bildir/', {}
    )
    assert resp.status_code == 302
    awaiting_order.refresh_from_db()
    assert awaiting_order.status == Order.STATUS_CANCELLED
    assert awaiting_order.payment_claimed_at is None


# ── 16. Claim: sender_name stored, claimed_at set ────────────────────────────

@pytest.mark.django_db
def test_claim_sender_name_stored(awaiting_order):
    with patch('django_q.tasks.async_task'):
        Client().post(
            f'/satin-al/havale/{awaiting_order.token}/bildir/',
            {'sender_name': 'Ahmet Yılmaz'},
        )
    awaiting_order.refresh_from_db()
    assert awaiting_order.payment_sender_name == 'Ahmet Yılmaz'
    assert awaiting_order.payment_claimed_at is not None


# ── 17. Claimed orders excluded from stale-cancel (7-day rule) ───────────────

@pytest.mark.django_db
def test_claimed_excluded_from_7day_cancel(awaiting_order, settings):
    from django.utils import timezone

    settings.BANK_TRANSFER_EXPIRY_DAYS = 7
    Order.objects.filter(pk=awaiting_order.pk).update(
        created_at=timezone.now() - timezone.timedelta(days=8),
        payment_claimed_at=timezone.now() - timezone.timedelta(days=1),
    )
    cancel_stale_orders()
    awaiting_order.refresh_from_db()
    assert awaiting_order.status == Order.STATUS_AWAITING_TRANSFER, \
        'Claimed orders must not be auto-cancelled'


# ── 18. Panel: claimed badge appears ─────────────────────────────────────────

@pytest.mark.django_db
def test_panel_shows_claimed_badge(awaiting_order):
    from django.utils import timezone

    Order.objects.filter(pk=awaiting_order.pk).update(
        payment_claimed_at=timezone.now(),
    )
    staff = baker.make('users_app.User', role='coach', is_active=True, is_staff=True)
    c = Client()
    c.force_login(staff)
    resp = c.get('/panel/satin-al/siparisler/')
    assert resp.status_code == 200
    assert 'Ödeme Bildirildi'.encode() in resp.content


# ── 19. Panel: filter=claimed shows only claimed orders ──────────────────────

@pytest.mark.django_db
def test_panel_filter_claimed(awaiting_order, coach, active_plan):
    from django.utils import timezone

    unclaimed = baker.make(
        'purchase_app.Order',
        email='unclaimed@example.com',
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_AWAITING_TRANSFER,
        provider='bank_transfer',
        provider_ref='VG-UNCLMD',
        full_name='Unclaimed User',
    )
    Order.objects.filter(pk=awaiting_order.pk).update(
        payment_claimed_at=timezone.now(),
    )
    staff = baker.make('users_app.User', role='coach', is_active=True, is_staff=True)
    c = Client()
    c.force_login(staff)
    resp = c.get('/panel/satin-al/siparisler/?filter=claimed')
    assert resp.status_code == 200
    assert awaiting_order.email.encode() in resp.content
    assert unclaimed.email.encode() not in resp.content


# ── 20. Panel: search by ref code ────────────────────────────────────────────

@pytest.mark.django_db
def test_panel_search_by_ref(awaiting_order, coach, active_plan):
    other = baker.make(
        'purchase_app.Order',
        email='other@example.com',
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_AWAITING_TRANSFER,
        provider='bank_transfer',
        provider_ref='VG-OTHER1',
        full_name='Other User',
    )
    staff = baker.make('users_app.User', role='coach', is_active=True, is_staff=True)
    c = Client()
    c.force_login(staff)
    resp = c.get(f'/panel/satin-al/siparisler/?q={awaiting_order.provider_ref}')
    assert resp.status_code == 200
    assert awaiting_order.email.encode() in resp.content
    assert other.email.encode() not in resp.content


# ── 21. Ref code format and alphabet ─────────────────────────────────────────

def test_ref_code_format():
    from purchase_app.providers.bank_transfer import _REF_ALPHABET, _generate_ref
    for _ in range(30):
        ref = _generate_ref()
        assert ref.startswith('VG-'), f'Ref must start with VG-: {ref}'
        assert len(ref) == 9, f'Ref length must be 9: {ref}'
        code = ref[3:]
        for ch in code:
            assert ch in _REF_ALPHABET, f'Char {ch!r} not in alphabet'


def test_ref_code_alphabet_excludes_ambiguous():
    from purchase_app.providers.bank_transfer import _REF_ALPHABET
    for ch in ('O', 'I', 'L', '0', '1'):
        assert ch not in _REF_ALPHABET, f'Ambiguous char {ch!r} must be excluded'


# ── 22. Ref code collision causes retry ──────────────────────────────────────

@pytest.mark.django_db
def test_ref_code_collision_retry(coach, active_plan):
    import purchase_app.providers.bank_transfer as bt_module
    from purchase_app.providers.bank_transfer import BankTransferProvider

    baker.make(
        'purchase_app.Order',
        email='existing@example.com',
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_AWAITING_TRANSFER,
        provider='bank_transfer',
        provider_ref='VG-CLASH1',
        full_name='Existing',
    )
    new_order = baker.make(
        'purchase_app.Order',
        email='new@example.com',
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='bank_transfer',
        provider_ref=None,
        full_name='New',
    )
    refs = iter(['VG-CLASH1', 'VG-UNIQUE'])
    with patch.object(bt_module, '_generate_ref', side_effect=refs):
        with patch('django_q.tasks.async_task'):
            with patch('django.db.transaction.on_commit', side_effect=lambda f: f()):
                BankTransferProvider('TR33x', 'H', 'B').create_checkout(new_order)

    new_order.refresh_from_db()
    assert new_order.provider_ref == 'VG-UNIQUE'


# ── 23. No sequential order number on buyer-facing instructions page ──────────

@pytest.mark.django_db
def test_no_order_number_on_instructions_page(awaiting_order, bt_settings):
    resp = Client().get(f'/satin-al/havale/{awaiting_order.token}/')
    assert resp.status_code == 200
    # The old template had a visible "Sipariş #" label row; after removal it must not appear.
    # CSS color codes (e.g. #1e40af) won't be preceded by "Sipariş".
    assert 'Sipariş #'.encode('utf-8') not in resp.content, \
        '"Sipariş #" order-number label must not appear on the buyer-facing instructions page'


# ── 24. Instructions page shows confirmation when order is already claimed ────

@pytest.mark.django_db
def test_instructions_page_shows_claimed_confirmation(awaiting_order, bt_settings):
    from django.utils import timezone

    Order.objects.filter(pk=awaiting_order.pk).update(
        payment_claimed_at=timezone.now(),
    )
    resp = Client().get(f'/satin-al/havale/{awaiting_order.token}/')
    assert resp.status_code == 200
    assert 'Bildiriminiz'.encode() in resp.content
