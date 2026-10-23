"""
Tests for the per-student period credit ledger and flag-gated expiry helpers.

Run: python manage.py test capacity_app.tests.test_credit_ledger --verbosity=2

Coverage:
  1. credit_balance sums mixed positive and negative deltas correctly
  2. consume_credit_for_invite is idempotent: same invite returns same entry, no duplicate
  3. consume on zero balance raises InsufficientCredits and writes nothing to the ledger
  4. two sequential consumes with only one credit — second raises InsufficientCredits
  5. expiry helpers: own student flag on (past/future/no-date) and off, Vagus unchanged
  6. CoachStudentRenewalOrder: at most one awaiting_transfer renewal per coach_student
"""
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from capacity_app.models import CoachCreditLedger, CoachStudentRenewalOrder
from capacity_app.services import (
    InsufficientCredits,
    consume_credit_for_invite,
    credit_balance,
    generate_unique_ref,
    grant_credits,
)
from users_app.models import CoachStudent, StudentInvite, User


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_user(suffix, role):
    u = User.objects.create_user(
        email=f'{role}_{suffix}@ledger.com',
        full_name=f'{role.capitalize()} {suffix}',
        role=role,
        password='testpass123',
    )
    u.is_active = True
    if role == 'coach':
        u.is_approved = True
    u.save(update_fields=['is_active', 'is_approved'] if role == 'coach' else ['is_active'])
    return u


def _link(coach, student, source='coach', next_payment_due=None):
    CoachStudent.objects.filter(coach=coach, student=student).delete()
    return CoachStudent.objects.create(
        coach=coach, student=student,
        source=source, active=True, next_payment_due=next_payment_due,
    )


def _invite(coach, suffix=''):
    return StudentInvite.objects.create(
        coach=coach,
        email=f'inv{suffix}_{coach.pk}@ledger.com',
        token=StudentInvite.generate_token(),
        is_used=False,
        initiated_by_staff=False,
    )


# ── Test 1 ────────────────────────────────────────────────────────────────────

class LedgerBalanceTest(TestCase):

    def test_01_balance_sums_mixed_deltas(self):
        """credit_balance aggregates all delta rows: 3 + (-1) + 2 = 4."""
        coach = _make_user('bal', 'coach')
        CoachCreditLedger.objects.create(
            coach=coach, delta=3, reason=CoachCreditLedger.REASON_MANUAL_GRANT)
        CoachCreditLedger.objects.create(
            coach=coach, delta=-1, reason=CoachCreditLedger.REASON_CONSUMED_INVITE)
        CoachCreditLedger.objects.create(
            coach=coach, delta=2, reason=CoachCreditLedger.REASON_PURCHASE_APPROVED)
        self.assertEqual(credit_balance(coach), 4)
        # unrelated coach must not bleed into the result
        other = _make_user('bal2', 'coach')
        CoachCreditLedger.objects.create(
            coach=other, delta=99, reason=CoachCreditLedger.REASON_MANUAL_GRANT)
        self.assertEqual(credit_balance(coach), 4)


# ── Tests 2-4 ─────────────────────────────────────────────────────────────────

class ConsumeTest(TestCase):

    def setUp(self):
        self.coach   = _make_user('con', 'coach')
        self.student = _make_user('cons', 'student')
        self.cs      = _link(self.coach, self.student)
        self.inv     = _invite(self.coach)

    def test_02_consume_idempotent_returns_same_entry(self):
        """Consuming the same invite twice returns the existing entry; no duplicate created."""
        grant_credits(self.coach, 2, CoachCreditLedger.REASON_MANUAL_GRANT)
        e1 = consume_credit_for_invite(self.coach, self.inv, self.cs)
        e2 = consume_credit_for_invite(self.coach, self.inv, self.cs)
        self.assertEqual(e1.pk, e2.pk)
        self.assertEqual(
            CoachCreditLedger.objects.filter(
                invite=self.inv, reason=CoachCreditLedger.REASON_CONSUMED_INVITE,
            ).count(),
            1,
        )

    def test_03_consume_zero_balance_raises_writes_nothing(self):
        """consume on zero balance raises InsufficientCredits; ledger row count unchanged."""
        before = CoachCreditLedger.objects.filter(coach=self.coach).count()
        with self.assertRaises(InsufficientCredits):
            consume_credit_for_invite(self.coach, self.inv, self.cs)
        self.assertEqual(
            CoachCreditLedger.objects.filter(coach=self.coach).count(), before
        )

    def test_04_two_invites_one_credit_second_raises(self):
        """With balance=1, first consume succeeds; a second (different) invite raises."""
        grant_credits(self.coach, 1, CoachCreditLedger.REASON_MANUAL_GRANT)
        inv2 = _invite(self.coach, '2')
        consume_credit_for_invite(self.coach, self.inv, self.cs)
        with self.assertRaises(InsufficientCredits):
            consume_credit_for_invite(self.coach, inv2, self.cs)
        self.assertEqual(
            CoachCreditLedger.objects.filter(
                coach=self.coach, reason=CoachCreditLedger.REASON_CONSUMED_INVITE,
            ).count(),
            1,
        )


