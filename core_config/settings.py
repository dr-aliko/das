from pathlib import Path
import dj_database_url
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key-change-in-production')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='127.0.0.1,localhost', cast=Csv())

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'users_app',
    'exams_app',
    'analytics_app',
    'tasks_app',
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
            ],
        },
    },
]

WSGI_APPLICATION = 'core_config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}'
    )
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

LANGUAGE_CODE = 'tr-tr'

TIME_ZONE = 'Europe/Istanbul'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Production security headers — only active when DEBUG=False
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER     = True
    SECURE_CONTENT_TYPE_NOSNIFF   = True
    X_FRAME_OPTIONS               = 'DENY'
    SESSION_COOKIE_SECURE         = True
    CSRF_COOKIE_SECURE            = True
    # Uncomment after confirming SSL is live on the VPS:
    # SECURE_HSTS_SECONDS           = 31536000
    # SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # SECURE_SSL_REDIRECT           = True

# External task catalog API (dersler / oynatma listeleri / videolar)
# Used only for konu_anlatimi create/refresh flow. Edit hydration uses meta.videos instead.
EXTERNAL_API_BASE_URL = config('EXTERNAL_API_BASE_URL', default='http://152.70.23.159:5000/api')
EXTERNAL_API_TIMEOUT = config('EXTERNAL_API_TIMEOUT', default=5, cast=int)

# Email — dev default prints to console; override via env vars in production
EMAIL_BACKEND       = config('EMAIL_BACKEND',       default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST          = config('EMAIL_HOST',          default='localhost')
EMAIL_PORT          = config('EMAIL_PORT',          default=25, cast=int)
EMAIL_USE_TLS       = config('EMAIL_USE_TLS',       default=False, cast=bool)
EMAIL_HOST_USER     = config('EMAIL_HOST_USER',     default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL  = config('DEFAULT_FROM_EMAIL',  default='noreply@das.com')

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

# DAS-350: Fast-entry create flow (Phase 3.3).
# Set DAS_FAST_ENTRY=true in .env to serve /student/exam/new/ as the v2 stepper create.
# Off by default; /student/exam/new/v2/ is always available for direct testing.
DAS_FAST_ENTRY = config('DAS_FAST_ENTRY', default=False, cast=bool)
