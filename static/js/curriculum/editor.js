/**
 * Aylık Plan Editörü — Drag-and-drop + soft workspace refresh.
 * Reads EDITOR_CONFIG injected by the template.
 *
 * Move strategy:
 *  - bucket→bucket: instant optimistic DOM move, POST in background, revert on error
 *  - all other moves: POST first, then swap only the workspace section (no full reload)
 */
(function () {
  'use strict';

  console.log('[editor.js] loaded');

  const C = window.EDITOR_CONFIG;
  if (!C) {
    console.warn('[editor.js] EDITOR_CONFIG not found — aborting');
    return;
  }
  console.log('[editor.js] EDITOR_CONFIG ok — buckets:', C.buckets.length, 'topics:', Object.keys(C.topicMeta).length);

  const HOURS_CAP = 60;
  let refreshing = false;

  /* ── Helpers ──────────────────────────────────────────────────────────────── */
  function csrf() {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }

  function toast(msg, type) {
    if (window.dasToast) window.dasToast(msg, type || 'emerald');
    else console.log('[toast]', type || 'emerald', msg);
  }

  async function apiPost(url, data) {
    const fd = new FormData();
    for (const [k, v] of Object.entries(data)) fd.append(k, v);
    const token = csrf();
    console.log('[editor.js] POST', url, 'csrf:', token ? 'ok' : 'MISSING');
    try {
      const r = await fetch(url, {
        method: 'POST',
        headers: { 'X-CSRFToken': token },
        body: fd,
      });
      console.log('[editor.js] response status:', r.status);
      if (!r.ok) return null;
      const json = await r.json();
      console.log('[editor.js] response json:', json);
      return json;
    } catch (err) {
      console.error('[editor.js] fetch error:', err);
      return null;
    }
  }

  /* ── Scroll helpers ──────────────────────────────────────────────────────── */
  function getMonthsScroll() {
    return document.getElementById('months-inner-scroll');
  }

  function saveMonthsScrollTop() {
    return getMonthsScroll()?.scrollTop ?? 0;
  }

  // Restore scrollTop after all pending layout/Alpine work settles.
  // Double-RAF ensures the browser has painted at least one frame and
  // processed any reflows triggered by Alpine.initTree / x-cloak reveals.
  function restoreMonthsScrollTop(top) {
    if (top <= 0) return;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const el = getMonthsScroll();
        if (el) {
          el.scrollTop = top;
          console.log('[editor.js] scroll restored to', top, '/ actual:', el.scrollTop);
        }
      });
    });
  }

  /* ── Soft workspace refresh ───────────────────────────────────────────────
   * restoreTop: scrollTop to apply to #months-inner-scroll after DOM swap.
   *             Caller must capture this BEFORE the async POST, not inside here.
   * ──────────────────────────────────────────────────────────────────────── */
  async function softRefresh(restoreTop) {
    if (refreshing) return;
    refreshing = true;

    // If caller didn't supply a value, read current position as fallback.
    const topToRestore = (typeof restoreTop === 'number') ? restoreTop : saveMonthsScrollTop();
    console.log('[editor.js] softRefresh start, topToRestore=', topToRestore);

    try {
      const r = await fetch(window.location.href);
      if (!r.ok) throw new Error('page fetch failed: ' + r.status);
      const html = await r.text();
      const doc = new DOMParser().parseFromString(html, 'text/html');

      const oldWs = document.querySelector('[data-workspace]');
      const newWs = doc.querySelector('[data-workspace]');
      if (!oldWs || !newWs) {
        console.warn('[editor.js] softRefresh: [data-workspace] not found, falling back to reload');
        window.location.reload();
        return;
      }

      dragging = null;
      oldWs.replaceWith(newWs);

      // Alpine may trigger x-cloak reveals and reflows that reset scrollTop,
      // so we initialize Alpine FIRST, then D&D, then restore scroll LAST.
      if (window.Alpine) window.Alpine.initTree(newWs);

      setupCards();
      setupZones();
      renderBucketHours();
      checkPrereqWarnings();

      // Sync metric badge text in the sticky bar (outside workspace)
      ['unplanned', 'planned', 'skipped', 'hours'].forEach(key => {
        const cur = document.querySelector('[data-count="' + key + '"]');
        const next = doc.querySelector('[data-count="' + key + '"]');
        if (cur && next) cur.textContent = next.textContent;
      });

      // Restore scroll position LAST — after Alpine and all DOM mutations.
      restoreMonthsScrollTop(topToRestore);

      console.log('[editor.js] softRefresh: DOM swapped, scroll restore scheduled');
    } catch (err) {
      console.error('[editor.js] softRefresh error:', err);
      window.location.reload();
    } finally {
      refreshing = false;
    }
  }

  // Expose so Alpine's post() in the template can call it.
  // Alpine callers don't know the scroll position so we capture it here.
  window.editorSoftRefresh = function () {
    return softRefresh(saveMonthsScrollTop());
  };

  /* ── Drag state ───────────────────────────────────────────────────────────── */
  let dragging = null;

  /* ── Setup ────────────────────────────────────────────────────────────────── */
  function setupCards() {
    const cards = document.querySelectorAll('[data-topic-id]');
    console.log('[editor.js] setupCards: found', cards.length, 'topic cards');
    cards.forEach(el => {
      if (el.dataset.dndReady) return;
      el.dataset.dndReady = '1';
      el.setAttribute('draggable', 'true');
      el.addEventListener('dragstart', onDragStart);
      el.addEventListener('dragend', onDragEnd);
      el.style.cursor = 'grab';
    });
  }

  function setupZones() {
    const zones = document.querySelectorAll('[data-dropzone]');
    console.log('[editor.js] setupZones: found', zones.length, 'drop zones');
    zones.forEach(zone => {
      if (zone.dataset.dndReady) return;
      zone.dataset.dndReady = '1';
      zone.addEventListener('dragover', e => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
      });
      zone.addEventListener('dragenter', e => {
        e.preventDefault();
        zone.classList.add('dz-over');
      });
      zone.addEventListener('dragleave', e => {
        if (!zone.contains(e.relatedTarget)) zone.classList.remove('dz-over');
      });
      zone.addEventListener('drop', onDrop);
    });
  }

  /* ── Drag handlers ────────────────────────────────────────────────────────── */
  function onDragStart(e) {
    const topicId = String(e.currentTarget.dataset.topicId);
    const source = e.currentTarget.dataset.topicSource || 'pool';
    console.log('[editor.js] dragstart topicId:', topicId, 'source:', source);
    dragging = { el: e.currentTarget, topicId, source };
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', topicId);

    // Save scroll before the browser takes its drag-image snapshot, then
    // restore it in the next frame (the snapshot fires during this event,
    // the browser may scroll to show the element after that).
    const monthsEl = getMonthsScroll();
    const savedTop = monthsEl ? monthsEl.scrollTop : 0;

    requestAnimationFrame(() => {
      if (monthsEl && savedTop > 0) monthsEl.scrollTop = savedTop;
      if (dragging?.el) dragging.el.classList.add('is-dragging');
    });
  }

  function onDragEnd() {
    if (dragging?.el) dragging.el.classList.remove('is-dragging');
    document.querySelectorAll('.dz-over').forEach(z => z.classList.remove('dz-over'));
    dragging = null;
  }

  async function onDrop(e) {
    e.preventDefault();
    const zone = e.currentTarget;
    zone.classList.remove('dz-over');

    console.log('[editor.js] drop on zone:', zone.dataset.dropzone, 'dragging topicId:', dragging?.topicId);

    if (!dragging) {
      console.warn('[editor.js] drop fired but dragging is null');
      return;
    }

    const { el, topicId, source } = dragging;
    const target = zone.dataset.dropzone;

    if (source === target) {
      console.log('[editor.js] same zone drop — no-op');
      return;
    }

    // Capture scroll position NOW — before any async work or DOM changes.
    // This is the position the user was at when they released the topic.
    const dropScrollTop = saveMonthsScrollTop();
    console.log('[editor.js] drop captured scrollTop=', dropScrollTop);

    const meta = C.topicMeta[topicId];
    const topicName = meta?.name ?? 'Konu';

    /* ── Client-side validation ─────────────────────────────────────────── */
    if (target === 'skipped' && meta?.baglayici) {
      toast(`"${topicName}" bağlayıcı konudur — atlamak bağımlı konuları etkiler.`, 'amber');
    }

    if (target.startsWith('bucket:')) {
      const bucketId = parseInt(target.split(':')[1]);
      const bucket = C.buckets.find(b => b.id === bucketId);
      if (bucket && meta) {
        const currentHours = computeBucketHours(zone);
        if (currentHours + (meta.hours || 0) > HOURS_CAP) {
          toast(
            `${bucket.label} ayında ${currentHours + meta.hours}s planlandı — ay kapasitesi aşılıyor (${HOURS_CAP}s önerilir).`,
            'amber'
          );
        }
      }
    }

    /* ── Optimistic DOM move for bucket→bucket (same card format) ─────── */
    let sourceZoneForRevert = null;
    if (source.startsWith('bucket:') && target.startsWith('bucket:')) {
      sourceZoneForRevert = document.querySelector('[data-dropzone="' + source + '"]');
      el.dataset.topicSource = target;
      zone.appendChild(el);
    }

    /* ── POST to server ─────────────────────────────────────────────────── */
    let url, body;
    if (target === 'skipped') {
      url = C.skipUrl;
      body = { topic_id: topicId, reason: 'Gerek Yok' };
    } else {
      url = C.moveUrl;
      body = { topic_id: topicId, target };
    }

    const result = await apiPost(url, body);

    if (result?.ok) {
      let where;
      if (target === 'pool') where = 'havuza';
      else if (target === 'skipped') where = '"Halledilmiş"e';
      else {
        const bucketId = parseInt(target.split(':')[1]);
        where = C.buckets.find(b => b.id === bucketId)?.label ?? 'aya';
      }
      toast(`"${topicName}" ${where} taşındı.`, 'emerald');

      if (sourceZoneForRevert) {
        // Optimistic bucket→bucket confirmed — no DOM refresh needed.
        renderBucketHours();
        checkPrereqWarnings();
      } else {
        // Format-changing move — refresh workspace, passing the captured scroll.
        await softRefresh(dropScrollTop);
      }
    } else {
      if (sourceZoneForRevert) {
        // Revert optimistic DOM move
        el.dataset.topicSource = source;
        sourceZoneForRevert.appendChild(el);
      }
      toast('İşlem başarısız — lütfen tekrar deneyin.', 'ruby');
    }
  }

  /* ── Bucket hours helpers ─────────────────────────────────────────────────── */
  function computeBucketHours(zone) {
    let total = 0;
    zone.querySelectorAll('[data-topic-id]').forEach(card => {
      total += C.topicMeta[card.dataset.topicId]?.hours ?? 0;
    });
    return total;
  }

  function renderBucketHours() {
    document.querySelectorAll('[data-dropzone^="bucket:"]').forEach(zone => {
      const total = computeBucketHours(zone);
      const badge = zone.closest('[data-bucket-wrapper]')?.querySelector('[data-bucket-hours]');
      if (!badge) return;
      badge.textContent = `${total}s`;
      if (total > HOURS_CAP) {
        badge.classList.add('text-ruby-500', 'font-bold');
        badge.classList.remove('text-ink-500');
      } else {
        badge.classList.remove('text-ruby-500', 'font-bold');
        badge.classList.add('text-ink-500');
      }
    });
  }

  /* ── Prereq order warnings ────────────────────────────────────────────────── */
  function checkPrereqWarnings() {
    const topicBucket = {};
    document.querySelectorAll('[data-dropzone^="bucket:"]').forEach(zone => {
      const bucketId = parseInt(zone.dataset.dropzone.split(':')[1]);
      const bucketIdx = C.buckets.findIndex(b => b.id === bucketId);
      zone.querySelectorAll('[data-topic-id]').forEach(card => {
        topicBucket[card.dataset.topicId] = bucketIdx;
      });
    });

    const warnings = [];
    for (const [topicId, bucketIdx] of Object.entries(topicBucket)) {
      const meta = C.topicMeta[topicId];
      if (!meta?.prereqs?.length) continue;
      for (const prereqId of meta.prereqs) {
        const prereqIdx = topicBucket[String(prereqId)];
        if (prereqIdx !== undefined && prereqIdx > bucketIdx) {
          warnings.push(`"${meta.name}" konusu, ön koşul konusundan önce planlandı.`);
          break;
        }
      }
    }

    const panel = document.getElementById('client-warnings');
    if (!panel) return;

    if (warnings.length > 0) {
      panel.innerHTML = warnings
        .map(w => `<div class="p-2.5 rounded-lg bg-amber-tint border-l-2 border-amber-500 text-[11px] text-amber-300 leading-snug">${w}</div>`)
        .join('');
      panel.classList.remove('hidden');
    } else {
      panel.innerHTML = '';
      panel.classList.add('hidden');
    }
  }

  /* ── Boot ─────────────────────────────────────────────────────────────────── */
  function boot() {
    console.log('[editor.js] boot() called');
    setupCards();
    setupZones();
    renderBucketHours();
    checkPrereqWarnings();
  }

  // Delay so Alpine.js finishes processing x-show/x-cloak before D&D listeners attach
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(boot, 150));
  } else {
    setTimeout(boot, 150);
  }
})();
