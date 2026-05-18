from datetime import date, timedelta
from math import ceil


def get_student_status(student):
    """Returns {'status': 'iyi'|'dusus'|'pasif'} based on recent exam activity (DAS-415).

    iyi   🟢 — exam within 7 days and no significant net drop
    dusus 🟡 — exam 8-14 days ago, or net dropped >5 points vs previous
    pasif 🔴 — no exam in 14+ days, or no exams at all
    """
    from exams_app.models import Exam

    today = date.today()
    recent = list(
        Exam.objects.filter(student=student)
        .prefetch_related('results')
        .order_by('-exam_date')[:3]
    )

    if not recent:
        return {'status': 'pasif'}

    days_since = (today - recent[0].exam_date).days

    if days_since > 14:
        return {'status': 'pasif'}

    if days_since > 7:
        return {'status': 'dusus'}

    if len(recent) >= 2:
        net0 = float(recent[0].total_net() if callable(recent[0].total_net) else recent[0].total_net)
        net1 = float(recent[1].total_net() if callable(recent[1].total_net) else recent[1].total_net)
        if net0 < net1 - 5:
            return {'status': 'dusus'}

    return {'status': 'iyi'}


def apply_sm2(task, quality: int) -> None:
    """
    Standard SM-2 spaced repetition algorithm.
    quality: 3 = Zor (Hard), 4 = Normal, 5 = Kolay (Easy)

    Updates task fields and saves in-place.
    """
    ef = task.easiness_factor
    new_ef = ef + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    task.easiness_factor = max(1.3, round(new_ef, 2))

    if quality < 3:
        # Başarısız → sıfırla
        task.repetition_count = 0
        task.interval_days = 1
    else:
        if task.repetition_count == 0:
            task.interval_days = 1
        elif task.repetition_count == 1:
            task.interval_days = 6
        else:
            task.interval_days = ceil(task.interval_days * task.easiness_factor)
        task.repetition_count += 1

    task.next_review_date = date.today() + timedelta(days=task.interval_days)
    task.save(update_fields=[
        'repetition_count', 'easiness_factor', 'interval_days', 'next_review_date',
    ])
