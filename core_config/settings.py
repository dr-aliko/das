from pathlib import Path
import subprocess
import dj_database_url
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

try:
    GIT_COMMIT = subprocess.check_output(
        ['git', 'rev-parse', '--short', 'HEAD'],
        cwd=BASE_DIR, stderr=subprocess.DEVNULL
    ).decode().strip() or 'dev'
except Exception:
    GIT_COMMIT = 'dev'

SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key-change-in-production')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='app.vagus.tr,127.0.0.1,localhost', cast=Csv())

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'import_export',
    'users_app',
    'exams_app',
    'tasks_app',
    'django_q',
    'konu_takip_app',
    'struggle_app',
    'marketing_app',
    'purchase_app',
    'earnings_app',
    'capacity_app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'core_config.middleware.V2CookieMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core_config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core_config.context_processors.v2_shell',
                'core_config.context_processors.desktop_v2',
                'core_config.context_processors.site_urls',
                'core_config.context_processors.coach_profile_popup',
                'marketing_app.context_processors.site_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'core_config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases
#
# Production: set DATABASE_URL in /srv/das/.env (loaded by systemd via EnvironmentFile)
#   e.g. DATABASE_URL=postgres://vagus:***@127.0.0.1:5432/vagus_prod
# Local dev: leave DATABASE_URL unset → falls back to SQLite at BASE_DIR/db.sqlite3.
#
# We route DATABASE_URL through python-decouple (NOT dj_database_url.config() directly)
# so it can be sourced from either:
#   1. The shell environment (set by systemd EnvironmentFile= or `source .env`), OR
#   2. The .env file found via cwd walk-up from BASE_DIR.
# dj_database_url.config() only checks os.environ, which silently fails over to
# SQLite when manual `manage.py` commands are run in a shell that hasn't sourced .env.

DATABASE_URL = config('DATABASE_URL', default='').strip()
if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL, conn_max_age=60),
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            'CONN_MAX_AGE': 60,
        }
    }


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

AUTH_USER_MODEL = 'users_app.User'
LOGIN_URL = '/auth/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/auth/login/'
PASSWORD_RESET_TIMEOUT = 3600  # reset links expire after 1 hour

# Cache — DatabaseCache uses PostgreSQL (shared across all Gunicorn workers).
# LocMemCache (Django's implicit default) is per-process and breaks rate limiting
# under multi-worker Gunicorn deployments.
# Run once on the VPS after every deploy that adds this setting:
#   python manage.py createcachetable
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'django_cache',
    }
}

LANGUAGE_CODE = 'tr-tr'

TIME_ZONE = 'Europe/Istanbul'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Django 5.1+ requires STORAGES instead of the deprecated STATICFILES_STORAGE.
# CompressedManifestStaticFilesStorage hashes file names so nginx's
# "expires 30d; Cache-Control: public, immutable" is safe: each deploy gets
# new filenames and browsers never serve a stale copy.
# manifest_strict=False prevents 500s if a third-party template references
# a file that was not collected (e.g. admin overrides, missing fonts).
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "core_config.storage.ManifestStorage",
    },
}

# User-uploaded media — local disk storage (single-VPS deployment).
# Dev default: BASE_DIR/media/  (created automatically on first upload).
# Production: set MEDIA_ROOT=/srv/das/media in .env, then add the nginx block below.
#
# Nginx config needed on the VPS (add inside the server {} block):
#   location /media/ {
#       alias /srv/das/media/;
#       expires 7d;
#       add_header Cache-Control "public";
#   }
MEDIA_URL  = config('MEDIA_URL',  default='/media/')
MEDIA_ROOT = Path(config('MEDIA_ROOT', default=str(BASE_DIR / 'media')))

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Trust Nginx's X-Forwarded-Proto header so request.is_secure() and secure
# cookies work correctly behind TLS termination. Safe in local dev (ignored when
# no such header is present).
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Allow form posts from our production domain. Override via env if needed.
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://app.vagus.tr',
    cast=Csv(),
)

PUBLIC_SITE_URL = config('PUBLIC_SITE_URL', default='https://vagus.tr').rstrip('/')
APP_BASE_URL = config('APP_BASE_URL', default='https://app.vagus.tr').rstrip('/')

# Production security headers — only active when DEBUG=False
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
else:
    # Lokalde geliştirme yaparken HTTPS zorlamasını devre dışı bırak
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

