{% load static %}
// Vagus — Service Worker
// Bump CACHE_NAME on every deploy that changes precached assets.
const CACHE_NAME = 'vagus-shell-v3';

// Assets fetched and stored on install.
// Only same-origin, version-stable resources belong here.
const PRECACHE = [
  '/offline/',
  "{% static 'vagus/pwa/icon-192.png' %}",
  "{% static 'vagus/pwa/icon-512.png' %}",
  "{% static 'vagus/pwa/icon-maskable-192.png' %}",
  "{% static 'vagus/pwa/icon-maskable-512.png' %}",
  "{% static 'vagus/pwa/apple-touch-icon.png' %}",
  "{% static 'js/student_tasks_panel.js' %}",
  "{% static 'js/tasks_panel.js' %}",
  "{% static 'js/a2hs.js' %}",
];

// ── Install ────────────────────────────────────────────────────────────────
// Pre-cache the shell assets, then activate immediately without waiting for
// existing tabs to close.
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

// ── Activate ───────────────────────────────────────────────────────────────
// Remove every cache whose name doesn't match the current version, then take
// control of all open clients immediately.
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys
          .filter(key => key !== CACHE_NAME)
          .map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

// ── Fetch ──────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Pass through non-GET requests (POST, DELETE, etc.)
  if (request.method !== 'GET') return;

  // Pass through cross-origin requests (Tailwind CDN, Alpine, Chart.js, etc.)
  // Let the browser's HTTP cache handle those.
  if (url.origin !== self.location.origin) return;

  // ── Strategy 1: HTML navigations → Network-first ────────────────────────
  // Try the network; on success, cache a copy so the page works offline later.
  // On network failure, serve a cached copy if available, then /offline/.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
          }
          return response;
        })
        .catch(() =>
          caches.match(request)
            .then(cached => cached || caches.match('/offline/'))
        )
    );
    return;
  }

  // ── Strategy 2a: Static CSS/JS → Network-first ──────────────────────────
  // Theme/styling fixes ship via CSS deploys, so we must never pin a stale
  // copy. Try the network; on success cache it; on failure (offline) fall
  // back to whatever we have cached.
  if (url.pathname.startsWith('/static/') &&
      (url.pathname.endsWith('.css') || url.pathname.endsWith('.js'))) {
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
          }
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // ── Strategy 2b: Other same-origin static assets → Cache-first ──────────
  // Images, fonts, icons — version-stable, safe to serve from cache instantly.
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(response => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  // All other same-origin requests (manifest, API calls, etc.) pass through.
});
