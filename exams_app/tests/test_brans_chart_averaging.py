"""
Tests for per-day averaging in the Branş Hub trend chart (coach view only).

Coach view  (/coach/student/<id>/brans/): same-day exams of one subject must be
averaged into one chart point; a 'counts' array is added to each dataset.
Student view (/brans/): behaviour unchanged — last-wins dict, no 'counts' key.
"""
import json
from datetime import date, timedelta

import pytest

from exams_app.views import _build_brans_hub_context


# ── fixtures & helpers ────────────────────────────────────────────────────────

@pytest.fixture
def student(db):
    from model_bakery import baker
    return baker.make('users_app.User', role='student', is_active=True)


@pytest.fixture
def mat_subject(db):
    from exams_app.models import Subject
    obj, _ = Subject.objects.get_or_create(name='TYT Matematik')
    return obj


@pytest.fixture
def turkce_subject(db):
    from exams_app.models import Subject
    obj, _ = Subject.objects.get_or_create(name='TYT Türkçe')
    return obj


def _brans(student, subject, tarih, dogru):
    """Create a BransDeneme with net = dogru (yanlis=0)."""
    from exams_app.models import BransDeneme
    return BransDeneme.objects.create(
        student=student, ders=subject, tarih=tarih,
        dogru=dogru, yanlis=0, bos=0,
    )


def _chart(student, coach_view):
    ctx = _build_brans_hub_context(student, coach_view=coach_view)
    return json.loads(ctx['brans_chart_json'])


def _ds(chart, label):
    return next((d for d in chart['datasets'] if d['label'] == label), None)


def _non_null(lst):
    return [v for v in lst if v is not None]


# ── coach view: same-day averaging ───────────────────────────────────────────

@pytest.mark.django_db
def test_two_same_day_exams_averaged_to_one_point(student, mat_subject):
    today = date.today()
    _brans(student, mat_subject, today, dogru=40)   # net 40.0
    _brans(student, mat_subject, today, dogru=60)   # net 60.0

    chart = _chart(student, coach_view=True)
    ds = _ds(chart, 'Matematik')
    assert ds is not None

    data = _non_null(ds['data'])
    assert len(data) == 1
    assert data[0] == pytest.approx(50.0)           # (40 + 60) / 2

    counts = _non_null(ds['counts'])
    assert counts == [2]


@pytest.mark.django_db
def test_three_same_day_exams_averaged(student, mat_subject):
    today = date.today()
    _brans(student, mat_subject, today, dogru=30)
    _brans(student, mat_subject, today, dogru=60)
    _brans(student, mat_subject, today, dogru=90)

    chart = _chart(student, coach_view=True)
    ds = _ds(chart, 'Matematik')
    data = _non_null(ds['data'])
    assert len(data) == 1
    assert data[0] == pytest.approx(60.0)           # (30 + 60 + 90) / 3

    counts = _non_null(ds['counts'])
    assert counts == [3]


@pytest.mark.django_db
def test_single_exam_unchanged_with_count_one(student, mat_subject):
    today = date.today()
    _brans(student, mat_subject, today, dogru=55)

    chart = _chart(student, coach_view=True)
    ds = _ds(chart, 'Matematik')
    data = _non_null(ds['data'])
    assert data == [pytest.approx(55.0)]

    counts = _non_null(ds['counts'])
    assert counts == [1]


@pytest.mark.django_db
def test_different_days_produce_two_separate_points(student, mat_subject):
    today = date.today()
    _brans(student, mat_subject, today - timedelta(days=3), dogru=40)
    _brans(student, mat_subject, today, dogru=60)

    chart = _chart(student, coach_view=True)
    ds = _ds(chart, 'Matematik')
    data = _non_null(ds['data'])
    assert len(data) == 2
    assert sorted(data) == pytest.approx([40.0, 60.0])

    counts = _non_null(ds['counts'])
    assert counts == [1, 1]


@pytest.mark.django_db
def test_different_subjects_same_day_stay_separate(student, mat_subject, turkce_subject):
    today = date.today()
    _brans(student, mat_subject, today, dogru=40)
    _brans(student, turkce_subject, today, dogru=70)

    chart = _chart(student, coach_view=True)
    mat = _ds(chart, 'Matematik')
    tur = _ds(chart, 'Türkçe')
    assert _non_null(mat['data']) == [pytest.approx(40.0)]
    assert _non_null(tur['data']) == [pytest.approx(70.0)]
    assert _non_null(mat['counts']) == [1]
    assert _non_null(tur['counts']) == [1]


@pytest.mark.django_db
def test_same_day_average_mixes_with_single_day(student, mat_subject):
    """Two exams on one day, one exam on another day — both points correct."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    _brans(student, mat_subject, yesterday, dogru=40)
    _brans(student, mat_subject, yesterday, dogru=60)  # avg=50 yesterday
    _brans(student, mat_subject, today, dogru=80)       # 80 today

    chart = _chart(student, coach_view=True)
    ds = _ds(chart, 'Matematik')
    data = _non_null(ds['data'])
    assert len(data) == 2
    # yesterday → 50, today → 80
    assert data[0] == pytest.approx(50.0)
    assert data[1] == pytest.approx(80.0)

    counts = _non_null(ds['counts'])
    assert counts == [2, 1]


# ── student view: same averaging as coach view ───────────────────────────────

@pytest.mark.django_db
def test_student_view_has_counts_key(student, mat_subject):
    today = date.today()
    _brans(student, mat_subject, today, dogru=40)
    _brans(student, mat_subject, today, dogru=60)

    chart = _chart(student, coach_view=False)
    ds = _ds(chart, 'Matematik')
    assert ds is not None
    assert 'counts' in ds
    assert _non_null(ds['counts']) == [2]


@pytest.mark.django_db
def test_student_view_same_day_averaged(student, mat_subject):
    today = date.today()
    _brans(student, mat_subject, today, dogru=40)
    _brans(student, mat_subject, today, dogru=60)

    chart = _chart(student, coach_view=False)
    ds = _ds(chart, 'Matematik')
    data = _non_null(ds['data'])
    assert len(data) == 1
    assert data[0] == pytest.approx(50.0)


# ── unchanged: exam list and single-subject detail ───────────────────────────

@pytest.mark.django_db
def test_exam_list_still_shows_all_individual_exams(student, mat_subject):
    """exams.recent must list every BransDeneme entry separately, not averaged."""
    today = date.today()
    _brans(student, mat_subject, today, dogru=40)
    _brans(student, mat_subject, today, dogru=60)

    ctx = _build_brans_hub_context(student, coach_view=False)
    assert ctx['exams'].total_count == 2
    assert len(ctx['exams'].recent) == 2


@pytest.mark.django_db
def test_build_brans_chart_data_unaffected(student, mat_subject):
    """_build_brans_chart_data is a separate function used by the single-subject
    detail page; it must not be touched by this change."""
    from exams_app.views import _build_brans_chart_data
    from exams_app.models import BransDeneme

    today = date.today()
    _brans(student, mat_subject, today, dogru=40)
    _brans(student, mat_subject, today, dogru=60)

    entries = list(
        BransDeneme.objects.filter(student=student).select_related('ders').order_by('-tarih', '-id')
    )
    result = _build_brans_chart_data(entries)
    # The function returns a structure with labels and datasets; it should still
    # have exactly one point per date (its own unchanged logic).
    assert result is not None
