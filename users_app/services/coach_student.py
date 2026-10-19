"""
Service layer for CoachStudent state transitions.

Every path that activates or deactivates a CoachStudent link MUST go through
this module so that CoachStudentInterval stays in sync.
"""
import logging

from django.db import transaction
from django.utils import timezone

_log = logging.getLogger(__name__)


def open_interval(link):
    """
    Open a new CoachStudentInterval for an active link.
    Idempotent: if an open interval already exists for this (coach, student) pair,
    returns without creating a second one.
    """
    from users_app.models import CoachStudentInterval
    if CoachStudentInterval.objects.filter(
        coach_id=link.coach_id,
        student_id=link.student_id,
        ended_at__isnull=True,
    ).exists():
        return
    CoachStudentInterval.objects.create(
        coach_id=link.coach_id,
        student_id=link.student_id,
        source=link.source,
        started_at=timezone.now(),
    )


def close_interval(link, reason, when=None):
    """Close the open interval for this link. Idempotent if already closed."""
    from users_app.models import CoachStudentInterval
    ts = when or timezone.now()
    CoachStudentInterval.objects.filter(
        coach_id=link.coach_id,
        student_id=link.student_id,
        ended_at__isnull=True,
    ).update(ended_at=ts, close_reason=reason)


def deactivate_link(link, reason, when=None):
    """Deactivate a CoachStudent and close its open interval."""
    close_interval(link, reason, when=when)
    link.active = False
    link.deactivation_reason = reason
    link.save(update_fields=['active', 'deactivation_reason'])


def ensure_active_link(coach, student, source, next_payment_due=None):
    """
    Get or create a CoachStudent and ensure it is active.
    Opens an interval when the link is created or reactivated.
    Returns (link, created, reactivated).
    """
    from users_app.models import CoachStudent
    link, created = CoachStudent.objects.get_or_create(
        coach=coach,
        student=student,
        defaults={
            'source': source,
            'active': True,
            'next_payment_due': next_payment_due,
        },
    )
    reactivated = False
    if not created and not link.active:
        link.active = True
        link.deactivation_reason = None
        link.save(update_fields=['active', 'deactivation_reason'])
        reactivated = True
    if created or reactivated:
        open_interval(link)
    return link, created, reactivated


def reassign_student(student, new_coach, acting_staff):
    """
    Transfer student from their current active coach to new_coach.

    Raises ValueError with a Turkish message for invalid inputs.
    Executes atomically: deactivates old link (reason=reassign), reactivates or
    creates new link (preserving source and next_payment_due), updates User.coach,
    and notifies both coaches.
    """
    from users_app.models import CoachStudent, CoachStudentInterval, Notification, User

    with transaction.atomic():
        student = User.objects.select_for_update().get(pk=student.pk)

        old_link = (
            CoachStudent.objects
            .select_for_update()
            .filter(student=student, active=True)
            .select_related('coach')
            .first()
        )
        if old_link is None:
            raise ValueError('Öğrencinin aktif bir koç bağlantısı yok.')

        new_coach = User.objects.select_for_update().get(pk=new_coach.pk)
        if old_link.coach_id == new_coach.pk:
            raise ValueError('Öğrenci zaten bu koçta.')
        if new_coach.role != 'coach':
            raise ValueError('Hedef kullanıcı koç değil.')
        if not new_coach.is_active:
            raise ValueError('Hedef koç pasif.')
        if not new_coach.is_approved:
            raise ValueError('Hedef koç onaylı değil.')

        old_coach = old_link.coach
        source = old_link.source
        next_payment_due = old_link.next_payment_due

        close_interval(old_link, CoachStudentInterval.REASON_REASSIGN)
        old_link.active = False
        old_link.deactivation_reason = CoachStudent.DEACTIVATION_REASSIGN
        old_link.save(update_fields=['active', 'deactivation_reason'])

        new_link, new_created = CoachStudent.objects.select_for_update().get_or_create(
            coach=new_coach,
            student=student,
            defaults={
                'source': source,
                'next_payment_due': next_payment_due,
                'active': True,
            },
        )
        if not new_created:
            new_link.active = True
            new_link.source = source
            new_link.next_payment_due = next_payment_due
            new_link.deactivation_reason = None
            new_link.save(update_fields=['active', 'source', 'next_payment_due', 'deactivation_reason'])
        open_interval(new_link)

        student.coach = new_coach
        student.save(update_fields=['coach'])

        Notification.objects.create(
            user=old_coach,
            title='Öğrenci başka bir koça atandı',
            body=(
                f'{student.full_name} adlı öğrenci {acting_staff.full_name} tarafından '
                f'{new_coach.full_name} adlı koça aktarıldı.'
            ),
        )
        Notification.objects.create(
            user=new_coach,
            title='Yeni öğrenci atandı',
            body=(
                f'{student.full_name} adlı öğrenci {acting_staff.full_name} tarafından '
                f'panelinize eklendi (eski koç: {old_coach.full_name}).'
            ),
        )

        _log.info(
            'reassign_student: student pk=%s moved from coach pk=%s to coach pk=%s by staff pk=%s',
            student.pk, old_coach.pk, new_coach.pk, acting_staff.pk,
        )


def rebuild_intervals():
    """
    Rebuild all CoachStudentInterval rows from existing CoachStudent state.
    Deletes all existing intervals first — use only for data repair.
    Returns count of rows created.
    """
    from users_app.models import CoachStudent, CoachStudentInterval
    now = timezone.now()
    CoachStudentInterval.objects.all().delete()
    rows = []
    for link in CoachStudent.objects.all():
        if link.active:
            rows.append(CoachStudentInterval(
                coach_id=link.coach_id,
                student_id=link.student_id,
                source=link.source,
                started_at=link.created_at,
                ended_at=None,
                close_reason=None,
            ))
        else:
            rows.append(CoachStudentInterval(
                coach_id=link.coach_id,
                student_id=link.student_id,
                source=link.source,
                started_at=link.created_at,
                ended_at=now,
                close_reason=CoachStudentInterval.REASON_BACKFILL,
            ))
    CoachStudentInterval.objects.bulk_create(rows, batch_size=1000)
    return len(rows)
