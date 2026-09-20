"""
Tests for the Zorlandığım Sorular (struggle questions) feature.

Run: python manage.py test struggle_app --verbosity=2

Coverage:
  1.  apply_sm2 extraction — intervals identical to original _compute_review
  2.  Create question → immediately due
  3.  Review with kolay / orta / zor → correct intervals from apply_sm2
  4.  AYT subject filtering respects student's alan
  5.  Image upload saves to MEDIA_ROOT at the correct path, URL accessible
  6.  Coach stats: correct aggregates, no image/individual data
  7.  Ownership: student cannot see another student's questions
  8.  Delete removes the question
  9.  Topic dropdown API returns only checkable leaf topics
  10. Invalid image (wrong MIME / too large) is rejected
"""
import io
import os

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.utils import timezone

from exams_app.models import Subject
from konu_takip_app.models import KonuTakipTopic
from konu_takip_app.sr_utils import apply_sm2
from struggle_app.models import StudentStruggleQuestion
from users_app.models import CoachStudent, User


# ── Test helpers ──────────────────────────────────────────────────────────────

def _make_student(suffix, alan='SAY'):
    u = User.objects.create_user(
        email=f'student_{suffix}@test.com',
        full_name=f'Student {suffix}',
        role='student',
        password='testpass123',
    )
    u.alan = alan
    u.is_active = True
    u.save(update_fields=['alan', 'is_active'])
    return u


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


def _make_subject(name, exam_type='TYT'):
    return Subject.objects.filter(name=name).first() or Subject.objects.create(
        name=name, exam_type=exam_type
    )


def _tiny_png():
    """Return a minimal valid PNG as bytes (1×1 white pixel)."""
    import base64
    b64 = (
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk'
        'YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
    )
    return base64.b64decode(b64)


def _png_upload(name='test.png'):
    return SimpleUploadedFile(name, _tiny_png(), content_type='image/png')


