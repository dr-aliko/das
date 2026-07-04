# Vagus (DAS) — UI/UX Redesign Plan

**Scope:** Full visual redesign of the coach + student panel. Dark-mode primary, mobile-first, dual-role aware.
**Hard constraint:** Zero changes to Django views, context variables, form `name` attributes, CSRF tokens, URL endpoints, or JS data-injection points (`window._DAS_*`, `{{ x|safe }}` blocks).
**Strategy:** Evolve the existing DAS token system (`tokens.css`, `theme_system.css`, `components.css`) — do not replace it. Every phase is independently shippable and revertible.

---

## Part 1 — Visual Direction

### 1.1 Aesthetic

**"Focused Academic Dark"** — a data-dense dashboard style with calm, desaturated surfaces. Not OLED-black (harsh halation on text-heavy screens), not neon/cyberpunk (eye strain, unserious for an education product). Think Linear/Height-style depth: a ladder of dark blue-grey surfaces, one confident brand accent, and semantic color used *only* for meaning (never decoration).

- **Coach surfaces:** density dial high — compact spacing, tabular data, minimal chrome.
- **Student surfaces:** same tokens, looser spacing scale and larger type — warmth comes from spacing and motivational microcopy, not a different theme.

### 1.2 Dark Mode Palette (primary theme)

Extend `tokens.css` under the existing `.das-dark` scope. Keep the brand purple, lighten it for dark backgrounds (dark mode = desaturate/lighten, never invert).

**Surface elevation ladder** (background lightens with elevation — no heavy shadows in dark mode):

| Token | Value | Use |
|---|---|---|
| `--surface-0` | `#0B0E16` | App background |
| `--surface-1` | `#121623` | Cards, panels (`.das-card`) |
| `--surface-2` | `#1A1F2F` | Nested cards, table header, hover rows |
| `--surface-3` | `#232A3D` | Dropdowns, popovers, sticky bars |
| `--surface-overlay` | `#2B3348` | Modals, sheets (+ scrim `rgba(4,6,12,0.6)`) |

**Text & borders:**

| Token | Value | Contrast on surface-1 |
|---|---|---|
| `--heading` | `#F1F3FA` | ~15:1 |
| `--body` | `#C3C9DA` | ~9:1 |
| `--muted` | `#8B93AB` | ~4.6:1 (AA — floor for any readable text) |
| `--border` | `#252C40` | hairline dividers |
| `--border-strong` | `#39415C` | inputs, focused cards |

**Brand & semantic** (all pairs verified ≥ 4.5:1 on `--surface-1` for text, ≥ 3:1 for large UI):

| Token | Value | Meaning |
|---|---|---|
| `--primary` | `#8B7CFF` (dark) / keep `#6D5BFF` (light) | Actions, active nav, links |
| `--primary-soft` | `rgba(139,124,255,0.14)` | Selected/active fills |
| `--success` / `--up` | `#4ADE80` text, `rgba(74,222,128,0.12)` fill | Net improvement, completed |
| `--danger` / `--down` | `#F87171` text, `rgba(248,113,113,0.12)` fill | Decline, missed |
| `--warning` | `#FBBF24` text, `rgba(251,191,36,0.12)` fill | Pending, due soon |
| `--info` | `#60A5FA` | Neutral notices |

Rules: semantic color **always** pairs with an icon or label (▲/▼ + text), never color alone (colorblind safety). Existing subject colors (`--turkce/--mat/--sosyal/--fen`) stay, but get dark-mode variants lightened ~15% for contrast on dark surfaces.

**Light mode** stays fully supported via existing `html:not(.dark)` scope — every new token gets both values, defined side by side.

### 1.3 Typography

Keep the current sans (no font swap = no layout risk). System is optimized for dense numerals:

- **Numeric data everywhere** (scores, nets, dates, deltas): `font-variant-numeric: tabular-nums` — extend the existing `tnum.css` utility to all tables, KPI cards, and chart tooltips. Prevents column jitter when values change.
- **Type scale** (rem): 12 (labels/captions), 14 (coach table body, secondary), 16 (body — mobile floor, prevents iOS zoom), 18 (card titles), 24 (section/KPI values), 32–36 (student hero numbers).
- **Weights:** 600–700 headings and KPI values, 500 labels/nav, 400 body. Muted color + smaller size for units ("net", "%") next to big numbers.
- **Line-height:** 1.5 body, 1.2 numeric displays, 1.3 headings.

