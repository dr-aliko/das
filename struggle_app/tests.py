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
        self.topic_a = KonuTakipTopic.objects.create(
            subject=self.subject, name='Hücre', order=1, checkable=True
        )
        self.topic_b = KonuTakipTopic.objects.create(
            subject=self.subject, name='Genetik', order=2, checkable=True
        )
        # 2 questions with topic_a (1 due, 1 not due), 1 question with no topic (due)
        from datetime import timedelta
        q1 = _create_question(self.student, self.subject, topic=self.topic_a)
        q2 = _create_question(self.student, self.subject, topic=self.topic_a)
        q2.next_review_at = timezone.now() + timedelta(days=7)
        q2.save(update_fields=['next_review_at'])
        _create_question(self.student, self.subject, topic=None)

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

    def test_37_coach_sorularim_topic_breakdown(self):
        """
        /coach/sorularim/ page must:
        - Return 200 for an authorised coach
        - Include topic-level breakdown in context (via CoachStruggleStatsView)
        - Show correct topic names and counts, no question content
        """
        print('\n' + '='*60)
        print('TEST 37: Coach sorularim page — topic breakdown')
        print('='*60)
        c = Client()
        c.login(username='coach_stats@test.com', password='testpass123')
        resp = c.get(f'/coach/sorularim/?student={self.student.id}')
        self.assertEqual(resp.status_code, 200)

        stats = resp.context['struggle_stats']
        self.assertEqual(len(stats), 1)
        row = stats[0]

        # Subject-level totals correct
        self.assertEqual(row['total'], 3)
        self.assertEqual(row['due'], 2)

        # Topic breakdown attached
        self.assertIn('topics', row, 'topics key must be present on each subject row')
        topics = {t['name']: t for t in row['topics']}
        print(f'  topics: {list(topics.keys())}')

        # topic_a: 2 questions (1 due)
        self.assertIn('Hücre', topics)
        self.assertEqual(topics['Hücre']['total'], 2)
        self.assertEqual(topics['Hücre']['due'], 1)

        # no-topic questions grouped as 'Konu belirtilmemiş'
        self.assertIn('Konu belirtilmemiş', topics)
        self.assertEqual(topics['Konu belirtilmemiş']['total'], 1)
        self.assertEqual(topics['Konu belirtilmemiş']['due'], 1)

        # Privacy: no image URLs, no question text, no IDs in any topic entry
        for t in row['topics']:
            self.assertNotIn('question_image_url', t)
            self.assertNotIn('question_text', t)
            self.assertNotIn('id', t)
        print('  topic counts correct, no content leaked  PASS')


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


# ── New tests for improvements #1-11 ─────────────────────────────────────────

