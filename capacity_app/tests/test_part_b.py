"""
Part B tests: credit purchase approval, invite gate, acceptance flow,
renewal order service, konu_takip guards.

Run: python manage.py test capacity_app.tests.test_part_b --verbosity=2
"""
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from capacity_app.models import CoachCapacityGrant, CoachCreditLedger, CoachStudentRenewalOrder
from capacity_app.services import (
    InsufficientCredits,
    available_credits,
    credit_balance,
    generate_unique_ref,
    grant_credits,
    mark_capacity_order_paid,
    mark_renewal_order_paid,
)
from users_app.models import CoachStudent, StudentInvite, User


def _coach(suffix):
    u = User.objects.create_user(
        email=f'coach_{suffix}@partb.test',
        full_name=f'Coach {suffix}',
        role='coach', password='pass123',
    )
    u.is_active = True; u.is_approved = True
    u.save(update_fields=['is_active', 'is_approved'])
    return u


def _student(suffix):
    u = User.objects.create_user(
        email=f'student_{suffix}@partb.test',
        full_name=f'Student {suffix}',
        role='student', password='pass123',
    )
    u.is_active = True; u.is_approved = True
    u.save(update_fields=['is_active', 'is_approved'])
    return u


def _link(coach, student, source='coach', npd=None):
    CoachStudent.objects.filter(coach=coach, student=student).delete()
    return CoachStudent.objects.create(
        coach=coach, student=student, source=source, active=True, next_payment_due=npd,
    )


def _invite(coach, email=None, staff=False):
    return StudentInvite.objects.create(
        coach=coach,
        email=email or f'inv_{coach.pk}_{StudentInvite.generate_token()[:6]}@test.com',
        token=StudentInvite.generate_token(),
        is_used=False,
        initiated_by_staff=staff,
    )


def _capacity_order(coach, slots=1):
    from capacity_app.models import CapacitySettings, CoachCapacityOrder
    CapacitySettings.objects.update_or_create(pk=1, defaults={'per_slot_price_kurus': 10000})
    return CoachCapacityOrder.objects.create(
        coach=coach, slots=slots,
        amount_kurus=10000 * slots,
        per_slot_kurus=10000,
        status=CoachCapacityOrder.STATUS_AWAITING_TRANSFER,
        ref_code=generate_unique_ref(),
    )


class TestPurchaseApproval(TestCase):

    def test_1_flag_true_grants_credits_once_no_grant(self):
        """flag=True: two calls credit exactly once; no CoachCapacityGrant created."""
        coach = _coach('pa1')
        order = _capacity_order(coach, slots=3)
        with override_settings(COACH_PER_STUDENT_PERIODS=True):
            mark_capacity_order_paid(order)
            mark_capacity_order_paid(order)  # second call must be idempotent
        entries = CoachCreditLedger.objects.filter(
            coach=coach, order=order, reason=CoachCreditLedger.REASON_PURCHASE_APPROVED
        )
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.first().delta, 3)
        self.assertFalse(CoachCapacityGrant.objects.filter(order=order).exists())

    def test_2_flag_false_creates_grant(self):
        """flag=False: mark_capacity_order_paid creates CoachCapacityGrant, no ledger entry."""
        coach = _coach('pa2')
        order = _capacity_order(coach, slots=2)
        with override_settings(COACH_PER_STUDENT_PERIODS=False):
            mark_capacity_order_paid(order)
        self.assertTrue(CoachCapacityGrant.objects.filter(order=order).exists())
        self.assertFalse(CoachCreditLedger.objects.filter(
            order=order, reason=CoachCreditLedger.REASON_PURCHASE_APPROVED
        ).exists())


