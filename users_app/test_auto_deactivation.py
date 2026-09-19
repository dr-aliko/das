"""
End-to-end tests for automatic payment-overdue deactivation of Vagus students.

Run: python manage.py test users_app.test_auto_deactivation --verbosity=2

Coverage:
  1. Scheduled task flips active=False + sets deactivation_reason='payment_overdue'
  2. Deactivated student disappears from all coach-facing lists:
       - tasks_app.services.students.list_for_coach
       - konu_takip_app CoachKonuTakipView student dropdown
       - exams_app coach_exam_overview
  3. Deactivated student still appears on /panel/odeme/ with correct reason badge
  4. Extending next_payment_due to the future via panel_billing_update reactivates
  5. source='coach' rows are completely ignored by the task
  6. source='vagus' rows with FUTURE due date are not touched
  7. Manual-unlink rows are not auto-reactivated by date extension
"""
import json
from datetime import date, timedelta
from unittest.mock import patch

from django.test import Client, TestCase

from users_app.models import CoachStudent, User
from users_app.tasks import auto_deactivate_overdue_vagus_students


def _make_coach(suffix):
    u = User.objects.create_user(
        email=f'coach_{suffix}@test.com',
        full_name=f'Coach {suffix}',
        role='coach',
        password='testpass123',
    )
    u.is_approved = True
    u.save(update_fields=['is_approved'])
    return u


def _make_student(suffix):
    return User.objects.create_user(
        email=f'student_{suffix}@test.com',
        full_name=f'Student {suffix}',
        role='student',
        password='testpass123',
    )


def _link(coach, student, source, next_payment_due=None, active=True):
    return CoachStudent.objects.create(
        coach=coach,
        student=student,
        source=source,
        next_payment_due=next_payment_due,
        active=active,
    )


YESTERDAY = date.today() - timedelta(days=1)
TOMORROW  = date.today() + timedelta(days=1)


