# Vagus — Brand Asset Package

Production-ready assets for the Vagus rebrand. Drop into your Django static
folder; reference paths below assume `STATIC_URL = '/static/'`.

---

## Package contents

```
vagus-brand/
├── svg/                          → Vector marks for in-app use
│   ├── vagus-mark.svg              currentColor — use inside SVG/HTML, color via CSS
│   ├── vagus-mark-indigo.svg       Solid indigo #6366F1 — drop-in for emails/PDFs
│   ├── vagus-mark-white.svg        White on dark surfaces
│   ├── vagus-mark-black.svg        Black on light surfaces
│   └── vagus-lockup.svg            Horizontal mark + "Vagus" wordmark
│
├── favicon/                      → Browser tab favicons
│   ├── favicon.svg                 Modern browsers (auto dark-mode aware)
│   ├── favicon-16.png              Legacy fallback
│   ├── favicon-32.png              Standard
│   └── favicon-48.png              High-density displays
│
├── pwa/                          → PWA / mobile home-screen icons
│   ├── icon-192.png                Standard PWA icon
│   ├── icon-512.png                Standard PWA icon (high-res)
│   ├── icon-maskable-192.png       Maskable PWA icon (full-bleed, safe zone)
│   ├── icon-maskable-512.png       Maskable PWA icon (high-res)
│   ├── apple-touch-icon.png        iOS Home Screen (180×180, solid bg)
│   └── manifest.json               Drop-in PWA manifest
│
├── social/                       → Marketing / link previews
│   ├── og-card.png                 Open Graph (1200×630)
│   └── og-card.html                Source HTML — re-render for variant copy
│
└── _sources/                     → Source SVGs for the rasterized PNGs above
                                     Keep these — they're what to edit if the
                                     mark or palette ever changes.
```

---

## 1. Drop into Django

Copy the entire `vagus-brand/` folder into `static/vagus/` (or similar):

```
your-project/
└── static/
    └── vagus/
        ├── svg/
        ├── favicon/
        ├── pwa/
        ├── social/
        └── _sources/
```

Run `collectstatic` after copying.

---

## 2. Wire up `base.html`

Inside `<head>`, add:

```django
{% load static %}

<!-- Favicons — modern SVG first, raster fallbacks -->
<link rel="icon" type="image/svg+xml" href="{% static 'vagus/favicon/favicon.svg' %}" />
<link rel="icon" type="image/png" sizes="32x32" href="{% static 'vagus/favicon/favicon-32.png' %}" />
<link rel="icon" type="image/png" sizes="16x16" href="{% static 'vagus/favicon/favicon-16.png' %}" />

<!-- Apple Home Screen -->
<link rel="apple-touch-icon" sizes="180x180" href="{% static 'vagus/pwa/apple-touch-icon.png' %}" />

<!-- PWA manifest -->
<link rel="manifest" href="{% static 'vagus/pwa/manifest.json' %}" />

<!-- Theme color (browser chrome on Android/iOS) -->
<meta name="theme-color" content="#6366F1" />

<!-- Open Graph / Twitter cards -->
<meta property="og:title" content="Vagus — Smarter Exam Analytics" />
<meta property="og:description" content="Track every exam. Master every topic." />
<meta property="og:image" content="https://yourdomain.com{% static 'vagus/social/og-card.png' %}" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
<meta property="og:type" content="website" />

<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:image" content="https://yourdomain.com{% static 'vagus/social/og-card.png' %}" />
```

Note the OG image URL must be **absolute** (with `https://yourdomain.com`) —
relative URLs break link previews on Facebook, LinkedIn, Slack, etc.

---

## 3. Update `manifest.json` paths

The shipped `manifest.json` assumes icons live at `/static/vagus/pwa/`.
If your `STATIC_URL` differs, edit the four `"src":` paths inside it.

---

## 4. Use the mark in templates

### Navbar / app bar

```django
<a href="/" class="flex items-center gap-2 text-white font-semibold tracking-tight">
  <span class="text-indigo-400">
    {% include "vagus/svg/vagus-mark.svg" %}
  </span>
  Vagus
</a>
```

The mark inherits `currentColor`. To re-color, change the parent's
`color:` / Tailwind `text-*` class.

### Inline (Tailwind size utilities)

```html
<svg class="w-7 h-7 text-indigo-500" viewBox="0 0 24 24"
     fill="none" stroke="currentColor" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
  <path d="M4.5 5L11.5 18.5C11.7 18.9 12.3 18.9 12.5 18.5L14.5 14.5L16 16.5L19.5 4.5"/>
</svg>
```

Inline is preferred for the navbar (fewer HTTP requests, can animate).

---

## 5. Brand palette

| Token | Hex | Tailwind | Used for |
|---|---|---|---|
| Vagus Indigo | `#6366F1` | `indigo-500` | Primary mark, CTAs, active states |
| Indigo Deep | `#4F46E5` | `indigo-600` | App icon base, hovers |
| Indigo Bright | `#818CF8` | `indigo-400` | Marks on dark surfaces, glow |
| Violet | `#8B5CF6` | `violet-500` | Gradient partner |
| Violet Deep | `#7C3AED` | `violet-600` | App icon gradient end |
| Background | `#0a0e14` | `ink-950` | Dark app background |

App icon gradient: `linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%)`.

---

## 6. Optional: real `.ico` favicon

Modern browsers happily use `favicon.svg` + raster PNGs. If you also want
a classic `favicon.ico` (for legacy IE / some bookmark managers), bundle
the three PNG sizes into one ICO file using either:

- **CLI:** `convert favicon-16.png favicon-32.png favicon-48.png favicon.ico` (ImageMagick)
- **Online:** drop the three PNGs into <https://favicon.io/favicon-converter/>

Then add to base.html:

```django
<link rel="shortcut icon" href="{% static 'vagus/favicon/favicon.ico' %}" />
```

---

## 7. Re-rendering the OG card

To produce variants (campaign-specific taglines, A/B tests), edit
`social/og-card.html` and re-render. Two paths:

- **Browser print-to-PDF:** open the HTML, set page size to 1200×630px, "Save as PDF".
- **Headless capture:** use Playwright/Puppeteer to screenshot at exact viewport.

Keep the rendered PNG at `social/og-card.png` so all `<meta>` tags continue
pointing at the same filename.

---

## 8. Asset preview

Open `preview.html` in a browser to see every asset at native scale,
including light/dark variants and the navbar lockup in context.

---

## Rollback

This is a brand-only change — no template logic depends on these files.
To revert, point base.html back at the previous DAS assets. The Vagus
folder can be deleted with no functional impact.