def _create_question(student, subject, topic=None, **kwargs):
    defaults = dict(
        question_image=_png_upload(),
        next_review_at=timezone.now(),
        current_interval_days=1,
        ease_factor=2.5,
        review_count=0,
    )
    defaults.update(kwargs)
    return StudentStruggleQuestion.objects.create(
        student=student, subject=subject, topic=topic, **defaults
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class ApplySm2ExtractionTests(TestCase):
    """Verify apply_sm2 produces byte-identical results to the original inline logic."""

    def _original(self, review_count, current_interval_days, ease_factor, quality):
        """Inline replica of the original _compute_review logic for comparison."""
        rc = review_count
        ef = ease_factor
        if rc == 0:
            interval = {'kolay': 10, 'orta': 6, 'zor': 3}[quality]
        elif rc == 1:
            interval = {'kolay': 21, 'orta': 14, 'zor': 4}[quality]
        else:
            if quality == 'kolay':
                interval = round(current_interval_days * ef)
                ef = min(2.2, ef + 0.15)
            elif quality == 'orta':
                interval = round(current_interval_days * ef * 0.85)
            else:
                interval = max(3, round(current_interval_days * 0.4))
                ef = max(1.3, ef - 0.20)
        return interval, ef

    def _check(self, rc, interval, ef, quality):
        expected_interval, expected_ef = self._original(rc, interval, ef, quality)
        got_interval, got_ef = apply_sm2(rc, interval, ef, quality)
        self.assertEqual(got_interval, expected_interval,
            f'apply_sm2({rc},{interval},{ef},{quality!r}): interval {got_interval} != {expected_interval}')
        self.assertAlmostEqual(got_ef, expected_ef, places=10,
            msg=f'apply_sm2({rc},{interval},{ef},{quality!r}): ease {got_ef} != {expected_ef}')

    def test_01_rc0_all_qualities(self):
        print('\n' + '='*60)
        print('TEST 1: apply_sm2 rc=0 — all qualities match original')
        print('='*60)
        for q in ('kolay', 'orta', 'zor'):
            self._check(0, 1, 2.5, q)
            print(f'  rc=0 quality={q}: interval={apply_sm2(0,1,2.5,q)[0]}  PASS')

    def test_02_rc1_all_qualities(self):
        print('\n' + '='*60)
        print('TEST 2: apply_sm2 rc=1 — all qualities match original')
        print('='*60)
        for q in ('kolay', 'orta', 'zor'):
            self._check(1, 10, 2.5, q)
            print(f'  rc=1 quality={q}: interval={apply_sm2(1,10,2.5,q)[0]}  PASS')

    def test_03_rc2_plus(self):
        print('\n' + '='*60)
        print('TEST 3: apply_sm2 rc>=2 — ease-factor formula matches original')
        print('='*60)
        for q in ('kolay', 'orta', 'zor'):
            self._check(2, 14, 2.5, q)
            interval, ef = apply_sm2(2, 14, 2.5, q)
            print(f'  rc=2 quality={q}: interval={interval}, ease={ef:.4f}  PASS')

    def test_04_ease_floor_and_ceiling(self):
        print('\n' + '='*60)
        print('TEST 4: ease-factor floor (1.3) and ceiling (2.2) respected')
        print('='*60)
        # Repeated zor drives ef to floor
        _, ef = apply_sm2(5, 10, 1.31, 'zor')
        self.assertGreaterEqual(ef, 1.3)
        print(f'  zor near floor: ef={ef:.4f} >= 1.3  PASS')
        # Repeated kolay at ceiling
        _, ef = apply_sm2(5, 10, 2.19, 'kolay')
        self.assertLessEqual(ef, 2.2)
        print(f'  kolay near ceiling: ef={ef:.4f} <= 2.2  PASS')


class StruggleQuestionLifecycleTests(TestCase):

    def setUp(self):
        self.student = _make_student('lifecycle')
        self.subject = _make_subject('TYT Matematik')

    def test_05_new_question_immediately_due(self):
        print('\n' + '='*60)
        print('TEST 5: New question is immediately due (next_review_at <= now)')
        print('='*60)
        q = _create_question(self.student, self.subject)
        self.assertIsNotNone(q.next_review_at)
        self.assertLessEqual(q.next_review_at, timezone.now())
        print(f'  next_review_at: {q.next_review_at}  PASS')

    def test_06_review_kolay(self):
        print('\n' + '='*60)
        print('TEST 6: Review with kolay (rc=0) -> interval=10 days')
        print('='*60)
        from struggle_app.services import submit_struggle_review
        q = _create_question(self.student, self.subject)
        result = submit_struggle_review(self.student, q.id, 'kolay')
        self.assertIsNotNone(result)
        self.assertEqual(result.review_count, 1)
        self.assertEqual(result.current_interval_days, 10)
        print(f'  interval={result.current_interval_days} review_count={result.review_count}  PASS')

    def test_07_review_orta(self):
        print('\n' + '='*60)
        print('TEST 7: Review with orta (rc=0) -> interval=6 days')
        print('='*60)
        from struggle_app.services import submit_struggle_review
        q = _create_question(self.student, self.subject)
        result = submit_struggle_review(self.student, q.id, 'orta')
        self.assertEqual(result.current_interval_days, 6)
        print(f'  interval={result.current_interval_days}  PASS')

    def test_08_review_zor(self):
        print('\n' + '='*60)
        print('TEST 8: Review with zor (rc=0) -> interval=3 days')
        print('='*60)
        from struggle_app.services import submit_struggle_review
        q = _create_question(self.student, self.subject)
        result = submit_struggle_review(self.student, q.id, 'zor')
        self.assertEqual(result.current_interval_days, 3)
        print(f'  interval={result.current_interval_days}  PASS')

    def test_09_review_sequence_rc2(self):
        print('\n' + '='*60)
        print('TEST 9: Review sequence - rc=2 uses ease-factor formula')
        print('='*60)
        from struggle_app.services import submit_struggle_review
        q = _create_question(self.student, self.subject)
        # rc=0 -> kolay: interval=10, ef unchanged (2.5)
        submit_struggle_review(self.student, q.id, 'kolay')
        # rc=1 -> kolay: interval=21, ef unchanged (2.5)
        submit_struggle_review(self.student, q.id, 'kolay')
        # rc=2 -> kolay: interval=round(21*2.5)=52, ef=min(2.2,2.5+0.15)=2.2
        submit_struggle_review(self.student, q.id, 'kolay')
        q.refresh_from_db()
        expected_interval, expected_ef = apply_sm2(2, 21, 2.5, 'kolay')
        print(f'  expected: interval={expected_interval} ease={expected_ef:.4f}')
        print(f'  got:      interval={q.current_interval_days} ease={q.ease_factor:.4f}')
        self.assertEqual(q.current_interval_days, expected_interval)
        self.assertAlmostEqual(q.ease_factor, expected_ef, places=10)
        print(f'  PASS')


class AytAlanFilterTests(TestCase):

    def setUp(self):
        # Create a subject that only SAY students should see
        self.say_subject = _make_subject('AYT Fizik', exam_type='AYT')
        # Create a topic so _subject_groups picks up the subject (konu_takip_topics__isnull=False)
        KonuTakipTopic.objects.create(
            subject=self.say_subject, name='Test Konu', order=1, checkable=True
        )

    def test_10_say_sees_fizik(self):
        print('\n' + '='*60)
        print('TEST 10: SAY student sees AYT Fizik')
        print('='*60)
        from konu_takip_app.alan_utils import subject_groups
        student = _make_student('say', alan='SAY')
        _, ayt = subject_groups(student)
        names = [s.name for s in ayt]
        print(f'  AYT subjects visible: {names}')
        self.assertIn('AYT Fizik', names)
        print('  PASS')

    def test_11_ea_does_not_see_fizik(self):
        print('\n' + '='*60)
        print('TEST 11: EA student does NOT see AYT Fizik')
        print('='*60)
        from konu_takip_app.alan_utils import subject_groups
        student = _make_student('ea', alan='EA')
        _, ayt = subject_groups(student)
        names = [s.name for s in ayt]
        print(f'  AYT subjects visible: {names}')
        self.assertNotIn('AYT Fizik', names)
        print('  PASS')


class ImageUploadTests(TestCase):

    def setUp(self):
        self.student = _make_student('imgtest')
        self.subject = _make_subject('TYT Kimya')
        self.client  = Client()
        self.client.login(username='student_imgtest@test.com', password='testpass123')

    def tearDown(self):
        # Clean up any uploaded files created during tests
        for q in StudentStruggleQuestion.objects.filter(student=self.student):
            if q.question_image:
                try:
                    q.question_image.delete(save=False)
                except Exception:
                    pass
            if q.solution_image:
                try:
                    q.solution_image.delete(save=False)
                except Exception:
                    pass

    def test_12_upload_saves_to_media_root(self):
        print('\n' + '='*60)
        print('TEST 12: Upload saves question image to MEDIA_ROOT/struggle/questions/')
        print('='*60)
        resp = self.client.post('/student/konu-takip/sorularim/add/', {
            'subject_id': self.subject.id,
            'question_image': _png_upload('q_test.png'),
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'], data)

        q = StudentStruggleQuestion.objects.get(id=data['question']['id'])
        full_path = settings.MEDIA_ROOT / q.question_image.name
        print(f'  saved to: {full_path}')
        self.assertTrue(os.path.exists(full_path), f'File not found: {full_path}')
        self.assertTrue(q.question_image.name.startswith('struggle/questions/'))
        print(f'  URL: {q.question_image.url}')
        self.assertTrue(q.question_image.url.startswith('/media/struggle/questions/'))
        print('  PASS')

    def test_13_invalid_mime_rejected(self):
        print('\n' + '='*60)
        print('TEST 13: Non-image MIME type rejected')
        print('='*60)
        bad_file = SimpleUploadedFile('malware.exe', b'MZ\x90\x00', content_type='application/octet-stream')
        resp = self.client.post('/student/konu-takip/sorularim/add/', {
            'subject_id': self.subject.id,
            'question_image': bad_file,
        })
        data = resp.json()
        self.assertFalse(data['ok'])
        print(f'  error: {data["error"]}  PASS')

    def test_14_oversized_image_rejected(self):
        print('\n' + '='*60)
        print('TEST 14: Image > 5 MB rejected')
        print('='*60)
        big = SimpleUploadedFile('big.png', b'X' * (5 * 1024 * 1024 + 1), content_type='image/png')
        resp = self.client.post('/student/konu-takip/sorularim/add/', {
            'subject_id': self.subject.id,
            'question_image': big,
        })
        data = resp.json()
        self.assertFalse(data['ok'])
        print(f'  error: {data["error"]}  PASS')


class CoachStatsTests(TestCase):

    def setUp(self):
        self.coach   = _make_coach('stats')
        self.student = _make_student('stats')
        CoachStudent.objects.create(coach=self.coach, student=self.student,
                                    source='vagus', active=True)
        self.subject = _make_subject('TYT Biyoloji')
        # Create 3 questions: 2 due, 1 not yet due
        _create_question(self.student, self.subject)
        _create_question(self.student, self.subject)
        future_q = _create_question(self.student, self.subject)
        from datetime import timedelta
        future_q.next_review_at = timezone.now() + timedelta(days=7)
        future_q.save(update_fields=['next_review_at'])

    def test_15_coach_stats_correct_counts(self):
        print('\n' + '='*60)
        print('TEST 15: Coach stats returns correct total and due counts')
        print('='*60)
        from struggle_app.views import coach_struggle_stats
        stats = coach_struggle_stats(self.coach, self.student)
        self.assertEqual(len(stats), 1)
        row = stats[0]
        print(f'  subject: {row["subject__name"]}, total: {row["total"]}, due: {row["due"]}')
        self.assertEqual(row['total'], 3)
        self.assertEqual(row['due'], 2)
        # Confirm no image URLs or individual data in the response
        self.assertNotIn('question_image_url', row)
        self.assertNotIn('id', row)
        print('  PASS')


class OwnershipTests(TestCase):

    def setUp(self):
        self.student_a = _make_student('owner_a')
        self.student_b = _make_student('owner_b')
        self.subject   = _make_subject('TYT Fizik')
        self.q_a = _create_question(self.student_a, self.subject)
        self.client = Client()

    def test_16_student_cannot_delete_other_students_question(self):
        print('\n' + '='*60)
        print('TEST 16: Student B cannot delete Student A\'s question')
        print('='*60)
        self.client.login(username='student_owner_b@test.com', password='testpass123')
        resp = self.client.post(f'/student/konu-takip/sorularim/{self.q_a.id}/delete/')
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(StudentStruggleQuestion.objects.filter(pk=self.q_a.pk).exists())
        print(f'  status={resp.status_code}  question still exists: True  PASS')

    def test_17_student_cannot_review_other_students_question(self):
        print('\n' + '='*60)
        print('TEST 17: Student B cannot submit review for Student A\'s question')
        print('='*60)
        import json as _json
        self.client.login(username='student_owner_b@test.com', password='testpass123')
        resp = self.client.post(
            '/student/konu-takip/sorularim/review/',
            data=_json.dumps({'question_id': self.q_a.id, 'quality': 'kolay'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        print(f'  status={resp.status_code} (400 = not found/forbidden)  PASS')

    def test_18_student_index_shows_only_own_questions(self):
        print('\n' + '='*60)
        print('TEST 18: Student index page only returns their own questions')
        print('='*60)
        _create_question(self.student_b, self.subject)
        self.client.login(username='student_owner_a@test.com', password='testpass123')
        resp = self.client.get('/student/konu-takip/sorularim/')
        self.assertEqual(resp.status_code, 200)
        # due_json should only contain student_a's question
        import json as _json
        due = _json.loads(resp.context['due_json'])
        all_q = _json.loads(resp.context['all_json'])
        ids = [q['id'] for q in all_q]
        print(f'  question ids in response: {ids}  (should only be {self.q_a.id})')
        self.assertIn(self.q_a.id, ids)
        self.assertEqual(len(ids), 1)
        print('  PASS')


class TopicsApiTests(TestCase):

    def setUp(self):
        self.student = _make_student('topics_api')
        self.subject = _make_subject('TYT Tarih')
        # Leaf topics
        self.leaf1 = KonuTakipTopic.objects.create(
            subject=self.subject, name='Osmanlı', order=1, checkable=True
        )
        self.leaf2 = KonuTakipTopic.objects.create(
            subject=self.subject, name='Cumhuriyet', order=2, checkable=True
        )
        # Category header (non-checkable) — should NOT appear
        self.header = KonuTakipTopic.objects.create(
            subject=self.subject, name='Genel Kültür', order=0, checkable=False
        )
        self.client = Client()
        self.client.login(username='student_topics_api@test.com', password='testpass123')

    def test_19_topics_api_returns_only_leaf(self):
        print('\n' + '='*60)
        print('TEST 19: Topics API returns only checkable leaf topics')
        print('='*60)
        resp = self.client.get(f'/student/konu-takip/sorularim/topics/?subject_id={self.subject.id}')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        names = [t['name'] for t in data['topics']]
        print(f'  topics returned: {names}')
        self.assertIn('Osmanlı', names)
        self.assertIn('Cumhuriyet', names)
        self.assertNotIn('Genel Kültür', names)
        print('  PASS')


class DeleteTests(TestCase):

    def setUp(self):
        self.student = _make_student('del')
        self.subject = _make_subject('TYT Coğrafya')
        self.client  = Client()
        self.client.login(username='student_del@test.com', password='testpass123')

    def test_20_delete_removes_question(self):
        print('\n' + '='*60)
        print('TEST 20: Delete removes question from DB')
        print('='*60)
        q = _create_question(self.student, self.subject)
        qid = q.id
        resp = self.client.post(f'/student/konu-takip/sorularim/{qid}/delete/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])
        self.assertFalse(StudentStruggleQuestion.objects.filter(pk=qid).exists())
        print(f'  question {qid} deleted successfully  PASS')
