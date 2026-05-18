const CSRF = document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? '';
const GUNLER = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar'];

function localISO(d) {
  return d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0');
}

const AKTIVITE_LABELS = { konu_anlatimi: 'Konu Anlatımı', soru_cozumu: 'Soru Çözümü', tekrar: 'Tekrar' };
const QUALITY_LABELS  = { easy: 'Kolay', medium: 'Orta', hard: 'Zor' };
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

// ── Standalone HTML export helper (mirrors tasks_panel.js version) ────────────
function _buildTaskHTML_s(g, cs) {
  const DEFAULTS = { konu_anlatimi: '#3b82f6', soru_cozumu: '#eab308', tekrar: '#22c55e' };
  const base = cs[g.aktivite_tipi] ?? DEFAULTS[g.aktivite_tipi] ?? '#6b7280';
  const r = parseInt(base.slice(1,3),16), gr = parseInt(base.slice(3,5),16), b = parseInt(base.slice(5,7),16);
  const bg     = `rgba(${r},${gr},${b},0.12)`;
  const border = `rgba(${r},${gr},${b},0.45)`;
  const title  = `rgb(${Math.round(r*.6)},${Math.round(gr*.6)},${Math.round(b*.6)})`;
  const dur = g.ozel_sure_dk ? `<span style="font-size:11px;color:#6b7280">⏱ ${g.ozel_sure_dk}dk</span>` : '';
  const details = (g.detaylar||[]).map(d =>
    `<div style="font-size:11px;color:#6b7280;margin-top:2px">• ${d.aciklama||''}${d.sure_bilgisi?' ('+d.sure_bilgisi+')':''}</div>`
  ).join('');
  const done = g.is_completed ? `<span style="font-size:10px;color:#22c55e;margin-left:4px">✓</span>` : '';
  return `<div style="background:${bg};border:2px solid ${border};border-radius:10px;padding:8px 10px;margin-bottom:6px;break-inside:avoid;${g.is_completed?'opacity:.55':''}">
    <div style="font-size:13px;font-weight:700;color:${title};line-height:1.3;margin-bottom:3px">${g.ders_title||''}${done}</div>
    ${dur}${details}
  </div>`;
}

