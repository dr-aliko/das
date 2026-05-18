"""
DAS Proactive Coaching Inbox — Alert Engine
Deterministic rule-based signal generation for coach alerts.

Entry point: generate_alerts_for_coach(coach)
Each rule returns a list of (student, alert_dict) tuples.
The orchestrator upserts via fingerprint unique_together to prevent duplicates.
"""
import hashlib
from datetime import date, timedelta


def _fp(*parts):
    """SHA-1 fingerprint for deduplication."""
    key = ":".join(str(p) for p in parts)
    return hashlib.sha1(key.encode()).hexdigest()


def _iso_week():
    return date.today().isocalendar()[:2]  # (year, week)


# ──────────────────────────────────────────────────────────────────────────────
# Individual rules — each returns a dict or None
# ──────────────────────────────────────────────────────────────────────────────

def _rule_exam_stagnation(student, today):
    from exams_app.models import Exam
    last = Exam.objects.filter(student=student).order_by('-exam_date').first()
    if not last:
        return None
    days = (today - last.exam_date).days
    if days < 7:
        return None
    return {
        'alert_type':  'exam_stagnation',
        'severity':    'critical',
        'title':       f'{days} gündür sınav kaydı yok',
        'detail':      f'Son sınav: {last.exam_date.strftime("%d %b %Y")} — {last.custom_name}',
        'metadata':    {'days_since_exam': days, 'last_exam_id': last.id,
                        'last_exam_date': last.exam_date.isoformat()},
        'fingerprint': _fp('stagnation', student.id, *_iso_week()),
        'expires_at':  today + timedelta(days=7),
    }


def _rule_net_decline(student, today):
    from exams_app.models import Exam
    last3 = list(Exam.objects.filter(student=student)
                 .prefetch_related('results').order_by('-exam_date')[:3])
    if len(last3) < 3:
        return None
    nets = [float(e.total_net()) for e in reversed(last3)]
    slope = (nets[2] - nets[0]) / 2
    if slope >= -1.5:
        return None
    delta = round(nets[2] - nets[0], 2)
    return {
        'alert_type':  'net_decline',
        'severity':    'warning',
        'title':       f'Son 3 sınavda düşüş trendi (Δ {delta:+.1f})',
        'detail':      f'{nets[0]:.1f} → {nets[1]:.1f} → {nets[2]:.1f}',
        'metadata':    {'slope': round(slope, 2), 'nets': nets,
                        'newest_exam_id': last3[0].id},
        'fingerprint': _fp('decline', student.id, last3[0].id),
        'expires_at':  today + timedelta(days=10),
    }


def _rule_net_momentum(student, today):
    from exams_app.models import Exam
    last2 = list(Exam.objects.filter(student=student)
                 .prefetch_related('results').order_by('-exam_date')[:2])
    if len(last2) < 2:
        return None
    delta = float(last2[0].total_net()) - float(last2[1].total_net())
    if delta < 5.0:
        return None
    return {
        'alert_type':  'net_momentum',
        'severity':    'positive',
        'title':       f'Son sınavda {delta:+.1f} net artışı',
        'detail':      (f'{last2[1].custom_name} ({float(last2[1].total_net()):.1f}) → '
                        f'{last2[0].custom_name} ({float(last2[0].total_net()):.1f})'),
        'metadata':    {'delta': round(delta, 2), 'newest_exam_id': last2[0].id},
        'fingerprint': _fp('momentum', student.id, last2[0].id),
        'expires_at':  today + timedelta(days=3),
    }


def _rule_task_neglect(student, today):
    from exams_app.models import StudentTask
    cutoff = today - timedelta(days=5)
    neglected = StudentTask.objects.filter(
        student=student, is_completed=False,
        task_source=StudentTask.SOURCE_TRIAL,
        created_at__date__lte=cutoff,
    ).count()
    if neglected < 2:
        return None
    return {
        'alert_type':  'task_neglect',
        'severity':    'warning',
        'title':       f'{neglected} aktif görev 5+ gündür tamamlanmadı',
        'detail':      'Öğrenci atanmış görevlerini ilerlemiyor.',
        'metadata':    {'neglected_count': neglected},
        'fingerprint': _fp('neglect', student.id, *_iso_week()),
        'expires_at':  today + timedelta(days=7),
    }


def _rule_radar_overload(student, today):
    from exams_app.models import StudentTask, ExamTopicError
    assigned_ids = set(StudentTask.objects.filter(student=student)
                       .values_list('topic_id', flat=True))
    unaddressed = (ExamTopicError.objects
                   .filter(exam__student=student)
                   .values('topic_id').distinct()
                   .exclude(topic_id__in=assigned_ids)
                   .count())
    if unaddressed < 8:
        return None
    return {
        'alert_type':  'radar_overload',
        'severity':    'warning',
        'title':       f'{unaddressed} hatalı konu henüz görev olarak atanmadı',
        'detail':      'Radar birikimi fazla — bazı konuları hızlıca ata.',
        'metadata':    {'unaddressed_count': unaddressed},
        'fingerprint': _fp('radar', student.id, *_iso_week()),
        'expires_at':  today + timedelta(days=7),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────────────────

_SEVERITY_RANK = {'critical': 0, 'warning': 1, 'positive': 2}
_RULES = [
    _rule_exam_stagnation,
    _rule_net_decline,
    _rule_net_momentum,
    _rule_task_neglect,
    _rule_radar_overload,
]


def generate_alerts_for_coach(coach):
    """
    Run all rules for all students under this coach.
    Upsert results using fingerprint unique_together.
    Returns the count of created/updated alerts.
    """
    from users_app.models import CoachAlert
    today = date.today()

    students = list(
        type(coach).objects.filter(coach=coach, role='student', is_active=True)
    )

    created = updated = 0
    for student in students:
        candidates = []
        for rule in _RULES:
            try:
                result = rule(student, today)
            except Exception:
                continue
            if result:
                candidates.append(result)

        # Cap at top-3 per student by severity rank
        candidates.sort(key=lambda a: _SEVERITY_RANK.get(a['severity'], 9))
        for data in candidates[:3]:
            fp = data.pop('fingerprint')
            obj, is_new = CoachAlert.objects.update_or_create(
                coach=coach, student=student, fingerprint=fp,
                defaults={
                    'alert_type':   data['alert_type'],
                    'severity':     data['severity'],
                    'title':        data['title'],
                    'detail':       data.get('detail', ''),
                    'metadata':     data.get('metadata', {}),
                    'expires_at':   data.get('expires_at'),
                    # preserve read/dismissed state on re-fire
                },
            )
            if is_new:
                created += 1
            else:
                updated += 1

    return created, updated