### 1.4 Layout & Spacing

- Extend existing `--s-*` scale to: 4 / 8 / 12 / 16 / 24 / 32 / 48.
- **Coach density:** card padding 16px, table row height 44px (still touch-safe), gaps 12px.
- **Student breathing room:** card padding 20–24px, section gaps 32px, one primary focus block per screen.
- Container: `max-w-7xl` coach (wide tables), `max-w-3xl` student content pages, dashboards `max-w-5xl`.
- Radius: keep `--r-card:14px`, `--r-chip:8px`, `--r-pill`.
- **Z-index scale (formalize):** content 0 / sticky headers 20 / bottom nav 30 / dropdowns 40 / modals 50 / toasts 60.
- Breakpoints: keep Tailwind defaults + existing `xs:360px`. Design at 375px first, verify at 768 / 1024 / 1440.

---

## Part 2 — Component Guidelines

### 2.1 Navigation

Current shells (`_shell_top_desktop.html`, `_shell_bottom.html`) are the right pattern — restyle, don't restructure.

- **Desktop (≥1024px):** sticky top bar → upgrade to a slim left **sidebar** for coach only if nav grows past 6 items; otherwise keep top tabs (less migration risk). Active state = `--primary` text + 2px bottom indicator + `--primary-soft` pill background. Never color alone.
- **Mobile:** keep bottom nav (max 5 items, icon + label, `env(safe-area-inset-bottom)` preserved). Active = filled icon variant + primary color. Badge dot on "Görevler"/"Denemeler" for pending items — clears on visit.
- Role separation stays template-driven (existing `if` branching) — no JS role logic.
- Touch targets ≥ 44×44px everywhere; nav items get expanded hit areas.

### 2.2 Dashboards (role-specific widgets)

**Coach dashboard — "radar for problems":**
1. KPI strip: active students, exams entered this week, avg net Δ, students with declining trend (tap → filtered roster).
2. **Alerts panel** (top priority): students with 2+ missed tasks, no exam in X days, net drop ≥ threshold. Each alert = one row: avatar, name, reason badge, quick action.
3. Recent exam entries feed (compact list, relative timestamps).
4. Mini comparative sparklines per student group.

**Student dashboard (`dashboard_v2.html`) — "today, one glance":**
1. Greeting + streak/momentum indicator (motivational, not shaming — show progress, frame gaps neutrally).
2. **Today's checklist** card: 3–5 tasks, large tap-to-complete toggles, progress ring.
3. Net trend chart (last N exams) with delta chip (▲ +2.5 net).
4. Next exam countdown card.
5. Weak-topic nudge: one card, one topic, one action ("10 soru çöz").

### 2.3 Responsive Tables & Data Lists

Decision rule per table:

- **≤5 columns, scannable (roster):** desktop table → **card list on mobile** (`lg:` visibility split, or CSS grid re-flow). Card shows: name, key metric, trend chip, tap target to detail. Both variants live in the same template so context/loops are shared.
- **Wide numeric tables (exam history, subject nets):** keep table on mobile with **sticky first column + horizontal scroll** (`overflow-x-auto`), scroll affordance (gradient fade edge). Converting 10-column score data to cards destroys comparability.
- Table anatomy: header row `--surface-2`, sticky on scroll; row hover `--surface-2`; 44px row height; numeric columns right-aligned + tabular-nums; sort indicators with `aria-sort`.
- Pagination: coach tables paginate ≥ 25 rows; "load more" button on mobile.
- **Empty states:** every list/table gets icon + one sentence + primary action ("Henüz deneme yok — İlk denemeni ekle"). No blank whitescreens.
- Quick-filters (roster): horizontal chip row, `overflow-x-auto no-scrollbar` (pattern already exists), active chip = `--primary-soft` fill.