class TytAytToggleTests(TestCase):
    """TYT/AYT segmented toggle + alan-filtered subjects including Geometri (#1-5)."""

    def setUp(self):
        self.student_say = _make_student('toggle_say', alan='SAY')
        self.student_ea  = _make_student('toggle_ea',  alan='EA')
        self.student_soz = _make_student('toggle_soz', alan='SOZ')
        # AYT subjects — no konu_takip_topics needed for struggle_subject_groups
        _make_subject('AYT Matematik',  'AYT')
        _make_subject('AYT Fizik',      'AYT')
        _make_subject('AYT Kimya',      'AYT')
        _make_subject('AYT Biyoloji',   'AYT')
        _make_subject('AYT Geometri',   'AYT')
        _make_subject('AYT Türk Dili ve Edebiyatı', 'AYT')
        _make_subject('AYT Tarih 2',    'AYT')
        _make_subject('AYT Coğrafya 2', 'AYT')
        _make_subject('AYT Felsefe Grubu', 'AYT')
        _make_subject('AYT Yabancı Dil', 'AYT')

    def test_21_say_sees_geometri_in_ayt(self):
        print('\n' + '='*60)
        print('TEST 21: SAY student sees AYT Geometri in struggle subjects')
        print('='*60)
        from konu_takip_app.alan_utils import struggle_subject_groups
        _, ayt = struggle_subject_groups(self.student_say)
        names = [s.name for s in ayt]
        print(f'  SAY AYT subjects: {sorted(names)}')
        self.assertIn('AYT Geometri', names)
        self.assertIn('AYT Fizik', names)
        print('  PASS')

    def test_22_ea_sees_geometri_in_ayt(self):
        print('\n' + '='*60)
        print('TEST 22: EA student sees AYT Geometri in struggle subjects')
        print('='*60)
        from konu_takip_app.alan_utils import struggle_subject_groups
        _, ayt = struggle_subject_groups(self.student_ea)
        names = [s.name for s in ayt]
        print(f'  EA AYT subjects: {sorted(names)}')
        self.assertIn('AYT Geometri', names)
        self.assertNotIn('AYT Fizik', names)
        print('  PASS')

    def test_23_soz_does_not_see_geometri(self):
        print('\n' + '='*60)
        print('TEST 23: SOZ student does NOT see AYT Geometri')
        print('='*60)
        from konu_takip_app.alan_utils import struggle_subject_groups
        _, ayt = struggle_subject_groups(self.student_soz)
        names = [s.name for s in ayt]
        print(f'  SOZ AYT subjects: {sorted(names)}')
        self.assertNotIn('AYT Geometri', names)
        print('  PASS')

    def test_24_konu_takip_say_does_not_see_geometri(self):
        """AYT_ALAN_MAP (Konu Takip) must be unaffected — SAY should not see Geometri there."""
        print('\n' + '='*60)
        print('TEST 24: Konu Takip subject_groups (SAY) does NOT include AYT Geometri')
        print('='*60)
        # Add a KonuTakipTopic so Fizik is visible in Konu Takip
        fizik = _make_subject('AYT Fizik', 'AYT')
        KonuTakipTopic.objects.create(subject=fizik, name='Hareket', order=1, checkable=True)
        from konu_takip_app.alan_utils import subject_groups
        _, ayt = subject_groups(self.student_say)
        names = [s.name for s in ayt]
        print(f'  KT SAY AYT subjects: {sorted(names)}')
        self.assertNotIn('AYT Geometri', names)
        self.assertIn('AYT Fizik', names)
        print('  PASS')


class TopicScopingTests(TestCase):
    """Topics stay scoped to the selected subject (#4)."""

    def setUp(self):
        self.student = _make_student('scoping')
        self.tyt_mat = _make_subject('TYT Matematik', 'TYT')
        self.ayt_mat = _make_subject('AYT Matematik', 'AYT')
        self.tyt_topic = KonuTakipTopic.objects.create(
            subject=self.tyt_mat, name='TYT Konu', order=1, checkable=True
        )
        self.ayt_topic = KonuTakipTopic.objects.create(
            subject=self.ayt_mat, name='AYT Konu', order=1, checkable=True
        )
        self.client = Client()
        self.client.login(username='student_scoping@test.com', password='testpass123')

    def test_25_topics_api_scoped_to_subject(self):
        """Topics API for TYT Matematik must not return AYT Matematik topics."""
        print('\n' + '='*60)
        print('TEST 25: Topics API only returns topics for the requested subject')
        print('='*60)
        resp = self.client.get(
            f'/student/konu-takip/sorularim/topics/?subject_id={self.tyt_mat.id}'
        )
        data = resp.json()
        names = [t['name'] for t in data['topics']]
        print(f'  topics for TYT Matematik: {names}')
        self.assertIn('TYT Konu', names)
        self.assertNotIn('AYT Konu', names)
        print('  PASS')


