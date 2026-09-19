from django.contrib.auth import get_user_model

User = get_user_model()


def list_for_coach(coach: User):
    """Return active students assigned to this coach (respects CoachStudent.active)."""
    from users_app.models import CoachStudent
    active_ids = (
        CoachStudent.objects
        .filter(coach=coach, active=True)
        .values_list('student_id', flat=True)
    )
    return User.objects.filter(role='student', id__in=active_ids).order_by('full_name')
