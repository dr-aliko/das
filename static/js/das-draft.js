/* ============================================================
   DAS Draft — LocalStorage persistence for exam entry flows
   DAS-342 / Phase 3.3

   Exported as window.DasDraft(key) — returns a small API:
     .save(data)   — debounced write (400 ms)
     .load()       — synchronous read, returns object or null
     .clear()      — remove key
     .ageMinutes() — minutes since last save, or null
   ============================================================ */

(function (global) {
  'use strict';

  global.DasDraft = function DasDraft(key) {
    var timer = null;

    return {
      save: function (data) {
        clearTimeout(timer);
        timer = setTimeout(function () {
          try {
            localStorage.setItem(key, JSON.stringify(
              Object.assign({}, data, { _ts: Date.now() })
            ));
          } catch (e) { /* quota exceeded or private mode */ }
        }, 400);
      },

      load: function () {
        try {
          var raw = localStorage.getItem(key);
          return raw ? JSON.parse(raw) : null;
        } catch (e) { return null; }
      },

      clear: function () {
        clearTimeout(timer);
        try { localStorage.removeItem(key); } catch (e) {}
      },

      ageMinutes: function () {
        try {
          var raw = localStorage.getItem(key);
          if (!raw) return null;
          var d = JSON.parse(raw);
          return d._ts ? Math.round((Date.now() - d._ts) / 60000) : null;
        } catch (e) { return null; }
      },
    };
  };
})(window);
