"""
Tests for the invite statistics boxes and history section on the coach invites page.

Run: python manage.py test users_app.test_invite_stats --verbosity=2
"""
from datetime import date, timedelta

from django.test import Client, TestCase, override_settings

from users_app.models import CoachStudent, StudentInvite, User

INVITE_URL = '/auth/invite-students/'


def _coach(n=0):
    u = User.objects.create_user(
        email=f'coach{n}@test.com',
        full_name=f'Coach {n}',
        role='coach',
        password='pass',
    )
    u.is_approved = True
    u.save(update_fields=['is_approved'])
    return u


def _student(n):
    return User.objects.create_user(
        email=f'stu{n}@test.com',
        full_name=f'Student {n}',
        role='student',
        password='pass',
    )


def _link(coach, student, source='coach', active=True, due=None):
    return CoachStudent.objects.create(
        coach=coach, student=student,
        source=source, active=active, next_payment_due=due,
    )


def _invite(coach, email, is_used=False):
    return StudentInvite.objects.create(
        coach=coach, email=email,
        token=StudentInvite.generate_token(), is_used=is_used,
    )


@override_settings(
    COACH_PER_STUDENT_PERIODS=True,
    COACH_CAPACITY_ENFORCED=False,
    RATELIMIT_ENABLE=False,
)
class InviteStatBoxesTest(TestCase):
    """
    Boxes show active count equal to roster, pending and expired for a fixture
    with removed, moved, Vagus, no-account and active students; lifetime note
    only when the accepted-lifetime count differs from the active count.
    """

    def setUp(self):
        self.coach = _coach(0)
        today = date.today()

        s_active = _student(1)
        _link(self.coach, s_active)
        _invite(self.coach, s_active.email, is_used=True)

        s_expired = _student(2)
        _link(self.coach, s_expired, due=today - timedelta(days=1))
        _invite(self.coach, s_expired.email, is_used=True)

        s_removed = _student(3)
        _link(self.coach, s_removed, active=False)
        _invite(self.coach, s_removed.email, is_used=True)

        s_moved = _student(4)
        _invite(self.coach, s_moved.email, is_used=True)

        s_vagus = _student(5)
        _link(self.coach, s_vagus, source='vagus')
        _invite(self.coach, s_vagus.email, is_used=True)

        _invite(self.coach, 'nouser@test.com', is_used=True)
        _invite(self.coach, 'pending@test.com', is_used=False)

        self.client = Client()
        self.client.force_login(self.coach)
        self.resp = self.client.get(INVITE_URL)

    def test_active_own_count(self):
        ctx = self.resp.context
        self.assertEqual(ctx['active_own_count'], 2)   # s_active + s_expired (both active=True)
        self.assertEqual(ctx['invite_pending'], 1)
        self.assertEqual(ctx['expired_own_count'], 1)  # s_expired only
        self.assertEqual(ctx['invite_accepted_lifetime'], 6)

    def test_lifetime_note_shown_when_counts_differ(self):
        self.assertContains(self.resp, 'Şimdiye kadar kabul edilen davet')


@override_settings(
    COACH_PER_STUDENT_PERIODS=True,
    COACH_CAPACITY_ENFORCED=False,
    RATELIMIT_ENABLE=False,
)
class InviteHistorySectionTest(TestCase):
    """
    History section lists inactive and no-account invites; active list does not.
    Vagus-source invites appear in neither list.
    """

    def test_active_and_history_split(self):
        coach = _coach(1)

        s_active = _student(10)
        _link(coach, s_active)
        _invite(coach, s_active.email, is_used=True)

        s_removed = _student(11)
        _link(coach, s_removed, active=False)
        _invite(coach, s_removed.email, is_used=True)

        s_vagus = _student(12)
        _link(coach, s_vagus, source='vagus')
        _invite(coach, s_vagus.email, is_used=True)

        _invite(coach, 'nouser2@test.com', is_used=True)

        c = Client()
        c.force_login(coach)
        ctx = c.get(INVITE_URL).context

        active_emails = [r['invite'].email for r in ctx['active_invited_rows'] if not r['is_pending']]
        history_emails = [r['invite'].email for r in ctx['invite_history_rows']]

        self.assertIn(s_active.email, active_emails)
        self.assertNotIn(s_removed.email, active_emails)
        self.assertNotIn(s_vagus.email, active_emails)
        self.assertNotIn('nouser2@test.com', active_emails)

        self.assertIn(s_removed.email, history_emails)
        self.assertIn('nouser2@test.com', history_emails)
        self.assertNotIn(s_vagus.email, history_emails)
        self.assertNotIn(s_active.email, history_emails)


@override_settings(
    COACH_PER_STUDENT_PERIODS=True,
    COACH_CAPACITY_ENFORCED=False,
    RATELIMIT_ENABLE=False,
)
class InviteLessStudentCountTest(TestCase):
    """
    Active own count equals the roster's own-student count even when one
    student joined without an invite (via staff or invite-less link).
    """

    def test_invite_less_student_counted(self):
        coach = _coach(2)

        s_invited = _student(20)
        _link(coach, s_invited)
        _invite(coach, s_invited.email, is_used=True)

        s_no_invite = _student(21)
        _link(coach, s_no_invite)

        c = Client()
        c.force_login(coach)
        ctx = c.get(INVITE_URL).context

        self.assertEqual(ctx['active_own_count'], 2)
        self.assertEqual(ctx['invite_accepted_lifetime'], 1)
