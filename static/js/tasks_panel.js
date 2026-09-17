// CSRF token read from cookie (standard Django pattern)
const CSRF = document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? '';
const GUNLER = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar'];

// Use local calendar date to avoid timezone-shift bugs.
function localISO(d) {
  return d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0');
}

// Returns the ISO date string of the Monday of the week containing the given ISO date.
function isoMonday(iso) {
  const d = new Date(iso + 'T00:00:00');
  const dow = d.getDay() || 7;
  d.setDate(d.getDate() - (dow - 1));
  return localISO(d);
}

const AKTIVITE_LABELS = { konu_anlatimi: 'Konu Anlatımı', soru_cozumu: 'Soru Çözümü', tekrar: 'Tekrar' };

// AYT subject display_names allowed per alan (extends konu_takip map with Geometri for SAY/EA)
const _PLAYLIST_AYT_MAP = {
  SAY: new Set(['Matematik', 'Fizik', 'Kimya', 'Biyoloji', 'Geometri']),
  EA:  new Set(['Matematik', 'Türk Dili ve Edebiyatı', 'Geometri']),
  SOZ: new Set(['Türk Dili ve Edebiyatı', 'Tarih 2', 'Coğrafya 2', 'Felsefe Grubu']),
  DIL: new Set(['Yabancı Dil']),
};
// AYT ders titles (legacy API field "ad") allowed per alan — matches kocluk.db Title values
const _DERS_AYT_MAP = {
  SAY: new Set(['Matematik', 'Fizik', 'Kimya', 'Biyoloji', 'Geometri']),
  EA:  new Set(['Matematik', 'Edebiyat', 'Geometri']),
  SOZ: new Set(['Edebiyat', 'Tarih', 'Coğrafya', 'Felsefe']),
  DIL: new Set(['Yabancı Dil']),
};
// TYT ders fixed allow-list — alan-independent (Edebiyat, Yabancı Dil are AYT-only)
const _DERS_TYT_ALLOW = new Set(['Matematik', 'Türkçe', 'Tarih', 'Coğrafya', 'Felsefe', 'Diğer', 'Din Kültürü', 'Fizik', 'Kimya', 'Biyoloji', 'Geometri']);
const COLORS_KEY = 'das-tasks-colors';
const DEFAULT_COLORS = { konu_anlatimi: '#3b82f6', soru_cozumu: '#eab308', tekrar: '#22c55e' };

function hexTints(hex) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return {
    bg:     `rgba(${r},${g},${b},0.10)`,
    border: `rgba(${r},${g},${b},0.42)`,
    title:  `rgb(${Math.round(r * .65)},${Math.round(g * .65)},${Math.round(b * .65)})`,
  };
}

// ── Standalone HTML export (shared helper) ────────────────────────────────────
function _buildTaskHTML(g, cs) {
  const DEFAULTS = { konu_anlatimi: '#3b82f6', soru_cozumu: '#eab308', tekrar: '#22c55e' };
  const base = cs[g.aktivite_tipi] ?? DEFAULTS[g.aktivite_tipi] ?? '#6b7280';
  const r = parseInt(base.slice(1,3),16), gr = parseInt(base.slice(3,5),16), b = parseInt(base.slice(5,7),16);
  const bg     = `rgba(${r},${gr},${b},0.12)`;
  const border = `rgba(${r},${gr},${b},0.45)`;
  const titleColor = `rgb(${Math.round(r*.6)},${Math.round(gr*.6)},${Math.round(b*.6)})`;
  const dur = g.ozel_sure_dk ? `<span class="task-dur">⏱ ${g.ozel_sure_dk}dk</span>` : '';
  const details = (g.detaylar||[]).map(d =>
    `<div class="task-detail">• ${d.aciklama||''}${d.sure_bilgisi?' ('+d.sure_bilgisi+')':''}</div>`
  ).join('');
  return `<div class="task-card" style="background:${bg};border-color:${border}">
    <div class="task-title" style="color:${titleColor}">${g.ders_title||''}</div>
    ${dur}${details}
  </div>`;
}

