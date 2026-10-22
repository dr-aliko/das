"""
Tests: widget and denemeler page show identical per-topic error counts.

Root cause fixed: _get_gray_topics returned wrong_total (wrong-only),
_build_trial_topic_errors returned wrong+blank.  Both now call
_exam_topic_error_totals so counts always match.
"""

import pytest
from model_bakery import baker

from exams_app.models import Exam, ExamTopicError, StudentTask
from exams_app.views import (
    _build_trial_topic_errors,
    _exam_topic_error_totals,
    _get_gray_topics,
)


@pytest.fixture
def student(db):
    return baker.make('users_app.User', role='student', is_active=True)


@pytest.fixture
def publisher(db):
    return baker.make('exams_app.Publisher', name='Test Pub', is_active=True)


@pytest.fixture
def subject(db):
    return baker.make('exams_app.Subject', name='TYT Matematik', exam_type='TYT')


@pytest.fixture
def topic(subject):
    return baker.make('exams_app.Topic', name='Kümeler', subject=subject)


@pytest.fixture
def topic2(subject):
    return baker.make('exams_app.Topic', name='Denklemler', subject=subject)


@pytest.mark.django_db
def test_widget_and_denemeler_counts_match(student, publisher, subject, topic, topic2):
    """Widget radar (via _exam_topic_error_totals) equals denemeler accordion for every topic."""
    exam1 = baker.make('exams_app.Exam', student=student, publisher=publisher,
                       exam_date='2026-10-01')
    exam2 = baker.make('exams_app.Exam', student=student, publisher=publisher,
                       exam_date='2026-10-10')
    # topic: 3Y in exam1, 2B in exam1, 1Y 0B in exam2 → errors=6
    ExamTopicError.objects.create(exam=exam1, topic=topic, wrong_count=3, blank_count=2)
    ExamTopicError.objects.create(exam=exam2, topic=topic, wrong_count=1, blank_count=0)
    # topic2: 2Y 1B in exam1 → errors=3
    ExamTopicError.objects.create(exam=exam1, topic=topic2, wrong_count=2, blank_count=1)

    # --- Denemeler accordion (source of truth) ---
    denemeler_topics = _build_trial_topic_errors(student, top_n=50)
    denemeler_map = {t['id']: t['errors'] for t in denemeler_topics}

    # --- Widget helper (shared) ---
    widget_rows = list(_exam_topic_error_totals(student.id))
    widget_map = {r['topic__id']: r['errors'] for r in widget_rows}

    assert set(denemeler_map.keys()) == set(widget_map.keys()), \
        'Widget and denemeler show different topic sets'
    for tid in denemeler_map:
        assert denemeler_map[tid] == widget_map[tid], \
            f'Topic {tid}: denemeler={denemeler_map[tid]} widget={widget_map[tid]}'

    # Spot-check specific expected values (wrong+blank combined)
    assert denemeler_map[topic.id] == 6   # 3+2 + 1+0
    assert denemeler_map[topic2.id] == 3  # 2+1


@pytest.mark.django_db
def test_student_side_widget_matches_denemeler(student, publisher, subject, topic):
    """_get_gray_topics also returns errors=wrong+blank, matching denemeler."""
    exam = baker.make('exams_app.Exam', student=student, publisher=publisher,
                      exam_date='2026-10-05')
    ExamTopicError.objects.create(exam=exam, topic=topic, wrong_count=4, blank_count=3)

    gray = list(_get_gray_topics(student.id))
    denemeler_topics = _build_trial_topic_errors(student, top_n=50)

    assert len(gray) == 1
    assert gray[0]['errors'] == 7          # 4Y + 3B combined
    assert gray[0]['wrong_total'] == 4
    assert gray[0]['blank_total'] == 3

    denemeler_map = {t['id']: t['errors'] for t in denemeler_topics}
    assert denemeler_map[topic.id] == gray[0]['errors'], \
        'Student widget errors != denemeler errors for same topic'


@pytest.mark.django_db
def test_rebuild_dry_run_detects_blank_topic(student, publisher, subject, topic):
    """rebuild_wrong_counts dry-run identifies topics where blank_count > 0."""
    from io import StringIO
    from django.core.management import call_command

    exam = baker.make('exams_app.Exam', student=student, publisher=publisher,
                      exam_date='2026-10-15')
    # wrong_count=2, blank_count=1 → old widget showed 2Y, denemeler showed 3Y
    ExamTopicError.objects.create(exam=exam, topic=topic, wrong_count=2, blank_count=1)

    out = StringIO()
    call_command('rebuild_wrong_counts', '--student', str(student.id), stdout=out)
    output = out.getvalue()

    assert 'blank_count=1' in output, 'Should report the topic with blank_count > 0'
    assert 'old widget=2Y' in output
    assert 'denemeler=3Y' in output
