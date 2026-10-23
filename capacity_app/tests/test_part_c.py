"""
Part C tests — at most 8 focused tests on the real database.

Run: python manage.py test capacity_app.tests.test_part_c --verbosity=2
"""
from datetime import date, timedelta

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from capacity_app.models import (
    CoachCapacityGrant, CoachCreditLedger, CoachStudentRenewalOrder,
)
from capacity_app.services import (
    credit_balance, generate_unique_ref, grant_credits, mark_renewal_order_paid,
    notify_expiring_student_periods,
)
from users_app.models import CoachStudent, Notification, User


# ── Helpers ───────────────────────────────────────────────────────────────────

def _coach(suffix):
    u = User.objects.create_user(
        email=f'coach_{suffix}@partc.test',
        full_name=f'Coach {suffix}',
        role='coach', password='pass123',
    )
    u.is_active = True; u.is_approved = True; u.is_staff = False
    u.save(update_fields=['is_active', 'is_approved', 'is_staff'])
    return u


def _staff(suffix):
    u = User.objects.create_user(
        email=f'staff_{suffix}@partc.test',
        full_name=f'Staff {suffix}',
        role='coach', password='pass123',
    )
    u.is_active = True; u.is_approved = True; u.is_staff = True
    u.save(update_fields=['is_active', 'is_approved', 'is_staff'])
    return u