### 2.4 Forms & Data Entry

**Coach fast score entry:**
- Grid layout: subjects as rows, D/Y (correct/wrong) inputs as columns; net auto-calculates live in a right-aligned tabular-nums cell.
- `inputmode="numeric"` on all score fields (correct mobile keyboard); Enter/Tab advances to next field; visible focus ring (2px `--primary`).
- Sticky submit bar bottom (pattern exists in `entry-flow.css`) with running total net.
- Validation on blur, not keystroke; error text below field in `--danger` + icon; on submit error, focus first invalid field.
- Keep existing draft persistence (`das-draft.js`) untouched.

**Student checklist toggles:**
- Full-row tap target (min 48px), custom checkbox with 150–200ms check animation, completed row gets strikethrough + muted (not removed — visible progress).
- Optimistic UI: toggle immediately, revert with toast on failure.

**Universal:** visible labels (never placeholder-only), required markers, disabled = 0.4 opacity + `cursor-not-allowed`, all inputs ≥ 44px tall on mobile.

**Never touch:** `name=`, `value=`, `{% csrf_token %}`, `action=`, hidden inputs, Alpine `x-model` bindings.

### 2.5 Data Visualization (Chart.js on dark)

All colors must flow through the existing `das-tokens.js` bridge (`DAS.getCssVar()`) — never hardcode hex in chart configs. This makes charts theme-switch correctly for free.

- **Gridlines:** `rgba(139,147,171,0.12)`; axis ticks `--muted`; no chart borders.
- **Net trend (line):** `--primary` line 2px, gradient fill fading to transparent (~15% → 0%), point radius 3 (5 on hover, ≥44px tap area via `hitRadius`), smooth tension 0.3.
- **Subject breakdown (radar):** max 2 datasets overlaid (student vs. class avg / vs. previous period), 25–30% alpha fills, distinct line styles (solid vs dashed) for colorblind users. > 2 comparisons → grouped bar instead.
- **Comparison (bar):** subject colors from tokens, value labels on bars, sorted by value.
- Tooltips: `--surface-3` background, `--border-strong` border, tabular-nums values.
- Delta chips next to every chart title (▲/▼ + value + color) so the insight survives without reading the chart.
- Loading: skeleton shimmer block, not empty axes. Empty data: message + CTA. Respect `prefers-reduced-motion` (disable entrance animation).
- Mobile: fewer x-ticks (`maxTicksLimit`), legend above chart, min chart height 220px.

### 2.6 Interactive Elements

- **Buttons:** primary (`--primary` fill, white text, hover lighten 8%, active scale 0.98), secondary (`--surface-2` fill + border), ghost, danger. Loading state = spinner + disabled. All transitions 150–200ms.
- **Status badges:** pill, 12px, semantic soft-fill + icon: `tamamlandı` (green + check), `bekliyor` (amber + clock), `kaçırıldı` (red + x), `aktif` (primary).
- **Modals:** `--surface-overlay` panel, 60% scrim, close X + Esc + scrim-click, focus trap; on mobile become **bottom sheets** (slide up, drag handle, safe-area padding).
- **Toasts:** top-right desktop / above bottom-nav mobile, auto-dismiss 4s, `aria-live="polite"`, undo action for destructive ops.
- **Confirmation dialog** before any delete (exam, task, student).
- Focus rings visible on everything interactive (2px `--primary`, offset 2px).

---

## Part 3 — Implementation Phases

Global risk rules (apply to every phase):

- **CSS-first:** changes go into `tokens.css` / `theme_system.css` / `components.css` / new `components-*.css` files and Tailwind classes in templates. Python files are read-only for this entire project.
- Template edits touch only `class=` attributes and presentational wrapper elements — never `{% %}` logic, `{{ }}` variables, `name/id/action/value` attributes, or `<script>` data blocks. `id`s referenced by JS/Alpine are frozen.
- After every phase: `python manage.py collectstatic --noinput` + `python manage.py test` + Playwright MCP visual pass at 375px and 1440px in **both** themes.
- One phase = one commit (or PR). Any regression → revert the single commit.

---

