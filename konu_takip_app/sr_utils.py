from datetime import timedelta

from django.utils import timezone

VALID_QUALITIES = ('kolay', 'orta', 'zor')


def apply_sm2(review_count, current_interval_days, ease_factor, quality):
    """
    Pure SM2-inspired interval calculator.
    Returns (new_interval_days, new_ease_factor). Caller handles persistence.
    Identical logic to the original _compute_review — extracted so it can be
    shared by any model that stores the same five SR fields.
    """
    rc = review_count

    if rc == 0:
        interval = {'kolay': 10, 'orta': 6, 'zor': 3}[quality]
        new_ease_factor = ease_factor
    elif rc == 1:
        interval = {'kolay': 21, 'orta': 14, 'zor': 4}[quality]
        new_ease_factor = ease_factor
    else:
        if quality == 'kolay':
            interval = round(current_interval_days * ease_factor)
            new_ease_factor = min(2.2, ease_factor + 0.15)
        elif quality == 'orta':
            interval = round(current_interval_days * ease_factor * 0.85)
            new_ease_factor = ease_factor
        else:  # zor
            interval = max(3, round(current_interval_days * 0.4))
            new_ease_factor = max(1.3, ease_factor - 0.20)

    return interval, new_ease_factor
