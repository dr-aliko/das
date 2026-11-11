import pytest
from model_bakery import baker

from users_app.decorators import coach_can_view_student
from users_app.models import CoachStudent


@pytest.mark.django_db
def test_active_link_grants_access(coach_user, student_user):
    CoachStudent.objects.create(coach=coach_user, student=student_user, active=True)
    assert coach_can_view_student(coach_user, student_user.id) is True


@pytest.mark.django_db
def test_inactive_link_denies_access(coach_user, student_user):
    CoachStudent.objects.create(coach=coach_user, student=student_user, active=False)
    assert coach_can_view_student(coach_user, student_user.id) is False


@pytest.mark.django_db
def test_legacy_fk_grants_access_without_creating_link(coach_user, student_user):
    # Backward-compat path: student.coach FK is set but no CoachStudent row yet.
    # Access is still granted; no write is performed (run check_coach_consistency --fix instead).
    student_user.coach = coach_user
    student_user.save(update_fields=['coach'])
    assert coach_can_view_student(coach_user, student_user.id) is True
    assert not CoachStudent.objects.filter(coach=coach_user, student=student_user).exists()


@pytest.mark.django_db
def test_no_relationship_denies_access(coach_user, student_user):
    assert coach_can_view_student(coach_user, student_user.id) is False


@pytest.mark.django_db
def test_coach_role_as_student_id_denies_access(coach_user):
    # student_id points to a coach account — role guard must reject it.
    another_coach = baker.make('users_app.User', role='coach', is_active=True)
    assert coach_can_view_student(coach_user, another_coach.id) is False


@pytest.mark.django_db
def test_nonexistent_student_id_denies_access(coach_user):
    assert coach_can_view_student(coach_user, 99999999) is False


@pytest.mark.django_db
def test_staff_reassigned_vagus_student_moves_to_new_coach(coach_user, student_user):
    from users_app.decorators import coach_students
    from users_app.services.coach_student import reassign_student

    new_coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    staff = baker.make('users_app.User', is_staff=True, is_active=True)
    student_user.coach = coach_user
    student_user.save(update_fields=['coach'])
    CoachStudent.objects.create(
        coach=coach_user, student=student_user, active=True, source=CoachStudent.SOURCE_VAGUS,
    )

    reassign_student(student_user, new_coach, staff)

    assert list(coach_students(new_coach)) == [student_user]
    assert not coach_students(coach_user).exists()