function _downloadWeeklyHTML(days, colorSettings, studentName, weekLabel, filename) {
  const cols = days.map((gun, idx) => {
    const weekend = gun.isWeekend ?? idx >= 5;
    const tasks = (gun.gorevler||[]).map(g => _buildTaskHTML(g, colorSettings)).join('');
    const empty = !gun.gorevler?.length ? `<div class="empty-msg">—</div>` : '';
    const colBg   = weekend ? '#f8fafc' : '#fff';
    const colBord = weekend ? '#e2e8f0' : '#f3f4f6';
    const headBg  = weekend ? '#f1f5f9' : '#f9fafb';
    const labelColor = weekend ? '#64748b' : '#4b5563';
    return `<div class="day-col" style="background:${colBg};border-color:${colBord}">
      <div class="day-head" style="background:${headBg};border-bottom-color:${colBord}">
        <div class="day-label" style="color:${labelColor}">${gun.label}</div>
        <div class="day-date">${gun.tarih}</div>
      </div>
      <div class="day-body">${tasks}${empty}</div>
    </div>`;
  }).join('');

  const html = `<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Haftalık Plan${studentName?' — '+studentName:''}</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:system-ui,-apple-system,sans-serif;background:#f3f4f6;color:#1f2937;padding:24px}
  .header{margin-bottom:20px}
  .header h1{font-size:20px;font-weight:700;color:#111827}
  .header .meta{font-size:13px;color:#6b7280;margin-top:4px}
  .grid{display:grid;grid-template-columns:repeat(7,1fr);gap:10px}
  .day-col{min-width:0;border:1px solid;border-radius:16px;overflow:hidden}
  .day-head{padding:10px 12px 8px;border-bottom:1px solid}
  .day-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em}
  .day-date{font-size:11px;color:#9ca3af;margin-top:1px}
  .day-body{padding:10px}
  .task-card{border:2px solid;border-radius:10px;padding:8px 10px;margin-bottom:6px;break-inside:avoid;page-break-inside:avoid}
  .task-title{font-size:13px;font-weight:700;line-height:1.3;margin-bottom:3px}
  .task-dur{font-size:11px;color:#6b7280}
  .task-detail{font-size:11px;color:#6b7280;margin-top:2px}
  .empty-msg{color:#d1d5db;font-size:12px;text-align:center;padding:16px 0}
  @media(max-width:900px){.grid{grid-template-columns:repeat(4,1fr)}}
  @media(max-width:600px){.grid{grid-template-columns:repeat(2,1fr)}}
  @page{size:A4 landscape;margin:8mm}
  @media print{
    *{print-color-adjust:exact;-webkit-print-color-adjust:exact}
    body{background:#fff;padding:4px}
    .header{margin-bottom:6px}
    .header h1{font-size:14px}
    .header .meta{font-size:10px;margin-top:2px}
    .grid{gap:3px}
    .day-col{border-radius:6px}
    .day-head{padding:4px 6px}
    .day-label{font-size:8px}
    .day-date{font-size:9px;margin-top:0}
    .day-body{padding:4px}
    .task-card{padding:4px 6px;margin-bottom:3px;border-radius:5px;border-width:1px}
    .task-title{font-size:10px;margin-bottom:1px;line-height:1.2}
    .task-dur{font-size:9px}
    .task-detail{font-size:9px;margin-top:0}
    .empty-msg{font-size:9px;padding:4px 0}
  }
</style>
</head>
<body>
<div class="header">
  <h1>Haftalık Ders Planı${studentName?' — '+studentName:''}</h1>
  <div class="meta">${weekLabel}</div>
</div>
<div class="grid">${cols}</div>
</body>
</html>`;

  const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
  const url  = URL.createObjectURL(blob);
  const a    = Object.assign(document.createElement('a'), { href: url, download: filename });
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function playlistImporter() {
  const _csrf = () => document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? '';
  return {
    show: false,
    step: 'input',       // 'input' | 'preview' | 'importing' | 'success' | 'error'
    url: '',
    errorMsg: '',
    preview: null,
    subjects: [],
    selectedSubjectId: '',
    selectedExamType: 'TYT',
    importResult: null,
    myPlaylists: [],
    loadingPlaylists: false,
    pendingDeletePk: null,
    deleteError: '',

    open() { this.reset(); this.show = true; this.loadMyPlaylists(); },
    close() { this.show = false; },
    reset() {
      this.step = 'input'; this.url = ''; this.errorMsg = '';
      this.preview = null; this.importResult = null;
      this.selectedSubjectId = ''; this.selectedExamType = 'TYT';
      this.pendingDeletePk = null; this.deleteError = '';
    },

    async loadMyPlaylists() {
      this.loadingPlaylists = true;
      try {
        const r = await fetch('/coach/tasks/api/youtube/list');
        const d = await r.json();
        this.myPlaylists = d.playlists ?? [];
      } catch (_) { this.myPlaylists = []; }
      this.loadingPlaylists = false;
    },

    async deletePl(pk) {
      if (this.pendingDeletePk !== pk) {
        this.pendingDeletePk = pk;
        setTimeout(() => { if (this.pendingDeletePk === pk) this.pendingDeletePk = null; }, 3000);
        return;
      }
      this.pendingDeletePk = null;
      this.deleteError = '';
      try {
        const r = await fetch(`/coach/tasks/api/youtube/${pk}`, {
          method: 'DELETE', headers: { 'X-CSRFToken': _csrf() },
        });
        if (r.ok) {
          this.myPlaylists = this.myPlaylists.filter(p => p.pk !== pk);
          window.dispatchEvent(new CustomEvent('yt-playlist-deleted', { detail: { pk } }));
        } else {
          const d = await r.json().catch(() => ({}));
          this.deleteError = d.error || 'Silme işlemi başarısız.';
        }
      } catch (_) { this.deleteError = 'Bağlantı hatası.'; }
    },

    async doPreview() {
      if (!this.url.trim()) return;
      this.step = 'importing'; this.errorMsg = '';
      try {
        const r = await fetch('/coach/tasks/api/youtube/preview', {
          method: 'POST',
          headers: { 'X-CSRFToken': _csrf(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: this.url }),
        });
        const data = await r.json();
        if (!r.ok) { this.step = 'error'; this.errorMsg = data.error || 'Bir hata olustu.'; return; }
        this.preview = data;
        this.subjects = data.subjects || [];
        this.selectedSubjectId = data.detected_subject_id ? String(data.detected_subject_id) : '';
        this.selectedExamType  = data.detected_exam_type || 'TYT';
        this.step = 'preview';
      } catch (e) {
        this.step = 'error'; this.errorMsg = 'Baglanti hatasi.';
      }
    },

    get needsSubject() { return this.preview && !this.preview.detected_subject_id && !this.selectedSubjectId; },
    get needsExamType() { return this.preview && !this.preview.detected_exam_type; },

    async doImport() {
      this.step = 'importing';
      try {
        const r = await fetch('/coach/tasks/api/youtube/import', {
          method: 'POST',
          headers: { 'X-CSRFToken': _csrf(), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            url:        this.url,
            subject_id: this.selectedSubjectId || null,
            exam_type:  this.selectedExamType,
          }),
        });
        const data = await r.json();
        if (!r.ok) { this.step = 'error'; this.errorMsg = data.error || 'Import basarisiz.'; return; }
        this.importResult = data;
        this.step = 'success';
      } catch (e) {
        this.step = 'error'; this.errorMsg = 'Baglanti hatasi.';
      }
    },

    useNow() {
      if (!this.importResult) return;
      window.dispatchEvent(new CustomEvent('playlist-imported', { detail: this.importResult }));
      this.close();
    },
  };
}

