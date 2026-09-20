from datetime import timedelta

from django.utils import timezone

from konu_takip_app.sr_utils import VALID_QUALITIES, apply_sm2


def submit_struggle_review(student, question_id, quality):
    """Submit a quality rating for a struggle question. Returns updated question or None."""
    from .models import StudentStruggleQuestion
    if quality not in VALID_QUALITIES:
        return None
    try:
        q = StudentStruggleQuestion.objects.get(id=question_id, student=student)
    except StudentStruggleQuestion.DoesNotExist:
        return None

    new_interval, new_ease = apply_sm2(
        q.review_count,
        q.current_interval_days,
        q.ease_factor,
        quality,
    )
    now = timezone.now()
    q.current_interval_days = new_interval
    q.ease_factor = new_ease
    q.next_review_at = now + timedelta(days=new_interval)
    q.last_reviewed_at = now
    q.review_count += 1
    q.save(update_fields=[
        'current_interval_days', 'ease_factor',
        'next_review_at', 'last_reviewed_at', 'review_count',
    ])
    return q
