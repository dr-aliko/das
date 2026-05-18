from functools import wraps
from django.shortcuts import redirect


def coach_can_view_student(coach, student_id):
    """Returns True if coach is authorised to view this student's data (DAS-412).

    Primary check: CoachStudent table (active=True).
    Fallback: User.coach FK — auto-creates CoachStudent on first access for seamless migration.
    """
    from users_app.models import CoachStudent, User
    try:
        student = User.objects.get(id=student_id, role='student')
    except User.DoesNotExist:
        return False

    if CoachStudent.objects.filter(coach=coach, student=student, active=True).exists():
        return True

    # Backward-compat: honour legacy User.coach FK and promote to CoachStudent
    if student.coach_id == coach.id:
        CoachStudent.objects.get_or_create(coach=coach, student=student, defaults={'active': True})
        return True

    return False


def student_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users_app:login')
        if not request.user.is_student:
            return redirect('coach:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def coach_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users_app:login')
        if not request.user.is_coach:
            return redirect('student:dashboard')
        if not request.user.is_approved:
            return redirect('users_app:awaiting_approval')
        return view_func(request, *args, **kwargs)
    return wrapper
