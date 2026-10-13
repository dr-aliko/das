"""
Regression test: split Sosyal subjects (TYT Tarih / Coğrafya / Felsefe / Din Kültürü)
must be included in both the per-subject bars and the total-net line of the dashboard
chart produced by _build_student_chart_data.
"""
import pytest
from datetime import date
from model_bakery import baker

from exams_app.views import _build_student_chart_data


@pytest.mark.django_db
def test_split_sosyal_subjects_included_in_chart_total(student_user):
    publisher = baker.make('exams_app.Publisher')
    exam = baker.make(
        'exams_app.Exam',
        student=student_user,
        publisher=publisher,
        exam_date=date(2026, 1, 10),
        custom_name='Test Deneme',
    )

    # Create split Sosyal subjects (post-migration-0015 style)
    tarih   = baker.make('exams_app.Subject', name='TYT Tarih')
    cografya = baker.make('exams_app.Subject', name='TYT Coğrafya')
    felsefe = baker.make('exams_app.Subject', name='TYT Felsefe')
    din     = baker.make('exams_app.Subject', name='TYT Din Kültürü')
    turkce  = baker.make('exams_app.Subject', name='TYT Türkçe')
    mat     = baker.make('exams_app.Subject', name='TYT Matematik')

    # Use baker.make for ExamResult so net_score is computed via save()
    baker.make('exams_app.ExamResult', exam=exam, subject=turkce,  correct_answers=30, wrong_answers=5,  blank_answers=5)
    baker.make('exams_app.ExamResult', exam=exam, subject=mat,     correct_answers=20, wrong_answers=10, blank_answers=10)
    baker.make('exams_app.ExamResult', exam=exam, subject=tarih,   correct_answers=4,  wrong_answers=1,  blank_answers=0)
    baker.make('exams_app.ExamResult', exam=exam, subject=cografya,correct_answers=3,  wrong_answers=2,  blank_answers=0)
    baker.make('exams_app.ExamResult', exam=exam, subject=felsefe, correct_answers=5,  wrong_answers=0,  blank_answers=0)
    baker.make('exams_app.ExamResult', exam=exam, subject=din,     correct_answers=4,  wrong_answers=0,  blank_answers=1)

    data = _build_student_chart_data(student_user.id)
    assert data, "chart builder returned empty"

    idx = 0  # only one exam
    chart_total = data['totals'][idx]

    # Sosyal net: (4-0.25) + (3-0.5) + 5 + 4 = 3.75+2.5+5+4 = 15.25
    expected_sosyal = round((4 - 1*0.25) + (3 - 2*0.25) + 5 + 4, 2)  # 15.25

    # Total from subjects data
    sosyal_series = next(s for s in data['subjects'] if s['name'] == 'TYT Sosyal Bilimler')
    assert sosyal_series['data'][idx] == pytest.approx(expected_sosyal), (
        f"Sosyal net in chart = {sosyal_series['data'][idx]}, expected {expected_sosyal}. "
        "Split Sosyal subjects not aggregated."
    )

    # The chart total must match Exam.total_net() (ground truth)
    exam.refresh_from_db()
    true_total = round(exam.total_net(), 2)
    assert chart_total == pytest.approx(true_total), (
        f"chart total = {chart_total}, Exam.total_net() = {true_total}. "
        "Sosyal contribution missing from chart total."
    )


@pytest.mark.django_db
def test_umbrella_sosyal_still_works(student_user):
    """Old exams stored under the umbrella 'TYT Sosyal Bilimler' must still render."""
    publisher = baker.make('exams_app.Publisher')
    exam = baker.make(
        'exams_app.Exam',
        student=student_user,
        publisher=publisher,
        exam_date=date(2025, 6, 1),
        custom_name='Eski Deneme',
    )

    umbrella = baker.make('exams_app.Subject', name='TYT Sosyal Bilimler')
    turkce   = baker.make('exams_app.Subject', name='TYT Türkçe')

    baker.make('exams_app.ExamResult', exam=exam, subject=turkce,   correct_answers=25, wrong_answers=5, blank_answers=10)
    baker.make('exams_app.ExamResult', exam=exam, subject=umbrella, correct_answers=15, wrong_answers=5, blank_answers=0)

    data = _build_student_chart_data(student_user.id)
    assert data

    sosyal_series = next(s for s in data['subjects'] if s['name'] == 'TYT Sosyal Bilimler')
    expected_sosyal = round(15 - 5*0.25, 2)  # 13.75
    assert sosyal_series['data'][0] == pytest.approx(expected_sosyal)

    exam.refresh_from_db()
    assert data['totals'][0] == pytest.approx(round(exam.total_net(), 2))