# ── Test 5 ────────────────────────────────────────────────────────────────────

class ExpiryHelperTest(TestCase):

    def setUp(self):
        self.coach   = _make_user('exh', 'coach')
        self.student = _make_user('exhs', 'student')

    def _cs(self, source='coach', npd=None):
        return _link(self.coach, self.student, source=source, next_payment_due=npd)

    def test_05_flag_gated_expiry_for_own_and_vagus(self):
        """
        Flag ON: own student (source='coach') with past date → expired badge and helper True;
                 own student with future date → non-expired badge and helper False;
                 own student with no date → no badge and helper False;
                 Vagus student with past date → expired (flag has no effect on Vagus).
        Flag OFF: own student with past date → no badge and helper False (original behaviour).
                  Vagus student with past date → still expired (original behaviour unchanged).
        """
        from users_app.utils import is_student_program_expired, membership_expiry_info

        today  = date.today()
        past   = today - timedelta(days=5)
        future = today + timedelta(days=15)

        with override_settings(COACH_PER_STUDENT_PERIODS=True):
            # own + past → expired badge + helper returns True
            cs = self._cs('coach', past)
            info = membership_expiry_info(cs)
            self.assertIsNotNone(info)
            self.assertTrue(info['expired'])
            self.assertTrue(is_student_program_expired(self.coach, self.student.pk))

            # own + future → non-expired badge + helper returns False
            cs = self._cs('coach', future)
            info = membership_expiry_info(cs)
            self.assertIsNotNone(info)
            self.assertFalse(info['expired'])
            self.assertFalse(is_student_program_expired(self.coach, self.student.pk))

            # own + no date → no badge + helper returns False
            cs = self._cs('coach', None)
            self.assertIsNone(membership_expiry_info(cs))
            self.assertFalse(is_student_program_expired(self.coach, self.student.pk))

            # vagus + past → expired regardless of flag value
            cs = self._cs('vagus', past)
            info = membership_expiry_info(cs)
            self.assertIsNotNone(info)
            self.assertTrue(info['expired'])
            self.assertTrue(is_student_program_expired(self.coach, self.student.pk))

        with override_settings(COACH_PER_STUDENT_PERIODS=False):
            # flag OFF: own + past → no badge, not expired (original behaviour unchanged)
            cs = self._cs('coach', past)
            self.assertIsNone(membership_expiry_info(cs))
            self.assertFalse(is_student_program_expired(self.coach, self.student.pk))

            # flag OFF: vagus + past → still expired (original behaviour unchanged)
            cs = self._cs('vagus', past)
            info = membership_expiry_info(cs)
            self.assertIsNotNone(info)
            self.assertTrue(info['expired'])
            self.assertTrue(is_student_program_expired(self.coach, self.student.pk))


# ── Test 6 ────────────────────────────────────────────────────────────────────

class RenewalOrderConstraintTest(TestCase):

    def setUp(self):
        self.coach   = _make_user('ren', 'coach')
        self.student = _make_user('rens', 'student')
        self.cs      = _link(self.coach, self.student)

    def test_06_at_most_one_open_renewal_per_coach_student(self):
        """A second awaiting_transfer renewal for the same link must raise IntegrityError."""
        CoachStudentRenewalOrder.objects.create(
            coach_student=self.cs,
            amount_kurus=10000,
            per_student_kurus=10000,
            status=CoachStudentRenewalOrder.STATUS_AWAITING_TRANSFER,
            ref_code=generate_unique_ref(),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CoachStudentRenewalOrder.objects.create(
                    coach_student=self.cs,
                    amount_kurus=10000,
                    per_student_kurus=10000,
                    status=CoachStudentRenewalOrder.STATUS_AWAITING_TRANSFER,
                    ref_code=generate_unique_ref(),
                )
        # Paid renewal may coexist with the open one — constraint is status-conditional
        CoachStudentRenewalOrder.objects.create(
            coach_student=self.cs,
            amount_kurus=10000,
            per_student_kurus=10000,
            status=CoachStudentRenewalOrder.STATUS_PAID,
            ref_code=generate_unique_ref(),
        )
        self.assertEqual(
            CoachStudentRenewalOrder.objects.filter(
                coach_student=self.cs,
                status=CoachStudentRenewalOrder.STATUS_AWAITING_TRANSFER,
            ).count(),
            1,
        )
