"""
SR opt-in default tests.
Run: python manage.py test konu_takip_app.test_sr_default --verbosity=2

Policy under test
-----------------
  No row (untouched subject) -> SR OFF (opt-in; absence means False)
  Existing row sr_enabled=True -> unchanged, still True
  Existing row sr_enabled=False -> unchanged, still False
  First toggle on a no-row subject -> creates row with True (turns ON)
"""
from django.test import TestCase

from exams_app.models import Subject
from konu_takip_app.models import KonuTakipTopic, StudentSubjectSrSetting, StudentTopicProgress
from konu_takip_app.services import get_all_reviews_json, get_subject_sr_settings, toggle_subject_sr
from users_app.models import User


def _make_student(email='sr_test@test.com'):
    u = User.objects.create_user(email=email, full_name='SR Test', role='student', password='X')
    u.is_active = True
    u.is_approved = True
    u.save(update_fields=['is_active', 'is_approved'])
    return u


def _make_subject(name='Matematik'):
    return Subject.objects.filter(name=name).first() or Subject.objects.create(
        name=name, exam_type='TYT'
    )


class SrOptInDefaultTests(TestCase):

    def setUp(self):
        self.student = _make_student()
        self.subject = _make_subject()

    # ── Test 1: no row -> SR OFF (fallback is now False) ─────────────────────

    def test_1_no_row_resolves_to_false(self):
        print('\n' + '='*60)
        print('TEST 1: NO ROW -> SR OFF (absence means False)')
        print('='*60)

        # Confirm no row exists for this student+subject
        row_exists = StudentSubjectSrSetting.objects.filter(
            student=self.student, subject=self.subject
        ).exists()
        print(f'  Row exists before test       : {row_exists}  (must be False)')
        self.assertFalse(row_exists, 'precondition: no row must exist')

        # get_subject_sr_settings returns empty dict for this student
        settings_map = get_subject_sr_settings(self.student)
        fallback = settings_map.get(self.subject.id, False)

        print(f'  settings_map for subject     : {settings_map.get(self.subject.id, "<absent>")}  (must be absent)')
        print(f'  Fallback value               : {fallback}  (must be False)')

        self.assertNotIn(self.subject.id, settings_map,
                         'no row means the subject is absent from the settings dict')
        self.assertFalse(fallback, 'absent subject must resolve to False (opt-in)')

    # ── Test 2: no row -> get_all_reviews_json excludes that subject ──────────

    def test_2_no_row_excludes_subject_from_reviews(self):
        print('\n' + '='*60)
        print('TEST 2: NO ROW -> SUBJECT EXCLUDED FROM TEKRAR TAKVIMİ')
        print('='*60)

        # Create a topic and finished progress entry with a pending review
        topic = KonuTakipTopic.objects.create(
            subject=self.subject, name='Test Konusu', order=1, checkable=True
        )
        from django.utils import timezone
        from datetime import timedelta
        StudentTopicProgress.objects.create(
            topic=topic,
            student=self.student,
            finished=True,
            review_count=1,
            next_review_at=timezone.now() - timedelta(days=1),  # overdue
        )

        reviews = get_all_reviews_json(self.student)
        subject_ids_in_reviews = {r['subject_id'] for r in reviews}

        print(f'  Review entries returned      : {len(reviews)}  (must be 0)')
        print(f'  Subject in reviews           : {self.subject.id in subject_ids_in_reviews}  (must be False)')

        self.assertEqual(len(reviews), 0,
                         'no-row subject must produce zero review entries')
        self.assertNotIn(self.subject.id, subject_ids_in_reviews,
                         'subject with no SR row must not appear in Tekrar Takvimi')

    # ── Test 3: existing row sr_enabled=True -> unchanged, still on ──────────

    def test_3_existing_true_row_unaffected(self):
        print('\n' + '='*60)
        print('TEST 3: EXISTING ROW sr_enabled=True -> UNCHANGED')
        print('='*60)

        # Simulate a row that was explicitly set True (e.g. toggled OFF then ON)
        StudentSubjectSrSetting.objects.create(
            student=self.student, subject=self.subject, sr_enabled=True
        )

        settings_map = get_subject_sr_settings(self.student)
        value = settings_map.get(self.subject.id)

        print(f'  sr_enabled value from DB     : {value}  (must be True)')
        self.assertTrue(value, 'existing True row must remain True — untouched by this change')

        # And its review entries ARE included
        topic = KonuTakipTopic.objects.create(
            subject=self.subject, name='Degismeyen Konu', order=1, checkable=True
        )
        from django.utils import timezone
        from datetime import timedelta
        StudentTopicProgress.objects.create(
            topic=topic,
            student=self.student,
            finished=True,
            review_count=1,
            next_review_at=timezone.now() - timedelta(days=1),
        )
        reviews = get_all_reviews_json(self.student)
        print(f'  Review entry present         : {len(reviews) == 1}  (must be True)')
        self.assertEqual(len(reviews), 1,
                         'subject with existing True row must appear in Tekrar Takvimi')

    # ── Test 4: existing row sr_enabled=False -> unchanged, still off ─────────

    def test_4_existing_false_row_unaffected(self):
        print('\n' + '='*60)
        print('TEST 4: EXISTING ROW sr_enabled=False -> UNCHANGED')
        print('='*60)

        StudentSubjectSrSetting.objects.create(
            student=self.student, subject=self.subject, sr_enabled=False
        )

        settings_map = get_subject_sr_settings(self.student)
        value = settings_map.get(self.subject.id)

        print(f'  sr_enabled value from DB     : {value}  (must be False)')
        self.assertFalse(value, 'existing False row must remain False — untouched')

    # ── Test 5: first toggle on a no-row subject -> creates True (turns ON) ───

    def test_5_first_toggle_creates_true(self):
        print('\n' + '='*60)
        print('TEST 5: FIRST TOGGLE ON NO-ROW SUBJECT -> CREATES TRUE (opt-in)')
        print('='*60)

        row_before = StudentSubjectSrSetting.objects.filter(
            student=self.student, subject=self.subject
        ).first()
        print(f'  Row before toggle            : {row_before}  (must be None)')
        self.assertIsNone(row_before, 'precondition: no row exists before first toggle')

        new_value = toggle_subject_sr(self.student, self.subject.id)

        row_after = StudentSubjectSrSetting.objects.get(
            student=self.student, subject=self.subject
        )
        print(f'  Return value of toggle       : {new_value}  (must be True)')
        print(f'  Row sr_enabled in DB         : {row_after.sr_enabled}  (must be True)')

        self.assertTrue(new_value, 'first toggle must return True (turning SR on)')
        self.assertTrue(row_after.sr_enabled, 'DB row must be True after first toggle')

    # ── Test 6: second toggle -> False (turns OFF) ────────────────────────────

    def test_6_second_toggle_creates_false(self):
        print('\n' + '='*60)
        print('TEST 6: SECOND TOGGLE -> False (turns OFF)')
        print('='*60)

        toggle_subject_sr(self.student, self.subject.id)   # ON
        new_value = toggle_subject_sr(self.student, self.subject.id)  # OFF

        row = StudentSubjectSrSetting.objects.get(student=self.student, subject=self.subject)
        print(f'  Return value of 2nd toggle   : {new_value}  (must be False)')
        print(f'  Row sr_enabled in DB         : {row.sr_enabled}  (must be False)')

        self.assertFalse(new_value, 'second toggle must return False (turning SR off)')
        self.assertFalse(row.sr_enabled, 'DB row must be False after second toggle')
