# Vagus — Architecture Reference

## Apps and their boundaries

| App | Responsibility |
|---|---|
| `core_config` | Project config package. Settings, root URL conf, `healthz_view`, `V2CookieMiddleware`, context processors (`v2_shell`, `desktop_v2`). Not in `INSTALLED_APPS` — it is the project package. |
| `users_app` | Custom `User` model, coach/student relationship (`CoachStudent`), invitations (`StudentInvite`), proactive alerts (`CoachAlert`), async tasks (`tasks.py`), management commands. |
| `exams_app` | Core domain: `Exam`, `ExamResult`, `ExamTopicError`, `StudentTask` (SM-2), `BransDeneme`. All student/coach dashboard views. |
| `tasks_app` | Weekly task planner (separate from SM-2 spaced-repetition tasks). |
| `django_q` | ORM-backed async task queue — tables only, no custom code here. |

## Permission model

`coach_can_view_student(coach, student_id)` in `users_app/decorators.py` is the **single authoritative permission check** for all coach→student data access.

Lookup order:
1. `CoachStudent` table — active=True row wins.
2. Legacy fallback: `User.coach` FK match → auto-creates a `CoachStudent` row and returns True.
3. Returns False (never raises 404 — callers decide HTTP response).

All coach views in `exams_app/views.py` call this check. The `CoachAuditLog` model records accesses for privacy accountability.

## V2 shell feature flags

Two context processors (`v2_shell`, `desktop_v2`) add `v2_shell` and `desktop_v2` booleans to every template context. `base.html` uses them to switch between:
- V1 nav (simple `<nav>` bar, authenticated only)
- V2 mobile shell (`_shell_top.html`, `_shell_bottom.html`, `_shell_fab.html`)
- V2 desktop layout (`_shell_top_desktop.html`)

| Setting | Default | Effect |
|---|---|---|
| `V2_SHELL_ENABLED` | True | Master kill-switch for V2 shell |
| `V2_DEFAULT` | False (True in dev `.env`) | Activates V2 shell for everyone without cookie |
| `DESKTOP_V2_ENABLED` | True | Enables desktop layout feature |
| `DESKTOP_V2_DEFAULT` | True | Activates desktop layout for everyone |

Per-user toggle: `?v2=1` / `?v2=0` querystring or `das_v2` cookie.

## SM-2 spaced repetition

`apply_sm2(task, quality)` in `exams_app/utils.py` implements the standard SM-2 algorithm.
- `quality` ∈ {2, 3, 4, 5} — 3/4/5 are success grades; <3 is failure (resets interval).
- Called from `exams_app/views.py` → `_task_action_handler` on `action='sm2_review'`.
- Mutates and saves the `StudentTask` instance (no return value).

## Async task queue (Django-Q2)

Broker: Django ORM (same database as the app — no Redis, no RabbitMQ).

| Component | Location |
|---|---|
| Task functions | `users_app/tasks.py` |
| Schedule registration | `python manage.py bootstrap_scheduled_tasks` |
| Worker process | `python manage.py qcluster` (systemd: `vagus-qcluster.service`) |
| Settings | `Q_CLUSTER` dict in `core_config/settings.py` |

Set `Q_SYNC=True` in `.env` to run all tasks synchronously (useful in dev/testing — no worker needed).

Periodic jobs registered via `bootstrap_scheduled_tasks`:
- `users_app.tasks.generate_all_coach_alerts` — every 30 minutes.

## PWA

| Component | URL / File |
|---|---|
| Manifest | `/manifest.webmanifest` → `templates/pwa/manifest.webmanifest` (Django template, uses `{% static %}`) |
| Service Worker | `/service-worker.js` → `templates/pwa/service-worker.js` (cache name: `vagus-shell-v2`) |
| SW registration | `templates/base.html` — registered on every page load |
| A2HS prompt | `static/js/a2hs.js` — handles `beforeinstallprompt` (Chromium) and iOS hint |
| Icons | `static/vagus/pwa/` — 192/512 regular + maskable + apple-touch-icon |

**Deploying static changes:** bump `CACHE_NAME` in `service-worker.js` so returning users get a fresh cache.

Suppress A2HS on specific pages by adding `a2hs-suppress` to `<body>` (or via inline script `document.body.classList.add('a2hs-suppress')` in `{% block extra_js %}`). Currently suppressed on: `invite_register.html`, `exam_create_v2.html`.

## Data model overview

```
User (AUTH_USER_MODEL)
  role: 'coach' | 'student'
  coach: FK(self) — legacy link, superseded by CoachStudent
  denemeler_v2: Bool — per-user V2 exam dashboard flag

CoachStudent         coach FK + student FK + active Bool
CoachAuditLog        coach FK + student FK + action str + timestamp
CoachAlert           coach + student + type + severity + fingerprint (deduped)
StudentInvite        coach FK + email + token + is_used
StudentAchievement   user FK + achievement_type + awarded_at

Subject              exam_type (TYT/AYT) + name
Topic                subject FK + name + sub_category
Exam                 student FK + publisher FK + exam_date + custom_name
ExamResult           exam FK + subject FK + correct/wrong/blank + net_score
ExamTopicError       exam FK + topic FK + wrong_count + blank_count
StudentTask          student FK + topic FK + task_source + SM-2 fields
BransDeneme          student FK + subject FK + date + scores
```

## Environment variables reference

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | (insecure dev default) | Django secret key — **must** be overridden in prod |
| `DEBUG` | False | Django debug mode |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost` | Comma-separated allowed host headers |
| `DATABASE_URL` | (unset → SQLite) | Full database URL; parsed via `dj-database-url` |
| `EMAIL_BACKEND` | console | Django email backend class |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_USE_TLS` | localhost/25/False | SMTP config |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | (empty) | SMTP credentials |
| `DEFAULT_FROM_EMAIL` | `Vagus <noreply@vagus.tr>` | Sender address for all outbound mail |
| `SENTRY_DSN` | (empty) | Sentry DSN — Sentry is only active when non-empty AND `DEBUG=False` |
| `V2_SHELL_ENABLED` | True | Master switch for V2 shell feature |
| `V2_DEFAULT` | False | Activate V2 shell for all users |
| `DESKTOP_V2_ENABLED` | True | Enable desktop layout |
| `DESKTOP_V2_DEFAULT` | True | Activate desktop layout for all users |
| `Q_SYNC` | False | Run Django-Q2 tasks synchronously (dev/test only) |
| `DJANGO_LOG_FILE` | (empty) | Path for rotating log file; unset disables file logging |
| `EXTERNAL_API_BASE_URL` | `http://...` | External task catalog API base |
| `CSRF_TRUSTED_ORIGINS` | `https://vagus.tr,...` | Comma-separated trusted CSRF origins |
