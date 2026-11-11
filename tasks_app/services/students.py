from users_app.decorators import coach_students


def list_for_coach(coach):
    return coach_students(coach).order_by('full_name')
