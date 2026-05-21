// Vagus — Add to Home Screen install prompt
// Handles Chromium (beforeinstallprompt) + iOS Safari (manual hint) separately.
// Suppressed when already installed or user has dismissed within 14 days.

(function () {
  'use strict';

  var DISMISS_KEY = 'a2hs_dismissed_until';
  var DISMISS_DAYS = 14;

  function isDismissed() {
    var until = localStorage.getItem(DISMISS_KEY);
    return until && Date.now() < parseInt(until, 10);
  }

  function setDismissed() {
    localStorage.setItem(DISMISS_KEY, Date.now() + DISMISS_DAYS * 864e5);
  }

  function isInstalled() {
    return window.matchMedia('(display-mode: standalone)').matches
      || window.navigator.standalone === true;
  }

  function isIOS() {
    return /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream;
  }

  function isSuppressedPage() {
    return document.body.classList.contains('a2hs-suppress');
  }

  // ── Chromium path: beforeinstallprompt ──────────────────────────────────────

  var deferredPrompt = null;

  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    deferredPrompt = e;

    if (isInstalled() || isDismissed() || isSuppressedPage()) return;

    var banner = document.getElementById('a2hs-banner');
    if (banner) banner.removeAttribute('hidden');
  });

  window.addEventListener('appinstalled', function () {
    var banner = document.getElementById('a2hs-banner');
    if (banner) banner.setAttribute('hidden', '');
    if (typeof window.dasToast === 'function') {
      window.dasToast('Vagus ana ekrana eklendi!', 'emerald');
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    var installBtn = document.getElementById('a2hs-install-btn');
    var dismissBtn = document.getElementById('a2hs-dismiss-btn');

    if (installBtn) {
      installBtn.addEventListener('click', function () {
        if (!deferredPrompt) return;
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(function (choice) {
          deferredPrompt = null;
          var banner = document.getElementById('a2hs-banner');
          if (banner) banner.setAttribute('hidden', '');
          if (choice.outcome !== 'accepted') setDismissed();
        });
      });
    }

    if (dismissBtn) {
      dismissBtn.addEventListener('click', function () {
        setDismissed();
        var banner = document.getElementById('a2hs-banner');
        if (banner) banner.setAttribute('hidden', '');
      });
    }

    // ── iOS path: show hint if Safari on iOS, not installed, not dismissed ──
    if (isIOS() && !isInstalled() && !isDismissed() && !isSuppressedPage()) {
      var iosBanner = document.getElementById('a2hs-ios-hint');
      if (iosBanner) iosBanner.removeAttribute('hidden');
    }

    var iosDismissBtn = document.getElementById('a2hs-ios-dismiss-btn');
    if (iosDismissBtn) {
      iosDismissBtn.addEventListener('click', function () {
        setDismissed();
        var iosBanner = document.getElementById('a2hs-ios-hint');
        if (iosBanner) iosBanner.setAttribute('hidden', '');
      });
    }
  });
})();