### Phase 1 — Design Tokens & Dark Mode Foundation

**Do:**
- Extend `tokens.css`: full surface ladder (`--surface-0..3`, `--surface-overlay`), text tokens, semantic set (success/warning/danger/info + soft fills), z-index scale, extended spacing — each with `.das-dark` and light values.
- Reconcile `theme_system.css` `--surface-*` names with new ladder (aliases, don't rename existing vars — old references must keep working).
- Dark-mode variants for subject colors.
- Extend `tnum.css` usage rules; add `color-scheme: dark` on `.das-dark` (native scrollbars/inputs).
- Sync `tailwind.config.js` palette to reference the same values; rebuild `tailwind.min.css`.
- Document every token in a short `static/css/TOKENS.md`.

**Don't:** touch any template layout, JS, or component structure.

**Acceptance criteria:**
- [ ] Every token has both dark and light values; theme toggle still works (`toggleDM()` untouched).
- [ ] All existing pages render pixel-equivalent or better (no regressions — tokens are additive).
- [ ] Contrast audit passes: body text ≥ 4.5:1, muted ≥ 4.5:1, semantic-on-soft-fill ≥ 4.5:1, UI borders ≥ 3:1 in both themes.
- [ ] `collectstatic` + test suite green.

---

### Phase 2 — Navigation & App Shell

**Do:**
- Restyle `_shell_top_desktop.html` and `_shell_bottom.html` with new tokens: active states (`--primary-soft` pill + indicator), pressed feedback, badge dot support (data comes from context vars that already exist — if a count isn't in context, ship the badge slot hidden/empty rather than adding view logic).
- Sticky top bar gets `--surface-1` + hairline border + backdrop-blur.
- Standardize page header pattern (title, breadcrumb where >2 levels deep on coach side, primary action button top-right).
- Verify safe-area insets, 44px targets, keyboard focus order through nav.

**Don't:** change URL structure, nav item order/logic, or the Alpine active-path detection.

**Acceptance criteria:**
- [ ] Both roles' nav renders correctly on 375 / 768 / 1440px, both themes.
- [ ] Active page always visibly indicated; focus ring visible tabbing through nav.
- [ ] Bottom nav never overlaps content (scroll padding reserved) and respects notch/gesture bar.
- [ ] No changes to any `href` or template `if` branching.

---### Phase 3 — Dashboards (Coach + Student)

**Do:**
- Restyle `coach/dashboard.html` + `coach/roster.html` header area: KPI strip, alerts panel styling (using data already in context; alerts that need new queries are deferred to a backlog list, not hacked in).
- Restyle `student/dashboard_v2.html`: greeting block, today-checklist card, KPI strip with tabular-nums and delta chips, next-exam countdown card, section rhythm per student spacing rules.
- Skeleton loading states for KPI cards and chart containers.
- Empty states for new users (no exams / no tasks yet).

**Don't:** modify `window.DASInitCharts()` call sites, `_DAS_*` globals, or period-switcher Alpine logic — restyle their containers only.

**Acceptance criteria:**
- [ ] Coach dashboard scannable in < 5s: KPIs + alerts above the fold at 1440px; stacked cleanly at 375px.
- [ ] Student dashboard shows today's tasks + net trend above the fold on mobile.
- [ ] Period switcher, comparison selector, and all charts still function (manual Playwright pass).
- [ ] Every widget has loading + empty states.

---

### Phase 4 — Tables, Lists & Mobile Responsiveness

**Do:**
- `coach/roster.html`: desktop table restyle + mobile card-list variant (same context loop, responsive visibility). Filter chips row restyled.
- `coach/student_detail.html` + `student/` exam list: exam history as sticky-first-column scrollable table on mobile with fade affordance.
- Standardize a `.das-table` component class set in `components.css` (header, row hover, numeric alignment, sort states, `aria-sort`).
- Pagination / load-more styling. Empty states everywhere.
- Status badges component (pill + icon set from existing SVG sprite).

**Don't:** alter sorting/filtering querystring parameters, pagination logic, or any `{% for %}` loop structure (duplicating a loop for a mobile variant is allowed; changing its contents is not).

**Acceptance criteria:**
- [ ] No horizontal page scroll at 375px anywhere; wide tables scroll internally with visible affordance.
- [ ] Roster usable one-handed on mobile: filter, find student, open detail in ≤ 3 taps.
- [ ] Numeric columns aligned (tabular-nums), sortable headers announce state.
- [ ] Zero diff in rendered data values vs. pre-redesign (spot-check same context → same numbers).

---

### Phase 5 — Forms & Exam Entry

**Do:**
- Restyle `student/exam_create_v2.html` stepper + `entry-flow.css`: score grid with live net cell, `inputmode="numeric"`, focus flow, sticky footer polish, draft banner restyle.
- Coach-side entry forms same treatment.
- Checklist toggle component for tasks (student + coach task panels): 48px rows, check animation, optimistic completed styling.
- Universal validation styles: on-blur errors below fields, error summary pattern, focus-first-invalid.
- Confirmation dialogs for deletes; toast component (`aria-live`).

**Don't:** touch `name`/`value`/hidden inputs, `{% csrf_token %}` placement, form `action`s, `das-draft.js`, or `tasks_panel.js` logic (its DOM hooks/`id`s are frozen — style via added classes only).

**Acceptance criteria:**
- [ ] Full exam entry flow completes on a 375px device: correct numeric keyboard, no zoom-on-focus (16px inputs), net updates live, draft persists.
- [ ] Submit with server-side error re-renders with all entered values intact (proves `name` attrs untouched).
- [ ] Task toggle works in both panels; failure shows toast and reverts.
- [ ] Keyboard-only user can complete entry end-to-end.

---

### Phase 6 — Charts & Data Visualization

**Do:**
- Extend `das-tokens.js` with a shared `DAS.chartDefaults()` (grid color, tick color, tooltip theme, font, reduced-motion check) applied via `Chart.defaults` — one place, all charts inherit.
- Restyle each chart: dashboard trend line (gradient fill), radar comparisons (alpha fills + line-style differentiation), subject bars (token colors, value labels).
- Delta chips beside chart titles; skeleton loaders; empty-data states.
- Theme-switch handling: charts re-read CSS vars on toggle (re-render hook on the existing `toggleDM()` event — additive listener, not a rewrite).
- Mobile chart config: tick limits, legend position, min heights, `hitRadius` for touch.

**Don't:** change any data injection (`|safe` JSON blocks, `window._DAS_*`), chart data mapping, or period-filter logic.

**Acceptance criteria:**
- [ ] All charts legible in dark mode: gridlines subtle, series ≥ 3:1 vs background, tooltips themed.
- [ ] Toggling theme updates chart colors without page reload (or documented fallback: reload).
- [ ] Radar limited to 2 datasets with distinct line styles; every chart has an adjacent text delta (insight without color perception).
- [ ] Charts readable at 375px; tooltip values use tabular-nums; `prefers-reduced-motion` disables animations.

---

### Phase 7 (optional polish) — Notifications, Micro-interactions & A11y Sweep

- Notification/reminder surface styling (badge dots, inbox list, toast reminders for upcoming exams).
- Motion pass: 150–300ms tokens (`--transition-fast/base`), ease-out enter / ease-in exit, stagger on list entrances, all behind `prefers-reduced-motion`.
- Full accessibility audit: heading hierarchy, skip-link, `aria-label`s on icon buttons, focus management in modals, screen-reader pass on both dashboards.
- Lighthouse ≥ 90 accessibility on the 6 key pages; PWA icons/splash re-checked against new palette.

---

## Handoff Notes

- Feed phases to Claude Code **one at a time**, in order — each phase's prompt should reference this file + the phase number.
- Phase 1 is the multiplier: do not start Phase 2+ until token contrast audit passes.
- Anything that requires new backend data (e.g., alert queries, badge counts not in context) goes on a **backend backlog** — never inline into a styling phase.
- Regression check after each phase: `manage.py test`, `collectstatic`, Playwright screenshots at 375/1440 × dark/light on: coach roster, student detail, student dashboard, exam entry, subject drill-down.