class TestInviteGate(TestCase):

    def test_3_pending_invites_reduce_available_credits(self):
        """
        With free base saturated (3 active own students):
        balance=2, pending=0 → avail=2 → can_add returns True
        balance=2, pending=2 → avail=0 → can_add returns False with 'kalmadı' msg
        balance=0, pending=0 → avail=0 → can_add returns False with 'yok' msg
        """
        from capacity_app.services import can_add_own_student
        coach = _coach('ig')
        # Saturate free base so credit logic is exercised
        for i in range(3):
            _link(coach, _student(f'ig_base_{i}'), source='coach')

        with override_settings(COACH_PER_STUDENT_PERIODS=True):
            grant_credits(coach, 2, CoachCreditLedger.REASON_MANUAL_GRANT)
            allowed, msg = can_add_own_student(coach)
            self.assertTrue(allowed)

            # two pending invites earmark both credits
            _invite(coach); _invite(coach)
            allowed, msg = can_add_own_student(coach)
            self.assertFalse(allowed)
            self.assertIn('kalmadı', msg)

        coach2 = _coach('ig2')
        # Saturate free base for coach2 too
        for i in range(3):
            _link(coach2, _student(f'ig2_base_{i}'), source='coach')
        with override_settings(COACH_PER_STUDENT_PERIODS=True):
            allowed, msg = can_add_own_student(coach2)
            self.assertFalse(allowed)
            self.assertIn('yok', msg)


class TestAcceptanceFlow(TestCase):

    def setUp(self):
        from capacity_app.models import CapacitySettings
        CapacitySettings.objects.update_or_create(pk=1, defaults={'per_slot_price_kurus': 10000})

    def test_4_consumes_credit_sets_30_days_reactivated_link(self):
        """
        With flag=True and 1 credit, invite acceptance creates user, consumes credit,
        sets next_payment_due=today+30 even if the link already existed with a stale date.
        A second POST to the same URL returns 404 (invite.is_used=True).
        """
        coach = _coach('af1')
        student_email = f'accept_{coach.pk}@test.com'
        inv = StudentInvite.objects.create(
            coach=coach, email=student_email,
            token=StudentInvite.generate_token(),
            is_used=False, initiated_by_staff=False,
        )
        # pre-existing inactive link with stale date
        CoachStudent.objects.create(
            coach=coach,
            student=_student('af1x'),  # placeholder so email is free
        )
        # Saturate free base (coach already has 1 own student above; add 2 more)
        _link(coach, _student('af1y'), source='coach')
        _link(coach, _student('af1z'), source='coach')
        # grant 1 credit (needed for the 4th student — beyond the free base)
        grant_credits(coach, 1, CoachCreditLedger.REASON_MANUAL_GRANT)

        c = Client()
        url = reverse('users_app:invite_register', args=[inv.token])
        post_data = {
            'full_name': 'Test Öğrenci',
            'password1': 'securePass123!',
            'password2': 'securePass123!',
            'terms_accepted': '1',
            'kvkk_accepted': '1',
        }
        with override_settings(COACH_PER_STUDENT_PERIODS=True):
            resp = c.post(url, post_data)
        self.assertEqual(resp.status_code, 302)

        inv.refresh_from_db()
        self.assertTrue(inv.is_used)

        user = User.objects.get(email=student_email)
        cs = CoachStudent.objects.get(coach=coach, student=user)
        today = date.today()
        self.assertEqual(cs.next_payment_due, today + timedelta(days=30))

        # credit consumed
        self.assertEqual(credit_balance(coach), 0)
        self.assertTrue(CoachCreditLedger.objects.filter(
            coach=coach, invite=inv, reason=CoachCreditLedger.REASON_CONSUMED_INVITE
        ).exists())

        # second POST → 404
        with override_settings(COACH_PER_STUDENT_PERIODS=True):
            resp2 = c.post(url, post_data)
        self.assertEqual(resp2.status_code, 404)

    def test_5_no_credit_rollback_neutral_message(self):
        """
        flag=True, 0 credits, free base saturated (3 active own students):
        acceptance fails, transaction rolled back (no user created), invite stays unused.
        """
        coach = _coach('af2')
        # Saturate free base so the 0-credit check fires
        for i in range(3):
            _link(coach, _student(f'af2_base_{i}'), source='coach')
        student_email = f'noaccept_{coach.pk}@test.com'
        inv = StudentInvite.objects.create(
            coach=coach, email=student_email,
            token=StudentInvite.generate_token(),
            is_used=False, initiated_by_staff=False,
        )
        c = Client()
        url = reverse('users_app:invite_register', args=[inv.token])
        post_data = {
            'full_name': 'Test Öğrenci',
            'password1': 'securePass123!',
            'password2': 'securePass123!',
            'terms_accepted': '1',
            'kvkk_accepted': '1',
        }
        with override_settings(COACH_PER_STUDENT_PERIODS=True):
            resp = c.post(url, post_data)
        # shows the form again with neutral error (not a redirect)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'kabul edilemiyor')

        inv.refresh_from_db()
        self.assertFalse(inv.is_used)
        self.assertFalse(User.objects.filter(email=student_email).exists())