def _student(suffix):
    u = User.objects.create_user(
        email=f'student_{suffix}@partc.test',
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


def _renewal_order(cs, claimed=False):
    import datetime
    order = CoachStudentRenewalOrder.objects.create(
        coach_student=cs,
        amount_kurus=10000,
        per_student_kurus=10000,
        ref_code=generate_unique_ref(),
    )
    if claimed:
        order.payment_claimed_at = datetime.datetime.now()
        order.save(update_fields=['payment_claimed_at'])
    return order


# ── Test 1: Staff renewal approval extends period; badge count matches ─────────

class TestStaffRenewalApproval(TestCase):

    @override_settings(COACH_PER_STUDENT_PERIODS=True)
    def test_1_approval_extends_period_once_badge_matches(self):
        """
        POST to renewal_mark_paid extends coach_student.next_payment_due by 30 days.
        A second POST is idempotent.  The badge count equals the claimed filter list count.
        """
        from users_app.panel_badges import qs_renewal_orders_claimed

        staff = _staff('rap')
        coach = _coach('rap')
        student = _student('rap')
        today = date.today()
        cs = _link(coach, student, npd=today + timedelta(days=5))
        order = _renewal_order(cs, claimed=True)

        # Badge count before approval: 1 claimed order
        self.assertEqual(qs_renewal_orders_claimed().count(), 1)

        c = Client()
        c.force_login(staff)
        url = reverse('capacity_panel:renewal_mark_paid', kwargs={'pk': order.pk})

        resp = c.post(url)
        self.assertEqual(resp.status_code, 302)

        order.refresh_from_db()
        cs.refresh_from_db()
        self.assertEqual(order.status, CoachStudentRenewalOrder.STATUS_PAID)
        # paid order leaves the claimed filter
        self.assertEqual(qs_renewal_orders_claimed().count(), 0)

        # Period was extended by 30 days from the current due date
        self.assertEqual(cs.next_payment_due, today + timedelta(days=5) + timedelta(days=30))

        # Second POST: idempotent — does not change the date again
        resp2 = c.post(url)
        self.assertEqual(resp2.status_code, 302)
        cs.refresh_from_db()
        self.assertEqual(cs.next_payment_due, today + timedelta(days=5) + timedelta(days=30))


# ── Test 2: Ledger forms record rows with notes; reject empty notes ────────────

class TestLedgerForms(TestCase):

    @override_settings(COACH_PER_STUDENT_PERIODS=True)
    def test_2_grant_and_adjust_forms(self):
        """
        grant form: creates +N ledger row with notes; empty notes rejected.
        adjust form: creates signed delta row with notes; empty notes rejected.
        """
        staff = _staff('lf')
        coach = _coach('lf')

        c = Client()
        c.force_login(staff)
        url = reverse('capacity_panel:coach_credits', kwargs={'coach_pk': coach.pk})

        # Grant with notes → creates row + notification
        resp = c.post(url, {'action': 'grant', 'n': '3', 'notes': 'test grant'})
        self.assertEqual(resp.status_code, 302)
        entry = CoachCreditLedger.objects.get(coach=coach, reason=CoachCreditLedger.REASON_MANUAL_GRANT)
        self.assertEqual(entry.delta, 3)
        self.assertEqual(entry.notes, 'test grant')
        self.assertTrue(Notification.objects.filter(user=coach, title='Davet hakkı tanımlandı').exists())

        # Grant with empty notes → 200 (form re-rendered with error, no new row)
        CoachCreditLedger.objects.filter(coach=coach).delete()
        resp2 = c.post(url, {'action': 'grant', 'n': '1', 'notes': ''})
        self.assertEqual(resp2.status_code, 200)
        self.assertFalse(CoachCreditLedger.objects.filter(coach=coach).exists())

        # Adjust with notes → creates signed row
        resp3 = c.post(url, {'action': 'adjust', 'delta': '-2', 'notes': 'correction'})
        self.assertEqual(resp3.status_code, 302)
        adj = CoachCreditLedger.objects.get(coach=coach, reason=CoachCreditLedger.REASON_STAFF_ADJUSTMENT)
        self.assertEqual(adj.delta, -2)
        self.assertEqual(adj.notes, 'correction')

        # Adjust with empty notes → error
        CoachCreditLedger.objects.filter(coach=coach).delete()
        resp4 = c.post(url, {'action': 'adjust', 'delta': '1', 'notes': ''})
        self.assertEqual(resp4.status_code, 200)
        self.assertFalse(CoachCreditLedger.objects.filter(coach=coach).exists())


# ── Test 3: Set-student-period writes the ledger row ──────────────────────────

class TestSetStudentPeriod(TestCase):

    @override_settings(COACH_PER_STUDENT_PERIODS=True)
    def test_3_set_period_writes_ledger_row(self):
        """
        POST action=set_period updates next_payment_due and writes a delta=0 ledger row.
        """
        staff = _staff('sp')
        coach = _coach('sp')
        student = _student('sp')
        today = date.today()
        cs = _link(coach, student, source='coach', npd=today + timedelta(days=10))

        new_date = today + timedelta(days=30)

        c = Client()
        c.force_login(staff)
        url = reverse('capacity_panel:coach_credits', kwargs={'coach_pk': coach.pk})
        resp = c.post(url, {
            'action':           'set_period',
            'coach_student_id': str(cs.pk),
            'new_end_date':     new_date.isoformat(),
            'notes':            'test period adjustment',
        })
        self.assertEqual(resp.status_code, 302)

        cs.refresh_from_db()
        self.assertEqual(cs.next_payment_due, new_date)

        entry = CoachCreditLedger.objects.get(
            coach=coach, reason=CoachCreditLedger.REASON_STAFF_ADJUSTMENT, delta=0
        )
        self.assertIn(new_date.isoformat(), entry.notes)
        self.assertIn('test period adjustment', entry.notes)


# ── Test 4: Reminder fires once, not twice, nothing when flag=False ────────────

class TestReminderTask(TestCase):

    def test_4_reminder_idempotent_and_flag_gated(self):
        """
        notify_expiring_student_periods():
        - flag=True, own student with due=today+5 → 1 notification
        - second call → 0 new (idempotent)
        - flag=False → 0 notifications for a fresh link
        """
        today = date.today()
        target = today + timedelta(days=5)

        coach_a = _coach('rem_a')
        student_a = _student('rem_a')
        _link(coach_a, student_a, source='coach', npd=target)

        with override_settings(COACH_PER_STUDENT_PERIODS=True):
            count1 = notify_expiring_student_periods()
            self.assertEqual(count1, 1)
            n = Notification.objects.filter(user=coach_a, title='Öğrenci süresi bitiyor').count()
            self.assertEqual(n, 1)

            # Second run — idempotent
            count2 = notify_expiring_student_periods()
            self.assertEqual(count2, 0)
            self.assertEqual(
                Notification.objects.filter(user=coach_a, title='Öğrenci süresi bitiyor').count(), 1
            )

        # Flag=False: should not fire
        coach_b = _coach('rem_b')
        student_b = _student('rem_b')
        _link(coach_b, student_b, source='coach', npd=target)

        with override_settings(COACH_PER_STUDENT_PERIODS=False):
            count3 = notify_expiring_student_periods()
            self.assertEqual(count3, 0)
            self.assertFalse(
                Notification.objects.filter(user=coach_b, title='Öğrenci süresi bitiyor').exists()
            )


# ── Test 5: Bootstrap re-run does not reset next_run ──────────────────────────

class TestBootstrapRerun(TestCase):

    def test_5_bootstrap_does_not_reset_next_run(self):
        """
        Running bootstrap_scheduled_tasks twice must not reset next_run on
        the notify_expiring_student_periods_task schedule.
        """
        from django_q.models import Schedule
        from django.utils import timezone
        from django.core.management import call_command

        call_command('bootstrap_scheduled_tasks', verbosity=0)

        func = 'capacity_app.tasks.notify_expiring_student_periods_task'
        sched = Schedule.objects.get(func=func)

        sentinel = timezone.now() + timedelta(days=99)
        sched.next_run = sentinel
        sched.save(update_fields=['next_run'])

        call_command('bootstrap_scheduled_tasks', verbosity=0)

        sched.refresh_from_db()
        self.assertEqual(sched.next_run, sentinel)


# ── Test 6: Activation command ───────────────────────────────────────────────

class TestActivationCommand(TestCase):

    def setUp(self):
        from capacity_app.models import CapacitySettings
        CapacitySettings.objects.update_or_create(pk=1, defaults={'per_slot_price_kurus': 10000})

    def test_6_dry_run_apply_idempotent_vagus_untouched(self):
        """
        dry run: nothing written.
        apply: own links get next_payment_due, active grants convert to credits once.
        second apply: no-op.
        vagus links: untouched.
        """
        from io import StringIO
        from django.core.management import call_command

        today = date.today()
        coach = _coach('act')
        student_own = _student('act_own')
        student_vagus = _student('act_vagus')

        cs_own = _link(coach, student_own, source='coach', npd=None)
        cs_vagus = _link(coach, student_vagus, source='vagus', npd=None)

        # Active grant with 3 slots; in_use own = 1 → unused = 2
        grant = CoachCapacityGrant.objects.create(
            coach=coach, slots=3,
            period_start=today - timedelta(days=5),
            period_end=today + timedelta(days=25),
        )

        # Dry run
        out = StringIO()
        call_command('activate_per_student_periods', stdout=out, verbosity=0)
        cs_own.refresh_from_db()
        cs_vagus.refresh_from_db()
        self.assertIsNone(cs_own.next_payment_due)
        self.assertIsNone(cs_vagus.next_payment_due)
        self.assertFalse(CoachCreditLedger.objects.filter(coach=coach).exists())

        # Apply
        call_command('activate_per_student_periods', '--apply', stdout=StringIO(), verbosity=0)
        cs_own.refresh_from_db()
        cs_vagus.refresh_from_db()

        # Own link gets date
        self.assertEqual(cs_own.next_payment_due, today + timedelta(days=30))
        # Vagus link untouched
        self.assertIsNone(cs_vagus.next_payment_due)

        # Grant converted: unused = 3 - 1 = 2 credits
        entry = CoachCreditLedger.objects.get(
            coach=coach, reason=CoachCreditLedger.REASON_CONVERTED_FROM_GRANT
        )
        self.assertEqual(entry.delta, 2)
        self.assertIn(f'grant_id:{grant.pk}', entry.notes)

        # Audit row for transition
        self.assertTrue(CoachCreditLedger.objects.filter(
            coach=coach, reason=CoachCreditLedger.REASON_TRANSITION_FIRST_PERIOD
        ).exists())

        # Second apply: nothing changes
        before_count = CoachCreditLedger.objects.filter(coach=coach).count()
        call_command('activate_per_student_periods', '--apply', stdout=StringIO(), verbosity=0)
        after_count = CoachCreditLedger.objects.filter(coach=coach).count()
        self.assertEqual(before_count, after_count)

        cs_own.refresh_from_db()
        self.assertEqual(cs_own.next_payment_due, today + timedelta(days=30))


# ── Test 7: Flag=False: staff nav and screens unchanged ──────────────────────

class TestFlagFalseNav(TestCase):

    @override_settings(COACH_PER_STUDENT_PERIODS=False)
    def test_7_flag_false_nav_unchanged(self):
        """
        With COACH_PER_STUDENT_PERIODS=False, the capacity nav item says 'Kontenjan',
        no 'Yenileme' link appears, and the overview page still renders slot columns.
        """
        from users_app.templatetags.panel_nav_tags import _build_nav_groups
        groups = _build_nav_groups(per_student=False)
        koclar = next(g for g in groups if g['key'] == 'koclar')
        keys = [p['key'] for p in koclar['pages']]
        labels = [p['label'] for p in koclar['pages']]

        self.assertIn('capacity', keys)
        self.assertNotIn('renewals', keys)
        self.assertIn('Kontenjan', labels)
        self.assertNotIn('Davet Hakkı', labels)

        # The overview renders without credit columns
        staff = _staff('nav')
        c = Client()
        c.force_login(staff)
        resp = c.get(reverse('capacity_panel:overview'))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('Kontenjan', content)
        self.assertNotIn('Davet Hakkı', content)


# ── Test 8: Guarded endpoints return 403 for expired own student ──────────────

class TestExpiredEndpointGuard(TestCase):
    """
    Endpoint guard table (all already guarded — no new guards added):

    App             | URL name                      | View function              | Guard?
    ----------------+-------------------------------+----------------------------+-------
    exams_app       | coach:assign_task             | assign_task                | YES
    exams_app       | coach:complete_task           | coach_complete_task        | YES
    exams_app       | coach:task_action             | coach_task_action          | YES
    exams_app       | coach:brans_task_assign       | coach_brans_task_assign    | YES
    exams_app       | coach:brans_task_action       | coach_brans_task_action    | YES
    exams_app       | coach:student_brans_create    | coach_brans_create_for_student | YES
    konu_takip_app  | konu_takip:coach_toggle       | CoachToggleView            | YES
    konu_takip_app  | konu_takip:coach_review       | CoachReviewView            | YES
    konu_takip_app  | konu_takip:coach_toggle_sr    | CoachToggleSrView          | YES
    tasks_app       | tasks:api-gorevler (create)   | GorevView                  | YES
    tasks_app       | tasks:api-gorev-detail (update/delete) | GorevDetailView  | YES
    tasks_app       | tasks:api-gorev-copy          | GorevCopyView              | YES
    tasks_app       | tasks:api-gorev-reorder       | GorevReorderView           | YES
    """

    @override_settings(COACH_PER_STUDENT_PERIODS=True)
    def test_8_assign_task_403_for_expired_own_student(self):
        """
        assign_task returns 403 when the student's period has expired.
        """
        import json
        from exams_app.models import Subject, Topic

        coach = _coach('ep')
        student = _student('ep')
        coach.is_approved = True
        coach.save(update_fields=['is_approved'])
        today = date.today()

        # Expired own student
        _link(coach, student, source='coach', npd=today - timedelta(days=1))

        # Create a minimal topic to reference
        subject = Subject.objects.create(name='Test Subject', exam_type='TYT')
        topic = Topic.objects.create(subject=subject, name='Test Topic')

        c = Client()
        c.force_login(coach)
        url = reverse('coach:assign_task')
        payload = json.dumps({'topic_id': topic.pk, 'student_id': student.pk})
        resp = c.post(url, data=payload, content_type='application/json')
        self.assertEqual(resp.status_code, 403)
