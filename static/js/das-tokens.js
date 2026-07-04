/**
 * DAS-003 — Chart.js token bridge
 * Source: _artifacts/implementation/DAS-003/chartjs_token_bridge.js
 *
 * Exposes window.DAS.getCssVar, window.DAS.DAS_COLORS, window.DAS.withAlpha
 * for use in any Chart.js config across the app.
 *
 * Usage in chart setup (any template extra_js block):
 *   const c = DAS.DAS_COLORS();
 *   datasets: [{ borderColor: c.turkce, backgroundColor: DAS.withAlpha(c.turkce, 0.15) }]
 */

(function (global) {
  'use strict';

  /**
   * Read a CSS custom property from the document root (or a scoped element).
   * Safe before or after .das-dark is applied.
   *
   * @param {string}  name — e.g. '--primary'
   * @param {Element} [el] — defaults to documentElement
   * @returns {string}
   */
  function getCssVar(name, el) {
    return getComputedStyle(el || document.documentElement)
      .getPropertyValue(name)
      .trim();
  }

  /**
   * Pre-resolved color map. Call each time you build a chart so colors
   * reflect the current theme (light vs .das-dark).
   *
   * @returns {Object}
   */
  function DAS_COLORS() {
    return {
      primary:     getCssVar('--primary'),
      primaryGlow: getCssVar('--primary-glow'),
      turkce:      getCssVar('--turkce'),
      mat:         getCssVar('--mat'),
      sosyal:      getCssVar('--sosyal'),
      fen:         getCssVar('--fen'),
      up:          getCssVar('--up'),
      down:        getCssVar('--down'),
      muted:       getCssVar('--muted'),
      border:      getCssVar('--border'),
      surface1:    getCssVar('--surface-1'),
      heading:     getCssVar('--heading'),

      // Subject array — order matches the subject picker UI
      subjects: [
        getCssVar('--turkce'),
        getCssVar('--mat'),
        getCssVar('--sosyal'),
        getCssVar('--fen'),
      ],
    };
  }

  /**
   * Returns a Chart.js-ready rgba string with alpha applied.
   * Works only for 6-digit hex values (all DAS tokens qualify).
   *
   * @param {string} hex   — e.g. '#3B82F6'
   * @param {number} alpha — 0–1
   * @returns {string}     — e.g. 'rgba(59, 130, 246, 0.15)'
   */
  function withAlpha(hex, alpha) {
    var h = hex.replace('#', '');
    var r = parseInt(h.slice(0, 2), 16);
    var g = parseInt(h.slice(2, 4), 16);
    var b = parseInt(h.slice(4, 6), 16);
    return 'rgba(' + r + ', ' + g + ', ' + b + ', ' + alpha + ')';
  }

  /**
   * REDESIGN Phase 6 — theme-aware Chart.js defaults.
   * Reads current CSS tokens and applies them to Chart.defaults so every
   * chart inherits grid/tick/tooltip/legend theming without per-chart config.
   * Safe to call repeatedly (e.g. on theme toggle).
   */
  function chartDefaults() {
    var Chart = global.Chart;
    if (!Chart) return;

    var muted   = getCssVar('--muted');
    var gridCol = muted && muted.charAt(0) === '#' ? withAlpha(muted, 0.12) : 'rgba(139,147,171,0.12)';

    Chart.defaults.color = muted;
    Chart.defaults.borderColor = gridCol;
    Chart.defaults.scale.grid.color = gridCol;
    Chart.defaults.scale.ticks.color = muted;

    var tooltip = Chart.defaults.plugins.tooltip;
    tooltip.backgroundColor = getCssVar('--surface-3');
    tooltip.titleColor  = getCssVar('--heading');
    tooltip.bodyColor   = getCssVar('--body');
    tooltip.borderColor = getCssVar('--border-strong');
    tooltip.borderWidth = 1;
    tooltip.cornerRadius = 8;
    tooltip.padding = 10;

    Chart.defaults.plugins.legend.labels.color = getCssVar('--body');

    if (global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      Chart.defaults.animation = false;
    }
  }

  // Apply once at load (Chart.js is loaded before this bridge in base.html)
  chartDefaults();

  // Re-theme on dark-mode toggle: refresh defaults, then repaint live charts.
  // Per-chart dataset colors resolved at build time keep their values; pages
  // that need full re-theme rebuild their charts on this same event.
  global.addEventListener('darkmode-change', function () {
    chartDefaults();
    var Chart = global.Chart;
    if (!Chart || !Chart.instances) return;
    Object.keys(Chart.instances).forEach(function (id) {
      try { Chart.instances[id].update('none'); } catch (e) { /* detached canvas */ }
    });
  });

  // Expose globally — no module bundler required
  global.DAS = global.DAS || {};
  global.DAS.getCssVar     = getCssVar;
  global.DAS.DAS_COLORS    = DAS_COLORS;
  global.DAS.withAlpha     = withAlpha;
  global.DAS.chartDefaults = chartDefaults;

}(window));
