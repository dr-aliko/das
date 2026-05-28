"""
Risk engine: generates PlanRiskAlert records for a MacroPlan.

Each check is a pure function that returns a list of (kind, severity, message)
tuples. The main entry point `assess_risks` deletes old alerts and inserts fresh
ones every time the plan is regenerated.

Checks implemented:
  1. Ahmet Syndrome  — BOTH/AYT plan but TYT ratio < 0.45 in foundation period
  2. EA Verbal Delay — EA-type student, no Türkçe/Sosyal topics in first 2 months
  3. Bağlayıcı Skipped — a is_baglayici topic appears AFTER month 3 while month 1-3 are empty of it
  4. Time Crunch     — fewer months than subjects to cover
  5. Overload        — avg topics/month > 25
"""
from __future__ import annotations

from curriculum_app.models import MacroPlan, PlanRiskAlert


def _check_ahmet_syndrome(plan: MacroPlan, buckets) -> list[tuple]:
    if plan.sinav_tipi not in ('AYT', 'BOTH'):
        return []
    if plan.months_remaining < 4:
        return []
    tyt_counts = []
    ayt_counts = []
    for bucket in buckets[:3]:
        for pt in bucket.topics.select_related('topic__subject').all():
            if pt.topic.subject.exam_type == 'TYT':
                tyt_counts.append(1)
            else:
                ayt_counts.append(1)
    total = len(tyt_counts) + len(ayt_counts)
    if total == 0:
        return []
    tyt_share = len(tyt_counts) / total
    if tyt_share < 0.45:
        return [(
            PlanRiskAlert.RISK_AHMET,
            PlanRiskAlert.SEVERITY_WARNING,
            f'İlk 3 ayda TYT oranı {tyt_share:.0%} — '
            "AYT'ye öncelik verilirken TYT ihmal edilebilir (Ahmet Sendromu).",
        )]
    return []


def _check_baglayici_skipped(plan: MacroPlan, buckets) -> list[tuple]:
    alerts = []
    # Baglayici topics that appear after bucket 3 while earlier buckets don't have them
    late_buckets = list(buckets[3:])
    early_topic_ids = set()
    for b in buckets[:3]:
        for pt in b.topics.all():
            early_topic_ids.add(pt.topic_id)

    for bucket in late_buckets:
        for pt in bucket.topics.select_related('topic').all():
            t = pt.topic
            if t.is_baglayici and t.id not in early_topic_ids:
                alerts.append((
                    PlanRiskAlert.RISK_BAGLAYICI,
                    PlanRiskAlert.SEVERITY_CRITICAL,
                    f'Bağlayıcı konu "{t.name}" ({bucket.label}) ilk aylara alınmalıydı.',
                ))
    return alerts


def _check_time_crunch(plan: MacroPlan, buckets) -> list[tuple]:
    if plan.months_remaining < 2:
        return [(
            PlanRiskAlert.RISK_TIME_CRUNCH,
            PlanRiskAlert.SEVERITY_CRITICAL,
            f'Sınava {plan.months_remaining} ay kaldı — uzun vadeli plan oluşturmak için süre yetersiz.',
        )]
    return []


def _check_overload(plan: MacroPlan, buckets) -> list[tuple]:
    total_topics = sum(b.topics.count() for b in buckets)
    n = len(buckets)
    if n == 0:
        return []
    avg = total_topics / n
    if avg > 25:
        return [(
            PlanRiskAlert.RISK_OVERLOAD,
            PlanRiskAlert.SEVERITY_WARNING,
            f'Aylık ortalama {avg:.0f} konu — öğrenci için fazla yoğun olabilir (önerilen: ≤25).',
        )]
    return []


def _check_ea_verbal_delay(plan: MacroPlan, buckets) -> list[tuple]:
    """
    EA (Eşit Ağırlık) students need Türkçe and Edebiyat coverage from month 1.
    Trigger: student.alan == 'EA' and first 2 buckets have no Türkçe/Edebiyat topics.
    """
    alan = getattr(plan.student, 'alan', None)
    if alan != 'EA':
        return []
    verbal_subjects = {'TYT Türkçe', 'AYT Türk Dili ve Edebiyatı'}
    early_subject_names = set()
    for bucket in buckets[:2]:
        for pt in bucket.topics.select_related('topic__subject').all():
            early_subject_names.add(pt.topic.subject.name)
    if not verbal_subjects.intersection(early_subject_names):
        return [(
            PlanRiskAlert.RISK_EA_VERBAL,
            PlanRiskAlert.SEVERITY_WARNING,
            'EA tipi ogrenci icin ilk 2 ayda Turkce/Edebiyat konusu yok. '
            'Sozel beceriler geride kalabilir.',
        )]
    return []


def assess_risks(plan: MacroPlan) -> None:
    """Delete existing risk alerts and create fresh ones for the given plan."""
    plan.risk_alerts.all().delete()

    buckets = list(plan.buckets.prefetch_related('topics__topic__subject').all())

    findings: list[tuple] = []
    findings += _check_time_crunch(plan, buckets)
    findings += _check_ahmet_syndrome(plan, buckets)
    findings += _check_baglayici_skipped(plan, buckets)
    findings += _check_overload(plan, buckets)
    findings += _check_ea_verbal_delay(plan, buckets)

    if findings:
        PlanRiskAlert.objects.bulk_create([
            PlanRiskAlert(plan=plan, kind=k, severity=s, message=m)
            for k, s, m in findings
        ])
