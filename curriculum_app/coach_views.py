from datetime import date

from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from users_app.decorators import coach_can_view_student, coach_required
from users_app.models import User

from .models import MacroPlan, MacroPlanBucket
from .services.engine import generate_macro_syllabus


@coach_required
def macro_plan_list(request):
    from users_app.models import CoachStudent
    student_filter = request.GET.get('student')

    qs = MacroPlan.objects.filter(coach=request.user).select_related('student')
    if student_filter:
        qs = qs.filter(student_id=student_filter)

    coached_students = User.objects.filter(
        student_coach_links__coach=request.user,
        student_coach_links__active=True,
        role='student',
    ).order_by('full_name')

    return render(request, 'coach/curriculum/macro_plan_list.html', {
        'plans': qs,
        'coached_students': coached_students,
        'student_filter': student_filter,
        'v2_shell': True,
        'shell_active': 'Müfredat',
    })


@coach_required
def macro_plan_create(request):
    from users_app.models import CoachStudent
    coached_students = User.objects.filter(
        student_coach_links__coach=request.user,
        student_coach_links__active=True,
        role='student',
    ).order_by('full_name')

    if request.method == 'POST':
        student_id  = request.POST.get('student_id')
        sinav_tipi  = request.POST.get('sinav_tipi', 'TYT')
        algorithm   = request.POST.get('algorithm', 'even')
        title       = request.POST.get('title', '').strip()

        if not student_id:
            messages.error(request, 'Bir öğrenci seçmelisiniz.')
            return redirect('curriculum:create')

        if not coach_can_view_student(request.user, int(student_id)):
            return HttpResponseForbidden()

        student = get_object_or_404(User, id=student_id, role='student')

        # Determine target date — prefer existing stored date; fall back to inline input
        if sinav_tipi == 'AYT':
            target_date = student.ayt_target_date
        else:
            target_date = student.tyt_target_date

        if not target_date:
            inline = request.POST.get('inline_target_date', '').strip()
            if not inline:
                messages.error(request, 'Sınav tarihi girilmedi.')
                return redirect('curriculum:create')
            from datetime import datetime
            try:
                target_date = datetime.strptime(inline, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, 'Geçersiz tarih formatı.')
                return redirect('curriculum:create')
            # Persist the inline date so the coach doesn't need to re-enter it next time
            if sinav_tipi == 'AYT':
                student.ayt_target_date = target_date
                student.save(update_fields=['ayt_target_date'])
            else:
                student.tyt_target_date = target_date
                student.save(update_fields=['tyt_target_date'])

        if target_date <= date.today():
            messages.error(request, 'Sınav tarihi geçmişte olamaz.')
            return redirect('curriculum:create')

        plan = MacroPlan.objects.create(
            coach=request.user,
            student=student,
            sinav_tipi=sinav_tipi,
            target_date=target_date,
            algorithm=algorithm,
            title=title or f'{student.full_name} — {sinav_tipi} Planı',
        )

        generate_macro_syllabus(plan)
        messages.success(request, f'"{plan.title}" planı oluşturuldu.')
        return redirect('curriculum:detail', pk=plan.pk)

    return render(request, 'coach/curriculum/macro_plan_create.html', {
        'coached_students': coached_students,
        'algo_choices': MacroPlan.ALGO_CHOICES,
        'v2_shell': True,
        'shell_active': 'Müfredat',
    })


@coach_required
def macro_plan_detail(request, pk):
    plan = get_object_or_404(MacroPlan, pk=pk, coach=request.user)
    buckets = (
        plan.buckets.all()
        .prefetch_related('topics__topic__subject')
    )
    return render(request, 'coach/curriculum/macro_plan_detail.html', {
        'plan': plan,
        'buckets': buckets,
        'v2_shell': True,
        'shell_active': 'Müfredat',
    })


@coach_required
def macro_plan_delete(request, pk):
    plan = get_object_or_404(MacroPlan, pk=pk, coach=request.user)
    if request.method == 'POST':
        title = plan.title
        plan.delete()
        messages.success(request, f'"{title}" planı silindi.')
        return redirect('curriculum:list')
    return redirect('curriculum:detail', pk=pk)


@coach_required
def macro_plan_regenerate(request, pk):
    if request.method != 'POST':
        return redirect('curriculum:detail', pk=pk)
    plan = get_object_or_404(MacroPlan, pk=pk, coach=request.user)
    generate_macro_syllabus(plan)
    messages.success(request, 'Plan yeniden oluşturuldu.')
    return redirect('curriculum:detail', pk=pk)


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