function panel() {
  return {
    studentId: '',
    refDate: isoMonday(localISO(new Date())),
    days: [],
    toplamlar: {},
    dersler: [], listeler: [], videolar: [], ytListeler: [],
    showTaskModal: false,
    showSettingsModal: false,
    pdfExporting: false,
    colorSettings: { ...DEFAULT_COLORS },
    isDark: document.documentElement.classList.contains('dark'),
    showCompleted: false,
    editingTask: null,
    dragTaskId: null, dragFromDate: null,
    taskForm: {
      aktivite_tipi: 'konu_anlatimi', sinav_tipi: 'TYT', ders_title: '',
      ozel_sure_dk: 0, aciklama: '', konu_not: '',
      konu_ders_id: '', liste_id: '', selectedVideos: [], tarih: '', error: '',
      ytPlaylistPk: null, ytPlaylistTitle: '',
    },

    async init() {
      this.loadColorSettings();
      this.buildDays();
      await this.loadDersler();
      await this.loadYtListeler();
      window.addEventListener('darkmode-change', (e) => { this.isDark = e.detail.isDark; });
      window.addEventListener('yt-playlist-deleted', (e) => {
        this.ytListeler = this.ytListeler.filter(l => l.pk !== e.detail.pk);
        if (this.taskForm.liste_id === 'yt:' + e.detail.pk) {
          this.taskForm.liste_id = ''; this.taskForm.ytPlaylistPk = null;
          this.videolar = []; this.taskForm.selectedVideos = []; this.updateSure();
        }
      });
    },

    buildDays() {
      const start = new Date(this.refDate + 'T00:00:00');
      this.days = Array.from({ length: 7 }, (_, i) => {
        const d = new Date(start); d.setDate(start.getDate() + i);
        const dow = d.getDay();
        return {
          label: GUNLER[dow === 0 ? 6 : dow - 1],
          tarih: localISO(d),
          gorevler: [],
          isWeekend: dow === 0 || dow === 6,
        };
      });
    },

    get weekLabel() {
      if (!this.days.length) return '';
      return `${this.days[0].tarih} – ${this.days[6].tarih}`;
    },

    prevWeek() {
      const d = new Date(this.refDate + 'T00:00:00');
      d.setDate(d.getDate() - 7);
      this.refDate = localISO(d);
      this.buildDays();
      this.loadWeek();
    },

    nextWeek() {
      const d = new Date(this.refDate + 'T00:00:00');
      d.setDate(d.getDate() + 7);
      this.refDate = localISO(d);
      this.buildDays();
      this.loadWeek();
    },

    prevDay() {
      const d = new Date(this.refDate + 'T00:00:00');
      d.setDate(d.getDate() - 1);
      this.refDate = localISO(d);
      this.buildDays();
      this.loadWeek();
    },

    nextDay() {
      const d = new Date(this.refDate + 'T00:00:00');
      d.setDate(d.getDate() + 1);
      this.refDate = localISO(d);
      this.buildDays();
      this.loadWeek();
    },

    goToDate(iso) {
      if (!iso) return;
      this.refDate = isoMonday(iso);
      this.buildDays();
      this.loadWeek();
    },

    async loadWeek() {
      if (!this.studentId) return;
      try {
        const [d0, d6] = [this.days[0].tarih, this.days[6].tarih];
        const base = `/coach/tasks/api/gorevler?student_id=${this.studentId}&hafta=`;
        const urls = [base + d0];
        if (isoMonday(d0) !== isoMonday(d6)) urls.push(base + d6);
        const jsons = await Promise.all(urls.map(u => fetch(u).then(r => r.json())));
        const seen = new Set(), all = [];
        for (const data of jsons) for (const g of (data.gorevler ?? []))
          if (!seen.has(g.id)) { seen.add(g.id); all.push(g); }
        const byDate = {};
        all.forEach(g => { (byDate[g.tarih] ??= []).push(g); });
        this.days = this.days.map(day => ({ ...day, gorevler: byDate[day.tarih] ?? [] }));
      } catch (e) {
        console.error('[loadWeek]', e);
      }
    },

    dailyLabel(idx) {
      const dk = (this.days[idx]?.gorevler ?? []).reduce((sum, g) => sum + (g.ozel_sure_dk ?? 0), 0);
      if (!dk) return '';
      const s = Math.floor(dk / 60), m = dk % 60;
      return s ? `${s}s ${m}dk` : `${m}dk`;
    },

    dailyActualDk(idx) {
      return (this.days[idx]?.gorevler ?? [])
        .filter(g => g.is_completed)
        .reduce((sum, g) => sum + (g.time_spent_dk ?? 0), 0);
    },

    fmtDk(dk) {
      if (!dk) return '';
      const s = Math.floor(dk / 60), m = dk % 60;
      return s ? `${s}s ${m}dk` : `${m}dk`;
    },

    dailyActualLabel(idx) {
      const dk = this.dailyActualDk(idx);
      return dk ? '✓ ' + this.fmtDk(dk) : '';
    },

    _tints(t) {
      if (this.isDark) {
        const DM = {
          konu_anlatimi: { bg: 'rgba(96,165,250,.20)',  border: '#60a5fa', title: '#93c5fd' },
          soru_cozumu:   { bg: 'rgba(252,211,77,.20)',   border: '#fbbf24', title: '#fcd34d' },
          tekrar:        { bg: 'rgba(74,222,128,.20)',   border: '#4ade80', title: '#86efac' },
        };
        return DM[t] ?? { bg: 'rgba(156,163,175,.20)', border: '#6b7280', title: '#9ca3af' };
      }
      return hexTints(this.colorSettings[t] ?? DEFAULT_COLORS[t] ?? '#6b7280');
    },
    colorFor(t)      { return this._tints(t).bg; },
    borderFor(t)     { return this._tints(t).border; },
    titleColorFor(t) { return this._tints(t).title; },
    visibleGorevler(gun) {
      return this.showCompleted ? gun.gorevler : gun.gorevler.filter(g => !g.is_completed);
    },
    get completionStats() {
      const all = this.days.flatMap(d => d.gorevler);
      return { done: all.filter(g => g.is_completed).length, total: all.length };
    },

    get filteredYtListeler() {
      const tip  = this.taskForm.sinav_tipi;
      const ders = this.dersler.find(d => d.id == this.taskForm.konu_ders_id);
      const alan = (typeof _STUDENT_ALAN_MAP !== 'undefined' && this.studentId)
        ? (_STUDENT_ALAN_MAP[this.studentId] || 'SAY') : 'SAY';
      return this.ytListeler.filter(l => {
        if (tip && l.exam_type !== tip) return false;
        if (l.exam_type === 'AYT' && alan && l.subject_display) {
          const allowed = _PLAYLIST_AYT_MAP[alan];
          if (allowed && !allowed.has(l.subject_display)) return false;
        }
        if (ders) return l.subject_display === ders.ad;
        return true;
      });
    },

    get filteredDersler() {
      const sinav = this.taskForm.sinav_tipi;
      if (sinav === 'TYT') return this.dersler.filter(d => _DERS_TYT_ALLOW.has(d.ad));
      if (sinav === 'AYT') {
        const alan = (typeof _STUDENT_ALAN_MAP !== 'undefined' && this.studentId)
          ? (_STUDENT_ALAN_MAP[this.studentId] || 'SAY') : 'SAY';
        const allowed = _DERS_AYT_MAP[alan];
        if (!allowed) return this.dersler;
        return this.dersler.filter(d => d.ad === 'Diğer' || allowed.has(d.ad));
      }
      return this.dersler;
    },

    aktiviteLabel: t => AKTIVITE_LABELS[t] ?? t ?? '',
    formatDetay: d => `• ${d.aciklama}${d.sure_bilgisi ? ' (' + d.sure_bilgisi + ')' : ''}`,
    durStr: dk => !dk ? '' : dk >= 60 ? `⏱ ${Math.floor(dk / 60)}s${dk % 60 ? ' ' + dk % 60 + 'dk' : ''}` : `⏱ ${dk}dk`,

    loadColorSettings() {
      try {
        const saved = JSON.parse(localStorage.getItem(COLORS_KEY) ?? '{}');
        this.colorSettings = { ...DEFAULT_COLORS, ...saved };
      } catch { this.colorSettings = { ...DEFAULT_COLORS }; }
    },
    saveColorSettings() { localStorage.setItem(COLORS_KEY, JSON.stringify(this.colorSettings)); },
    resetColors() { this.colorSettings = { ...DEFAULT_COLORS }; this.saveColorSettings(); },

    exportUrl(ext) {
      return `/coach/tasks/export/${ext}?student_id=${this.studentId}&hafta=${this.refDate}`;
    },

    exportHTML() {
      const studentName = document.querySelector('select[x-model="studentId"]')
        ?.selectedOptions[0]?.text?.trim() || '';
      _downloadWeeklyHTML(this.days, this.colorSettings, studentName, this.weekLabel, `hafta_${this.refDate}.html`);
    },

    async exportPDF() {
      if (this.pdfExporting) return;
      this.pdfExporting = true;

      const toHide = [...document.querySelectorAll('[data-pdf-hide]')];
      toHide.forEach(el => { el.dataset.wasDisplay = el.style.display; el.style.display = 'none'; });

      // Apply pdf-mode: disables flex stretch, transforms, overflow, normalises spacing.
      document.body.classList.add('pdf-mode');

      const grid = document.getElementById('weekly-grid');
      await this.$nextTick();

      try {
        const SCALE = 2;
        const canvas = await html2canvas(grid, {
          scale: SCALE,
          useCORS: true,
          scrollX: 0,
          scrollY: 0,
          backgroundColor: '#f3f4f6',
          logging: false,
          windowWidth:  grid.scrollWidth,
          windowHeight: grid.scrollHeight,
        });

        const MARGIN   = 6;
        const avW      = 297 - 2 * MARGIN;   // 285 mm
        const avH      = 210 - 2 * MARGIN;   // 198 mm
        const pxPerMm  = (96 * SCALE) / 25.4;
        const imgWmm   = canvas.width  / pxPerMm;
        const imgHmm   = canvas.height / pxPerMm;

        // Fit both dimensions into one page; clamp between 0.6 (min) and 1.0 (no upscale)
        const finalScale = Math.min(Math.max(Math.min(avW / imgWmm, avH / imgHmm), 0.6), 1);

        const { jsPDF } = window.jspdf;
        const pdf = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
        pdf.addImage(
          canvas.toDataURL('image/jpeg', 0.92), 'JPEG',
          MARGIN, MARGIN,
          imgWmm * finalScale, imgHmm * finalScale
        );
        pdf.save(`hafta_${this.refDate}.pdf`);
      } catch (e) {
        console.error('[exportPDF]', e);
      } finally {
        document.body.classList.remove('pdf-mode');
        toHide.forEach(el => { el.style.display = el.dataset.wasDisplay ?? ''; delete el.dataset.wasDisplay; });
        this.pdfExporting = false;
      }
    },

    // ── External API (create / refresh flow only) ──────────────────────────

    async loadDersler() {
      try {
        const r = await fetch('/coach/tasks/api/dersler');
        const d = await r.json();
        this.dersler = d.dersler ?? [];
      } catch (e) {
        console.error('[loadDersler]', e);
        this.dersler = [];
      }
    },

    async loadListeler() {
      if (!this.taskForm.konu_ders_id) return;
      try {
        const tip = this.taskForm.sinav_tipi || 'TYT';
        const r = await fetch(`/coach/tasks/api/oynatma-listeleri/${this.taskForm.konu_ders_id}?tip=${tip}`);
        const d = await r.json();
        this.listeler = d.listeler ?? [];
        this.taskForm.liste_id = '';
        this.taskForm.ytPlaylistPk = null;
        this.videolar = [];
      } catch (e) {
        console.error('[loadListeler]', e);
      }
      await this.loadYtListeler();
    },

    async loadVideolar(listeId) {
      // Accept an explicit listeId so the edit flow can pass meta.liste_id directly
      // without relying on reactive state being flushed. The create flow calls this
      // with no argument and falls back to reading taskForm.liste_id from state.
      const id = listeId ?? this.taskForm.liste_id;
      if (!id) return;
      try {
        const r = await fetch(`/coach/tasks/api/videolar/${id}`);
        const d = await r.json();
        this.videolar = d.videolar ?? [];
      } catch (e) {
        console.error('[loadVideolar]', e);
      }
    },

    // ── YouTube playlist helpers ────────────────────────────────────────────

    async loadYtListeler() {
      try {
        const r = await fetch('/coach/tasks/api/youtube/list');
        const d = await r.json();
        this.ytListeler = d.playlists ?? [];
      } catch (e) { this.ytListeler = []; }
    },

    async loadYtVideolar(pk) {
      this.videolar = [];
      this.taskForm.ytPlaylistPk = pk;
      try {
        const r = await fetch(`/coach/tasks/api/youtube/${pk}/videos`);
        const d = await r.json();
        // Normalise to the same shape videolar uses: {id, baslik, sure_dk}
        this.videolar = (d.videos ?? []).map(v => ({
          id: v.id, baslik: v.title, sure_dk: v.duration,
        }));
        this.taskForm.ytPlaylistTitle = d.title ?? '';
        this.taskForm.selectedVideos = [];
        this.updateSure();
      } catch (e) { console.error('[loadYtVideolar]', e); }
    },

    handleListeChange() {
      const val = this.taskForm.liste_id;
      if (typeof val === 'string' && val.startsWith('yt:')) {
        this.loadYtVideolar(parseInt(val.slice(3)));
      } else {
        this.taskForm.ytPlaylistPk = null;
        this.loadVideolar();
      }
    },

    async deleteYtPlaylist(pk) {
      if (!confirm('Bu playlisti ve tüm videolarını silmek istiyor musunuz?')) return;
      try {
        const r = await fetch(`/coach/tasks/api/youtube/${pk}`, {
          method: 'DELETE',
          headers: { 'X-CSRFToken': CSRF },
        });
        if (!r.ok) {
          const d = await r.json().catch(() => ({}));
          alert(d.error || 'Silme işlemi başarısız.');
          return;
        }
        this.ytListeler = this.ytListeler.filter(l => l.pk !== pk);
        if (this.taskForm.liste_id === 'yt:' + pk) {
          this.taskForm.liste_id = ''; this.taskForm.ytPlaylistPk = null;
          this.videolar = []; this.taskForm.selectedVideos = []; this.updateSure();
        }
      } catch (e) { console.error('[deleteYtPlaylist]', e); }
    },

    onPlaylistImported(payload) {
      // Called when the import modal fires 'playlist-imported'.
      // Pre-fill the create-task form with the imported playlist.
      this.taskForm.aktivite_tipi   = 'konu_anlatimi';
      this.taskForm.sinav_tipi      = payload.exam_type;
      this.taskForm.ders_title      = (payload.subject_display || payload.exam_type) + ' - Konu Anlatimi';
      this.taskForm.liste_id        = 'yt:' + payload.playlist_pk;
      this.taskForm.ytPlaylistPk    = payload.playlist_pk;
      this.taskForm.ytPlaylistTitle = payload.title;
      this.listeler = [];
      this.videolar = (payload.videos ?? []).map(v => ({
        id: v.id, baslik: v.title, sure_dk: v.duration,
      }));
      this.taskForm.selectedVideos = [];
      this.updateSure();
      this.showTaskModal = true;
    },

    updateSure() {
      const total = this.taskForm.selectedVideos.reduce((sum, vid_id) => {
        const v = this.videolar.find(v => v.id == vid_id);
        return sum + (v?.sure_dk ?? 0);
      }, 0);
      this.taskForm.ozel_sure_dk = total;
    },

    // ── Task CRUD ──────────────────────────────────────────────────────────

    openAddTask(tarih) {
      this.editingTask = null;
      this.taskForm = {
        aktivite_tipi: 'konu_anlatimi', sinav_tipi: 'TYT', ders_title: '',
        ozel_sure_dk: 0, aciklama: '', konu_not: '',
        konu_ders_id: '', liste_id: '', selectedVideos: [], tarih, error: '',
      };
      this.listeler = []; this.videolar = [];
      this.showTaskModal = true;
    },

    async editTask(g) {
      this.editingTask = g;
      // Recover sinav_tipi + konu_ders_id from denormalised ders_title for Soru/Tekrar.
      let sinav_tipi = 'TYT', konu_ders_id = '';
      if (g.aktivite_tipi !== 'konu_anlatimi' && g.ders_title) {
        const sep = g.ders_title.indexOf(' - ');
        if (sep !== -1) {
          const maybeExam = g.ders_title.slice(0, sep);
          if (['TYT', 'AYT'].includes(maybeExam)) {
            sinav_tipi = maybeExam;
            const dersAd = g.ders_title.slice(sep + 3);
            konu_ders_id = this.dersler.find(d => d.ad === dersAd)?.id ?? '';
          }
        }
      }
      this.taskForm = {
        aktivite_tipi: g.aktivite_tipi ?? 'konu_anlatimi',
        sinav_tipi, konu_ders_id, liste_id: '',
        ders_title: g.ders_title ?? '',
        ozel_sure_dk: g.ozel_sure_dk ?? 0,
        aciklama: g.detaylar?.[0]?.aciklama ?? '',
        konu_not: '', selectedVideos: [], tarih: g.tarih, error: '',
      };
      this.listeler = []; this.videolar = [];
      // Hydrate fully before opening the modal so videolar is complete when x-for renders.
      // This eliminates the race where sinav_tipi @change="videolar=[]" could fire between
      // loadVideolar completing and the modal rendering.
      if (g.aktivite_tipi === 'konu_anlatimi' && g.meta) {
        await this._hydrateKonuEdit(g);
      }
      this.showTaskModal = true;
      // Scroll AFTER modal is visible — scrollIntoView on a hidden element has no effect.
      if (g.aktivite_tipi === 'konu_anlatimi' && g.meta) {
        await this.$nextTick();
        const checked = this.$refs.videoList?.querySelector('input[type="checkbox"]:checked');
        checked?.closest('label')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    },

    async _hydrateKonuEdit(g) {
      const meta = g.meta ?? {};
      this.taskForm.sinav_tipi = meta.sinav_tipi ?? 'TYT';

      if (meta.source === 'youtube' && meta.youtube_playlist_pk) {
        // YouTube-sourced task: load videos from our DB
        this.taskForm.liste_id = 'yt:' + meta.youtube_playlist_pk;
        await this.loadYtVideolar(meta.youtube_playlist_pk);
        const savedIds = new Set((meta.videos ?? []).map(v => String(v.id)));
        this.taskForm.selectedVideos = this.videolar
          .filter(v => savedIds.has(String(v.id)))
          .map(v => String(v.id));
      } else {
        // External API task (existing path)
        this.taskForm.konu_ders_id = meta.ders_id ?? '';
        await this.loadListeler();
        this.taskForm.liste_id = meta.liste_id ?? '';
        console.log('[hydrate] loading videos for liste:', meta.liste_id);
        await this.loadVideolar(meta.liste_id);
        console.log('[hydrate] videolar loaded:', this.videolar.length, 'videos');
        const savedIds = new Set((meta.videos ?? []).map(v => String(v.id)));
        this.taskForm.selectedVideos = this.videolar
          .filter(v => savedIds.has(String(v.id)))
          .map(v => String(v.id));
      }

      this.updateSure();
    },

    async saveTask() {
      this.taskForm.error = '';
      let detaylar;

      if (this.taskForm.aktivite_tipi === 'konu_anlatimi') {
        detaylar = this.taskForm.selectedVideos.map(vid_id => {
          const v = this.videolar.find(v => v.id == vid_id);
          return { aciklama: v?.baslik ?? String(vid_id), sure_bilgisi: v ? `${v.sure_dk} dk` : '' };
        });
        if (this.taskForm.konu_not.trim()) {
          detaylar.push({ aciklama: this.taskForm.konu_not.trim(), sure_bilgisi: '' });
        }
        const isYtSource = typeof this.taskForm.liste_id === 'string' && this.taskForm.liste_id.startsWith('yt:');
        if (isYtSource) {
          const pl = this.ytListeler.find(l => l.pk === this.taskForm.ytPlaylistPk);
          this.taskForm.ders_title = this.taskForm.ders_title ||
            (pl ? (pl.subject_display || pl.exam_type) + ' - Konu Anlatimi' : 'Konu Anlatimi');
        } else {
          const ders = this.dersler.find(d => d.id == this.taskForm.konu_ders_id);
          this.taskForm.ders_title = ders ? `${ders.ad} - Konu Anlatımı` : (this.taskForm.ders_title || 'Konu Anlatımı');
        }
      } else {
        if (!this.taskForm.konu_ders_id) { this.taskForm.error = 'Ders seçilmeli.'; return; }
        if (!this.taskForm.aciklama.trim()) { this.taskForm.error = 'Açıklama boş olamaz.'; return; }
        const ders = this.dersler.find(d => d.id == this.taskForm.konu_ders_id);
        this.taskForm.ders_title = ders ? `${this.taskForm.sinav_tipi} - ${ders.ad}` : '';
        detaylar = [{ aciklama: this.taskForm.aciklama.trim(), sure_bilgisi: '' }];
      }

      const payload = {
        tarih:        this.taskForm.tarih,
        aktivite_tipi: this.taskForm.aktivite_tipi,
        ders_title:   this.taskForm.ders_title,
        ozel_sure_dk: this.taskForm.ozel_sure_dk,
        detaylar:     JSON.stringify(detaylar),
      };

      if (!this.editingTask) {
        payload.student_id = parseInt(this.studentId);
      }

      if (this.taskForm.aktivite_tipi === 'konu_anlatimi') {
        payload.sinav_tipi = this.taskForm.sinav_tipi;
        const isYt = typeof this.taskForm.liste_id === 'string' && this.taskForm.liste_id.startsWith('yt:');
        if (isYt) {
          const ytPk = this.taskForm.ytPlaylistPk ?? parseInt(this.taskForm.liste_id.slice(3));
          payload.youtube_playlist_pk = ytPk;
          payload.liste_baslik = this.taskForm.ytPlaylistTitle || '';
        } else {
          payload.konu_ders_id = this.taskForm.konu_ders_id;
          payload.liste_id     = this.taskForm.liste_id;
          payload.liste_baslik = this.listeler.find(l => String(l.id) === String(this.taskForm.liste_id))?.baslik ?? '';
        }
        // videos array goes into meta — source of truth for future edit hydration
        payload.videos = this.taskForm.selectedVideos.map(vid_id => {
          const v = this.videolar.find(v => v.id == vid_id);
          return { id: Number(vid_id), title: v?.baslik ?? '', duration: v?.sure_dk ?? 0 };
        });
      }

      const url    = this.editingTask ? `/coach/tasks/api/gorev/${this.editingTask.id}` : '/coach/tasks/api/gorevler';
      const method = this.editingTask ? 'PUT' : 'POST';

      try {
        const r = await fetch(url, {
          method,
          headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await r.json();
        if (!r.ok) { this.taskForm.error = JSON.stringify(data.errors ?? data); return; }
        this.showTaskModal = false;
        await this.loadWeek();
      } catch (e) {
        this.taskForm.error = 'Kayıt sırasında hata oluştu.';
        console.error('[saveTask]', e);
      }
    },

    async deleteTask(id) {
      try {
        await fetch(`/coach/tasks/api/gorev/${id}`, { method: 'DELETE', headers: { 'X-CSRFToken': CSRF } });
        await this.loadWeek();
      } catch (e) {
        console.error('[deleteTask]', e);
      }
    },

    // ── Drag & drop ─────────────────────────────────────────────────────────
    // Cross-day drag = COPY (preserves meta server-side via copy_to_date).
    // Same-day drop  = no-op (reorder not wired to drag; meta invariant safe).

    onDragStart(evt, taskId, fromDate) {
      this.dragTaskId   = taskId;
      this.dragFromDate = fromDate;
      evt.dataTransfer.effectAllowed = 'copyMove';
    },

    async onDrop(evt, toDate) {
      if (!this.dragTaskId) return;
      if (this.dragFromDate !== toDate) {
        // Cross-day: copy — server carries meta.videos forward intact.
        try {
          await fetch(`/coach/tasks/api/gorev/${this.dragTaskId}/copy`, {
            method: 'POST',
            headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/json' },
            body: JSON.stringify({ hedef_tarih: toDate }),
          });
        } catch (e) {
          console.error('[onDrop copy]', e);
        }
      }
      // Same-day drop: intentional no-op (meta invariant preserved).
      this.dragTaskId = null; this.dragFromDate = null;
      await this.loadWeek();
    },
  };
}
