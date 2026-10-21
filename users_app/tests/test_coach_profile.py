"""
Tests for CoachProfile: IBAN validator, private file serving (path traversal,
permissions, headers), IBAN-change email notification, popup condition, phone
normalisation/lock, IBAN without spaces, /coach/profil/ redirect, coach section
visibility on /profil/.
"""
import pytest
from django.test import Client
from django.urls import reverse
from model_bakery import baker

from users_app.forms import mask_iban, validate_tr_iban, _normalize_tr_phone_e164
from users_app.models import CoachProfile, User


# ── Autouse: redirect every test away from the real PRIVATE_MEDIA_ROOT ───────

@pytest.fixture(autouse=True)
def _isolate_private_media(tmp_path, settings):
    """Ensure no test ever writes into the real private_media/ directory."""
    settings.PRIVATE_MEDIA_ROOT = str(tmp_path)


# ── Helpers ───────────────────────────────────────────────────────────────────

_VALID_IBAN = 'TR330006100519786457841326'


def _make_coach(**kw):
    return baker.make(User, role='coach', is_active=True, is_approved=True, **kw)


def _make_student(**kw):
    return baker.make(User, role='student', is_active=True, **kw)


# ── 1. IBAN mod-97 validator ──────────────────────────────────────────────────

class TestIbanValidator:
    def test_valid_iban(self):
        assert validate_tr_iban(_VALID_IBAN) == _VALID_IBAN

    def test_spaces_stripped(self):
        result = validate_tr_iban('TR33 0006 1005 1978 6457 8413 26')
        assert ' ' not in result

    def test_wrong_country_raises(self):
        from django.core.exceptions import ValidationError
        with pytest.raises(ValidationError):
            validate_tr_iban('DE89370400440532013000')

    def test_bad_checksum_raises(self):
        from django.core.exceptions import ValidationError
        with pytest.raises(ValidationError, match='mod-97'):
            validate_tr_iban('TR330006100519786457841327')  # last digit changed

    def test_mask_shows_first_and_last_four(self):
        masked = mask_iban(_VALID_IBAN)
        assert masked.startswith('TR33')
        assert masked.endswith('1326')
        assert '****' in masked


# ── 2. IBAN change email notification ────────────────────────────────────────

@pytest.mark.django_db
class TestIbanEmailNotification:
    def test_iban_change_sends_email(self):
        """Saving a new IBAN must call send_mail with the coach's email."""
        from unittest.mock import patch
        coach = _make_coach()
        baker.make(CoachProfile, user=coach, iban='')

        with patch('django.core.mail.send_mail') as mock_send:
            c = Client()
            c.force_login(coach)
            c.post(reverse('profil'), {
                'coach_payment_submit': '1',
                'iban': _VALID_IBAN,
            })

        mock_send.assert_called_once()
        _args, kwargs = mock_send.call_args
        recipient = kwargs.get('recipient_list') or (_args[3] if len(_args) > 3 else [])
        assert coach.email in recipient
        subject = kwargs.get('subject') or (_args[0] if _args else '')
        assert 'IBAN' in subject

    def test_email_failure_does_not_block_iban_save(self):
        """Even if send_mail raises, the IBAN change must be persisted."""
        from unittest.mock import patch
        coach = _make_coach()
        profile = baker.make(CoachProfile, user=coach, iban='')

        with patch('django.core.mail.send_mail', side_effect=Exception('SMTP down')):
            c = Client()
            c.force_login(coach)
            c.post(reverse('profil'), {
                'coach_payment_submit': '1',
                'iban': _VALID_IBAN,
            })

        profile.refresh_from_db()
        assert profile.iban == _VALID_IBAN


# ── 3. Private file serving ───────────────────────────────────────────────────

