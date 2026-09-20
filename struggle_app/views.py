import json

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from exams_app.models import Subject
from konu_takip_app.alan_utils import struggle_subject_groups
from konu_takip_app.models import KonuTakipTopic
from users_app.decorators import coach_can_view_student, coach_required, student_required

from .models import StudentStruggleQuestion
from .services import submit_struggle_review

_ALLOWED_MIME = frozenset({'image/jpeg', 'image/png', 'image/webp', 'image/gif'})
_MAX_SIZE = 5 * 1024 * 1024  # 5 MB


def _validate_image(f):
    """Return error string or None if the uploaded file is a valid image."""
    if f.size > _MAX_SIZE:
        return "Görsel 5 MB'dan büyük olamaz."
    if f.content_type not in _ALLOWED_MIME:
        return "Yalnızca JPEG, PNG, WebP veya GIF yükleyebilirsiniz."
    try:
        from PIL import Image
        img = Image.open(f)
        img.verify()
        f.seek(0)
    except Exception:
        return "Geçersiz görsel dosyası."
    return None


def _question_json(q):
    return {
        'id': q.id,
        'subject_name': q.subject.display_name,
        'topic_name': q.topic.name if q.topic else None,
        'question_image_url': q.question_image.url if q.question_image else None,
        'question_text': q.question_text,
        'solution_image_url': q.solution_image.url if q.solution_image else None,
        'solution_text': q.solution_text,
        'notes': q.notes,
        'next_review_at': q.next_review_at.isoformat() if q.next_review_at else None,
        'review_count': q.review_count,
        'ease_factor': q.ease_factor,
        'created_at': q.created_at.isoformat(),
        'subject_id': q.subject_id,
    }


# ── Student views ─────────────────────────────────────────────────────────────

@method_decorator(student_required, name='dispatch')
class StudentStruggleIndexView(View):
    def get(self, request):
        tyt_subjects, ayt_subjects = struggle_subject_groups(request.user)

        now = timezone.now()
        due_qs = list(
            StudentStruggleQuestion.objects
            .filter(student=request.user, next_review_at__lte=now)
            .select_related('subject', 'topic')
            .order_by('next_review_at')
        )
        all_qs = list(
            StudentStruggleQuestion.objects
            .filter(student=request.user)
            .select_related('subject', 'topic')
            .order_by('next_review_at', '-created_at')
        )

        due_json = [_question_json(q) for q in due_qs]
        all_json = [_question_json(q) for q in all_qs]

        tyt_subjects_json = [{'id': s.id, 'name': s.display_name} for s in tyt_subjects]
        ayt_subjects_json = [{'id': s.id, 'name': s.display_name} for s in ayt_subjects]

        return render(request, 'struggle/index.html', {
            'due_json': json.dumps(due_json),
            'all_json': json.dumps(all_json),
            'tyt_subjects_json': json.dumps(tyt_subjects_json),
            'ayt_subjects_json': json.dumps(ayt_subjects_json),
            'due_count': len(due_qs),
            'total_count': len(all_qs),
        })


@method_decorator(student_required, name='dispatch')
class StudentStruggleAddView(View):
    def post(self, request):
        subject_id = request.POST.get('subject_id', '').strip()
        topic_id   = request.POST.get('topic_id', '').strip() or None
        notes      = request.POST.get('notes', '').strip()
        q_img      = request.FILES.get('question_image')
        s_img      = request.FILES.get('solution_image') or None
        q_text     = request.POST.get('question_text', '').strip()
        s_text     = request.POST.get('solution_text', '').strip()

        if not subject_id:
            return JsonResponse({'ok': False, 'error': 'Ders seçilmedi.'}, status=400)

        if q_img and q_text:
            return JsonResponse(
                {'ok': False, 'error': 'Görsel veya metin yöntemlerinden yalnızca birini kullanın.'},
                status=400,
            )
        if not q_img and not q_text:
            return JsonResponse(
                {'ok': False, 'error': 'Soru görseli veya soru metni gerekli.'},
                status=400,
            )

        if q_img:
            err = _validate_image(q_img)
            if err:
                return JsonResponse({'ok': False, 'error': err}, status=400)
        if s_img:
            err = _validate_image(s_img)
            if err:
                return JsonResponse({'ok': False, 'error': err}, status=400)

        try:
            subject = Subject.objects.get(id=int(subject_id))
        except (Subject.DoesNotExist, ValueError):
            return JsonResponse({'ok': False, 'error': 'Geçersiz ders.'}, status=400)

        topic = None
        if topic_id:
            try:
                topic = KonuTakipTopic.objects.get(
                    id=int(topic_id), subject=subject, checkable=True
                )
            except (KonuTakipTopic.DoesNotExist, ValueError):
                topic = None

        q = StudentStruggleQuestion.objects.create(
            student=request.user,
            subject=subject,
            topic=topic,
            question_image=q_img or None,
            question_text=q_text,
            solution_image=s_img,
            solution_text=s_text,
            notes=notes,
            next_review_at=timezone.now(),
            current_interval_days=1,
            ease_factor=2.5,
            review_count=0,
        )
        return JsonResponse({'ok': True, 'question': _question_json(q)})


@method_decorator(student_required, name='dispatch')
class StudentStruggleDeleteView(View):
    def post(self, request, pk):
        try:
            q = StudentStruggleQuestion.objects.get(pk=pk, student=request.user)
        except StudentStruggleQuestion.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'not found'}, status=404)
        if q.question_image:
            q.question_image.delete(save=False)
        if q.solution_image:
            q.solution_image.delete(save=False)
        q.delete()
        return JsonResponse({'ok': True})


@method_decorator(student_required, name='dispatch')
class StudentStruggleReviewView(View):
    def post(self, request):
        try:
            body       = json.loads(request.body or b'{}')
            question_id = int(body['question_id'])
            quality     = str(body.get('quality', '')).lower()
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            return JsonResponse({'ok': False, 'error': 'invalid'}, status=400)

        q = submit_struggle_review(request.user, question_id, quality)
        if not q:
            return JsonResponse({'ok': False, 'error': 'not found or invalid quality'}, status=400)

        return JsonResponse({
            'ok': True,
            'next_review_at': q.next_review_at.isoformat(),
            'review_count': q.review_count,
            'interval_days': q.current_interval_days,
        })


@method_decorator(student_required, name='dispatch')
class StudentStruggleTopicsApiView(View):
    """Return leaf topics for a given subject_id — used by the add-form topic dropdown."""
    def get(self, request):
        try:
            subject_id = int(request.GET.get('subject_id', 0))
        except (ValueError, TypeError):
            return JsonResponse({'topics': []})

        topics = list(
            KonuTakipTopic.objects
            .filter(subject_id=subject_id, checkable=True)
            .order_by('order', 'name')
            .values('id', 'name')
        )
        return JsonResponse({'topics': topics})


# ── Coach read-only stats view ────────────────────────────────────────────────

def coach_struggle_stats(coach, student):
    """
    Return aggregate struggle stats for one student as a list of dicts,
    sorted by subject name. Used by CoachKonuTakipView template.
    No image URLs or individual question access — aggregates only.
    """
    from django.db.models import Count, Q

    now = timezone.now()
    rows = (
        StudentStruggleQuestion.objects
        .filter(student=student)
        .values('subject__name')
        .annotate(
            total=Count('id'),
            due=Count('id', filter=Q(next_review_at__lte=now)),
        )
        .order_by('subject__name')
    )
    return list(rows)