function _downloadWeeklyHTML_s(days, colorSettings, studentName, weekLabel, filename) {
  const cols = days.map((gun, idx) => {
    const weekend = idx >= 5;
    const tasks = (gun.gorevler||[]).map(g => _buildTaskHTML_s(g, colorSettings)).join('');
    const empty = !gun.gorevler?.length ? `<div style="color:#d1d5db;font-size:12px;text-align:center;padding:16px 0">—</div>` : '';
    return `<div style="min-width:0;background:${weekend?'#f8fafc':'#fff'};border:1px solid ${weekend?'#e2e8f0':'#f3f4f6'};border-radius:16px;overflow:hidden">
      <div style="padding:10px 12px 8px;background:${weekend?'#f1f5f9':'#f9fafb'};border-bottom:1px solid ${weekend?'#e2e8f0':'#f3f4f6'}">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:${weekend?'#64748b':'#4b5563'}">${gun.label}</div>
        <div style="font-size:11px;color:#9ca3af;margin-top:1px">${gun.tarih}</div>
      </div>
      <div style="padding:10px">${tasks}${empty}</div>
    </div>`;
  }).join('');

  const html = `<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Haftalık Planım${studentName?' — '+studentName:''}</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:system-ui,-apple-system,sans-serif;background:#f3f4f6;color:#1f2937;padding:24px}
  .header{margin-bottom:20px}
  .header h1{font-size:20px;font-weight:700;color:#111827}
  .header .meta{font-size:13px;color:#6b7280;margin-top:4px}
  .grid{display:grid;grid-template-columns:repeat(7,1fr);gap:10px}
  @media(max-width:900px){.grid{grid-template-columns:repeat(4,1fr)}}
  @media(max-width:600px){.grid{grid-template-columns:repeat(2,1fr)}}
  @media print{
    body{background:#fff;padding:10px}
    .grid{gap:6px}
    @page{size:A4 landscape;margin:10mm}
  }
</style>
</head>
<body>
<div class="header">
  <h1>Haftalık Ders Planım${studentName?' — '+studentName:''}</h1>
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

function studentPanel(studentId, studentName) {
  return {
    studentId,
    refDate: localISO(new Date()),
    days: [],
    toplamlar: {},
    colorSettings: { ...DEFAULT_COLORS },
    isDark: document.documentElement.classList.contains('dark'),
    showEditModal: false,
    showAddModal: false,
    pdfExporting: false,
    editForm: { id: null, ozel_sure_dk: 0, aciklama: '', error: '' },
    addForm:  { tarih: '', aktivite_tipi: 'tekrar', ders_title: '', ozel_sure_dk: 0, aciklama: '', error: '' },
    dragTaskId: null, dragFromDate: null,

    get hasEditableTask() {
      return this.days.some(d => d.gorevler.some(g => g.student_can_edit));
    },

    async init() {
      this.loadColorSettings();
      this.buildDays();
      await this.loadWeek();
      window.addEventListener('darkmode-change', (e) => { this.isDark = e.detail.isDark; });
    },

    buildDays() {
      const ref = new Date(this.refDate + 'T00:00:00');
      const monday = new Date(ref);
      monday.setDate(ref.getDate() - (ref.getDay() === 0 ? 6 : ref.getDay() - 1));
      this.days = GUNLER.map((label, i) => {
        const d = new Date(monday); d.setDate(monday.getDate() + i);
        return { label, tarih: localISO(d), gorevler: [] };
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

    async loadWeek() {
      try {
        const r = await fetch(`/student/tasks/api/gorevler?hafta=${this.refDate}`);
        const data = await r.json();
        this.toplamlar = data.gunluk_toplamlar ?? {};
        const byDate = {};
        (data.gorevler ?? []).forEach(g => { (byDate[g.tarih] ??= []).push(g); });
        this.days = this.days.map(day => ({ ...day, gorevler: byDate[day.tarih] ?? [] }));
      } catch (e) {
        console.error('[loadWeek]', e);
      }
    },

    dailyLabel(idx) {
      const dk = this.toplamlar[idx] ?? 0;
      if (!dk) return '';
      const s = Math.floor(dk / 60), m = dk % 60;
      return s ? `${s}s ${m}dk` : `${m}dk`;
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
    aktiviteLabel: t => AKTIVITE_LABELS[t] ?? t ?? '',
    formatDetay: d => `• ${d.aciklama}${d.sure_bilgisi ? ' (' + d.sure_bilgisi + ')' : ''}`,
    durStr: dk => !dk ? '' : dk >= 60 ? `⏱ ${Math.floor(dk / 60)}s${dk % 60 ? ' ' + dk % 60 + 'dk' : ''}` : `⏱ ${dk}dk`,
    qualityLabel: q => QUALITY_LABELS[q] ?? '',

    loadColorSettings() {
      try {
        const saved = JSON.parse(localStorage.getItem(COLORS_KEY) ?? '{}');
        this.colorSettings = { ...DEFAULT_COLORS, ...saved };
      } catch { this.colorSettings = { ...DEFAULT_COLORS }; }
    },

    async toggleComplete(id) {
      try {
        const r = await fetch(`/student/tasks/api/complete/${id}`, {
          method: 'POST',
          headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        });
        if (r.ok) await this.loadWeek();
      } catch (e) { console.error('[toggleComplete]', e); }
    },

    async markQuality(id, quality) {
      try {
        const r = await fetch(`/student/tasks/api/complete/${id}`, {
          method: 'POST',
          headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/json' },
          body: JSON.stringify({ quality }),
        });
        if (r.ok) await this.loadWeek();
      } catch (e) { console.error('[markQuality]', e); }
    },

    openEditModal(g) {
      this.editForm = {
        id: g.id,
        ozel_sure_dk: g.ozel_sure_dk ?? 0,
        aciklama: g.detaylar?.[0]?.aciklama ?? '',
        error: '',
      };
      this.showEditModal = true;
    },

    async saveEdit() {
      this.editForm.error = '';
      try {
        const r = await fetch(`/student/tasks/api/gorev/${this.editForm.id}/edit`, {
          method: 'PUT',
          headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ozel_sure_dk: this.editForm.ozel_sure_dk,
            aciklama:     this.editForm.aciklama.trim() || null,
          }),
        });
        if (!r.ok) { this.editForm.error = 'Kayıt başarısız.'; return; }
        this.showEditModal = false;
        await this.loadWeek();
      } catch (e) {
        this.editForm.error = 'Bir hata oluştu.';
        console.error('[saveEdit]', e);
      }
    },

    async reorderTask(id, targetId) {
      try {
        const r = await fetch(`/student/tasks/api/gorev/${id}/reorder`, {
          method: 'POST',
          headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/json' },
          body: JSON.stringify({ hedef_id: targetId }),
        });
        if (r.ok) await this.loadWeek();
      } catch (e) { console.error('[reorderTask]', e); }
    },

    // ── Student create ────────────────────────────────────────────────────────
    openAddModal(tarih) {
      this.addForm = { tarih, aktivite_tipi: 'tekrar', ders_title: '', ozel_sure_dk: 0, aciklama: '', error: '' };
      this.showAddModal = true;
    },

    async saveNewTask() {
      this.addForm.error = '';
      if (!this.addForm.ders_title.trim() && !this.addForm.aciklama.trim()) {
        this.addForm.error = 'Başlık veya açıklama giriniz.'; return;
      }
      try {
        const r = await fetch('/student/tasks/api/gorev/new', {
          method: 'POST',
          headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tarih:        this.addForm.tarih,
            aktivite_tipi: this.addForm.aktivite_tipi,
            ders_title:   this.addForm.ders_title.trim() || null,
            ozel_sure_dk: this.addForm.ozel_sure_dk || null,
            aciklama:     this.addForm.aciklama.trim(),
          }),
        });
        if (!r.ok) { this.addForm.error = 'Kayıt başarısız.'; return; }
        this.showAddModal = false;
        await this.loadWeek();
      } catch (e) { this.addForm.error = 'Hata oluştu.'; console.error('[saveNewTask]', e); }
    },

    // ── Student delete (non-master only) ──────────────────────────────────────
    async deleteTask(id) {
      try {
        await fetch(`/student/tasks/api/gorev/${id}/delete`, { method: 'DELETE', headers: { 'X-CSRFToken': CSRF } });
        await this.loadWeek();
      } catch (e) { console.error('[deleteTask]', e); }
    },

    // ── Reset to coach plan ───────────────────────────────────────────────────
    async resetToCoachPlan() {
      if (!this.days.length) return;
      try {
        await fetch('/student/tasks/api/reset/', {
          method: 'POST',
          headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/json' },
          body: JSON.stringify({ week_start: this.days[0].tarih }),
        });
        await this.loadWeek();
      } catch (e) { console.error('[resetToCoachPlan]', e); }
    },

    // ── PDF + HTML export ─────────────────────────────────────────────────────
    exportUrl(ext) {
      return `/student/tasks/export/${ext}?hafta=${this.refDate}`;
    },

    exportHTML() {
      _downloadWeeklyHTML_s(this.days, this.colorSettings, studentName, this.weekLabel, `hafta_${this.refDate}.html`);
    },

    async exportPDF() {
      if (this.pdfExporting) return;
      this.pdfExporting = true;
      const toHide = [...document.querySelectorAll('[data-pdf-hide]')];
      toHide.forEach(el => { el.dataset.wasDisplay = el.style.display; el.style.display = 'none'; });
      document.body.classList.add('pdf-mode');
      const grid = document.getElementById('student-weekly-grid');
      await this.$nextTick();
      try {
        const SCALE = 2;
        const canvas = await html2canvas(grid, {
          scale: SCALE, useCORS: true, scrollX: 0, scrollY: 0,
          backgroundColor: '#f3f4f6', logging: false,
          windowWidth: grid.scrollWidth, windowHeight: grid.scrollHeight,
        });

        const MARGIN  = 6;
        const avW     = 297 - 2 * MARGIN;
        const avH     = 210 - 2 * MARGIN;
        const pxPerMm = (96 * SCALE) / 25.4;
        const imgWmm  = canvas.width  / pxPerMm;
        const imgHmm  = canvas.height / pxPerMm;

        const finalScale = Math.min(Math.max(Math.min(avW / imgWmm, avH / imgHmm), 0.6), 1);

        const { jsPDF } = window.jspdf;
        const pdf = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
        pdf.addImage(
          canvas.toDataURL('image/jpeg', 0.92), 'JPEG',
          MARGIN, MARGIN,
          imgWmm * finalScale, imgHmm * finalScale
        );
        pdf.save(`hafta_${this.refDate}.pdf`);
      } catch (e) { console.error('[exportPDF]', e); }
      finally {
        document.body.classList.remove('pdf-mode');
        toHide.forEach(el => { el.style.display = el.dataset.wasDisplay ?? ''; delete el.dataset.wasDisplay; });
        this.pdfExporting = false;
      }
    },

    // ── Drag & drop (only active when student_can_edit) ──────────────────────
    onDragStart(evt, taskId, fromDate, canEdit) {
      if (!canEdit) { evt.preventDefault(); return; }
      this.dragTaskId   = taskId;
      this.dragFromDate = fromDate;
      evt.dataTransfer.effectAllowed = 'copyMove';
    },

    async onDrop(evt, toDate) {
      if (!this.dragTaskId) return;
      if (this.dragFromDate !== toDate) {
        try {
          await fetch(`/student/tasks/api/gorev/${this.dragTaskId}/copy`, {
            method: 'POST',
            headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/json' },
            body: JSON.stringify({ hedef_tarih: toDate }),
          });
        } catch (e) { console.error('[onDrop copy]', e); }
      }
      this.dragTaskId = null; this.dragFromDate = null;
      await this.loadWeek();
    },
  };
}
