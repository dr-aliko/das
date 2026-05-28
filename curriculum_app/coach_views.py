from datetime import date

from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from users_app.decorators import coach_can_view_student, coach_required
from users_app.models import User

from .models import MacroPlan, MacroPlanBucket, MacroPlanTopic, MacroPlanSkippedTopic
from .services.engine_v2 import generate_macro_syllabus_v2 as generate_macro_syllabus, create_empty_buckets


@coach_required
def macro_plan_list(request):
    """Redirects to the new editor. Old list page is no longer the main flow."""
    student_id = request.GET.get('student')
    if student_id:
        try:
            student_id = int(student_id)
            if coach_can_view_student(request.user, student_id):
                return redirect('curriculum:editor', student_id=student_id)
        except (ValueError, TypeError):
            pass
    return redirect('coach:dashboard')


@coach_required
def macro_plan_create(request):
    """Redirects to the new editor. Plan creation now happens auto on first editor open."""
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        if student_id:
            try:
                student_id = int(student_id)
                if coach_can_view_student(request.user, student_id):
                    return redirect('curriculum:editor', student_id=student_id)
            except (ValueError, TypeError):
                pass
    return redirect('coach:dashboard')


@coach_required
def macro_plan_detail(request, pk):
    """Redirects to the new editor. Old detail page is no longer the main flow."""
    plan = get_object_or_404(MacroPlan, pk=pk, coach=request.user)
    return redirect('curriculum:editor', student_id=plan.student_id)


@coach_required
def macro_plan_approve(request, pk):
    """POST: mark a DRAFT plan as APPROVED. Redirects back to editor."""
    plan = get_object_or_404(MacroPlan, pk=pk, coach=request.user)
    if request.method == 'POST' and plan.status == MacroPlan.STATUS_DRAFT:
        plan.status = MacroPlan.STATUS_APPROVED
        plan.save(update_fields=['status'])
        messages.success(request, f'"{plan.title}" planı onaylandı.')
    return redirect('curriculum:editor', student_id=plan.student_id)


@coach_required
def macro_plan_delete(request, pk):
    plan = get_object_or_404(MacroPlan, pk=pk, coach=request.user)
    if request.method == 'POST':
        title = plan.title
        plan.delete()
        messages.success(request, f'"{title}" planı silindi.')
        return redirect('coach:dashboard')
    return redirect('curriculum:editor', student_id=plan.student_id)


@coach_required
def macro_plan_regenerate(request, pk):
    plan = get_object_or_404(MacroPlan, pk=pk, coach=request.user)
    if request.method == 'POST':
        generate_macro_syllabus(plan)
        messages.success(request, 'Plan yeniden oluşturuldu.')
    return redirect('curriculum:editor', student_id=plan.student_id)


@coach_required
def set_student_exam_dates(request, student_id):
    """AJAX/POST: coach sets tyt_target_date / ayt_target_date for a student."""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    if not coach_can_view_student(request.user, student_id):
        return JsonResponse({'ok': False, 'error': 'Yetkisiz'}, status=403)

    student = get_object_or_404(User, id=student_id, role='student')

    tyt = request.POST.get('tyt_target_date') or None
    ayt = request.POST.get('ayt_target_date') or None

    update_fields = []
    if tyt is not None:
        student.tyt_target_date = tyt or None
        update_fields.append('tyt_target_date')
    if ayt is not None:
        student.ayt_target_date = ayt or None
        update_fields.append('ayt_target_date')

    if update_fields:
        student.save(update_fields=update_fields)

    return JsonResponse({
        'ok': True,
        'tyt_target_date': str(student.tyt_target_date) if student.tyt_target_date else '',
        'ayt_target_date': str(student.ayt_target_date) if student.ayt_target_date else '',
    })


# ─────────────────────────────────────────────────────────────────────────────
# EDITOR VIEWS
# ─────────────────────────────────────────────────────────────────────────────

