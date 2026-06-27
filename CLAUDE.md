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
