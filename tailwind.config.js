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
        // ── Core DAS semantic tokens (REDESIGN Phase 1 ladder) ────────────
        'bg':            '#0B0E16',
        'surface-1':     '#121623',
        'surface-2':     '#1A1F2F',
        'surface-3':     '#232A3D',
        'border-soft':   '#252C40',
        'border-strong': '#39415C',
        'primary':       '#6D5BFF',
        'primary-soft':  '#4F44B8',
        'primary-glow':  '#9C8BFF',
        'primary-tint':  'rgba(109, 91, 255, 0.12)',
        'turkce':        '#60A5FA',
        'mat':           '#C4B5FD',
        'sosyal':        '#FBBF24',
        'fen':           '#34D399',
        'up':            '#4ADE80',
        'up-tint':       'rgba(34, 197, 94, 0.12)',
        'down':          '#F87171',
        'down-tint':     'rgba(239, 68, 68, 0.12)',
        'heading':       '#F1F3FA',
        'body':          '#C3C9DA',
        'muted':         '#8B93AB',
        'muted-2':       '#6B7390',
        // ── Ink ramp — dark blue-grey surface ladder (Phase 1 retune) ─────
        ink: {
          950: '#0B0E16',
          900: '#121623',
          850: '#161B29',
          800: '#1A1F2F',
          750: '#232A3D',
          700: '#252C40',
          600: '#39415C',
          500: '#7E87A0',
          400: '#97A0B8',
          300: '#B3BACF',
          200: '#C3C9DA',
          100: '#E5E9F4',
          50:  '#F1F3FA',
        },
        // ── Brand accent ramp (kept name `steel`, retuned to Vagus purple) ─
        steel: {
          300:  '#A99DFF',
          400:  '#8B7CFF',
          500:  '#6D5BFF',
          600:  '#5B4BE0',
          700:  '#4F44B8',
          tint: 'rgba(139,124,255,0.14)',
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