def _get_or_create_primary_plan(coach, student):
    """Return the latest MacroPlan for this coach+student pair, creating a DRAFT if none exists."""
    plan = (
        MacroPlan.objects
        .filter(coach=coach, student=student)
        .order_by('-created_at')
        .first()
    )
    if plan is None:
        target_date = student.tyt_target_date or student.ayt_target_date
        if not target_date:
            return None, False
        sinav_tipi = 'BOTH' if (student.tyt_target_date and student.ayt_target_date) else (
            'TYT' if student.tyt_target_date else 'AYT'
        )
        plan = MacroPlan.objects.create(
            coach=coach,
            student=student,
            sinav_tipi=sinav_tipi,
            target_date=target_date,
            title=f'{student.full_name} — {sinav_tipi} Planı',
        )
        try:
            create_empty_buckets(plan)
        except Exception:
            pass
        return plan, True
    return plan, False


def _editor_capacity(plan):
    """Return (planned_topics, planned_hours, skipped_topics, total_hours) for the plan."""
    from django.db.models import Sum
    from exams_app.models import Topic
    planned_qs = MacroPlanTopic.objects.filter(bucket__plan=plan).select_related('topic')
    planned_topics = planned_qs.count()
    planned_hours = planned_qs.aggregate(h=Sum('topic__expected_hours'))['h'] or 0
    skipped_topics = plan.skipped_topics.count()
    return planned_topics, planned_hours, skipped_topics


@coach_required
def macro_plan_editor(request, student_id):
    """Full-page monthly roadmap editor for a student."""
    if not coach_can_view_student(request.user, student_id):
        return HttpResponseForbidden()

    student = get_object_or_404(User, id=student_id, role='student')
    plan, created = _get_or_create_primary_plan(request.user, student)

    if plan is None:
        messages.error(request, 'Bu öğrenci için sınav tarihi girilmemiş. Önce profil sayfasından tarih ekleyin.')
        return redirect('coach:student_detail', student_id=student_id)

    from exams_app.models import Subject, Topic
    buckets = (
        plan.buckets.all()
        .prefetch_related('topics__topic__subject')
    )

    # All subjects for the plan's sinav type
    # Exclude TYT umbrella groupings (name field includes exam-type prefix in DB)
    _TYT_UMBRELLA = {'TYT Sosyal Bilimler', 'TYT Fen Bilimleri'}
    exam_types = ['TYT', 'AYT'] if plan.sinav_tipi == 'BOTH' else [plan.sinav_tipi]
    subjects_tyt = list(
        Subject.objects.filter(exam_type='TYT', excluded_from_planning=False)
        .exclude(name__in=_TYT_UMBRELLA).order_by('name')
    ) if 'TYT' in exam_types else []
    subjects_ayt = list(Subject.objects.filter(exam_type='AYT', excluded_from_planning=False).order_by('name')) \
        if 'AYT' in exam_types else []

    # Already-placed topic IDs
    placed_ids = set(
        MacroPlanTopic.objects.filter(bucket__plan=plan).values_list('topic_id', flat=True)
    )
    skipped_ids = set(plan.skipped_topics.values_list('topic_id', flat=True))
    excluded_from_pool = placed_ids | skipped_ids

    # Pool: topics not yet placed and not skipped, grouped by subject
    # Also exclude topics belonging to TYT umbrella subjects
    all_plan_topics = list(
        Topic.objects.filter(
            subject__exam_type__in=exam_types,
            subject__excluded_from_planning=False,
            excluded_from_planning=False,
        ).exclude(subject__name__in=_TYT_UMBRELLA)
        .select_related('subject').prefetch_related('depends_on')
        .order_by('subject__name', 'order_index', 'sub_category', 'name')
    )
    pool_by_subject: dict[int, list] = {}
    for t in all_plan_topics:
        if t.id not in excluded_from_pool:
            pool_by_subject.setdefault(t.subject_id, []).append(t)

    # Metadata for JS (D&D validation)
    import json as _json
    topic_meta_json = _json.dumps({
        str(t.id): {
            'name': t.name,
            'subject': t.subject.display_name,
            'hours': t.expected_hours or 0,
            'baglayici': t.is_baglayici,
            'prereqs': [str(p.id) for p in t.depends_on.all()],
        }
        for t in all_plan_topics
    })
    bucket_meta_json = _json.dumps([
        {
            'id': b.pk,
            'label': b.label,
            'kind': b.window_kind,
        }
        for b in plan.buckets.all()
    ])

    skipped = list(
        plan.skipped_topics.select_related('topic__subject').order_by('topic__subject__name', 'topic__name')
    )
    risk_alerts = plan.risk_alerts.filter(is_dismissed=False).order_by('-severity', 'kind')

    planned_topics, planned_hours, skipped_count = _editor_capacity(plan)
    unplanned_count = len([t for t in all_plan_topics if t.id not in placed_ids and t.id not in skipped_ids])

    # Safe Alpine defaults — computed server-side to avoid any client-side ternary issues
    default_pool_type = 'AYT' if plan.sinav_tipi == 'AYT' else 'TYT'
    if default_pool_type == 'TYT' and subjects_tyt:
        default_subject_id = subjects_tyt[0].id
    elif subjects_ayt:
        default_subject_id = subjects_ayt[0].id
    else:
        default_subject_id = 0

    return render(request, 'coach/curriculum/macro_plan_editor.html', {
        'plan':               plan,
        'student':            student,
        'buckets':            buckets,
        'subjects_tyt':       subjects_tyt,
        'subjects_ayt':       subjects_ayt,
        'pool_by_subject':    pool_by_subject,
        'skipped':            skipped,
        'risk_alerts':        risk_alerts,
        'planned_topics':     planned_topics,
        'planned_hours':      planned_hours,
        'skipped_count':      skipped_count,
        'unplanned_count':    unplanned_count,
        'topic_meta_json':    topic_meta_json,
        'bucket_meta_json':   bucket_meta_json,
        'default_pool_type':  default_pool_type,
        'default_subject_id': default_subject_id,
        'v2_shell': True,
        'shell_active': 'Öğrenciler',
    })