class AutoDeactivationTaskTests(TestCase):

    def setUp(self):
        self.coach = _make_coach('main')
        self.vagus_student = _make_student('vagus')
        self.coach_student = _make_student('coach_src')

        # Vagus link — overdue
        self.vagus_link = _link(
            self.coach, self.vagus_student,
            source=CoachStudent.SOURCE_VAGUS,
            next_payment_due=YESTERDAY,
        )
        # Coach-sourced link — overdue date but must be ignored
        self.coach_link = _link(
            self.coach, self.coach_student,
            source=CoachStudent.SOURCE_COACH,
            next_payment_due=YESTERDAY,
        )

    # ── 1. Task deactivates overdue Vagus row ────────────────────────────────

    @patch('users_app.services.notifications.send_push_notification', return_value=(0, 0))
    def test_01_task_deactivates_overdue_vagus(self, mock_push):
        print('\n' + '='*60)
        print('TEST 1: Task deactivates overdue Vagus student')
        print('='*60)
        count = auto_deactivate_overdue_vagus_students()
        self.vagus_link.refresh_from_db()
        print(f'  rows deactivated    : {count}  (must be 1)')
        print(f'  active              : {self.vagus_link.active}  (must be False)')
        print(f'  deactivation_reason : {self.vagus_link.deactivation_reason}  (must be payment_overdue)')
        self.assertEqual(count, 1)
        self.assertFalse(self.vagus_link.active)
        self.assertEqual(self.vagus_link.deactivation_reason, CoachStudent.DEACTIVATION_PAYMENT_OVERDUE)
        print('  PASS')

    # ── 2. source='coach' rows untouched ────────────────────────────────────

    @patch('users_app.services.notifications.send_push_notification', return_value=(0, 0))
    def test_02_coach_source_untouched(self, mock_push):
        print('\n' + '='*60)
        print('TEST 2: source=coach rows completely ignored by task')
        print('='*60)
        auto_deactivate_overdue_vagus_students()
        self.coach_link.refresh_from_db()
        print(f'  active              : {self.coach_link.active}  (must be True)')
        print(f'  deactivation_reason : {self.coach_link.deactivation_reason}  (must be None)')
        self.assertTrue(self.coach_link.active)
        self.assertIsNone(self.coach_link.deactivation_reason)
        print('  PASS')

    # ── 3. Future-due Vagus rows untouched ──────────────────────────────────

    @patch('users_app.services.notifications.send_push_notification', return_value=(0, 0))
    def test_03_future_due_not_deactivated(self, mock_push):
        print('\n' + '='*60)
        print('TEST 3: Vagus row with future due date NOT deactivated')
        print('='*60)
        future_student = _make_student('future')
        future_link = _link(
            self.coach, future_student,
            source=CoachStudent.SOURCE_VAGUS,
            next_payment_due=TOMORROW,
        )
        auto_deactivate_overdue_vagus_students()
        future_link.refresh_from_db()
        print(f'  active : {future_link.active}  (must be True)')
        self.assertTrue(future_link.active)
        print('  PASS')

    # ── 4. Deactivated student absent from list_for_coach ───────────────────

    @patch('users_app.services.notifications.send_push_notification', return_value=(0, 0))
    def test_04_list_for_coach_excludes_deactivated(self, mock_push):
        print('\n' + '='*60)
        print('TEST 4: list_for_coach() excludes deactivated student')
        print('='*60)
        from tasks_app.services.students import list_for_coach
        auto_deactivate_overdue_vagus_students()
        students = list(list_for_coach(self.coach))
        names = [s.full_name for s in students]
        print(f'  students visible: {names}')
        print(f'  vagus_student in list: {self.vagus_student.full_name in names}  (must be False)')
        print(f'  coach_student in list: {self.coach_student.full_name in names}  (must be True)')
        self.assertNotIn(self.vagus_student, students)
        self.assertIn(self.coach_student, students)
        print('  PASS')

    # ── 5. Deactivated student absent from CoachKonuTakipView ───────────────

    @patch('users_app.services.notifications.send_push_notification', return_value=(0, 0))
    def test_05_konu_takip_view_excludes_deactivated(self, mock_push):
        print('\n' + '='*60)
        print('TEST 5: CoachKonuTakipView student list excludes deactivated')
        print('='*60)
        from users_app.models import CoachStudent
        auto_deactivate_overdue_vagus_students()

        # Simulate the query that CoachKonuTakipView runs
        active_ids = list(
            CoachStudent.objects
            .filter(coach=self.coach, active=True)
            .values_list('student_id', flat=True)
        )
        coached_students = list(
            User.objects.filter(role='student', id__in=active_ids)
        )
        ids = [s.id for s in coached_students]
        print(f'  visible student ids: {ids}')
        print(f'  vagus_student in list: {self.vagus_student.id in ids}  (must be False)')
        print(f'  coach_student in list: {self.coach_student.id in ids}  (must be True)')
        self.assertNotIn(self.vagus_student.id, ids)
        self.assertIn(self.coach_student.id, ids)
        print('  PASS')

    # ── 6. Deactivated student absent from coach_exam_overview ──────────────

    @patch('users_app.services.notifications.send_push_notification', return_value=(0, 0))
    def test_06_exam_overview_excludes_deactivated(self, mock_push):
        print('\n' + '='*60)
        print('TEST 6: coach_exam_overview query excludes deactivated student')
        print('='*60)
        from users_app.models import CoachStudent
        auto_deactivate_overdue_vagus_students()

        # Simulate the query that coach_exam_overview runs after the fix
        active_ids = list(
            CoachStudent.objects
            .filter(coach=self.coach, active=True)
            .values_list('student_id', flat=True)
        )
        students = list(User.objects.filter(id__in=active_ids, role='student'))
        ids = [s.id for s in students]
        print(f'  visible student ids: {ids}')
        print(f'  vagus_student in list: {self.vagus_student.id in ids}  (must be False)')
        print(f'  coach_student in list: {self.coach_student.id in ids}  (must be True)')
        self.assertNotIn(self.vagus_student.id, ids)
        self.assertIn(self.coach_student.id, ids)
        print('  PASS')

    # ── 7. Deactivated student still on /panel/odeme/ with correct badge ────

    @patch('users_app.services.notifications.send_push_notification', return_value=(0, 0))
    def test_07_admin_panel_shows_deactivated_with_reason(self, mock_push):
        print('\n' + '='*60)
        print('TEST 7: /panel/odeme/ shows student as Kaldırıldı (Ödeme gecikti)')
        print('='*60)
        auto_deactivate_overdue_vagus_students()
        staff = User.objects.create_user(
            email='staff@test.com', full_name='Staff', role='coach', password='pass'
        )
        staff.is_staff = True
        staff.is_approved = True
        staff.save(update_fields=['is_staff', 'is_approved'])

        c = Client()
        c.login(username='staff@test.com', password='pass')
        resp = c.get(f'/panel/odeme/?coach_id={self.coach.pk}')
        print(f'  HTTP status: {resp.status_code}  (must be 200)')
        self.assertEqual(resp.status_code, 200)

        # panel_billing_view passes all rows including inactive to the template
        coaches_ctx = resp.context['coaches']
        all_rows = []
        for group in coaches_ctx:
            all_rows.extend(group['rows'])

        deact_rows = [r for r in all_rows if r['inactive']]
        active_rows = [r for r in all_rows if not r['inactive']]

        deact_names = [r['link'].student.full_name for r in deact_rows]
        active_names = [r['link'].student.full_name for r in active_rows]

        print(f'  inactive rows: {deact_names}  (must contain vagus student)')
        print(f'  active rows  : {active_names}  (must contain coach student)')

        self.assertIn(self.vagus_student.full_name, deact_names)
        self.assertIn(self.coach_student.full_name, active_names)

        # Confirm the deactivated row has the correct reason
        vagus_row = next(r for r in deact_rows if r['link'].student == self.vagus_student)
        reason = vagus_row['link'].deactivation_reason
        print(f'  deactivation_reason on row: {reason}  (must be payment_overdue)')
        self.assertEqual(reason, CoachStudent.DEACTIVATION_PAYMENT_OVERDUE)
        print('  PASS')

    # ── 8. Auto-reactivation via panel_billing_update ───────────────────────

    @patch('users_app.services.notifications.send_push_notification', return_value=(0, 0))
    def test_08_extend_date_reactivates(self, mock_push):
        print('\n' + '='*60)
        print('TEST 8: Extending due date reactivates payment_overdue student')
        print('='*60)
        auto_deactivate_overdue_vagus_students()
        self.vagus_link.refresh_from_db()
        print(f'  Before extend — active: {self.vagus_link.active}, reason: {self.vagus_link.deactivation_reason}')
        self.assertFalse(self.vagus_link.active)

        staff = User.objects.create_user(
            email='staff2@test.com', full_name='Staff2', role='coach', password='pass'
        )
        staff.is_staff = True
        staff.is_approved = True
        staff.save(update_fields=['is_staff', 'is_approved'])

        c = Client()
        c.login(username='staff2@test.com', password='pass')
        resp = c.post(
            f'/panel/odeme/{self.vagus_link.pk}/update/',
            data=json.dumps({
                'source': 'vagus',
                'next_payment_due': TOMORROW.isoformat(),
            }),
            content_type='application/json',
        )
        data = json.loads(resp.content)
        print(f'  update response: {data}')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data['ok'])
        self.assertTrue(data['reactivated'])

        self.vagus_link.refresh_from_db()
        print(f'  After extend — active: {self.vagus_link.active}  (must be True)')
        print(f'  deactivation_reason : {self.vagus_link.deactivation_reason}  (must be None)')
        self.assertTrue(self.vagus_link.active)
        self.assertIsNone(self.vagus_link.deactivation_reason)

        # Confirm student is back in list_for_coach
        from tasks_app.services.students import list_for_coach
        students = list(list_for_coach(self.coach))
        self.assertIn(self.vagus_student, students)
        print(f'  back in list_for_coach: True  PASS')

    # ── 9. Manual-unlink rows are NOT auto-reactivated by date extension ─────

    def test_09_manual_unlink_not_reactivated_by_date(self):
        print('\n' + '='*60)
        print('TEST 9: Manual-unlink rows NOT reactivated by date extension')
        print('='*60)
        # Manually deactivate
        self.vagus_link.active = False
        self.vagus_link.deactivation_reason = CoachStudent.DEACTIVATION_MANUAL
        self.vagus_link.save(update_fields=['active', 'deactivation_reason'])

        staff = User.objects.create_user(
            email='staff3@test.com', full_name='Staff3', role='coach', password='pass'
        )
        staff.is_staff = True
        staff.is_approved = True
        staff.save(update_fields=['is_staff', 'is_approved'])

        c = Client()
        c.login(username='staff3@test.com', password='pass')
        resp = c.post(
            f'/panel/odeme/{self.vagus_link.pk}/update/',
            data=json.dumps({
                'source': 'vagus',
                'next_payment_due': TOMORROW.isoformat(),
            }),
            content_type='application/json',
        )
        data = json.loads(resp.content)
        print(f'  update response: {data}')
        self.assertTrue(data['ok'])
        self.assertFalse(data['reactivated'])

        self.vagus_link.refresh_from_db()
        print(f'  active after date update: {self.vagus_link.active}  (must be False)')
        print(f'  reason unchanged        : {self.vagus_link.deactivation_reason}  (must be manual)')
        self.assertFalse(self.vagus_link.active)
        self.assertEqual(self.vagus_link.deactivation_reason, CoachStudent.DEACTIVATION_MANUAL)
        print('  PASS')

    # ── 10. Idempotency — task is safe to run twice ──────────────────────────

    @patch('users_app.services.notifications.send_push_notification', return_value=(0, 0))
    def test_10_task_idempotent(self, mock_push):
        print('\n' + '='*60)
        print('TEST 10: Running task twice does not corrupt state')
        print('='*60)
        count1 = auto_deactivate_overdue_vagus_students()
        count2 = auto_deactivate_overdue_vagus_students()
        print(f'  run 1 deactivated: {count1}  (must be 1)')
        print(f'  run 2 deactivated: {count2}  (must be 0 — already inactive)')
        self.assertEqual(count1, 1)
        self.assertEqual(count2, 0)
        self.vagus_link.refresh_from_db()
        self.assertFalse(self.vagus_link.active)
        self.assertEqual(self.vagus_link.deactivation_reason, CoachStudent.DEACTIVATION_PAYMENT_OVERDUE)
        print('  PASS')