class TextInputMethodTests(TestCase):
    """Three input methods: camera/gallery (image) and text (#6-7)."""

    def setUp(self):
        self.student = _make_student('textinput')
        self.subject = _make_subject('TYT Matematik')
        self.client  = Client()
        self.client.login(username='student_textinput@test.com', password='testpass123')

    def tearDown(self):
        for q in StudentStruggleQuestion.objects.filter(student=self.student):
            if q.question_image:
                try:
                    q.question_image.delete(save=False)
                except Exception:
                    pass

    def test_26_text_only_question_saves(self):
        print('\n' + '='*60)
        print('TEST 26: question_text-only submission saves and returns correct JSON')
        print('='*60)
        resp = self.client.post('/student/konu-takip/sorularim/add/', {
            'subject_id': self.subject.id,
            'question_text': 'Bu soru neden zor?',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'], data)
        q_json = data['question']
        self.assertEqual(q_json['question_text'], 'Bu soru neden zor?')
        self.assertIsNone(q_json['question_image_url'])
        print(f'  question_text: {q_json["question_text"]}  image_url: {q_json["question_image_url"]}  PASS')

    def test_27_neither_image_nor_text_rejected(self):
        print('\n' + '='*60)
        print('TEST 27: Submission with neither image nor text is rejected')
        print('='*60)
        resp = self.client.post('/student/konu-takip/sorularim/add/', {
            'subject_id': self.subject.id,
        })
        data = resp.json()
        self.assertFalse(data['ok'])
        print(f'  error: {data["error"]}  PASS')

    def test_28_both_image_and_text_rejected(self):
        print('\n' + '='*60)
        print('TEST 28: Submission with both image and text is rejected')
        print('='*60)
        resp = self.client.post('/student/konu-takip/sorularim/add/', {
            'subject_id': self.subject.id,
            'question_image': _png_upload('q.png'),
            'question_text': 'aynı anda her ikisi',
        })
        data = resp.json()
        self.assertFalse(data['ok'])
        print(f'  error: {data["error"]}  PASS')

    def test_29_solution_text_saved(self):
        print('\n' + '='*60)
        print('TEST 29: solution_text saved correctly alongside question_text')
        print('='*60)
        resp = self.client.post('/student/konu-takip/sorularim/add/', {
            'subject_id': self.subject.id,
            'question_text': 'Soru metni',
            'solution_text': 'Çözüm açıklaması',
        })
        data = resp.json()
        self.assertTrue(data['ok'], data)
        q_json = data['question']
        self.assertEqual(q_json['solution_text'], 'Çözüm açıklaması')
        self.assertIsNone(q_json['solution_image_url'])
        print(f'  solution_text: {q_json["solution_text"]}  PASS')


class EaseFactorSortTests(TestCase):
    """ease_factor sort modes: En Zorladıklarım / En Kolaylarım (#10-11).

    SR ceiling for kolay is 2.2, which is BELOW the default 2.5.
    So the provable relationship is: repeated-zor (ef=2.3) < never-reviewed (ef=2.5).
    """

    def setUp(self):
        self.student = _make_student('easesort')
        self.subject = _make_subject('TYT Biyoloji')
        from struggle_app.services import submit_struggle_review
        # q_hard: 3 zor reviews → ef decreases; after rc>=2 zor: ef=max(1.3,2.5-0.20)=2.3
        self.q_hard    = _create_question(self.student, self.subject)
        # q_default: no reviews → ef stays at 2.5
        self.q_default = _create_question(self.student, self.subject,
                                          next_review_at=None)  # not yet due
        for _ in range(3):
            submit_struggle_review(self.student, self.q_hard.id, 'zor')
        self.q_hard.refresh_from_db()
        self.q_default.refresh_from_db()

    def test_30_ease_factor_ordering(self):
        """Hard (zor-reviewed) question has lower ease_factor than fresh question."""
        print('\n' + '='*60)
        print('TEST 30: ease_factor ordering — zor-reviewed < default')
        print('='*60)
        print(f'  hard.ease_factor:    {self.q_hard.ease_factor:.4f}')
        print(f'  default.ease_factor: {self.q_default.ease_factor:.4f}')
        self.assertLess(self.q_hard.ease_factor, self.q_default.ease_factor)
        print('  PASS')

    def test_31_ease_factor_sort_order(self):
        """
        Creates 4 questions with explicitly varied ease_factors, fetches all_json,
        then applies the same sort Alpine.js uses and confirms the actual ID order.

        ease_factors set directly:
          q_a: 1.3  (worst — hit the floor)
          q_b: 1.8
          q_c: 2.3
          q_d: 2.5  (best / freshest)

        En Zorladıklarım = ease_factor ASC  → expected: q_a, q_b, q_c, q_d
        En Kolaylarım    = ease_factor DESC → expected: q_d, q_c, q_b, q_a
        """
        import json as _json
        print('\n' + '='*60)
        print('TEST 31: En Zorladiklarim / En Kolaylarim sort order')
        print('='*60)

        subject = _make_subject('TYT Kimya')
        # Build student with 4 questions at specific ease_factors
        student = _make_student('ef_sort')
        qa = _create_question(student, subject, ease_factor=1.3)
        qb = _create_question(student, subject, ease_factor=1.8)
        qc = _create_question(student, subject, ease_factor=2.3)
        qd = _create_question(student, subject, ease_factor=2.5)

        client = Client()
        client.login(username='student_ef_sort@test.com', password='testpass123')
        resp = client.get('/student/konu-takip/sorularim/')
        self.assertEqual(resp.status_code, 200)
        all_q = _json.loads(resp.context['all_json'])

        # Keep only our 4 questions (setUp may have added others)
        our_ids = {qa.id, qb.id, qc.id, qd.id}
        our_q = [q for q in all_q if q['id'] in our_ids]

        print('  Raw ease_factors from JSON:')
        for q in our_q:
            print(f'    id={q["id"]}  ease_factor={q["ease_factor"]}')

        # Verify all ease_factor values are present and correct
        ef_map = {q['id']: q['ease_factor'] for q in our_q}
        self.assertAlmostEqual(ef_map[qa.id], 1.3, places=5)
        self.assertAlmostEqual(ef_map[qb.id], 1.8, places=5)
        self.assertAlmostEqual(ef_map[qc.id], 2.3, places=5)
        self.assertAlmostEqual(ef_map[qd.id], 2.5, places=5)

        # Apply same sort as Alpine: En Zorladıklarım = ease_factor ASC
        hardest_ids = [q['id'] for q in sorted(our_q, key=lambda q: q['ease_factor'])]
        expected_hardest = [qa.id, qb.id, qc.id, qd.id]
        print(f'\n  En Zorladiklarim (ef ASC):')
        for qid in hardest_ids:
            print(f'    id={qid}  ef={ef_map[qid]}')
        print(f'  Expected order: {expected_hardest}')
        self.assertEqual(hardest_ids, expected_hardest)
        print('  PASS')

        # Apply same sort as Alpine: En Kolaylarım = ease_factor DESC
        easiest_ids = [q['id'] for q in sorted(our_q, key=lambda q: q['ease_factor'], reverse=True)]
        expected_easiest = [qd.id, qc.id, qb.id, qa.id]
        print(f'\n  En Kolaylarim (ef DESC):')
        for qid in easiest_ids:
            print(f'    id={qid}  ef={ef_map[qid]}')
        print(f'  Expected order: {expected_easiest}')
        self.assertEqual(easiest_ids, expected_easiest)
        print('  PASS')


class SortByNextReviewTests(TestCase):
    """Default sort by next_review_at ASC (#9)."""

    def setUp(self):
        self.student = _make_student('sortnr')
        self.subject = _make_subject('TYT Fizik')
        from datetime import timedelta
        now = timezone.now()
        # q1 due furthest in future, q3 due soonest
        self.q1 = _create_question(self.student, self.subject,
                                   next_review_at=now + timedelta(days=10))
        self.q2 = _create_question(self.student, self.subject,
                                   next_review_at=now + timedelta(days=5))
        self.q3 = _create_question(self.student, self.subject,
                                   next_review_at=now + timedelta(days=1))

    def test_32_default_sort_next_review_ascending(self):
        print('\n' + '='*60)
        print('TEST 32: Default sort is next_review_at ascending (soonest first)')
        print('='*60)
        client = Client()
        client.login(username='student_sortnr@test.com', password='testpass123')
        resp = client.get('/student/konu-takip/sorularim/')
        import json as _json
        all_q = _json.loads(resp.context['all_json'])
        ids = [q['id'] for q in all_q]
        print(f'  order: {ids}  (expected: [{self.q3.id}, {self.q2.id}, {self.q1.id}])')
        self.assertEqual(ids, [self.q3.id, self.q2.id, self.q1.id])
        print('  PASS')


# ── New tests for refinements: early review (#7) and subject leak (#1) ─────────

class EarlyReviewTests(TestCase):
    """
    Voluntary early review (#7):
      - POST /sorularim/review/ on a NOT-YET-DUE question → schedule updates
      - Closing without rating (no POST) → schedule completely unchanged
    """

    def setUp(self):
        import json as _json
        self._json = _json
        from datetime import timedelta
        self.student = _make_student('earlyrev')
        self.subject = _make_subject('TYT Matematik')
        self.client  = Client()
        self.client.login(username='student_earlyrev@test.com', password='testpass123')
        # Create a question that is NOT yet due (next_review_at = 30 days from now)
        self.future_date = timezone.now() + timedelta(days=30)
        self.q = _create_question(
            self.student, self.subject,
            next_review_at=self.future_date,
            current_interval_days=30,
            ease_factor=2.5,
            review_count=2,
        )

    def tearDown(self):
        if self.q.question_image:
            try:
                self.q.question_image.delete(save=False)
            except Exception:
                pass

    def test_33_early_review_updates_schedule(self):
        """
        POST review on a not-yet-due question must update next_review_at via apply_sm2.
        rc=2, interval=30, ef=2.5, quality='kolay' -> interval=round(30*2.5)=75, ef=2.2
        next_review_at should be ~75 days from now, not the original 30 days.
        """
        print('\n' + '='*60)
        print('TEST 33: Early review on not-yet-due question updates schedule')
        print('='*60)
        original_nra = self.q.next_review_at

        resp = self.client.post(
            '/student/konu-takip/sorularim/review/',
            data=self._json.dumps({'question_id': self.q.id, 'quality': 'kolay'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'], data)

        self.q.refresh_from_db()
        print(f'  original next_review_at: {original_nra.date()}')
        print(f'  updated  next_review_at: {self.q.next_review_at.date()}')
        print(f'  updated  interval_days:  {self.q.current_interval_days}')
        print(f'  updated  ease_factor:    {self.q.ease_factor:.4f}')

        # rc=2, interval=30, ef=2.5, kolay -> interval=75, ef=2.2
        expected_interval, expected_ef = apply_sm2(2, 30, 2.5, 'kolay')
        self.assertEqual(self.q.current_interval_days, expected_interval,
            f'interval: got {self.q.current_interval_days}, expected {expected_interval}')
        self.assertAlmostEqual(self.q.ease_factor, expected_ef, places=10,
            msg=f'ease_factor: got {self.q.ease_factor}, expected {expected_ef}')
        self.assertEqual(self.q.review_count, 3)

        # next_review_at must be strictly later than the old future_date
        self.assertGreater(self.q.next_review_at, original_nra,
            'next_review_at should advance beyond the old scheduled date')
        print(f'  next_review_at advanced by {expected_interval} days  PASS')

    def test_34_no_review_leaves_schedule_unchanged(self):
        """
        Simply viewing the page (GET) without POSTing a review must NOT mutate
        the question's schedule in any way.
        """
        print('\n' + '='*60)
        print('TEST 34: Viewing page without rating leaves schedule unchanged')
        print('='*60)
        original_nra      = self.q.next_review_at
        original_interval = self.q.current_interval_days
        original_ef       = self.q.ease_factor
        original_rc       = self.q.review_count

        # GET the page (simulates opening and closing without rating)
        resp = self.client.get('/student/konu-takip/sorularim/')
        self.assertEqual(resp.status_code, 200)

        self.q.refresh_from_db()
        print(f'  next_review_at unchanged: {self.q.next_review_at == original_nra}')
        print(f'  interval unchanged:       {self.q.current_interval_days == original_interval}')
        print(f'  ease_factor unchanged:    {self.q.ease_factor == original_ef}')
        print(f'  review_count unchanged:   {self.q.review_count == original_rc}')

        self.assertEqual(self.q.next_review_at, original_nra)
        self.assertEqual(self.q.current_interval_days, original_interval)
        self.assertAlmostEqual(self.q.ease_factor, original_ef, places=10)
        self.assertEqual(self.q.review_count, original_rc)
        print('  PASS — no state mutation from GET-only visit')


class SubjectLeakTests(TestCase):
    """
    Subject leak fix (#1):
      - excluded_from_planning=True subjects must NOT appear in struggle subject list
      - Umbrella names 'TYT Fen Bilimleri' / 'TYT Sosyal Bilimler' must be absent
    """

    def setUp(self):
        self.student = _make_student('subleak', alan='SAY')
        # Migration 0024 already seeds TYT Problemler with excluded_from_planning=True.
        # Migration 0015 seeds the umbrella names (excluded_from_planning=False by default).
        # Use get_or_create to avoid UNIQUE constraint errors.
        self.excluded_subj, _ = Subject.objects.get_or_create(
            name='TYT Problemler', exam_type='TYT',
            defaults={'excluded_from_planning': True},
        )
        self.excluded_subj.excluded_from_planning = True
        self.excluded_subj.save(update_fields=['excluded_from_planning'])

        self.umbrella_fen, _ = Subject.objects.get_or_create(
            name='TYT Fen Bilimleri', exam_type='TYT',
            defaults={'excluded_from_planning': False},
        )
        self.umbrella_sos, _ = Subject.objects.get_or_create(
            name='TYT Sosyal Bilimler', exam_type='TYT',
            defaults={'excluded_from_planning': False},
        )
        self.normal_subj, _ = Subject.objects.get_or_create(
            name='TYT Matematik', exam_type='TYT',
            defaults={'excluded_from_planning': False},
        )

    def test_35_excluded_from_planning_not_in_struggle_subjects(self):
        print('\n' + '='*60)
        print('TEST 35: excluded_from_planning=True subject absent from struggle list')
        print('='*60)
        from konu_takip_app.alan_utils import struggle_subject_groups
        tyt, _ = struggle_subject_groups(self.student)
        names = [s.name for s in tyt]
        print(f'  TYT subjects visible: {sorted(names)}')
        self.assertNotIn('TYT Problemler', names,
            'TYT Problemler (excluded_from_planning=True) must not appear')
        self.assertIn('TYT Matematik', names,
            'TYT Matematik (normal) must appear')
        print('  PASS')

    def test_36_umbrella_names_not_in_struggle_subjects(self):
        print('\n' + '='*60)
        print('TEST 36: Umbrella subjects TYT Fen/Sosyal Bilimleri absent from list')
        print('='*60)
        from konu_takip_app.alan_utils import struggle_subject_groups
        tyt, _ = struggle_subject_groups(self.student)
        names = [s.name for s in tyt]
        print(f'  TYT subjects visible: {sorted(names)}')
        self.assertNotIn('TYT Fen Bilimleri', names,
            'TYT Fen Bilimleri (umbrella) must be excluded')
        self.assertNotIn('TYT Sosyal Bilimler', names,
            'TYT Sosyal Bilimler (umbrella) must be excluded')
        print('  PASS')
