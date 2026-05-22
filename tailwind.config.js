/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './**/templates/**/*.html',
    './static/js/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        // ── Core DAS semantic tokens ──────────────────────────────────────
        'bg':            '#0B0B12',
        'surface-1':     '#15151F',
        'surface-2':     '#1E1E2C',
        'surface-3':     '#262635',
        'border-soft':   '#262635',
        'border-strong': '#2F2F42',
        'primary':       '#6D5BFF',
        'primary-soft':  '#4F44B8',
        'primary-glow':  '#9C8BFF',
        'primary-tint':  'rgba(109, 91, 255, 0.12)',
        'turkce':        '#3B82F6',
        'mat':           '#A78BFA',
        'sosyal':        '#F59E0B',
        'fen':           '#10B981',
        'up':            '#22C55E',
        'up-tint':       'rgba(34, 197, 94, 0.12)',
        'down':          '#EF4444',
        'down-tint':     'rgba(239, 68, 68, 0.12)',
        'heading':       '#FFFFFF',
        'body':          '#E5E5F0',
        'muted':         '#8A8AA3',
        'muted-2':       '#5E5E78',
        // ── Phase 7: ink ramp (deep charcoal surface) ─────────────────────
        ink: {
          950: '#0a0e14',
          900: '#0f141c',
          850: '#131820',
          800: '#1a2030',
          750: '#222a3c',
          700: '#2a3142',
          600: '#3a4356',
          500: '#5b6477',
          400: '#94a3b8',
          200: '#cbd5e1',
          100: '#e8ecf3',
          50:  '#ffffff',
        },
        // ── Phase 7: steel-blue brand accent ─────────────────────────────
        steel: {
          300:  '#9ec5f5',
          400:  '#6ba8f0',
          500:  '#4a90e2',
          600:  '#3a7fce',
          700:  '#2c66ad',
          tint: 'rgba(74,144,226,0.12)',
        },
        // ── Status semantic tints ─────────────────────────────────────────
        emerald: { 500: '#10b981', tint: 'rgba(16,185,129,0.12)' },
        ruby:    { 500: '#ef4444', tint: 'rgba(239,68,68,0.12)' },
        amber:   { 500: '#f59e0b', tint: 'rgba(245,158,11,0.12)' },
      },
      screens: {
        xs: '360px',
      },
      maxWidth: {
        'page':       '1400px',
        'prose-wide': '1100px',
      },
      borderRadius: {
        'card': '14px',
        'chip': '8px',
        'pill': '9999px',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'card':    '0 1px 3px rgba(0, 0, 0, 0.4)',
        'card-md': '0 4px 16px rgba(0, 0, 0, 0.5)',
        'card-lg': '0 1px 0 0 rgba(255,255,255,0.04) inset, 0 8px 24px rgba(0,0,0,0.5)',
        'fab':     '0 6px 20px rgba(109, 91, 255, 0.45)',
      },
    },
  },
  plugins: [],
};
