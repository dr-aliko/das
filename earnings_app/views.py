import csv
import logging
from datetime import date

from django.contrib.auth import get_user_model
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from users_app.decorators import staff_required

from .models import EarningConfig, EarningRow, ManualPaymentRecord
from .services import (
    approve_earning,
    create_earning_for_manual_record,
    mark_paid,
    void_earning,
)

_log = logging.getLogger(__name__)
User = get_user_model()


# ── Panel (staff) ─────────────────────────────────────────────────────────────

@staff_required
def panel_kazanclar_list(request):
    rows = (
        EarningRow.objects
        .select_related('coach', 'student', 'order', 'order__plan', 'manual_record')
        .order_by('-coverage_start', '-created_at')
    )

    status_filter = request.GET.get('status', '')
    coach_filter  = request.GET.get('coach', '')
    month_filter  = request.GET.get('month', '')

    if status_filter:
        rows = rows.filter(status=status_filter)
    if coach_filter:
        rows = rows.filter(coach_id=coach_filter)
    if month_filter:
        try:
            y, m = month_filter.split('-')
            rows = rows.filter(coverage_start__year=y, coverage_start__month=m)
        except (ValueError, AttributeError):
            month_filter = ''

    rows = list(rows[:500])

    totals = _compute_totals(rows)
    config = EarningConfig.get()
    coaches = User.objects.filter(role='coach', is_active=True).order_by('full_name')

    return render(request, 'earnings/panel_kazanclar.html', {
        'rows':          rows,
        'totals':        totals,
        'config':        config,
        'coaches':       coaches,
        'status_filter': status_filter,
        'coach_filter':  coach_filter,
        'month_filter':  month_filter,
        'status_choices': EarningRow.STATUS_CHOICES,
    })


def _compute_totals(rows):
    non_void = [r for r in rows if r.status != EarningRow.STATUS_VOID]
    paid     = [r for r in rows if r.status == EarningRow.STATUS_PAID]
    approved = [r for r in rows if r.status == EarningRow.STATUS_APPROVED]
    released = [r for r in rows if r.status == EarningRow.STATUS_RELEASED]
    held     = [r for r in rows if r.status == EarningRow.STATUS_HELD]

    # Gross collected = sum of order.amount_kurus for unique non-void orders
    seen_orders = set()
    gross = 0
    for r in non_void:
        if r.order_id and r.order_id not in seen_orders:
            seen_orders.add(r.order_id)
            gross += r.order.amount_kurus if r.order else 0

    coach_share = sum(r.pool_kurus for r in non_void if r.kind == EarningRow.KIND_EARNING)
    vagus_share = gross - coach_share

    return {
        'gross_collected':   gross,
        'coach_share_pool':  coach_share,
        'vagus_share':       vagus_share,
        'paid_amount':       sum(r.amount_kurus for r in paid),
        'approved_amount':   sum(r.amount_kurus for r in approved),
        'released_amount':   sum(r.amount_kurus for r in released),
        'held_count':        len(held),
        'held_pool':         sum(r.pool_kurus for r in held),
    }


@staff_required
@require_POST
def panel_kazanclar_approve(request, pk):
    row = get_object_or_404(EarningRow, pk=pk)
    try:
        approve_earning(row, request.user)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    return redirect(request.META.get('HTTP_REFERER', 'earnings_panel:list'))


@staff_required
@require_POST
def panel_kazanclar_mark_paid(request, pk):
    row = get_object_or_404(EarningRow, pk=pk)
    payout_ref = request.POST.get('payout_ref', '').strip()
    try:
        mark_paid(row, request.user, payout_ref=payout_ref)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    return redirect(request.META.get('HTTP_REFERER', 'earnings_panel:list'))


@staff_required
@require_POST
def panel_kazanclar_void(request, pk):
    row = get_object_or_404(EarningRow, pk=pk)
    reason = request.POST.get('reason', '').strip()
    try:
        void_earning(row, request.user, reason=reason)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    return redirect(request.META.get('HTTP_REFERER', 'earnings_panel:list'))


