"""
Tests for _build_denemeler_v2_context chart_data format.
Verifies the data structure required by the _net_gelisimi_chart.html partial.
"""
import pytest
from datetime import date
from model_bakery import baker

from exams_app.views import _build_denemeler_v2_context


@pytest.mark.django_db
def test_chart_data_is_list_with_correct_keys(student_user):
    publisher = baker.make('exams_app.Publisher')
    subject   = baker.make('exams_app.Subject', name='TYT Türkçe')

    for day in [1, 5, 10]:
        exam = baker.make(
            'exams_app.Exam',
            student=student_user,
            publisher=publisher,
            exam_date=date(2026, 3, day),
            custom_name=f'Deneme {day}',
        )
        baker.make(
            'exams_app.ExamResult',
            exam=exam, subject=subject,
            correct_answers=20 + day, wrong_answers=5, blank_answers=5,
        )

    ctx = _build_denemeler_v2_context(student_user)
    data = ctx['chart_data']

    assert isinstance(data, list), "chart_data must be a Python list (not a JSON string)"
    assert len(data) == 3

    for point in data:
        assert 'iso'   in point, "each point needs 'iso' for client-side period filter"
        assert 'label' in point, "each point needs 'label' for x-axis display"
        assert 'n'     in point, "each point needs 'n' for net score"
        assert 'name'  in point, "each point needs 'name' for tooltip"
        assert isinstance(point['n'],   float)
        assert isinstance(point['iso'], str)
        assert '-' in point['iso'], "iso must be YYYY-MM-DD"


@pytest.mark.django_db
def test_chart_data_is_chronological(student_user):
    """Oldest first so Chart.js draws left-to-right correctly."""
    publisher = baker.make('exams_app.Publisher')
    subject   = baker.make('exams_app.Subject', name='TYT Matematik')

    dates = [date(2026, 1, 10), date(2026, 2, 15), date(2026, 3, 20)]
    for d in dates:
        exam = baker.make(
            'exams_app.Exam', student=student_user, publisher=publisher,
            exam_date=d, custom_name=str(d),
        )
        baker.make('exams_app.ExamResult', exam=exam, subject=subject,
                   correct_answers=10, wrong_answers=0, blank_answers=0)

    ctx  = _build_denemeler_v2_context(student_user)
    isos = [p['iso'] for p in ctx['chart_data']]
    assert isos == sorted(isos), "chart_data must be in ascending date order"


@pytest.mark.django_db
def test_chart_data_n_uses_dot_decimal(student_user):
    """Net values must be Python floats (dot decimal) — not strings or locale-formatted."""
    publisher = baker.make('exams_app.Publisher')
    subject   = baker.make('exams_app.Subject', name='TYT Türkçe')
    exam = baker.make(
        'exams_app.Exam', student=student_user, publisher=publisher,
        exam_date=date(2026, 4, 1), custom_name='Float Test',
    )
    baker.make('exams_app.ExamResult', exam=exam, subject=subject,
               correct_answers=10, wrong_answers=2, blank_answers=0)

    ctx = _build_denemeler_v2_context(student_user)
    n = ctx['chart_data'][0]['n']
    assert isinstance(n, float)
    assert ',' not in str(n), "net must be dot-decimal float, not locale-formatted string"


@pytest.mark.django_db
def test_chart_data_empty_when_no_exams(student_user):
    ctx = _build_denemeler_v2_context(student_user)
    assert ctx['chart_data'] == []
    assert ctx['all_exam_count'] == 0


@pytest.mark.django_db
def test_chart_data_label_uses_turkish_months(student_user):
    publisher = baker.make('exams_app.Publisher')
    subject   = baker.make('exams_app.Subject', name='TYT Türkçe')
    exam = baker.make(
        'exams_app.Exam', student=student_user, publisher=publisher,
        exam_date=date(2026, 9, 16), custom_name='Eylül Denemesi',
    )
    baker.make('exams_app.ExamResult', exam=exam, subject=subject,
               correct_answers=15, wrong_answers=0, blank_answers=0)

    ctx = _build_denemeler_v2_context(student_user)
    label = ctx['chart_data'][0]['label']
    assert 'Eyl' in label, f"label '{label}' should contain Turkish short month 'Eyl'"
    assert '16' in label
