/* coach_search.js — shared staff coach live-search component
 *
 * data-mode="select": live dropdown from a hidden <select>.
 *   Attribute: data-select-id="<select element id>"
 *   The dropdown is appended to document.body with position:fixed so it escapes
 *   overflow:hidden / overflow:auto ancestors (cards, scroll panes, modals).
 *   Repositions on scroll (capture phase) and resize; closes when the input
 *   leaves the viewport. Opens upward when there is not enough space below.
 *
 * data-mode="list": filters DOM rows live as the user types.
 *   Attribute: data-row-sel="<CSS selector>"  (default: [data-coach-row])
 *   Rows must carry data-coach-name and data-coach-email attributes.
 */
(function () {
  'use strict';

  var MARGIN = 8;   /* minimum gap from viewport edge (px) */
  var MAX_H  = 200; /* maximum dropdown height (px) */
  var Z      = 9999;/* above sticky headers, modals, bottom-nav */

  /* Turkish-aware normalisation ------------------------------------------- */
  function norm(s) {
    return (s || '')
      .replace(/İ/g, 'i').replace(/I/g, 'ı').replace(/Ğ/g, 'ğ')
      .replace(/Ü/g, 'ü').replace(/Ş/g, 'ş').replace(/Ö/g, 'ö').replace(/Ç/g, 'ç')
      .toLowerCase();
  }

  function esc(s) {
    return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /* Visual-viewport helpers — respects on-screen keyboard on mobile ------- */
  function vpHeight() {
    return window.visualViewport ? window.visualViewport.height : window.innerHeight;
  }
  function vpOffsetTop() {
    return window.visualViewport ? window.visualViewport.offsetTop : 0;
  }

  function inViewport(r) {
    /* r = getBoundingClientRect result */
    return r.bottom > vpOffsetTop() && r.top < vpOffsetTop() + vpHeight();
  }

  /* Compute and apply fixed position for the dropdown --------------------- */
  function positionDropdown(inp, dd) {
    var r       = inp.getBoundingClientRect();
    var vTop    = vpOffsetTop();
    var vH      = vpHeight();
    var below   = vTop + vH - r.bottom - MARGIN; /* available space below */
    var above   = r.top - vTop          - MARGIN; /* available space above */
    var openUp  = below < 120 && above > below;
    var avail   = Math.max(openUp ? above : below, 60);
    var height  = Math.min(MAX_H, avail);

    dd.style.left      = r.left  + 'px';
    dd.style.width     = r.width + 'px';
    dd.style.maxHeight = height  + 'px';

    if (openUp) {
      dd.style.top = (r.top - height - 2) + 'px';
    } else {
      dd.style.top = (r.bottom + 2) + 'px';
    }
  }

  /* ── Select mode ─────────────────────────────────────────────────────── */
  function initSelectMode(inp) {
    var selId = inp.getAttribute('data-select-id');
    if (!selId) return;
    var sel = document.getElementById(selId);
    if (!sel) return;

    /* Build coaches list from the existing <select> options */
    var coaches = [];
    for (var n = 0; n < sel.options.length; n++) {
      var opt = sel.options[n];
      if (!opt.value) continue;
      var parts = opt.text.split(' — ');
      coaches.push({ id: opt.value, name: parts[0] || opt.text, email: parts[1] || '' });
    }
    sel.style.display = 'none';

    /* Dropdown appended to body — never clipped by any ancestor ----------- */
    var dd = document.createElement('div');
    dd.style.cssText = 'display:none;position:fixed;z-index:' + Z + ';overflow-y:auto;'
      + 'background:#111827;border:1px solid #374151;border-radius:8px;'
      + 'box-shadow:0 4px 16px rgba(0,0,0,.4);';
    document.body.appendChild(dd);

    var active = -1, filtered = [], open = false;

    function hl(idx) {
      var items = dd.children;
      for (var j = 0; j < items.length; j++) {
        items[j].style.background = j === idx ? '#1f2937' : '';
      }
    }

    function render(q) {
      var lq = norm(q);
      filtered = coaches.filter(function (c) {
        return !lq || norm(c.name).indexOf(lq) >= 0 || norm(c.email).indexOf(lq) >= 0;
      });
      dd.innerHTML = '';
      active = -1;
      if (!filtered.length) {
        dd.innerHTML = '<div style="padding:8px 12px;font-size:11px;color:#6b7280;">Sonuç yok</div>';
      } else {
        filtered.forEach(function (c, i) {
          var item = document.createElement('div');
          item.style.cssText = 'padding:6px 12px;cursor:pointer;transition:background .12s;';
          item.innerHTML =
            '<div style="font-size:12px;font-weight:500;color:#e5e7eb;">' + esc(c.name)  + '</div>'
            + '<div style="font-size:10px;color:#6b7280;margin-top:1px;">'  + esc(c.email) + '</div>';
          item.addEventListener('mousedown', function (e) { e.preventDefault(); pick(i); });
          item.addEventListener('mouseover',  function ()  { active = i; hl(active); });
          dd.appendChild(item);
        });
      }
    }

    function showDd() {
      positionDropdown(inp, dd);
      dd.style.display = '';
      open = true;
    }

    function hideDd() {
      dd.style.display = 'none';
      open = false;
      active = -1;
    }

    function pick(i) {
      if (!filtered[i]) return;
      inp.value = filtered[i].name;
      sel.value = filtered[i].id;
      hideDd();
      sel.dispatchEvent(new Event('change', { bubbles: true }));
    }

    inp.addEventListener('input',  function () { render(inp.value); showDd(); });
    inp.addEventListener('focus',  function () { render(inp.value); showDd(); });
    inp.addEventListener('blur',   function () { setTimeout(hideDd, 180); });

    inp.addEventListener('keydown', function (e) {
      if (!open) return;
      var items = dd.children;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        active = Math.min(active + 1, items.length - 1);
        hl(active);
        if (items[active]) items[active].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        active = Math.max(active - 1, 0);
        hl(active);
        if (items[active]) items[active].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (active >= 0) pick(active);
      } else if (e.key === 'Escape') {
        hideDd();
      }
    });

    /* Reposition on scroll — capture so inner-container scrolls count too -- */
    function onScroll() {
      if (!open) return;
      var r = inp.getBoundingClientRect();
      if (!inViewport(r)) { hideDd(); return; }
      positionDropdown(inp, dd);
    }
    window.addEventListener('scroll', onScroll, true);

    /* Reposition on window resize and virtual-keyboard resize --------------- */
    function onResize() {
      if (open) positionDropdown(inp, dd);
    }
    window.addEventListener('resize', onResize);
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', onResize);
    }

    /* Restore label when the select already has a value (e.g. after POST) -- */
    if (sel.value) {
      var chosen = coaches.find(function (c) { return String(c.id) === String(sel.value); });
      if (chosen) inp.value = chosen.name;
    }
  }

  /* ── List mode ───────────────────────────────────────────────────────── */
  function initListMode(inp) {
    var rowSel = inp.getAttribute('data-row-sel') || '[data-coach-row]';
    inp.addEventListener('input', function () {
      var q = norm(inp.value);
      document.querySelectorAll(rowSel).forEach(function (row) {
        var name  = norm(row.getAttribute('data-coach-name')  || '');
        var email = norm(row.getAttribute('data-coach-email') || '');
        row.style.display = (!q || name.indexOf(q) >= 0 || email.indexOf(q) >= 0) ? '' : 'none';
      });
    });
  }

  /* ── Bootstrap ───────────────────────────────────────────────────────── */
  function init() {
    document.querySelectorAll('[data-ara-btn]').forEach(function (b) { b.style.display = 'none'; });
    document.querySelectorAll('[data-coach-search]').forEach(function (inp) {
      if (inp.getAttribute('data-mode') === 'select') {
        initSelectMode(inp);
      } else {
        initListMode(inp);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
