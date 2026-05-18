from django.contrib.auth import get_user_model

User = get_user_model()


def list_for_coach(coach: User):
    """Return all students assigned to this coach."""
    return User.objects.filter(role='student', coach=coach).order_by('full_name')
