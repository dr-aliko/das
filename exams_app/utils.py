import json
from datetime import date, timedelta
from math import ceil


def safe_json(data, **kwargs):
    """json.dumps that escapes < > & as Unicode escapes so </script> can't break out of <script> blocks."""
    raw = json.dumps(data, **kwargs)
    return raw.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')


def get_student_status(student):
    """Returns {'status': 'iyi'|'dusus'}.

    dusus — at least two exams and the most-recent net is strictly lower than the previous
    iyi   — everyone else (no exams, one exam, equal or improved net)
    """
    from exams_app.models import Exam

    recent = list(
        Exam.objects.filter(student=student)
        .prefetch_related('results')
        .order_by('-exam_date')[:2]
    )

    if len(recent) >= 2:
        net0 = float(recent[0].total_net())
        net1 = float(recent[1].total_net())
        if net0 < net1:
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
