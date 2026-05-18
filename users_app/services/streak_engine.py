"""
DAS Streak & Achievement Engine
Tracks daily study streaks and awards milestone badges.

Entry point: record_activity(student)
Called explicitly from qualifying view endpoints after each study action.
"""
from django.utils import timezone


def record_activity(student):
    """
    Update streak fields for a qualifying study action (exam saved, task completed).
    Awards badges as appropriate. Thread-safe at normal session concurrency.
    """
    today = timezone.localdate()  # Europe/Istanbul local date

    last = student.last_activity_date

    if last == today:
        return  # already counted today

    from_streak = student.current_streak

    if last == today - timezone.timedelta(days=1):
        student.current_streak += 1
    else:
        # Streak broken — check comeback badge before reset
        if from_streak >= 5:
            _award(student, 'comeback')
        student.current_streak = 1

    student.last_activity_date = today
    if student.current_streak > student.longest_streak:
        student.longest_streak = student.current_streak

    student.save(update_fields=['current_streak', 'longest_streak', 'last_activity_date'])

    _award_badges(student)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _award(student, badge_key):
    from users_app.models import StudentAchievement
    StudentAchievement.objects.get_or_create(student=student, badge_key=badge_key)


def _award_badges(student):
    """Check all badge conditions and award any newly-satisfied ones."""
    from exams_app.models import Exam, StudentTask

    s = student.current_streak

    # Streak milestones
    for threshold, key in [(3, 'streak_3'), (7, 'streak_7'), (14, 'streak_14'),
                           (30, 'streak_30'), (60, 'streak_60'), (100, 'streak_100')]:
        if s >= threshold:
            _award(student, key)

    # Perfect week (alias for 7-day streak — already covered above)
    if s >= 7:
        _award(student, 'perfect_week')

    # Exam count milestones
    exam_count = Exam.objects.filter(student=student).count()
    for threshold, key in [(1, 'exam_1'), (10, 'exam_10'), (25, 'exam_25'), (50, 'exam_50')]:
        if exam_count >= threshold:
            _award(student, key)

    # Task completion milestones
    task_count = StudentTask.objects.filter(student=student, is_completed=True).count()
    for threshold, key in [(10, 'task_10'), (50, 'task_50')]:
        if task_count >= threshold:
            _award(student, key)
