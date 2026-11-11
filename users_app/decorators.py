import logging
from functools import wraps

from django.shortcuts import redirect

_log = logging.getLogger(__name__)


def coach_students(coach):
    """Students this coach may see and edit: the single source of truth for coach access.

    An active CoachStudent row grants access; so does the User.coach FK, which unlink and
    staff reassign keep in step with the link.
    """
    from django.db.models import Q
    from users_app.models import CoachStudent, User
    active_links = CoachStudent.objects.filter(coach=coach, active=True)
    return User.objects.filter(role='student').filter(
        Q(pk__in=active_links.values('student_id')) | Q(coach=coach)
    )


def coach_can_view_student(coach, student_id):
    return coach_students(coach).filter(pk=student_id).exists()


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


def staff_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users_app:login')
        if not request.user.is_staff:
            return redirect('/')
        return view_func(request, *args, **kwargs)
    return wrapper
