"""
Staff coach search tests.

Covers:
- Search by name
- Search by email
- Turkish case (İ/I/ı/i)
- Empty result
- Non-staff access blocked
- No email leak on coach-facing pages
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from model_bakery import baker

from users_app.utils import filter_coaches_by_q, tr_lower

User = get_user_model()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def staff_client(db):
    user = baker.make(User, role='staff', is_active=True, is_staff=True)
    user.set_password('pass')
    user.save()
    c = Client()
    c.login(username=user.email, password='pass')
    return c


@pytest.fixture
def coach_ibrahim(db):
    return baker.make(User, role='coach', is_active=True, is_approved=True,
                      full_name='İbrahim Yıldız', email='ibrahim@vagus-test.com')


@pytest.fixture
def coach_ali(db):
    return baker.make(User, role='coach', is_active=True, is_approved=True,
                      full_name='Ali Öztürk', email='ali@vagus-test.com')


# ── 1. tr_lower unit tests ─────────────────────────────────────────────────────

def test_tr_lower_dotted_i():
    assert tr_lower('İstanbul') == 'istanbul'


def test_tr_lower_undotted_i():
    assert tr_lower('IŞIK') == 'ışık'


def test_tr_lower_mixed():
    assert tr_lower('İbrahim') == 'ibrahim'
    assert tr_lower('ibrahim') == 'ibrahim'


# ── 2. filter_coaches_by_q unit tests ─────────────────────────────────────────

@pytest.mark.django_db
def test_filter_by_name(coach_ibrahim, coach_ali):
    result = filter_coaches_by_q([coach_ibrahim, coach_ali], 'Yıldız')
    assert coach_ibrahim in result
    assert coach_ali not in result


@pytest.mark.django_db
def test_filter_by_email(coach_ibrahim, coach_ali):
    result = filter_coaches_by_q([coach_ibrahim, coach_ali], 'ali@vagus')
    assert coach_ali in result
    assert coach_ibrahim not in result


@pytest.mark.django_db
def test_filter_turkish_case_ibrahim(coach_ibrahim, coach_ali):
    # Searching 'ibrahim' (lowercase dotless-i) must find İbrahim (dotted-I)
    result = filter_coaches_by_q([coach_ibrahim, coach_ali], 'ibrahim')
    assert coach_ibrahim in result
    assert coach_ali not in result


@pytest.mark.django_db
def test_filter_empty_q_returns_all(coach_ibrahim, coach_ali):
    result = filter_coaches_by_q([coach_ibrahim, coach_ali], '')
    assert len(result) == 2


@pytest.mark.django_db
def test_filter_no_match_returns_empty(coach_ibrahim, coach_ali):
    result = filter_coaches_by_q([coach_ibrahim, coach_ali], 'xyz_no_match_999')
    assert result == []


# ── 3. HTTP – list pages return filtered results ───────────────────────────────

@pytest.mark.django_db
def test_odemeler_search_by_name(staff_client, coach_ibrahim, coach_ali):
    resp = staff_client.get('/panel/odemeler/', {'q': 'Yıldız'})
    assert resp.status_code == 200
    content = resp.content.decode()
    assert 'İbrahim' in content
    assert 'Ali Öztürk' not in content


@pytest.mark.django_db
def test_odemeler_search_by_email(staff_client, coach_ibrahim, coach_ali):
    resp = staff_client.get('/panel/odemeler/', {'q': 'ibrahim@vagus'})
    assert resp.status_code == 200
    content = resp.content.decode()
    assert 'İbrahim' in content
    assert 'Ali Öztürk' not in content


@pytest.mark.django_db
def test_odemeler_search_turkish_case(staff_client, coach_ibrahim, coach_ali):
    # Lower-case 'ibrahim' should find 'İbrahim' (dotted-I name)
    resp = staff_client.get('/panel/odemeler/', {'q': 'ibrahim'})
    assert resp.status_code == 200
    assert 'İbrahim' in resp.content.decode()


@pytest.mark.django_db
def test_odemeler_search_empty_result(staff_client, coach_ibrahim, coach_ali):
    resp = staff_client.get('/panel/odemeler/', {'q': 'no_such_coach_xyz'})
    assert resp.status_code == 200
    assert 'İbrahim' not in resp.content.decode()
    assert 'Ali Öztürk' not in resp.content.decode()


@pytest.mark.django_db
def test_ogrenciler_search_by_name(staff_client, coach_ibrahim, coach_ali):
    resp = staff_client.get('/panel/ogrenciler/', {'q': 'ibrahim'})
    assert resp.status_code == 200


@pytest.mark.django_db
def test_koc_ekle_search_by_email(staff_client, coach_ibrahim):
    resp = staff_client.get('/panel/koc-ekle/', {'q': 'ibrahim@vagus'})
    assert resp.status_code == 200


# ── 4. Non-staff access blocked ───────────────────────────────────────────────

@pytest.mark.django_db
def test_nonstaff_coach_blocked_from_odemeler(coach_ibrahim):
    coach_ibrahim.set_password('pass')
    coach_ibrahim.save()
    c = Client()
    c.login(username=coach_ibrahim.email, password='pass')
    resp = c.get('/panel/odemeler/')
    assert resp.status_code in (302, 403)


@pytest.mark.django_db
def test_nonstaff_student_blocked_from_capacity(db):
    student = baker.make(User, role='student', is_active=True)
    student.set_password('pass')
    student.save()
    c = Client()
    c.login(username=student.email, password='pass')
    resp = c.get('/panel/kontenjan/')
    assert resp.status_code in (302, 403)


@pytest.mark.django_db
def test_unauthenticated_blocked_from_odemeler():
    c = Client()
    resp = c.get('/panel/odemeler/')
    assert resp.status_code in (302, 403)


# ── 5. No email leak on coach-facing pages ────────────────────────────────────

@pytest.mark.django_db
def test_no_other_coach_email_on_roster(coach_ibrahim, coach_ali):
    """Coach roster must not expose another coach's email."""
    coach_ibrahim.set_password('pass')
    coach_ibrahim.save()
    c = Client()
    c.login(username=coach_ibrahim.email, password='pass')
    resp = c.get('/ogrencilerim/')
    # The response must not contain the other coach's email address
    assert coach_ali.email not in resp.content.decode()


@pytest.mark.django_db
def test_no_coach_email_on_student_dashboard(db, coach_ibrahim):
    """Student dashboard must not expose their coach's email."""
    student = baker.make(User, role='student', is_active=True)
    student.coach = coach_ibrahim
    student.save(update_fields=['coach'])
    student.set_password('pass')
    student.save()
    c = Client()
    c.login(username=student.email, password='pass')
    resp = c.get('/dashboard/')
    assert coach_ibrahim.email not in resp.content.decode()
