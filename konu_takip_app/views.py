import json

from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views import View

from exams_app.models import Subject
from users_app.decorators import coach_can_view_student, coach_required, student_required
from users_app.models import User

from .models import KonuTakipTopic
from .services import (
    build_flat_topics, build_topic_list,
    get_all_reviews_json, get_due_reviews_json, get_subject_sr_settings,
    submit_review, toggle_progress, toggle_subject_sr,
)


def _serialize_subjects(subjects):
    return [{'id': s.id, 'name': s.display_name} for s in subjects]


def _serialize_topics(subject, student):
    if not (subject and student):
        return [], {}, None
    topics_data, progress_json = build_topic_list(subject, student)
    return build_flat_topics(topics_data), progress_json, subject.id


_AYT_ALAN_MAP = {
    'SAY': {'AYT Matematik', 'AYT Fizik', 'AYT Kimya', 'AYT Biyoloji'},
    'EA':  {'AYT Matematik', 'AYT Türk Dili ve Edebiyatı'},
    'SOZ': {'AYT Türk Dili ve Edebiyatı', 'AYT Tarih 2', 'AYT Coğrafya 2', 'AYT Felsefe Grubu'},
    'DIL': {'AYT Yabancı Dil'},
}
_DEFAULT_AYT = _AYT_ALAN_MAP['SAY']  # blank alan → SAY subjects


def _subject_groups(student):
    """Return (tyt_subjects, ayt_subjects) for this student, AYT filtered by alan."""
    all_subjects = list(
        Subject.objects.filter(konu_takip_topics__isnull=False)
        .distinct()
        .order_by('name')
    )
    ayt_allowed = _AYT_ALAN_MAP.get(student.alan, _DEFAULT_AYT)
    tyt = [s for s in all_subjects if s.name.startswith('TYT ')]
    ayt = [s for s in all_subjects if s.name.startswith('AYT ') and s.name in ayt_allowed]
    return tyt, ayt


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