@pytest.mark.django_db
class TestServePrivateDocument:

    def _setup_doc(self, tmp_path, filename='testdoc.pdf', content=b'%PDF-1.4'):
        (tmp_path / filename).write_bytes(content)
        coach = _make_coach()
        baker.make(CoachProfile, user=coach, document=filename)
        return coach, filename

    # ── permissions ───────────────────────────────────────────────────────────

    def test_owner_gets_200(self, tmp_path):
        coach, doc = self._setup_doc(tmp_path)
        c = Client()
        c.force_login(coach)
        assert c.get(reverse('private_document', args=[doc])).status_code == 200

    def test_staff_gets_200(self, tmp_path):
        coach, doc = self._setup_doc(tmp_path)
        staff = baker.make(User, role='coach', is_staff=True, is_active=True)
        c = Client()
        c.force_login(staff)
        assert c.get(reverse('private_document', args=[doc])).status_code == 200

    def test_other_coach_gets_403(self, tmp_path):
        _coach, doc = self._setup_doc(tmp_path)
        other = _make_coach()
        c = Client()
        c.force_login(other)
        assert c.get(reverse('private_document', args=[doc])).status_code == 403

    def test_student_gets_403(self, tmp_path):
        _coach, doc = self._setup_doc(tmp_path)
        student = _make_student()
        c = Client()
        c.force_login(student)
        assert c.get(reverse('private_document', args=[doc])).status_code == 403

    def test_anonymous_redirected_to_login(self, tmp_path):
        _coach, doc = self._setup_doc(tmp_path)
        resp = Client().get(reverse('private_document', args=[doc]))
        assert resp.status_code == 302
        assert '/auth/login/' in resp['Location']

    # ── path traversal ────────────────────────────────────────────────────────

    def test_dotdot_segment_rejected(self, tmp_path):
        coach = _make_coach()
        c = Client()
        c.force_login(coach)
        resp = c.get(reverse('private_document', args=['../etc/passwd']))
        assert resp.status_code == 403

    def test_dotdot_in_subpath_rejected(self, tmp_path):
        coach = _make_coach()
        c = Client()
        c.force_login(coach)
        resp = c.get(reverse('private_document', args=['subdir/../secret.txt']))
        assert resp.status_code == 403

    def test_absolute_path_rejected(self, tmp_path, settings):
        # Create a file that matches the absolute-path tail so the DB lookup
        # could theoretically succeed if we didn't guard.
        coach = _make_coach()
        c = Client()
        c.force_login(coach)
        # Django's <path:path> won't route a leading slash in the URL, but we
        # test the view function directly via the test client's internal path.
        # The view itself must also reject paths that start with '/'.
        from django.test import RequestFactory
        from users_app.views import serve_private_document
        rf = RequestFactory()
        req = rf.get('/private-media//etc/passwd')
        req.user = coach
        resp = serve_private_document(req, '/etc/passwd')
        assert resp.status_code == 403

    # ── response headers ──────────────────────────────────────────────────────

    def test_pdf_has_attachment_disposition(self, tmp_path):
        coach, doc = self._setup_doc(tmp_path, 'report.pdf', b'%PDF-1.4')
        c = Client()
        c.force_login(coach)
        resp = c.get(reverse('private_document', args=[doc]))
        assert resp.status_code == 200
        cd = resp['Content-Disposition']
        assert 'attachment' in cd
        assert '.pdf' in cd

    def test_png_has_inline_disposition(self, tmp_path):
        coach, doc = self._setup_doc(tmp_path, 'photo.png', b'\x89PNG\r\n\x1a\n')
        c = Client()
        c.force_login(coach)
        resp = c.get(reverse('private_document', args=[doc]))
        assert resp.status_code == 200
        assert 'inline' in resp['Content-Disposition']

    def test_nosniff_header_present(self, tmp_path):
        coach, doc = self._setup_doc(tmp_path)
        c = Client()
        c.force_login(coach)
        resp = c.get(reverse('private_document', args=[doc]))
        assert resp.get('X-Content-Type-Options') == 'nosniff'


# ── 4. Registration creates CoachProfile with phone ──────────────────────────

@pytest.mark.django_db
class TestRegistrationCreatesProfile:
    def test_profile_and_phone_created(self, settings):
        settings.EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
        c = Client()
        c.post(reverse('users_app:register'), {
            'full_name': 'Test Koç',
            'email': 'testregister@example.com',
            'phone': '05321234567',
            'password1': 'V@gus2024!x',
            'password2': 'V@gus2024!x',
        })
        user = User.objects.filter(email='testregister@example.com').first()
        assert user is not None
        assert hasattr(user, 'coach_profile')
        assert user.coach_profile.phone == '+905321234567'


# ── 5. Popup context processor ───────────────────────────────────────────────