@staff_required
@require_POST
def panel_manuel_odeme_create(request):
    errors = []

    student_id     = request.POST.get('student_id', '').strip()
    coach_id       = request.POST.get('coach_id', '').strip()
    amount_str     = request.POST.get('amount_kurus', '').strip()
    pool_str       = request.POST.get('coach_pool_kurus', '').strip()
    date_str       = request.POST.get('date', '').strip()
    days_str       = request.POST.get('days', '').strip()
    note           = request.POST.get('note', '').strip()

    student = None
    coach   = None

    try:
        student = User.objects.get(pk=student_id, role='student')
    except (User.DoesNotExist, ValueError):
        errors.append('Geçerli bir öğrenci seçin.')

    try:
        coach = User.objects.get(pk=coach_id, role='coach')
    except (User.DoesNotExist, ValueError):
        errors.append('Geçerli bir koç seçin.')

    try:
        amount_kurus = int(amount_str)
        if amount_kurus <= 0:
            raise ValueError
    except (ValueError, TypeError):
        errors.append('Geçerli bir ödeme tutarı girin (kuruş, pozitif tam sayı).')
        amount_kurus = None

    try:
        pool_kurus = int(pool_str)
        if pool_kurus <= 0:
            raise ValueError
    except (ValueError, TypeError):
        errors.append('Geçerli bir koç havuzu tutarı girin.')
        pool_kurus = None

    try:
        payment_date = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        errors.append('Geçerli bir tarih girin (YYYY-AA-GG).')
        payment_date = None

    try:
        days = int(days_str)
        if days <= 0:
            raise ValueError
    except (ValueError, TypeError):
        errors.append('Geçerli bir süre girin (pozitif tam sayı gün).')
        days = None

    if not errors:
        record = ManualPaymentRecord.objects.create(
            student=student,
            coach=coach,
            amount_kurus=amount_kurus,
            coach_pool_kurus=pool_kurus,
            date=payment_date,
            days=days,
            note=note,
            created_by=request.user,
        )
        create_earning_for_manual_record(record)

    if errors:
        rows    = list(EarningRow.objects.select_related('coach', 'student', 'order').order_by('-coverage_start')[:500])
        coaches = User.objects.filter(role='coach', is_active=True).order_by('full_name')
        students = User.objects.filter(role='student', is_active=True).order_by('full_name')
        return render(request, 'earnings/panel_kazanclar.html', {
            'rows':           rows,
            'totals':         _compute_totals(rows),
            'config':         EarningConfig.get(),
            'coaches':        coaches,
            'students':       students,
            'status_choices': EarningRow.STATUS_CHOICES,
            'form_errors':    errors,
            'show_form':      True,
        })

    return redirect('earnings_panel:list')


@staff_required
def panel_kazanclar_export_csv(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="kazanclar.csv"'
    response.write('﻿')  # BOM for Excel

    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Koç', 'Öğrenci', 'Sipariş', 'Kapsam Başlangıç', 'Kapsam Bitiş',
        'Dönem Gün', 'Koç Gün', 'Havuz (kr)', 'Tutar (kr)', 'Tür', 'Durum',
        'Boşluk Fallback', 'Ödeme Ref', 'Onay Tarihi', 'Ödeme Tarihi',
    ])

    rows = (
        EarningRow.objects
        .select_related('coach', 'student', 'order')
        .order_by('-coverage_start')
        [:5000]
    )

    status_filter = request.GET.get('status', '')
    coach_filter  = request.GET.get('coach', '')
    month_filter  = request.GET.get('month', '')
    if status_filter:
        rows = rows.filter(status=status_filter)
    if coach_filter:
        rows = rows.filter(coach_id=coach_filter)
    if month_filter:
        try:
            y, m = month_filter.split('-')
            rows = rows.filter(coverage_start__year=y, coverage_start__month=m)
        except (ValueError, AttributeError):
            pass

    for r in rows:
        writer.writerow([
            r.pk,
            r.coach.full_name if r.coach else '',
            r.student.full_name if r.student else '',
            r.order_id or '',
            r.coverage_start,
            r.coverage_end,
            r.period_days,
            r.coach_days,
            r.pool_kurus,
            r.amount_kurus,
            r.get_kind_display(),
            r.get_status_display(),
            'Evet' if r.gap_fallback else 'Hayır',
            r.payout_ref,
            r.approved_at.date() if r.approved_at else '',
            r.paid_at.date() if r.paid_at else '',
        ])

    return response


# ── Coach ─────────────────────────────────────────────────────────────────────

def coach_kazanclar(request):
    from django.contrib.auth.decorators import login_required

    if not request.user.is_authenticated:
        return redirect('users_app:login')
    if not request.user.is_coach:
        return redirect('/')

    rows = (
        EarningRow.objects
        .filter(coach=request.user)
        .select_related('student', 'order', 'order__plan')
        .order_by('-coverage_start', '-created_at')
    )

    status_filter = request.GET.get('status', '')
    if status_filter:
        rows = rows.filter(status=status_filter)

    rows = list(rows[:300])

    paid_total     = sum(r.amount_kurus for r in rows if r.status == EarningRow.STATUS_PAID)
    approved_total = sum(r.amount_kurus for r in rows if r.status == EarningRow.STATUS_APPROVED)
    released_total = sum(r.amount_kurus for r in rows if r.status == EarningRow.STATUS_RELEASED)

    return render(request, 'earnings/coach_kazanclar.html', {
        'rows':           rows,
        'status_filter':  status_filter,
        'status_choices': EarningRow.STATUS_CHOICES,
        'paid_total':     paid_total,
        'approved_total': approved_total,
        'released_total': released_total,
    })
