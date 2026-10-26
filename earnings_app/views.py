import csv
import logging
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from users_app.decorators import staff_required
from users_app.models import CoachProfile

from .models import EarningConfig, EarningRow, ManualPaymentRecord
from .services import (
    approve_earning,
    create_earning_for_manual_record,
    mark_paid,
    void_earning,
)

_log = logging.getLogger(__name__)
User = get_user_model()


def _live_days_for_held(held_rows):
    """Return {row.pk: live_coach_days} for a list of HELD EarningRow objects.

    Mirrors the interval-log algorithm in coach_kazanclar but works across
    multiple coaches, so both the staff panel and the coach view can use it.
    """
    if not held_rows:
        return {}

    from django.utils.timezone import localtime, now as tz_now
    from users_app.models import CoachStudentInterval

    today    = localtime(tz_now()).date()
    tomorrow = today + timedelta(days=1)

    coach_ids   = {r.coach_id   for r in held_rows}
    student_ids = {r.student_id for r in held_rows}

    ivs_by_key = {}
    for iv in CoachStudentInterval.objects.filter(
        coach_id__in=coach_ids,
        student_id__in=student_ids,
    ):
        ivs_by_key.setdefault((iv.coach_id, iv.student_id), []).append(iv)

    result = {}
    for r in held_rows:
        total = 0
        for iv in ivs_by_key.get((r.coach_id, r.student_id), []):
            iv_start  = localtime(iv.started_at).date()
            # Open (active) interval — exclusive upper bound is tomorrow so today counts
            iv_end    = tomorrow if iv.ended_at is None else localtime(iv.ended_at).date()
            seg_start = max(iv_start, r.coverage_start)
            seg_end   = min(iv_end, tomorrow)
            d = (seg_end - seg_start).days
            if d > 0:
                total += d
        result[r.pk] = min(total, r.period_days)
    return result


# ── Panel (staff) ─────────────────────────────────────────────────────────────