@coach_required
def editor_move_topic(request, pk):
    """POST {topic_id, target: 'pool'|'bucket:<id>'}. Marks moved entries is_manual=True."""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    plan = get_object_or_404(MacroPlan, pk=pk, coach=request.user)
    topic_id = request.POST.get('topic_id')
    target   = request.POST.get('target', '').strip()

    if not topic_id or not target:
        return JsonResponse({'ok': False, 'error': 'Eksik parametre'}, status=400)

    from exams_app.models import Topic
    topic = get_object_or_404(Topic, pk=topic_id)

    # Validate topic belongs to this plan's sinav scope
    exam_types = ['TYT', 'AYT'] if plan.sinav_tipi == 'BOTH' else [plan.sinav_tipi]
    if topic.subject.exam_type not in exam_types:
        return JsonResponse({'ok': False, 'error': 'Konu bu plana ait değil'}, status=400)

    # Remove from any existing bucket first
    MacroPlanTopic.objects.filter(bucket__plan=plan, topic=topic).delete()
    # Also remove from skipped in case it was there
    MacroPlanSkippedTopic.objects.filter(plan=plan, topic=topic).delete()

    if target != 'pool':
        if not target.startswith('bucket:'):
            return JsonResponse({'ok': False, 'error': 'Geçersiz hedef'}, status=400)
        try:
            bucket_id = int(target.split(':')[1])
        except (IndexError, ValueError):
            return JsonResponse({'ok': False, 'error': 'Geçersiz bucket id'}, status=400)
        bucket = get_object_or_404(MacroPlanBucket, pk=bucket_id, plan=plan)
        next_order = MacroPlanTopic.objects.filter(bucket=bucket).count()
        MacroPlanTopic.objects.create(bucket=bucket, topic=topic, order=next_order, is_manual=True)

    planned_topics, planned_hours, skipped_count = _editor_capacity(plan)
    return JsonResponse({'ok': True, 'planned_topics': planned_topics, 'planned_hours': planned_hours})