@pytest.mark.django_db
class TestCoachProfilePopup:

    def _req_popup(self, settings, path='/coach/'):
        """Return the show_coach_popup value for a given path via context processor."""
        from unittest.mock import MagicMock
        from core_config.context_processors import coach_profile_popup
        settings.COACH_PROFILE_REQUIRED = True
        coach = _make_coach(full_name='')
        baker.make(CoachProfile, user=coach, phone='')
        req = MagicMock()
        req.user = coach
        req.path = path
        return coach_profile_popup(req).get('show_coach_popup')

    def test_shown_for_coach_missing_phone(self, settings):
        settings.COACH_PROFILE_REQUIRED = True
        coach = _make_coach(full_name='Ada Yılmaz')
        baker.make(CoachProfile, user=coach, phone='')
        c = Client()
        c.force_login(coach)
        resp = c.get(reverse('coach:dashboard'))
        assert resp.context.get('show_coach_popup') is True

    def test_not_shown_for_staff(self, settings):
        settings.COACH_PROFILE_REQUIRED = True
        staff = _make_coach(is_staff=True, full_name='')
        baker.make(CoachProfile, user=staff, phone='')
        c = Client()
        c.force_login(staff)
        resp = c.get(reverse('coach:dashboard'))
        assert not resp.context.get('show_coach_popup')

    def test_not_shown_for_student(self, settings):
        settings.COACH_PROFILE_REQUIRED = True
        student = _make_student()
        c = Client()
        c.force_login(student)
        resp = c.get(reverse('student:dashboard'))
        assert not resp.context.get('show_coach_popup')

    def test_not_shown_when_gate_off(self):
        coach = _make_coach(full_name='')
        baker.make(CoachProfile, user=coach, phone='')
        c = Client()
        c.force_login(coach)
        resp = c.get(reverse('coach:dashboard'))
        assert not resp.context.get('show_coach_popup')

    def test_exempt_on_coach_profile_path(self, settings):
        assert self._req_popup(settings, path='/coach/profil/') is None

    def test_exempt_on_logout_path(self, settings):
        assert self._req_popup(settings, path='/auth/logout') is None

    def test_exempt_on_quick_update_path(self, settings):
        assert self._req_popup(settings, path='/coach/profil/guncelle/') is None

    def test_fails_open_on_exception(self, settings):
        """Context processor must return {} (not raise) when an unexpected error occurs."""
        from unittest.mock import MagicMock, PropertyMock
        from core_config.context_processors import coach_profile_popup
        settings.COACH_PROFILE_REQUIRED = True

        # Build a fully-mocked user so we don't mutate the real User class.
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.is_coach = True
        mock_user.is_staff = False
        mock_user.full_name = 'Coach Name'
        # Accessing coach_profile raises a non-ObjectDoesNotExist exception.
        type(mock_user).coach_profile = PropertyMock(
            side_effect=RuntimeError('DB gone')
        )

        req = MagicMock()
        req.user = mock_user
        req.path = '/coach/'

        result = coach_profile_popup(req)
        assert isinstance(result, dict)
        assert not result.get('show_coach_popup')


# ── 6. Phone normalisation and lock ──────────────────────────────────────────

class TestPhoneNormalisation:
    @pytest.mark.parametrize('raw,expected', [
        ('05051234567',       '+905051234567'),
        ('5051234567',        '+905051234567'),
        ('+90 505 123 45 67', '+905051234567'),
        ('0505-123-45-67',    '+905051234567'),
        ('(0505) 123 45 67',  '+905051234567'),
        ('905051234567',      '+905051234567'),
    ])
    def test_normalises_to_e164(self, raw, expected):
        assert _normalize_tr_phone_e164(raw) == expected

    @pytest.mark.django_db
    def test_phone_locked_after_first_save(self):
        """A second popup POST must not overwrite an already-saved phone."""
        coach = _make_coach()
        baker.make(CoachProfile, user=coach, phone='+905051111111')

        c = Client()
        c.force_login(coach)
        c.post(reverse('coach_profile_quick_update'), {
            'full_name': coach.full_name or 'Test Koç',
            'phone': '05059999999',
        })

        from users_app.models import CoachProfile as CP
        assert CP.objects.get(user=coach).phone == '+905051111111'


# ── 7. IBAN stored without spaces ─────────────────────────────────────────────

@pytest.mark.django_db
class TestIbanStoredWithoutSpaces:
    def test_spaces_stripped_on_save(self):
        """Submitting a spaced IBAN via the profile form must store it spaceless."""
        _SPACED = 'TR33 0006 1005 1978 6457 8413 26'
        coach = _make_coach()
        baker.make(CoachProfile, user=coach, iban='')

        c = Client()
        c.force_login(coach)
        resp = c.post(reverse('profil'), {
            'coach_payment_submit': '1',
            'iban': _SPACED,
        })

        assert resp.status_code == 302
        from users_app.models import CoachProfile as CP
        profile = CP.objects.get(user=coach)
        assert ' ' not in profile.iban
        assert profile.iban == 'TR330006100519786457841326'