# External task catalog API (dersler / oynatma listeleri / videolar)
# Used only for konu_anlatimi create/refresh flow. Edit hydration uses meta.videos instead.
EXTERNAL_API_BASE_URL = config('EXTERNAL_API_BASE_URL', default='http://152.70.23.159:5000/api')
EXTERNAL_API_TIMEOUT = config('EXTERNAL_API_TIMEOUT', default=5, cast=int)
LEGACY_PLAYLISTS_ENABLED = config('LEGACY_PLAYLISTS_ENABLED', default=True, cast=bool)

# YouTube Data API v3 — used by the playlist importer; never exposed to frontend
YOUTUBE_API_KEY = config('YOUTUBE_API_KEY', default='')

# Email — dev default prints to console; override via env vars in production
EMAIL_BACKEND       = config('EMAIL_BACKEND',       default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST          = config('EMAIL_HOST',          default='localhost')
EMAIL_PORT          = config('EMAIL_PORT',          default=25, cast=int)
EMAIL_USE_TLS       = config('EMAIL_USE_TLS',       default=False, cast=bool)
EMAIL_HOST_USER     = config('EMAIL_HOST_USER',     default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL  = config('DEFAULT_FROM_EMAIL',  default='Vagus <noreply@vagus.tr>')

# Web Push (VAPID) — generate key pair once with py_vapid; store in .env
VAPID_PUBLIC_KEY  = config('VAPID_PUBLIC_KEY',  default='')
VAPID_PRIVATE_KEY = config('VAPID_PRIVATE_KEY', default='')
VAPID_ADMIN_EMAIL = config('VAPID_ADMIN_EMAIL', default='info@vagus.tr')

# ── Self-purchase feature ──────────────────────────────────────────────────────
SELF_PURCHASE_ENABLED    = config('SELF_PURCHASE_ENABLED',    default=False, cast=bool)
LEGAL_TERMS_URL          = config('LEGAL_TERMS_URL',          default='https://vagus.tr/kullanim-kosullari/')
LEGAL_DISTANCE_SALES_URL = config('LEGAL_DISTANCE_SALES_URL', default='https://vagus.tr/mesafeli-satis-sozlesmesi/')
LEGAL_PRELIM_INFO_URL    = config('LEGAL_PRELIM_INFO_URL',    default='https://vagus.tr/on-bilgilendirme-formu/')
LEGAL_REFUND_URL         = config('LEGAL_REFUND_URL',         default='https://vagus.tr/iptal-iade-ve-cayma-kosullari/')
LEGAL_KVKK_URL           = config('LEGAL_KVKK_URL',           default='https://vagus.tr/kvkk/')
LEGAL_PRIVACY_URL        = config('LEGAL_PRIVACY_URL',        default='')
LEGAL_DOCS_VERSION       = config('LEGAL_DOCS_VERSION',       default='2026-10-20')
PURCHASE_PRICE_TAX_LABEL = config('PURCHASE_PRICE_TAX_LABEL', default='KDV dahil')
PAYMENT_SANDBOX          = config('PAYMENT_SANDBOX',          default=False, cast=bool)

# Bank-transfer provider
PURCHASE_IBAN                     = config('PURCHASE_IBAN',                     default='')
PURCHASE_IBAN_HOLDER              = config('PURCHASE_IBAN_HOLDER',              default='')
PURCHASE_BANK_NAME                = config('PURCHASE_BANK_NAME',                default='')
PURCHASE_STAFF_NOTIFICATION_EMAIL = config('PURCHASE_STAFF_NOTIFICATION_EMAIL', default='')
BANK_TRANSFER_EXPIRY_DAYS         = config('BANK_TRANSFER_EXPIRY_DAYS',         default=7, cast=int)
PURCHASE_WHATSAPP_NUMBER          = config('PURCHASE_WHATSAPP_NUMBER',          default='')
AUTO_DEACTIVATE_VAGUS_OVERDUE     = config('AUTO_DEACTIVATE_VAGUS_OVERDUE',     default=True, cast=bool)
COACH_EARNING_AUTO_RELEASE        = config('COACH_EARNING_AUTO_RELEASE',        default=True, cast=bool)

# ── Coach capacity enforcement ─────────────────────────────────────────────────
# When True, coaches cannot create invites or accept students beyond their granted slots.
# Default False: enforcement disabled (safe rollout gate).
COACH_CAPACITY_ENFORCED = config('COACH_CAPACITY_ENFORCED', default=False, cast=bool)

# ── Coach profile / payment identity ──────────────────────────────────────────
# Files stored here are NEVER served by nginx or whitenoise; always via a Django
# view that checks ownership + staff permission.
# Production: set PRIVATE_MEDIA_ROOT=/srv/das/private_media in .env and make
# sure the backup routine covers this directory (same rsync/pg_dump run).
PRIVATE_MEDIA_ROOT = Path(config('PRIVATE_MEDIA_ROOT', default=str(BASE_DIR / 'private_media')))

# When True, coaches without a full_name or phone see a non-dismissible overlay
# on every page until they fill in the missing fields.
# Default False: gate is off; turn on after existing coaches have been notified.
COACH_PROFILE_REQUIRED = config('COACH_PROFILE_REQUIRED', default=False, cast=bool)

# V2 shell feature flag — set V2_SHELL_ENABLED=False in env to disable for all users.
V2_SHELL_ENABLED = config('V2_SHELL_ENABLED', default=True, cast=bool)

# V2_DEFAULT=True activates the V2 shell for all users without ?v2=1 or cookie.
# Set True in .env for local development. Leave unset (defaults False) in production.
V2_DEFAULT = config('V2_DEFAULT', default=False, cast=bool)

# Phase 7: Desktop layout refactor. Additive — zero mobile impact.
# DESKTOP_V2_DEFAULT=True activates the desktop layout for all users.
# Per-user toggle: ?desktop_v2=1 / ?desktop_v2=0, cookie das_desktop_v2.
DESKTOP_V2_ENABLED = config('DESKTOP_V2_ENABLED', default=True, cast=bool)
DESKTOP_V2_DEFAULT = config('DESKTOP_V2_DEFAULT', default=True, cast=bool)

# ── Logging ───────────────────────────────────────────────────────────────────
# Console handler is always active (captured by Gunicorn/systemd on prod).
# File handler activates only when DJANGO_LOG_FILE is set in the environment,
# so local dev never needs the /var/log/ directory to exist.
_LOG_FILE = config('DJANGO_LOG_FILE', default='')
_LOG_HANDLERS = ['console'] + (['file'] if _LOG_FILE else [])

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
            'level': 'WARNING',
        },
    },
    'root': {
        'handlers': _LOG_HANDLERS,
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': _LOG_HANDLERS,
            'level': 'ERROR',
            'propagate': False,
        },
        'django.request': {
            'handlers': _LOG_HANDLERS,
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

if _LOG_FILE:
    LOGGING['handlers']['file'] = {
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': _LOG_FILE,
        'maxBytes': 10 * 1024 * 1024,  # 10 MB per file
        'backupCount': 5,
        'formatter': 'verbose',
        'level': 'ERROR',
    }

# ── Django-Q2 — async task queue (ORM broker, no Redis required) ──────────────
Q_CLUSTER = {
    'name': 'vagus',
    'workers': 3,
    'recycle': 500,
    'timeout': 60,
    'retry': 360,
    'max_attempts': 3,
    'queue_limit': 50,
    'bulk': 10,
    'orm': 'default',
    # Set Q_SYNC=True in .env to run tasks synchronously (useful for dev/testing).
    'sync': config('Q_SYNC', default=False, cast=bool),
}

# ── Sentry — error tracking ───────────────────────────────────────────────────
# Activates whenever SENTRY_DSN is non-empty — set it in .env for both production
# and local testing. Leave it unset (or empty) to disable entirely.
# The `environment` tag lets you filter production vs. local events in the dashboard.

def _sentry_before_send(event, hint):
    # Drop DisallowedHost noise from the logging integration path.
    if event.get('logger') == 'django.security.DisallowedHost':
        return None
    # Drop DisallowedHost noise from the exception path (e.g. via DjangoIntegration).
    exc_info = hint.get('exc_info')
    if exc_info is not None:
        exc_type = exc_info[0]
        if exc_type is not None:
            from django.core.exceptions import DisallowedHost
            if issubclass(exc_type, DisallowedHost):
                return None
    return event


SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        environment='development' if DEBUG else 'production',
        traces_sample_rate=0.1,   # capture 10% of requests for performance tracing
        send_default_pii=False,   # never attach user PII (name/email) to Sentry events
        before_send=_sentry_before_send,
    )
