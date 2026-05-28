# Vagus — Deneme Analiz Sistemi

TYT/AYT deneme analizleri, spaced-repetition görev takvimi ve koç–öğrenci iş birliği için Django platformu.

## Stack

| Layer | Technology |
|---|---|
| Backend | Django 5.2 (Python 3.10+) |
| Database | PostgreSQL (prod) / SQLite (dev) |
| Async tasks | Django-Q2 (ORM broker — no Redis needed) |
| Frontend | Tailwind CSS + Alpine.js + Chart.js |
| PWA | Web App Manifest + Service Worker + A2HS prompt |
| Monitoring | Sentry (prod only) |
| CI | GitHub Actions (`.github/workflows/ci.yml`) |

## Local setup

```bash
git clone <repo>
cd projem

# 1. Create venv
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install deps (SQLite dev profile — no psycopg2 needed on Windows)
pip install -r requirements-dev.txt

# 3. Configure env
cp .env.example .env               # fill in SECRET_KEY at minimum

# 4. Migrate and run
python manage.py migrate
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` — shows the landing page for anonymous users.

**Creating a superuser for local admin:**
```bash
python manage.py createsuperuser
```

**Running async tasks inline (no worker needed in dev):**
Add `Q_SYNC=True` to your `.env`. All Django-Q2 tasks then run synchronously.

**YouTube Playlist Importer (optional):**
The coach panel's "Playlist Ekle" button requires a YouTube Data API v3 key.
Without it every import attempt returns a friendly JSON error — no other functionality is affected.

To enable it:
1. Go to [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Library**
2. Enable **YouTube Data API v3**
3. Go to **Credentials** → **Create Credentials** → **API key**
4. (Recommended) Restrict the key to *YouTube Data API v3* and your server's IP
5. Add to your `.env`:
   ```
   YOUTUBE_API_KEY=AIza...
   ```

The key is read only by the backend (`settings.YOUTUBE_API_KEY`) and is never sent to the browser.

## Running tests

```bash
pytest              # run all tests
pytest -v           # verbose output
pytest --cov=.      # with coverage report
```

Test files live at `exams_app/tests/` and `users_app/tests/`.

## Project layout

```
projem/
├── core_config/          # Project config package (settings, urls, views, middleware)
│   └── views.py          # healthz_view → /healthz/
├── users_app/            # Auth, coach/student model, invites, alerts, tasks
├── exams_app/            # Exams, results, topics, brans, SM-2, dashboards
├── tasks_app/            # Weekly task planner
├── templates/            # All Django templates (single template root)
├── static/               # Source static assets (CSS, JS, icons, PWA)
├── deployment/           # Systemd unit examples, ops scripts
├── RUNBOOK.md            # VPS deploy & ops procedures
└── ARCHITECTURE.md       # System design reference
```

## Conventions

- **Branches:** `feature/<slug>`, `fix/<slug>`, `chore/<slug>`
- **Commit style:** imperative mood, present tense ("Add ...", "Fix ...", "Remove ...")
- **Settings:** single `core_config/settings.py`, all values via `python-decouple`; see `.env.example`
- **Feature flags:** `V2_SHELL_ENABLED`, `V2_DEFAULT`, `DESKTOP_V2_ENABLED`, `DESKTOP_V2_DEFAULT` — see ARCHITECTURE.md
- **Migrations:** always commit generated migration files; never squash without a team notice

## Production deployment

See **[RUNBOOK.md](RUNBOOK.md)** for the full deploy checklist including env loading, migrations, worker restart, and smoke tests.

## Architecture deep-dive

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for the app boundary map, permission model, async task wiring, and full env-var reference.