# ── 8. /coach/profil/ redirect and /profil/ section visibility ────────────────

@pytest.mark.django_db
class TestProfileRouting:
    def test_coach_profil_url_redirects_to_profil(self):
        coach = _make_coach()
        c = Client()
        c.force_login(coach)
        resp = c.get(reverse('coach_profile'))
        assert resp.status_code == 302
        assert resp['Location'].rstrip('/') == '/profil'

    def test_profil_shows_payment_section_for_coach(self):
        coach = _make_coach()
        baker.make(CoachProfile, user=coach)
        c = Client()
        c.force_login(coach)
        resp = c.get(reverse('profil'))
        assert resp.status_code == 200
        assert b'coach_payment_submit' in resp.content

    def test_profil_hides_payment_section_for_student(self):
        student = _make_student()
        c = Client()
        c.force_login(student)
        resp = c.get(reverse('profil'))
        assert resp.status_code == 200
        assert b'coach_payment_submit' not in resp.content


# ── 9. Payment section open/closed default ───────────────────────────────────

@pytest.mark.django_db
class TestPaymentSectionDefault:
    def test_open_when_items_missing(self):
        coach = _make_coach()
        baker.make(CoachProfile, user=coach, phone='', iban='', document='')
        c = Client()
        c.force_login(coach)
        resp = c.get(reverse('profil'))
        assert resp.context['coach_section_open'] is True

    def test_closed_when_all_complete(self, tmp_path, settings):
        settings.PRIVATE_MEDIA_ROOT = str(tmp_path)
        (tmp_path / 'doc.pdf').write_bytes(b'%PDF-1.4')
        coach = _make_coach()
        baker.make(CoachProfile, user=coach,
                   phone='+905051234567', iban=_VALID_IBAN, document='doc.pdf')
        c = Client()
        c.force_login(coach)
        resp = c.get(reverse('profil'))
        assert resp.context['coach_section_open'] is False


# ── 10. End-to-end document upload ───────────────────────────────────────────

@pytest.mark.django_db
class TestDocumentUploadEndToEnd:
    def test_upload_writes_file_and_is_served(self, tmp_path, settings):
        settings.PRIVATE_MEDIA_ROOT = str(tmp_path)
        coach = _make_coach()
        baker.make(CoachProfile, user=coach, iban=_VALID_IBAN)

        from django.core.files.uploadedfile import SimpleUploadedFile
        upload = SimpleUploadedFile('testdoc.pdf', b'%PDF-1.4 fake', content_type='application/pdf')

        c = Client()
        c.force_login(coach)
        resp = c.post(reverse('profil'), {
            'coach_payment_submit': '1',
            'iban': _VALID_IBAN,
            'document': upload,
        })
        assert resp.status_code == 302

        profile = CoachProfile.objects.get(user=coach)
        assert profile.document                          # DB was updated
        assert profile.document.name.endswith('.pdf')   # correct extension
        assert profile.document_status == 'pending'     # status reset on new upload

        # Verify file exists on disk via the storage's own path resolution.
        from pathlib import Path
        assert Path(profile.document.path).exists()

    def test_owner_gets_200_other_coach_gets_403(self, tmp_path, settings):
        settings.PRIVATE_MEDIA_ROOT = str(tmp_path)
        filename = 'shared_doc.pdf'
        (tmp_path / filename).write_bytes(b'%PDF-1.4')
        coach = _make_coach()
        baker.make(CoachProfile, user=coach, document=filename)
        other = _make_coach()

        owner_c = Client()
        owner_c.force_login(coach)
        assert owner_c.get(reverse('private_document', args=[filename])).status_code == 200

        other_c = Client()
        other_c.force_login(other)
        assert other_c.get(reverse('private_document', args=[filename])).status_code == 403

    def test_staff_gets_200(self, tmp_path, settings):
        settings.PRIVATE_MEDIA_ROOT = str(tmp_path)
        filename = 'staff_doc.pdf'
        (tmp_path / filename).write_bytes(b'%PDF-1.4')
        coach = _make_coach()
        baker.make(CoachProfile, user=coach, document=filename)
        staff = baker.make(User, role='coach', is_staff=True, is_active=True)

        c = Client()
        c.force_login(staff)
        assert c.get(reverse('private_document', args=[filename])).status_code == 200
