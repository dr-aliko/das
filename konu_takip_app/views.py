import json

from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views import View

from exams_app.models import Subject
from users_app.decorators import coach_can_view_student, coach_required, student_required
from users_app.models import User

from .models import KonuTakipTopic
from .services import build_topic_list, toggle_progress


def _subjects_with_topics():
    return list(
        Subject.objects.filter(konu_takip_topics__isnull=False)
        .distinct()
        .order_by('name')
    )


def _resolve_subject(subjects, subject_id_str):
    try:
        sid = int(subject_id_str or 0)
        if sid:
            match = next((s for s in subjects if s.id == sid), None)
            if match:
                return match
    except (ValueError, TypeError):
        pass
    return subjects[0] if subjects else None


# ── Coach views ───────────────────────────────────────────────────────────────

@method_decorator(coach_required, name='dispatch')
class CoachKonuTakipView(View):
    def get(self, request):
        coached_students = list(
            User.objects.filter(role='student', coach=request.user).order_by('full_name')
        )

        selected_student = None
        try:
            sid = int(request.GET.get('student', 0))
            if sid and coach_can_view_student(request.user, sid):
                selected_student = User.objects.get(id=sid, role='student')
        except (ValueError, User.DoesNotExist):
            pass
        if not selected_student and coached_students:
            selected_student = coached_students[0]

        subjects = _subjects_with_topics()
        selected_subject = _resolve_subject(subjects, request.GET.get('subject'))

        topics_data, progress_json = [], {}
        if selected_student and selected_subject:
            topics_data, progress_json = build_topic_list(selected_subject, selected_student)

        return render(request, 'konu_takip/index.html', {
            'students': coached_students,
            'selected_student': selected_student,
            'subjects': subjects,
            'selected_subject': selected_subject,
            'topics_data': topics_data,
            'progress_json': json.dumps(progress_json),
            'toggle_url': '/coach/konu-takip/toggle/',
            'is_coach_view': True,
        })


@method_decorator(coach_required, name='dispatch')
class CoachToggleView(View):
    def post(self, request):
        try:
            body = json.loads(request.body or b'{}')
            topic_id = int(body['topic_id'])
            field = body['field']
            value = bool(body['value'])
            student_id = int(body['student_id'])
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            return JsonResponse({'ok': False, 'error': 'invalid'}, status=400)

        if field not in ('started', 'finished'):
            return JsonResponse({'ok': False, 'error': 'invalid field'}, status=400)

        if not coach_can_view_student(request.user, student_id):
            return HttpResponseForbidden()

        topic = get_object_or_404(KonuTakipTopic, pk=topic_id, checkable=True)
        student = get_object_or_404(User, pk=student_id, role='student')

        progress = toggle_progress(student, topic.id, field, value)
        return JsonResponse({'ok': True, 'started': progress.started, 'finished': progress.finished})


# ── Student views ─────────────────────────────────────────────────────────────

@method_decorator(student_required, name='dispatch')
class StudentKonuTakipView(View):
    def get(self, request):
        subjects = _subjects_with_topics()
        selected_subject = _resolve_subject(subjects, request.GET.get('subject'))

        topics_data, progress_json = [], {}
        if selected_subject:
            topics_data, progress_json = build_topic_list(selected_subject, request.user)

        return render(request, 'konu_takip/index.html', {
            'subjects': subjects,
            'selected_subject': selected_subject,
            'topics_data': topics_data,
            'progress_json': json.dumps(progress_json),
            'toggle_url': '/student/konu-takip/toggle/',
            'is_coach_view': False,
        })


@method_decorator(student_required, name='dispatch')
class StudentToggleView(View):
    def post(self, request):
        try:
            body = json.loads(request.body or b'{}')
            topic_id = int(body['topic_id'])
            field = body['field']
            value = bool(body['value'])
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            return JsonResponse({'ok': False, 'error': 'invalid'}, status=400)

        if field not in ('started', 'finished'):
            return JsonResponse({'ok': False, 'error': 'invalid field'}, status=400)

        topic = get_object_or_404(KonuTakipTopic, pk=topic_id, checkable=True)
        progress = toggle_progress(request.user, topic.id, field, value)
        return JsonResponse({'ok': True, 'started': progress.started, 'finished': progress.finished})