@coach_required
def editor_skip_topic(request, pk):
    """POST {topic_id, reason?}. Moves topic to Halledilmiş / Gerek Yok zone."""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    plan = get_object_or_404(MacroPlan, pk=pk, coach=request.user)
    topic_id = request.POST.get('topic_id')
    reason   = request.POST.get('reason', 'Gerek Yok')[:120]

    if not topic_id:
        return JsonResponse({'ok': False, 'error': 'Eksik parametre'}, status=400)

    from exams_app.models import Topic
    topic = get_object_or_404(Topic, pk=topic_id)

    MacroPlanTopic.objects.filter(bucket__plan=plan, topic=topic).delete()
    MacroPlanSkippedTopic.objects.get_or_create(plan=plan, topic=topic, defaults={'reason': reason})

    planned_topics, planned_hours, skipped_count = _editor_capacity(plan)
    return JsonResponse({
        'ok': True,
        'planned_topics': planned_topics,
        'planned_hours': planned_hours,
        'skipped_count': skipped_count,
    })


@coach_required
def editor_unskip_topic(request, pk):
    """POST {topic_id}. Restores topic from Halledilmiş back to the pool."""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    plan = get_object_or_404(MacroPlan, pk=pk, coach=request.user)
    topic_id = request.POST.get('topic_id')

    if not topic_id:
        return JsonResponse({'ok': False, 'error': 'Eksik parametre'}, status=400)

    MacroPlanSkippedTopic.objects.filter(plan=plan, topic_id=topic_id).delete()

    planned_topics, planned_hours, skipped_count = _editor_capacity(plan)
    return JsonResponse({
        'ok': True,
        'planned_topics': planned_topics,
        'planned_hours': planned_hours,
        'skipped_count': skipped_count,
    })


@coach_required
def macro_plan_to_weekly(request, pk):
    """POST: regenerate weekly distribution from approved monthly plan."""
    plan = get_object_or_404(MacroPlan, pk=pk, coach=request.user)

    if request.method != 'POST':
        return redirect('curriculum:editor', student_id=plan.student_id)

    if plan.status != MacroPlan.STATUS_APPROVED:
        messages.error(request, 'Planı onayladıktan sonra haftalık planı oluşturabilirsiniz.')
        return redirect('curriculum:editor', student_id=plan.student_id)

    from curriculum_app.services.segments import determine_segment
    from curriculum_app.services.period import determine_period
    from curriculum_app.services.weekly_mixer import create_week_buckets
    from curriculum_app.services.weekly_distributor import distribute_bucket_into_weeks

    segment = determine_segment(plan.student)
    period  = determine_period(plan.months_remaining)
    from exams_app.models import StudentTask
    mastered_ids = set(
        StudentTask.objects.filter(student=plan.student, is_completed=True, repetition_count__gte=2)
        .values_list('topic_id', flat=True)
    )
    from django.db.models import Sum
    from exams_app.models import ExamTopicError
    rows = (ExamTopicError.objects.filter(exam__student=plan.student)
            .values('topic_id').annotate(e=Sum('wrong_count') + Sum('blank_count')))
    weakness_ids = {r['topic_id'] for r in rows if r['e'] >= 3}

    for bucket in plan.buckets.all():
        bucket.weeks.all().delete()
        create_week_buckets(bucket, period, segment)
        distribute_bucket_into_weeks(bucket, weakness_ids, mastered_ids)

    messages.success(request, 'Haftalık plan güncellendi.')
    return redirect('curriculum:editor', student_id=plan.student_id)