@staff_required
def panel_kazanclar_list(request):
    filtre = request.GET.get('filtre', '').strip()
    filtre_label = ''
    filtre_count = 0

    if filtre == 'earnings-ready':
        from users_app.panel_badges import qs_earnings
        rows = list(qs_earnings()[:500])
        filtre_label = 'Ödeme bekleyen kazançlar'
        filtre_count = len(rows)
        status_filter = ''
        coach_filter  = ''
        month_filter  = ''
    else:
        if filtre:
            filtre = ''
        rows = (
            EarningRow.objects
            .select_related('coach', 'student', 'order', 'order__plan', 'manual_record')
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

        if not status_filter and not coach_filter and not month_filter:
            from django.db.models import Case, IntegerField, Value, When
            rows = rows.annotate(_ready=Case(
                When(status__in=[EarningRow.STATUS_RELEASED, EarningRow.STATUS_APPROVED], then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )).order_by('_ready', '-coverage_start', '-created_at')
        else:
            rows = rows.order_by('-coverage_start', '-created_at')

        rows = list(rows[:500])

    # Patch coach_days on HELD rows with a live recalculation from the interval log.
    # This is an in-memory attribute override — nothing is written to the database.
    held_rows = [r for r in rows if r.status == EarningRow.STATUS_HELD]
    live_days = _live_days_for_held(held_rows)
    for r in held_rows:
        r.coach_days = live_days.get(r.pk, r.coach_days)

    totals = _compute_totals(rows)
    config = EarningConfig.get()
    coaches = User.objects.filter(role='coach', is_active=True).order_by('full_name')

    coach_ids = {r.coach_id for r in rows if r.coach_id}
    profiles = CoachProfile.objects.filter(user_id__in=coach_ids, iban__gt='').values('user_id', 'iban')
    coach_iban_map = {p['user_id']: p['iban'] for p in profiles}

    return render(request, 'earnings/panel_kazanclar.html', {
        'rows':           rows,
        'totals':         totals,
        'config':         config,
        'coaches':        coaches,
        'status_filter':  status_filter,
        'coach_filter':   coach_filter,
        'month_filter':   month_filter,
        'status_choices': EarningRow.STATUS_CHOICES,
        'coach_iban_map': coach_iban_map,
        'filtre':         filtre,
        'filtre_label':   filtre_label,
        'filtre_count':   filtre_count,
        'active_section': 'earnings',
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

    coach_share = sum(
        (r.pool_kurus if r.status == EarningRow.STATUS_HELD else r.amount_kurus)
        for r in non_void
        if r.kind == EarningRow.KIND_EARNING
    )
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
    from users_app.panel_badges import invalidate_panel_badges
    transaction.on_commit(lambda: invalidate_panel_badges('pbadge:earnings'))
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
    from users_app.panel_badges import invalidate_panel_badges
    transaction.on_commit(lambda: invalidate_panel_badges('pbadge:earnings'))
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
    from users_app.panel_badges import invalidate_panel_badges
    transaction.on_commit(lambda: invalidate_panel_badges('pbadge:earnings'))
    return redirect(request.META.get('HTTP_REFERER', 'earnings_panel:list'))


@staff_required
@require_POST
def panel_manuel_odeme_create(request):
    errors = []

    student_id     = request.POST.get('student_id', '').strip()
    coach_id       = request.POST.get('coach_id', '').strip()
    amount_str     = request.POST.get('amount_tl', '').strip()
    pool_str       = request.POST.get('coach_pool_tl', '').strip()
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
        amount_kurus = int(amount_str) * 100
        if amount_kurus <= 0:
            raise ValueError
    except (ValueError, TypeError):
        errors.append('Geçerli bir ödeme tutarı girin (₺, pozitif tam sayı).')
        amount_kurus = None

    try:
        pool_kurus = int(pool_str) * 100
        if pool_kurus <= 0:
            raise ValueError
    except (ValueError, TypeError):
        errors.append('Geçerli bir koç havuzu tutarı girin (₺, pozitif tam sayı).')
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
        from users_app.panel_badges import invalidate_panel_badges
        transaction.on_commit(lambda: invalidate_panel_badges('pbadge:earnings'))

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
            'active_section': 'earnings',
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
        'Dönem Gün', 'Koç Gün', 'Havuz (kr)', 'Havuz (TL)', 'Tutar (kr)', 'Tutar (TL)',
        'Tür', 'Durum', 'Boşluk Fallback', 'Ödeme Ref', 'Onay Tarihi', 'Ödeme Tarihi',
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
            r.pool_kurus // 100,
            r.amount_kurus,
            r.amount_kurus // 100,
            r.get_kind_display(),
            r.get_status_display(),
            'Evet' if r.gap_fallback else 'Hayır',
            r.payout_ref,
            r.approved_at.date() if r.approved_at else '',
            r.paid_at.date() if r.paid_at else '',
        ])

    return response


# ── Coach ─────────────────────────────────────────────────────────────────────

_TR_MONTHS = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara']

_STATUS_LABELS = {
    EarningRow.STATUS_HELD:     'Bekliyor',
    EarningRow.STATUS_RELEASED: 'Serbest',
    EarningRow.STATUS_APPROVED: 'Onaylandı',
    EarningRow.STATUS_PAID:     'Ödendi',
    EarningRow.STATUS_VOID:     'İptal',
}

_STATUS_LABEL_SPLIT_RELEASED = 'Tamamlandı'


def _fmt_tl(kurus):
    tl = abs(int(kurus)) // 100
    return f'{tl:,}'.replace(',', '.') + ' ₺'


def _fmt_day(d):
    return f'{d.day} {_TR_MONTHS[d.month - 1]}'


def _build_segments(coach_days, period_days):
    """
    Returns a list of {filled, today} dicts, one per day, for the segmented
    progress bar. Returns [] when period_days > 62 (continuous bar fallback).
    The last filled segment carries today=True (the most recent day served).
    """
    if period_days > 62:
        return []
    n = min(max(coach_days, 0), period_days)
    segs = []
    for i in range(period_days):
        if i < n:
            segs.append({'filled': True, 'today': i == n - 1})
        else:
            segs.append({'filled': False, 'today': False})
    return segs


def coach_kazanclar(request):
    from django.utils.timezone import localtime, now as tz_now

    if not request.user.is_authenticated:
        return redirect('users_app:login')
    if not request.user.is_coach:
        return redirect('/')

    today = localtime(tz_now()).date()

    rows = list(
        EarningRow.objects
        .filter(coach=request.user)
        .select_related('student')
        .order_by('-coverage_start', '-created_at')
        [:300]
    )

    # Compute live coach_days for held rows from interval log
    held_rows = [r for r in rows if r.status == EarningRow.STATUS_HELD]
    live_days_map = {}
    if held_rows:
        from users_app.models import CoachStudentInterval
        student_ids = {r.student_id for r in held_rows}
        ivs_by_student = {}
        for iv in CoachStudentInterval.objects.filter(
            coach=request.user,
            student_id__in=student_ids,
        ):
            ivs_by_student.setdefault(iv.student_id, []).append(iv)

        tomorrow = today + timedelta(days=1)
        for r in held_rows:
            total = 0
            for iv in ivs_by_student.get(r.student_id, []):
                iv_start = localtime(iv.started_at).date()
                # Open interval: exclusive upper bound is tomorrow so today is counted
                iv_end = tomorrow if iv.ended_at is None else localtime(iv.ended_at).date()
                seg_start = max(iv_start, r.coverage_start)
                seg_end   = min(iv_end, tomorrow)
                d = (seg_end - seg_start).days
                if d > 0:
                    total += d
            live_days_map[r.pk] = min(total, r.period_days)

    # Summary tile amounts
    held_pool      = sum(r.pool_kurus   for r in rows if r.status == EarningRow.STATUS_HELD)
    ready_sum      = sum(r.amount_kurus for r in rows if r.status in (EarningRow.STATUS_RELEASED, EarningRow.STATUS_APPROVED))
    paid_sum       = sum(r.amount_kurus for r in rows if r.status == EarningRow.STATUS_PAID)
    this_month_sum = 0
    for r in rows:
        if r.status in (EarningRow.STATUS_RELEASED, EarningRow.STATUS_APPROVED, EarningRow.STATUS_PAID):
            ref = localtime(r.paid_at).date() if (r.status == EarningRow.STATUS_PAID and r.paid_at) else r.coverage_end
            if (ref.year, ref.month) == (today.year, today.month):
                this_month_sum += r.amount_kurus

    count_tumu     = len(rows)
    count_bekleyen = sum(1 for r in rows if r.status == EarningRow.STATUS_HELD)
    count_hazir    = sum(1 for r in rows if r.status in (EarningRow.STATUS_RELEASED, EarningRow.STATUS_APPROVED))
    count_odenen   = sum(1 for r in rows if r.status == EarningRow.STATUS_PAID)

    # Build safe row dicts — no raw kurus values, no student price, no Vagus share
    row_dicts = []
    for r in rows:
        is_held = r.status == EarningRow.STATUS_HELD
        live_n  = live_days_map.get(r.pk, r.coach_days)

        if is_held:
            filter_group = 'bekleyen'
        elif r.status in (EarningRow.STATUS_RELEASED, EarningRow.STATUS_APPROVED):
            filter_group = 'hazir'
        elif r.status == EarningRow.STATUS_PAID:
            filter_group = 'odenen'
        else:
            filter_group = 'iptal'

        # coverage_end is exclusive, so display end = coverage_end - 1 day
        display_end = r.coverage_end - timedelta(days=1)

        mk = ''
        ml = ''
        if r.status != EarningRow.STATUS_VOID:
            ref = localtime(r.paid_at).date() if (r.status == EarningRow.STATUS_PAID and r.paid_at) else r.coverage_end
            mk = ref.strftime('%Y-%m')
            ml = f'{_TR_MONTHS[ref.month - 1]} {ref.year}'

        paid_date_str = ''
        if r.status == EarningRow.STATUS_PAID and r.paid_at:
            paid_date_str = _fmt_day(localtime(r.paid_at).date())

        is_split_released = r.split_from_reassign and r.status == EarningRow.STATUS_RELEASED
        row_dicts.append({
            'id':                 r.pk,
            'student_name':       r.student.full_name,
            'coverage_label':     f'{_fmt_day(r.coverage_start)} – {_fmt_day(display_end)}',
            'period_days':        r.period_days,
            'coach_days':         live_n,
            'segments':           _build_segments(live_n, r.period_days) if is_held else [],
            'is_held':            is_held,
            'amount_display':     '' if is_held else _fmt_tl(r.amount_kurus),
            'pool_display':       _fmt_tl(r.pool_kurus) if is_held else '',
            'status':             'split' if is_split_released else r.status,
            'status_label':       _STATUS_LABEL_SPLIT_RELEASED if is_split_released else _STATUS_LABELS.get(r.status, r.status),
            'split_from_reassign': r.split_from_reassign,
            'filter_group':       filter_group,
            'month_key':          mk,
            'month_label':        ml,
            'paid_date':          paid_date_str,
            'payout_ref':         r.payout_ref,
        })

    # Soft reminder for missing phone / IBAN / document
    try:
        cp = request.user.coach_profile
        profile_has_phone = bool(cp.phone)
        profile_has_iban = bool(cp.iban)
        profile_has_document = bool(cp.document)
    except Exception:
        profile_has_phone = False
        profile_has_iban = False
        profile_has_document = False

    return render(request, 'earnings/coach_kazanclar.html', {
        'rows':            row_dicts,
        'tile_held_pool':  _fmt_tl(held_pool),
        'tile_ready':      _fmt_tl(ready_sum),
        'tile_paid':       _fmt_tl(paid_sum),
        'tile_this_month': _fmt_tl(this_month_sum),
        'count_tumu':      count_tumu,
        'count_bekleyen':  count_bekleyen,
        'count_hazir':     count_hazir,
        'count_odenen':    count_odenen,
        'has_rows':        bool(rows),
        'profile_has_phone': profile_has_phone,
        'profile_has_iban': profile_has_iban,
        'profile_has_document': profile_has_document,
    })


def coach_kazanclar_export_csv(request):
    from django.utils.timezone import localtime

    if not request.user.is_authenticated:
        return redirect('users_app:login')
    if not request.user.is_coach:
        return redirect('/')

    rows = (
        EarningRow.objects
        .filter(coach=request.user)
        .select_related('student')
        .order_by('-coverage_start', '-created_at')
        [:5000]
    )

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="kazanclarim.csv"'
    response.write('﻿')  # BOM for Excel

    writer = csv.writer(response)
    writer.writerow(['ID', 'Öğrenci', 'Kapsam Başlangıç', 'Kapsam Bitiş',
                     'Dönem Gün', 'Koç Gün', 'Tutar (TL)', 'Durum', 'Ödeme Ref', 'Ödeme Tarihi'])
    for r in rows:
        is_held = r.status == EarningRow.STATUS_HELD
        amount_str = f'En fazla {r.pool_kurus // 100}' if is_held else str(r.amount_kurus // 100)
        paid_str = localtime(r.paid_at).date().isoformat() if r.paid_at else ''
        writer.writerow([
            r.pk,
            r.student.full_name if r.student else '',
            r.coverage_start,
            r.coverage_end,
            r.period_days,
            r.coach_days,
            amount_str,
            _STATUS_LABELS.get(r.status, r.status),
            r.payout_ref,
            paid_str,
        ])

    return response
