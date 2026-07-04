# DAS Design Tokens — Reference (REDESIGN Phase 1)

Single source of truth: `tokens.css`. Dark values live in the internal `--dark-*` set
(defined at `:root`), mapped onto live tokens by `theme_system.css` for the scopes
`.das-dark`, `.das-theme-dark`, `html.dark`, and `.das-theme-auto` (OS dark).
Never hardcode a dark hex — reference `var(--dark-*)` or use the live token.

## Surfaces (elevation ladder — background lightens with elevation)

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` / `--surface-0` | `#F6F7FB` | `#0B0E16` | Page background |
| `--surface-1` | `#ffffff` | `#121623` | Cards (`.das-card`), nav bars |
| `--surface-2` | `#f4f4f8` | `#1A1F2F` | Nested fills, table headers, hover rows, inputs |
| `--surface-3` | `#e8e8ef` | `#232A3D` | Dropdowns, chips, sticky bars |
| `--surface-overlay` | `#ffffff` | `#2B3348` | Modals, sheets |
| `--scrim` | `rgba(9,11,20,.45)` | `rgba(4,6,12,.6)` | Modal backdrop |

## Borders

| Token | Light | Dark |
|---|---|---|
| `--border` | `#e2e2ea` | `#252C40` (hairlines) |
| `--border-strong` | `#c8c8d8` | `#39415C` (inputs, focus-adjacent) |

## Text

| Token | Light | Dark | Contrast on surface-1 (dark) |
|---|---|---|---|
| `--heading` | `#111118` | `#F1F3FA` | ~15:1 |
| `--body` | `#2d2d3a` | `#C3C9DA` | ~9:1 |
| `--muted` | `#62627a` | `#8B93AB` | ~4.6:1 (AA floor — lowest readable) |
| `--muted-2` | `#9898ad` | `#6B7390` | decorative only, never body copy |

## Brand

| Token | Light | Dark |
|---|---|---|
| `--primary` | `#6D5BFF` | `#8B7CFF` |
| `--primary-glow` | `#7C6BF2` | `#A99DFF` (links/accents on dark) |
| `--primary-tint` | `rgba(109,91,255,.10)` | `rgba(139,124,255,.14)` (selected fills) |
| `--primary-soft` | `#4F44B8` | (constant — solid deep purple) |

## Semantic status (always pair with icon/text, never color alone)

| Token | Light | Dark | Meaning |
|---|---|---|---|
| `--up` / `--success` (+`-tint`) | `#15803D` | `#4ADE80` | improvement, completed |
| `--down` / `--danger` (+`-tint`) | `#B91C1C` | `#F87171` | decline, missed |
| `--warn` (+`-tint`) | `#B45309` | `#FBBF24` | pending, due soon |
| `--info` (+`-tint`) | `#2563EB` | `#60A5FA` | neutral notice |

## Subjects

| Token | Light | Dark |
|---|---|---|
| `--turkce` | `#3B82F6` | `#60A5FA` |
| `--mat` | `#A78BFA` | `#C4B5FD` |
| `--sosyal` | `#D97706` | `#FBBF24` |
| `--fen` | `#059669` | `#34D399` |

## Layout & misc

- Spacing: `--s-1..7` = 4 / 8 / 12 / 16 / 24 / 32 / 48px
- Radius: `--r-card` 14px · `--r-chip` 8px · `--r-pill`
- Z-index: `--z-sticky` 20 · `--z-nav` 30 · `--z-dropdown` 40 · `--z-modal` 50 · `--z-toast` 60
- Focus: `box-shadow: var(--focus-ring)` (2px offset ring in `--primary`)
- Motion: `--t-fast` 120ms · `--t-base` 200ms · `--t-slow` 300ms · `--ease-out`
- Numerals: add `.tnum` or `data-tnum` for tabular figures on any numeric display

## Tailwind utility mirrors (`tailwind.config.js`)

- `ink-*` ramp = the dark surface/text ladder above (dark-first; light remaps in `base.html`)
- `steel-*` = brand accent ramp (purple — name kept for template compatibility)
- `up/down`, `surface-*`, `heading/body/muted*` = dark values (static; use tokens for theme-aware CSS)
- Utilities are **static** — for theme-switching styles use `var(--token)` in CSS, not utilities.

## Rules

1. New component styles reference tokens, never raw hex.
2. Dark values change in exactly one place: the `--dark-*` block in `tokens.css`
   (then rebuild Tailwind if `tailwind.config.js` mirrors changed:
   `npx -y tailwindcss@3.4.17 -c tailwind.config.js -i static/css/tailwind.in.css -o static/css/tailwind.min.css --minify`).
3. Muted text is the contrast floor — nothing lighter than `--muted` for readable text.
4. Semantic color always accompanied by an icon or label.
