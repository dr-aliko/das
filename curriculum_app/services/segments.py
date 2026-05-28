"""
Student segment detection.

Segments:
  starter   — few or no exam results, brand new student
  mid       — has some results, average performance
  advanced  — strong exam history, high net scores
"""
from __future__ import annotations


def determine_segment(student) -> str:
    """
    Returns one of 'starter', 'mid', 'advanced' based on the student's
    TYT exam history (ExamResult net scores).
    """
    from exams_app.models import ExamResult
    from django.db.models import Avg

    results = ExamResult.objects.filter(
        exam__student=student,
        subject__exam_type='TYT',
    )
    count = results.count()

    if count < 3:
        return 'starter'

    avg_net = results.aggregate(avg=Avg('net_score'))['avg'] or 0

    # TYT total max net ≈ 120 (40Q × 3 subjects approx); normalize
    # Thresholds: <40 net → starter, 40-75 → mid, >75 → advanced
    if avg_net < 6:   # per-subject average (40Q paper)
        return 'starter'
    if avg_net < 20:
        return 'mid'
    return 'advanced'
