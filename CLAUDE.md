# Vagus (DAS) Project Guidelines

Vagus (Deneme Analiz Sistemi - DAS) is a Django and Tailwind-based platform designed to help students manage their exam preparation, track trial exam results, and monitor their academic curriculum.

## Development Workflow
- **Adding Packages:** After running `pip install`, ensure `requirements.txt` is updated.
- **Testing:** Always run `python manage.py test` after any significant code changes.
- **Static Assets:** When modifying CSS or templates, run `python manage.py collectstatic --noinput` to ensure changes reflect in production.

## Tools & MCP Servers
- **Playwright:** Use the Playwright MCP server for UI testing and DOM interaction. Use it to verify layout consistency and resolve CSS alignment issues.

## Coding Standards
- **Keep it Simple:** Avoid excessive comments. Write self-documenting code with clear variable and function names.
- **Frontend:** Use Tailwind CSS. Follow the CSS variables defined in `theme_system.css` (e.g., `var(--surface-*)`) to maintain design consistency.
- **Themes:** Always consider both `html:not(.dark)` and `.dark` scopes when writing component styles.

## Debugging
- **Logs:** Check `/var/log/vagus/gunicorn-error.log` for runtime issues.
- **502 Errors:** If you encounter 502 Bad Gateway, verify directory permissions (`chown`/`chmod`) and check Gunicorn status (`systemctl status gunicorn`).

## Business Logic & Key Files
- **Curriculum Engine:** The core logic is located in `core/curriculum/`. It generates dynamic study plans based on exam dates.
- **Models:** The `User` and `Student` models are the foundation of the system.
- **Reference Patterns:** Refer to `templates/student/dashboard_v2.html` and `templates/coach/curriculum/macro_plan_create.html` for preferred Tailwind component structures.

## Communication Style
- Be concise and focus directly on the solution.
- Propose a brief plan before executing complex architectural changes.
- When an error occurs, provide the fix along with the diagnosis.

## Kurallar (production'da yaşanan hatalardan)
- Every setting read in code must be declared in `core_config/settings.py` with `decouple config()`; reading an undeclared setting with `getattr` caused a production 404.
- When finishing a task, list every NEW file (migrations, templates, tests); a forgotten new file caused a production 500. Add files to git by name, never `git add -A`.
- Pass data to JS only with `json_script`; never dump JSON with `{{ }}` inside `<script>` (HTML escaping breaks the script). Alpine expressions may only use variables defined in their own `x-data` component (the coach task page has `panel()` and `coachMobilePanel()` with different variables); `:disabled` must evaluate to a real boolean.
- No Tailwind arbitrary-value or opacity classes (not in the compiled CSS bundle): use inline styles or component CSS. Use `{% comment %}` for multi-line template comments (`{# #}` is single-line only).
- `django_ratelimit key='ip'` crashes behind the Unix socket (`REMOTE_ADDR` empty): use `key='user'` on authenticated views or the project's `DatabaseCache` helpers.
- Student–coach links live in `CoachStudent` AND `User.coach`: keep both consistent; queryset `.update()` bypasses model code.
- Restrictions (blocks, locks) fail open on unexpected errors and never restrict the student side unless the task says so.
- Money actions: POST + CSRF, staff-only, idempotent (`select_for_update`), unguessable tokens in public URLs, amounts in kuruş, never trust a price from the request.
- Deploy: no `deploy.sh` on the server (manual steps), `pg_dump` before migrations, restart gunicorn AND `vagus-qcluster` after task or model changes, `bootstrap_scheduled_tasks` must not reset existing `next_run`, check `/var/log/das/gunicorn-*.log` ownership (`ubuntu`/`www-data`) after restarts.
- Playwright is blocked in the sandbox: state what could not be verified in a browser instead of claiming it works.