def _progress_response(progress):
    return {
        'ok': True,
        'started': progress.started,
        'finished': progress.finished,
        'next_review_at': progress.next_review_at.isoformat() if progress.next_review_at else None,
        'review_count': progress.review_count,
    }


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

        tyt_subjects, ayt_subjects = _subject_groups(selected_student) if selected_student else ([], [])
        exam_type = request.GET.get('exam_type', 'TYT')
        if exam_type not in ('TYT', 'AYT'):
            exam_type = 'TYT'
        subjects = tyt_subjects if exam_type == 'TYT' else ayt_subjects
        selected_subject = _resolve_subject(subjects, request.GET.get('subject'))

        flat_topics, progress_json, selected_subject_id = _serialize_topics(
            selected_subject, selected_student
        )

        all_reviews = get_all_reviews_json(selected_student) if selected_student else []
        sr_settings = get_subject_sr_settings(selected_student) if selected_student else {}
        qs_student = f'student={selected_student.id}&' if selected_student else ''
        return render(request, 'konu_takip/index.html', {
            'students': coached_students,
            'selected_student': selected_student,
            'is_coach_view': True,
            'qs_student': qs_student,
            'kt_cfg': json.dumps({
                'examType': exam_type,
                'tytSubjects': _serialize_subjects(tyt_subjects),
                'aytSubjects': _serialize_subjects(ayt_subjects),
                'selectedSubjectId': selected_subject_id,
                'flatTopics': flat_topics,
                'progress': progress_json,
                'toggleUrl': '/coach/konu-takip/toggle/',
                'apiUrl': '/coach/konu-takip/api/',
                'reviewUrl': '/coach/konu-takip/review/',
                'allReviewsApiUrl': '/coach/konu-takip/schedule/',
                'toggleSrUrl': '/coach/konu-takip/toggle-sr/',
                'studentId': selected_student.id if selected_student else None,
                'allReviews': all_reviews,
                'subjectSrSettings': sr_settings,
            }),
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

        quality = body.get('quality') or None
        progress = toggle_progress(student, topic.id, field, value, quality)
        return JsonResponse(_progress_response(progress))


@method_decorator(coach_required, name='dispatch')
class CoachKonuTakipApiView(View):
    def get(self, request):
        try:
            sid = int(request.GET.get('student_id') or 0)
        except (ValueError, TypeError):
            sid = 0

        if not sid:
            return JsonResponse({'error': 'student_id required'}, status=400)

        if not coach_can_view_student(request.user, sid):
            return JsonResponse({'error': 'forbidden'}, status=403)

        try:
            selected_student = User.objects.get(id=sid, role='student')
        except User.DoesNotExist:
            return JsonResponse({'error': 'student not found'}, status=400)

        tyt_subjects, ayt_subjects = _subject_groups(selected_student)
        exam_type = request.GET.get('exam_type', 'TYT')
        if exam_type not in ('TYT', 'AYT'):
            exam_type = 'TYT'
        subjects = tyt_subjects if exam_type == 'TYT' else ayt_subjects
        selected_subject = _resolve_subject(subjects, request.GET.get('subject_id'))

        flat_topics, progress_json, selected_subject_id = _serialize_topics(selected_subject, selected_student)
        sr_settings = get_subject_sr_settings(selected_student)
        return JsonResponse({
            'flat_topics': flat_topics,
            'progress': progress_json,
            'selected_subject_id': selected_subject_id,
            'sr_enabled': sr_settings.get(selected_subject_id, True),
        })


@method_decorator(coach_required, name='dispatch')
class CoachReviewView(View):
    def post(self, request):
        try:
            body = json.loads(request.body or b'{}')
            topic_id = int(body['topic_id'])
            quality = str(body.get('quality', '')).lower()
            student_id = int(body['student_id'])
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            return JsonResponse({'ok': False, 'error': 'invalid'}, status=400)

        if not coach_can_view_student(request.user, student_id):
            return HttpResponseForbidden()

        student = get_object_or_404(User, pk=student_id, role='student')
        progress = submit_review(student, topic_id, quality)
        if not progress:
            return JsonResponse({'ok': False, 'error': 'not found or invalid quality'}, status=400)

        return JsonResponse({
            'ok': True,
            'next_review_at': progress.next_review_at.isoformat() if progress.next_review_at else None,
            'review_count': progress.review_count,
        })


@method_decorator(coach_required, name='dispatch')
class CoachReviewsApiView(View):
    def get(self, request):
        try:
            sid = int(request.GET.get('student_id') or 0)
        except (ValueError, TypeError):
            sid = 0

        if not sid or not coach_can_view_student(request.user, sid):
            return JsonResponse({'error': 'forbidden'}, status=403)

        try:
            student = User.objects.get(id=sid, role='student')
        except User.DoesNotExist:
            return JsonResponse({'error': 'not found'}, status=404)

        return JsonResponse({'reviews': get_due_reviews_json(student)})


# ── Student views ─────────────────────────────────────────────────────────────

@method_decorator(student_required, name='dispatch')
class StudentKonuTakipView(View):
    def get(self, request):
        tyt_subjects, ayt_subjects = _subject_groups(request.user)
        exam_type = request.GET.get('exam_type', 'TYT')
        if exam_type not in ('TYT', 'AYT'):
            exam_type = 'TYT'
        subjects = tyt_subjects if exam_type == 'TYT' else ayt_subjects
        selected_subject = _resolve_subject(subjects, request.GET.get('subject'))

        flat_topics, progress_json, selected_subject_id = _serialize_topics(selected_subject, request.user)

        return render(request, 'konu_takip/index.html', {
            'is_coach_view': False,
            'qs_student': '',
            'kt_cfg': json.dumps({
                'examType': exam_type,
                'tytSubjects': _serialize_subjects(tyt_subjects),
                'aytSubjects': _serialize_subjects(ayt_subjects),
                'selectedSubjectId': selected_subject_id,
                'flatTopics': flat_topics,
                'progress': progress_json,
                'toggleUrl': '/student/konu-takip/toggle/',
                'apiUrl': '/student/konu-takip/api/',
                'reviewUrl': '/student/konu-takip/review/',
                'allReviewsApiUrl': '/student/konu-takip/schedule/',
                'toggleSrUrl': '/student/konu-takip/toggle-sr/',
                'studentId': None,
                'allReviews': get_all_reviews_json(request.user),
                'subjectSrSettings': get_subject_sr_settings(request.user),
            }),
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
        quality = body.get('quality') or None
        progress = toggle_progress(request.user, topic.id, field, value, quality)
        return JsonResponse(_progress_response(progress))


@method_decorator(student_required, name='dispatch')
class StudentKonuTakipApiView(View):
    def get(self, request):
        tyt_subjects, ayt_subjects = _subject_groups(request.user)
        exam_type = request.GET.get('exam_type', 'TYT')
        if exam_type not in ('TYT', 'AYT'):
            exam_type = 'TYT'
        subjects = tyt_subjects if exam_type == 'TYT' else ayt_subjects
        selected_subject = _resolve_subject(subjects, request.GET.get('subject_id'))

        flat_topics, progress_json, selected_subject_id = _serialize_topics(selected_subject, request.user)
        sr_settings = get_subject_sr_settings(request.user)
        return JsonResponse({
            'flat_topics': flat_topics,
            'progress': progress_json,
            'selected_subject_id': selected_subject_id,
            'sr_enabled': sr_settings.get(selected_subject_id, True),
        })


@method_decorator(student_required, name='dispatch')
class StudentReviewView(View):
    def post(self, request):
        try:
            body = json.loads(request.body or b'{}')
            topic_id = int(body['topic_id'])
            quality = str(body.get('quality', '')).lower()
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            return JsonResponse({'ok': False, 'error': 'invalid'}, status=400)

        progress = submit_review(request.user, topic_id, quality)
        if not progress:
            return JsonResponse({'ok': False, 'error': 'not found or invalid quality'}, status=400)

        return JsonResponse({
            'ok': True,
            'next_review_at': progress.next_review_at.isoformat() if progress.next_review_at else None,
            'review_count': progress.review_count,
        })


@method_decorator(student_required, name='dispatch')
class StudentReviewsApiView(View):
    def get(self, request):
        return JsonResponse({'reviews': get_due_reviews_json(request.user)})


@method_decorator(coach_required, name='dispatch')
class CoachToggleSrView(View):
    def post(self, request):
        try:
            body = json.loads(request.body or b'{}')
            student_id = int(body['student_id'])
            subject_id = int(body['subject_id'])
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            return JsonResponse({'ok': False, 'error': 'invalid'}, status=400)

        if not coach_can_view_student(request.user, student_id):
            return HttpResponseForbidden()

        student = get_object_or_404(User, pk=student_id, role='student')
        new_value = toggle_subject_sr(student, subject_id)
        return JsonResponse({'ok': True, 'sr_enabled': new_value, 'subject_id': subject_id})


@method_decorator(student_required, name='dispatch')
class StudentToggleSrView(View):
    def post(self, request):
        try:
            body = json.loads(request.body or b'{}')
            subject_id = int(body['subject_id'])
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            return JsonResponse({'ok': False, 'error': 'invalid'}, status=400)

        new_value = toggle_subject_sr(request.user, subject_id)
        return JsonResponse({'ok': True, 'sr_enabled': new_value, 'subject_id': subject_id})


@method_decorator(coach_required, name='dispatch')
class CoachAllReviewsApiView(View):
    def get(self, request):
        try:
            sid = int(request.GET.get('student_id') or 0)
        except (ValueError, TypeError):
            sid = 0

        if not sid or not coach_can_view_student(request.user, sid):
            return JsonResponse({'error': 'forbidden'}, status=403)

        try:
            student = User.objects.get(id=sid, role='student')
        except User.DoesNotExist:
            return JsonResponse({'error': 'not found'}, status=404)

        return JsonResponse({'reviews': get_all_reviews_json(student)})


@method_decorator(student_required, name='dispatch')
class StudentAllReviewsApiView(View):
    def get(self, request):
        return JsonResponse({'reviews': get_all_reviews_json(request.user)})