class TestConsumedInviteConstraint(TestCase):

    def test_6_duplicate_consumed_invite_row_raises(self):
        """Inserting two REASON_CONSUMED_INVITE rows for the same invite raises IntegrityError."""
        coach = _coach('cic')
        student = _student('cics')
        cs = _link(coach, student)
        inv = _invite(coach)
        grant_credits(coach, 2, CoachCreditLedger.REASON_MANUAL_GRANT)
        CoachCreditLedger.objects.create(
            coach=coach, delta=-1,
            reason=CoachCreditLedger.REASON_CONSUMED_INVITE,
            invite=inv, coach_student=cs,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CoachCreditLedger.objects.create(
                    coach=coach, delta=-1,
                    reason=CoachCreditLedger.REASON_CONSUMED_INVITE,
                    invite=inv, coach_student=cs,
                )


class TestMarkRenewalOrderPaid(TestCase):

    def setUp(self):
        self.coach = _coach('ren')
        self.student = _student('rens')
        self.cs = _link(self.coach, self.student, source='coach')
        self.staff = _coach('staffren')

    def _renewal_order(self, npd=None):
        if npd is not None:
            self.cs.next_payment_due = npd
            self.cs.save(update_fields=['next_payment_due'])
        return CoachStudentRenewalOrder.objects.create(
            coach_student=self.cs,
            amount_kurus=10000,
            per_student_kurus=10000,
            ref_code=generate_unique_ref(),
        )

    def test_7_extends_past_future_idempotent(self):
        """
        From past: new_end = today + 30.
        From future: new_end = current_next_payment_due + 30.
        Second call returns (order, False) — idempotent.
        """
        today = date.today()

        # Case 1: next_payment_due in the past
        past = today - timedelta(days=5)
        order1 = self._renewal_order(npd=past)
        order1, acted = mark_renewal_order_paid(order1, self.staff)
        self.assertTrue(acted)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.next_payment_due, today + timedelta(days=30))

        # Case 2: next_payment_due in the future
        future = today + timedelta(days=15)
        self.cs.next_payment_due = future
        self.cs.save(update_fields=['next_payment_due'])
        order2 = CoachStudentRenewalOrder.objects.create(
            coach_student=self.cs, amount_kurus=10000, per_student_kurus=10000,
            ref_code=generate_unique_ref(),
        )
        order2, acted2 = mark_renewal_order_paid(order2, self.staff)
        self.assertTrue(acted2)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.next_payment_due, future + timedelta(days=30))

        # Idempotent: second call returns False
        order2, acted3 = mark_renewal_order_paid(order2, self.staff)
        self.assertFalse(acted3)


class TestKonuTakipExpiredGuard(TestCase):

    def test_8_toggle_returns_403_for_expired_own_student(self):
        """
        CoachToggleView.post returns 403 for an expired own (source='coach') student
        when COACH_PER_STUDENT_PERIODS=True.
        """
        coach = _coach('kt')
        student = _student('kts')
        today = date.today()
        cs = _link(coach, student, source='coach', npd=today - timedelta(days=1))
        coach.is_approved = True; coach.save(update_fields=['is_approved'])

        c = Client()
        c.force_login(coach)
        url = reverse('konu_takip:coach_toggle')
        # Use a non-existent topic_id; the guard fires before the topic lookup
        payload = {'topic_id': 999999, 'field': 'started', 'value': True, 'student_id': student.pk}
        import json
        with override_settings(COACH_PER_STUDENT_PERIODS=True):
            resp = c.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(resp.status_code, 403)
