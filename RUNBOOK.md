# Vagus Production Runbook

Operational procedures for the Vagus VPS deployment. Follow this end-to-end after every code pull that touches dependencies, migrations, or scheduled tasks.

## 1. Load environment variables in a manual shell

When you SSH into the VPS and want to run `manage.py` commands by hand, your shell does **not** automatically load `/srv/das/.env`. systemd loads it for services via `EnvironmentFile=`, but interactive shells must do it explicitly:

```bash
cd /srv/das
set -a
source /srv/das/.env
set +a
```

`set -a` causes every assignment that follows to be exported to child processes (so Django subprocesses see `DATABASE_URL`).

## 2. Verify Django is using PostgreSQL

After loading env vars:

```bash
source /srv/das/.venv/bin/activate
python manage.py verify_environment
```

Expected output in production:
- `DEBUG: False`
- `DATABASE_URL in os.environ: yes`
- `DATABASE_URL via decouple: yes`
- `ENGINE: django.db.backends.postgresql`
- `vendor (live): postgresql`
- `All required django_q tables exist.`

If `vendor (live): sqlite`, `DATABASE_URL` was not loaded. Re-run the `source` block in step 1, then try again.

## 3. Run migrations

After confirming env is correct:

```bash
python manage.py migrate
```

To specifically apply the django_q tables (idempotent — safe to re-run):

```bash
python manage.py migrate django_q
```

## 4. Register scheduled tasks

```bash
python manage.py bootstrap_scheduled_tasks
```

Uses `update_or_create`, so it is safe to re-run.

## 5. Restart services

```bash
sudo systemctl restart gunicorn
sudo systemctl restart vagus-qcluster
sudo systemctl restart nginx
```

Order matters: restart `gunicorn` and `vagus-qcluster` before `nginx`. If `nginx` was misconfigured, a restart may briefly drop traffic, so reload prefers `sudo systemctl reload nginx` after `nginx -t` passes.

## 6. Check logs

```bash
sudo journalctl -u vagus-qcluster -n 100 --no-pager
sudo journalctl -u gunicorn -n 100 --no-pager
tail -n 100 /var/log/vagus/qcluster-error.log
```

If the qcluster log shows `relation "django_q_ormq" does not exist`, the django_q migrations have not been applied to the database the worker is connecting to. Run steps 1, 2, and 3 again.

## 7. Smoke test

```bash
curl -i https://app.vagus.tr/healthz/
# Expect: HTTP/2 200 + {"status":"healthy","database":"up"}
```

## Standard deploy sequence (after `git pull`)

```bash
cd /srv/das
set -a; source /srv/das/.env; set +a
source /srv/das/.venv/bin/activate

pip install -r requirements-prod.txt
python manage.py verify_environment           # confirm PostgreSQL + DATABASE_URL
python manage.py migrate                      # apply all pending migrations
python manage.py bootstrap_scheduled_tasks    # register/refresh schedules
python manage.py collectstatic --noinput      # if static files changed

sudo systemctl restart vagus-qcluster
sudo systemctl restart gunicorn
sudo systemctl reload nginx

curl -i https://app.vagus.tr/healthz/
```

---

## Appendix A — Service worker version bumps

Any deploy that changes files listed in `templates/pwa/service-worker.js`'s `PRECACHE` array (icons, JS bundles, the offline page) **must** also bump the `CACHE_NAME` constant in that file (e.g. `vagus-shell-v2` → `vagus-shell-v3`). The activate handler deletes all caches with a different name, forcing returning users to re-download changed assets.

## Appendix B — First-run session flags

`invite_register_view` and `CustomLoginView.form_valid` write `request.session['first_run'] = True` on a new user's first landing. The respective dashboards (`student_dashboard`, `coach_dashboard`) pop this key and pass it as `first_run` to the template, where it controls a one-time welcome banner. No special production handling is needed — Django's session backend (database-backed by default) persists it until popped.

## Appendix C — Common incidents

### qcluster: `relation "django_q_ormq" does not exist`
The django_q migrations were not applied to the database the worker is connecting to. Fix:
```bash
set -a; source /srv/das/.env; set +a
python manage.py verify_environment   # confirm DATABASE_URL is loaded and vendor=postgresql
python manage.py migrate django_q
sudo systemctl restart vagus-qcluster
```

### dbshell opens SQLite instead of PostgreSQL
`DATABASE_URL` is not in the shell environment. Run `set -a; source /srv/das/.env; set +a` first, then retry the command.

### A2HS banner does not appear
The browser either: (a) already has the app installed (`display-mode: standalone`), (b) the user dismissed it within the past 14 days (`a2hs_dismissed_until` key in localStorage), or (c) `beforeinstallprompt` hasn't fired yet (can take a few seconds after page load). Check the browser's DevTools → Application → Manifest for installability criteria.

## Appendix D — Sentry

Sentry is only activated in production (`DEBUG=False` AND `SENTRY_DSN` is non-empty). Local development never sends events. To verify Sentry is wired correctly after a deploy, check the Sentry dashboard for the first error or trigger a test event:
```bash
python manage.py shell -c "import sentry_sdk; sentry_sdk.capture_message('test from VPS')"
```
