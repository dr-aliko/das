import re, sys
css = open('static/css/tailwind.min.css', encoding='utf-8', errors='replace').read()

checks = [
    # arbitrary-value classes (expected NO)
    ('bg-[var(--surface-1)]',   r'bg-\[var\(--surface-1\)\]'),
    ('bg-[var(--surface-2)]',   r'bg-\[var\(--surface-2\)\]'),
    ('bg-[var(--surface-3)]',   r'bg-\[var\(--surface-3\)\]'),
    ('border-[var(--border)]',  r'border-\[var\(--border\)\]'),
    ('text-[var(--muted)]',     r'text-\[var\(--muted\)\]'),
    ('text-[var(--muted-2)]',   r'text-\[var\(--muted-2\)\]'),
    ('text-[var(--heading)]',   r'text-\[var\(--heading\)\]'),
    ('text-[var(--body)]',      r'text-\[var\(--body\)\]'),
    ('hover:bg-[var(--surface-2)]', r'hover.bg-\[var'),
    ('hover:bg-[var(--surface-3)]', r'hover.bg-\[var\(--surface-3'),
    ('placeholder:text-[var]',  r'placeholder.'),
    # pseudo-class utilities
    ('focus:border-steel-500',  r'focus.border-steel-500'),
    ('focus:outline-none',      r'focus.outline-none'),
    ('hover:bg-steel-400',      r'hover.bg-steel-400'),
    ('hover:bg-steel-500/20',   r'hover.bg-steel-500'),
    ('hover:text-ruby-400',     r'hover.text-ruby-400'),
    ('hover:bg-ruby-500/10',    r'hover.bg-ruby'),
    ('disabled:opacity-50',     r'disabled.opacity-50'),
    ('disabled:cursor-not-allowed', r'disabled.cursor-not-allowed'),
    ('active:bg-steel-600',     r'active.bg-steel-600'),
    # standard layout
    ('flex-none',               r'flex-none'),
    ('min-h-0',                 r'min-h-0'),
    ('bg-black/60',             r'bg-black'),
    # sizes
    ('py-2.5',                  r'py-2\.5'),
    ('w-3.5',                   r'w-3\.5'),
    ('h-3.5',                   r'h-3\.5'),
    ('truncate',                r'truncate'),
    ('shrink-0',                r'shrink-0'),
    ('flex-wrap',               r'flex-wrap'),
    ('min-w-0',                 r'min-w-0'),
    ('print:hidden',            r'print.hidden'),
    ('border-steel-500/30',     r'border-steel-500'),
    ('bg-steel-500/20',         r'bg-steel-500'),
    ('bg-amber-500/20',         r'bg-amber-500'),
    ('bg-emerald-500/20',       r'bg-emerald-500'),
    ('text-emerald-400',        r'text-emerald-400'),
    ('text-amber-400',          r'text-amber-400'),
    ('opacity-25',              r'opacity-25'),
    ('opacity-75',              r'opacity-75'),
]

for name, pat in checks:
    found = bool(re.search(pat, css))
    print(f"{'YES' if found else 'NO '}: {name}")
