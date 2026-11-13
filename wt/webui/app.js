/* WorkTime review UI — local single-page app.
 *
 * Timeline: drag blocks to move, drag edges to resize, drag onto a matter chip
 * to tag. Detail drawer shows the captured focus text / clipboard / page text
 * only when the "show content" switch is on.
 */
(() => {
  'use strict';

  const $ = (sel) => document.querySelector(sel);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
  const PALETTE = ['#4f46e5', '#0891b2', '#16a34a', '#d97706', '#dc2626',
                   '#7c3aed', '#db2777', '#0d9488', '#ca8a04', '#2563eb',
                   '#9333ea', '#059669'];
  const APP_STYLE = {
    Excel: { c: '#217346', l: 'X' },
    Outlook: { c: '#0f6cbd', l: 'O' },
    Edge: { c: '#0c59a4', l: 'E' },
    Chrome: { c: '#ea4335', l: 'C' },
    Lync: { c: '#5b5fc7', l: 'L' },
    Teams: { c: '#5059c9', l: 'T' },
    Explorer: { c: '#f59e0b', l: '📁' },
    Cmd: { c: '#475569', l: '>' },
    'Deepseek harness': { c: '#4f46e5', l: 'D' },
    Notepad: { c: '#64748b', l: 'N' },
    Word: { c: '#2b579a', l: 'W' },
    PowerPoint: { c: '#c43e1c', l: 'P' },
    Acrobat: { c: '#b91c1c', l: 'A' },
  };

  const state = {
    date: '', segments: [], selected: new Set(), showContent: false,
    zoom: 1, undo: [], drawerId: null, detail: null, interrupts: new Map(),
    dates: [], policy: null,
    live: null, settingsTab: 'capture', settingsData: null,
    rules: [], matters: [], pendingRule: null, autoRefreshTimer: null,
  };
  let layout = { minStart: 0, ppm: 1.5 };
  let drag = null;
  let toastTimer = null;
  let reportPeriod = 'day';
  let reportMarkdown = '';

  // ---------- helpers ----------
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const mins = (ts) => Number(ts.slice(11, 13)) * 60 + Number(ts.slice(14, 16));
  const clock = (ts) => ts.slice(11, 16);
  const fmtDur = (sec) => {
    sec = Math.round(sec || 0);
    if (sec < 60) return sec + 's';
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    return h ? h + 'h' + String(m).padStart(2, '0') + 'm' : m + 'm';
  };
  const tsFromMins = (date, m) => {
    m = clamp(Math.round(m), 0, 1439);
    return date + 'T' + String(Math.floor(m / 60)).padStart(2, '0') + ':'
      + String(m % 60).padStart(2, '0') + ':00';
  };
  const localToday = () => {
    const d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')
      + '-' + String(d.getDate()).padStart(2, '0');
  };
  const matterOf = (s) => s.final_matter || s.auto_matter || '未归类';
  const taskOf = (s) => s.final_task || s.auto_task || '未归类';

  // Matters can be hierarchical: "P2404 项目预算 / 供应商报价 / Q-8892".
  const MATTER_SEP = ' / ';

  function matterParts(matter) {
    return String(matter || '未归类').split('/')
      .map((part) => part.trim()).filter(Boolean);
  }

  function matterTop(matter) {
    const parts = matterParts(matter);
    return parts[0] || '未归类';
  }

  function matterLeaf(matter) {
    const parts = matterParts(matter);
    return parts[parts.length - 1] || '未归类';
  }

  // A short segment that sits between two segments of another app looks like
  // an interruption (e.g. email -> Lync message -> back to email).
  function computeInterrupts() {
    const map = new Map();
    const segs = state.segments;
    for (let i = 1; i < segs.length - 1; i += 1) {
      const prev = segs[i - 1];
      const seg = segs[i];
      const next = segs[i + 1];
      const short = (seg.duration_s || 0) <= 300;
      const crossed = prev.app === next.app && seg.app !== prev.app;
      const adjacent = (mins(seg.start_ts) - mins(prev.end_ts)) <= 2
        && (mins(next.start_ts) - mins(seg.end_ts)) <= 5;
      if (short && crossed && adjacent) map.set(seg.id, { prev, next });
    }
    return map;
  }
  const appMeta = (app) => APP_STYLE[app] || { c: '#64748b', l: (app || '?').slice(0, 1).toUpperCase() };
  const colorFor = (matter) => {
    if (!matter || matter === '未归类') return '#94a3b8';
    let hash = 0;
    for (let i = 0; i < matter.length; i += 1) hash = (hash * 31 + matter.charCodeAt(i)) >>> 0;
    return PALETTE[hash % PALETTE.length];
  };
  const segById = (id) => state.segments.find((s) => s.id === id);
  const appIcon = (app) => {
    const meta = appMeta(app);
    return '<span class="app-ic" style="background:' + meta.c + '">' + esc(meta.l) + '</span>';
  };

  function toast(message) {
    const el = $('#toast');
    el.textContent = message;
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('show'), 2200);
  }

  // ---------- data ----------
  async function load(date) {
    const url = '/api/day' + (date ? '?date=' + encodeURIComponent(date) : '');
    const res = await fetch(url);
    const data = await res.json();
    state.date = data.date;
    $('#date').value = data.date;
    state.segments = data.segments || [];
    state.dates = data.dates || [];
    state.policy = data.policy || null;
    if (data.live !== undefined) {
      state.live = data.live;
      renderLive();
    }
    state.interrupts = computeInterrupts();
    state.selected.clear();
    applyDisplayPolicy();
    const wrap = $('#timelineWrap');
    const scrollLeft = wrap ? wrap.scrollLeft : 0;
    render();
    if (wrap) wrap.scrollLeft = scrollLeft;
  }

  async function reprocess() {
    if (!confirm('重新分段并命名 ' + state.date + ' 的数据？\n手动调整过的时间边界会被覆盖（标签会尽量保留）。')) return;
    const res = await fetch('/api/process', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: state.date }),
    });
    const out = await res.json();
    if (out.ok) toast('处理完成：' + out.segments + ' 段');
    else toast('处理失败：' + (out.error || ''));
    await load(state.date);
  }

  // ---------- date chips ----------
  function renderDateChips() {
    const el = $('#dateChips');
    if (!state.dates.length) { el.innerHTML = ''; return; }
    el.innerHTML = state.dates.map((item) => {
      const label = item.date.slice(5);
      const hours = ((item.seconds || 0) / 3600).toFixed(1) + 'h';
      return '<button class="chip' + (item.date === state.date ? ' active' : '')
        + '" data-date="' + esc(item.date) + '">' + label
        + '<span class="t">' + hours + '</span></button>';
    }).join('');
  }

  // ---------- stats ----------
  function renderStats() {
    const segs = state.segments;
    const active = segs.reduce((sum, s) => sum + (s.duration_s || 0), 0);
    const matters = new Set(segs.map(matterOf));
    const conf = segs.length
      ? segs.reduce((sum, s) => sum + (s.confidence || 0), 0) / segs.length : 0;
    const span = segs.length
      ? (mins(segs[segs.length - 1].end_ts) - mins(segs[0].start_ts)) : 0;
    const cards = [
      ['活跃时间', fmtDur(active), '占 8h ' + (active / 288).toFixed(0) + '%'],
      ['时间跨度', fmtDur(span * 60), '含离开'],
      ['分段', String(segs.length), ''],
      ['事项', String(matters.size), ''],
      ['平均置信度', conf.toFixed(2), ''],
    ];
    $('#stats').innerHTML = cards.map(([k, v, sub]) => (
      '<div class="stat"><div class="k">' + k + '</div><div class="v">' + v
      + (sub ? ' <small>' + sub + '</small>' : '') + '</div></div>'
    )).join('');
  }

  // ---------- day strip ----------
  function renderStrip() {
    const strip = $('#dayStrip');
    if (!state.segments.length) {
      strip.innerHTML = '<div class="strip-empty">暂无数据</div>';
      return;
    }
    strip.innerHTML = state.segments.map((s) => {
      const left = mins(s.start_ts) / 1440 * 100;
      const width = Math.max(mins(s.end_ts) - mins(s.start_ts), 1) / 1440 * 100;
      return '<div class="strip-block" data-seg-id="' + s.id + '" style="left:' + left
        + '%;width:' + width + '%;background:' + colorFor(matterTop(matterOf(s))) + '" title="'
        + clock(s.start_ts) + '–' + clock(s.end_ts) + ' ' + esc(taskOf(s)) + '"></div>';
    }).join('');
  }

  // ---------- timeline ----------
  function timelineWindow() {
    if (!state.segments.length) return { minStart: 9 * 60, maxEnd: 18 * 60 };
    const starts = state.segments.map((s) => mins(s.start_ts));
    const ends = state.segments.map((s) => mins(s.end_ts));
    let minStart = Math.floor(Math.min(...starts) / 30) * 30 - 30;
    let maxEnd = Math.ceil(Math.max(...ends) / 30) * 30 + 30;
    minStart = clamp(minStart, 0, 1380);
    maxEnd = clamp(maxEnd, minStart + 60, 1440);
    return { minStart, maxEnd };
  }

  function renderTimeline() {
    const wrap = $('#timelineWrap');
    const axis = $('#axis');
    const lanes = $('#lanes');
    if (!state.segments.length) {
      axis.style.width = '0px';
      lanes.innerHTML = '<div class="strip-empty" style="position:relative;height:80px">暂无数据，先运行 process-today.bat</div>';
      return;
    }
    const { minStart, maxEnd } = timelineWindow();
    const span = Math.max(60, maxEnd - minStart);
    const available = Math.max((wrap.clientWidth || 900) - 132 - 8, 500);
    const basePpm = Math.max(0.9, available / span);
    const ppm = basePpm * state.zoom;
    layout = { minStart, ppm };
    const width = Math.round(span * ppm);

    const step = ppm >= 2.4 ? 30 : ppm >= 1.2 ? 60 : 120;
    let ticks = '';
    for (let t = Math.ceil(minStart / step) * step; t <= maxEnd; t += step) {
      if (t - minStart < 10 || maxEnd - t < 10) continue;
      const left = Math.round((t - minStart) * ppm);
      ticks += '<span style="left:' + left + 'px">'
        + String(Math.floor(t / 60)).padStart(2, '0') + ':' + String(t % 60).padStart(2, '0')
        + '</span>';
    }
    axis.style.width = width + 'px';
    axis.style.marginLeft = '132px';
    axis.innerHTML = ticks;
    const oldLine = wrap.querySelector('.now-line');
    if (oldLine) oldLine.remove();
    const now = new Date();
    const nowStr = localToday();
    const nowMin = now.getHours() * 60 + now.getMinutes();
    if (state.date === nowStr && nowMin >= minStart && nowMin <= maxEnd) {
      const line = document.createElement('div');
      line.className = 'now-line';
      line.style.left = (132 + (nowMin - minStart) * ppm) + 'px';
      wrap.appendChild(line);
    }

    const byApp = new Map();
    state.segments.forEach((s) => {
      if (!byApp.has(s.app)) byApp.set(s.app, []);
      byApp.get(s.app).push(s);
    });
    const apps = Array.from(byApp.entries())
      .sort((a, b) => b[1].reduce((x, s) => x + s.duration_s, 0)
                     - a[1].reduce((x, s) => x + s.duration_s, 0));

    lanes.innerHTML = apps.map(([app, segs]) => {
      const blocks = segs.map((s) => {
        const left = Math.round((mins(s.start_ts) - minStart) * ppm);
        const durMin = Math.max(mins(s.end_ts) - mins(s.start_ts), 1);
        const w = Math.max(Math.round(durMin * ppm), 3);
        const interrupt = state.interrupts.has(s.id);
        const title = matterOf(s) !== '未归类' ? matterOf(s) : taskOf(s);
        let label = '';
        if (w > 34) {
          label = '<span class="blabel"><b>' + esc(title) + '</b>'
            + (w > 62 ? '<i>' + esc(s.app) + '</i>' : '') + '</span>';
        }
        return '<div class="block' + (interrupt ? ' interrupt' : '') + '" data-id="' + s.id
          + '" data-seg-id="' + s.id + '" style="left:' + left + 'px;width:' + w + 'px;background:'
          + colorFor(matterTop(matterOf(s))) + '">' + label
          + (interrupt ? '<span class="flag">⚡</span>' : '')
          + '<span class="handle l"></span><span class="handle r"></span></div>';
      }).join('');
      return '<div class="lane"><div class="lane-label">' + appIcon(app)
        + '<span class="name">' + esc(app) + '</span></div>'
        + '<div class="lane-track" style="width:' + width + 'px;background-size:'
        + Math.round(ppm * 60) + 'px 100%">' + blocks + '</div></div>';
    }).join('');
    applySelection();
  }

  function applySelection() {
    document.querySelectorAll('.block').forEach((el) => {
      el.classList.toggle('selected', state.selected.has(Number(el.dataset.id)));
    });
    document.querySelectorAll('.strip-block').forEach((el) => {
      el.classList.toggle('sel', state.selected.has(Number(el.dataset.segId)));
    });
  }

  function setSegmentHighlight(id, on) {
    document.querySelectorAll('[data-seg-id="' + id + '"]').forEach((el) => {
      el.classList.toggle('hl', on);
    });
  }

  let hoverSegId = null;

  function hoverSegment(id) {
    if (hoverSegId === id) return;
    if (hoverSegId !== null) setSegmentHighlight(hoverSegId, false);
    hoverSegId = id;
    if (id !== null) setSegmentHighlight(id, true);
  }

  function highlightWhere(predicate, on) {
    state.segments.filter(predicate).forEach((s) => setSegmentHighlight(s.id, on));
  }

  function focusSegment(id) {
    selectSegment(id, false);
    openDrawer(id);
    const wrap = $('#timelineWrap');
    const block = document.querySelector('.block[data-seg-id="' + id + '"]');
    if (wrap && block) {
      const target = block.getBoundingClientRect().left - wrap.getBoundingClientRect().left
        + wrap.scrollLeft - wrap.clientWidth / 2 + block.offsetWidth / 2;
      wrap.scrollTo({ left: Math.max(0, target), behavior: 'smooth' });
    }
    const row = document.querySelector('tr[data-seg-id="' + id + '"]');
    if (row) row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function currentPpm() { return layout.ppm; }

  // ---------- tooltip ----------
  function showTooltip(html, x, y) {
    const tip = $('#tooltip');
    tip.innerHTML = html;
    tip.classList.add('show');
    const pad = 14;
    const rect = tip.getBoundingClientRect();
    const left = Math.min(x + pad, window.innerWidth - rect.width - 8);
    const top = Math.max(8, Math.min(y + pad, window.innerHeight - rect.height - 8));
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  }
  function hideTooltip() { $('#tooltip').classList.remove('show'); }

  function blockTooltip(seg) {
    let html = '<b>' + clock(seg.start_ts) + '–' + clock(seg.end_ts) + '</b> · '
      + fmtDur(seg.duration_s) + ' · ' + esc(seg.app) + '<br>'
      + '任务：' + esc(taskOf(seg)) + '<br>事项：' + esc(matterOf(seg));
    if (seg.page_title) html += '<br>页面：' + esc(seg.page_title);
    if (state.showContent) {
      const snip = [];
      if (seg.focused_text) snip.push('<span class="k">输入/焦点：</span>' + esc(seg.focused_text.slice(0, 80)));
      if (seg.clipboard_text) snip.push('<span class="k">剪贴板：</span>' + esc(seg.clipboard_text.slice(0, 80)));
      if (snip.length) html += '<div class="snip">' + snip.join('<br>') + '</div>';
    }
    return html;
  }

  // ---------- drag / select ----------
  function blockUnderChip(x, y) {
    const el = document.elementFromPoint(x, y);
    return el ? el.closest('.chip[data-matter]') : null;
  }

  function onPointerDown(e) {
    const block = e.target.closest('.block');
    if (!block || e.button !== 0) return;
    const id = Number(block.dataset.id);
    const seg = segById(id);
    if (!seg) return;
    const mode = e.target.classList.contains('l') ? 'l'
      : e.target.classList.contains('r') ? 'r' : 'move';
    drag = {
      id, mode, startX: e.clientX, ppm: currentPpm(), block,
      origStart: mins(seg.start_ts), origEnd: mins(seg.end_ts),
      origStartIso: seg.start_ts, origEndIso: seg.end_ts,
      lastStart: mins(seg.start_ts), lastEnd: mins(seg.end_ts), moved: false,
    };
    try { block.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
    block.classList.add('dragging');
    e.preventDefault();
  }

  function onPointerMove(e) {
    if (!drag) return;
    const dx = e.clientX - drag.startX;
    if (Math.abs(dx) > 2) drag.moved = true;
    const delta = Math.round(dx / drag.ppm);
    let s = drag.origStart;
    let en = drag.origEnd;
    const dur = drag.origEnd - drag.origStart;
    if (drag.mode === 'move') {
      s = clamp(drag.origStart + delta, 0, 1440 - dur);
      en = s + dur;
    } else if (drag.mode === 'l') {
      s = clamp(drag.origStart + delta, 0, drag.origEnd - 1);
    } else {
      en = clamp(drag.origEnd + delta, drag.origStart + 1, 1440);
    }
    drag.lastStart = s;
    drag.lastEnd = en;
    drag.block.style.left = Math.round((s - layout.minStart) * drag.ppm) + 'px';
    drag.block.style.width = Math.max(Math.round((en - s) * drag.ppm), 3) + 'px';
    showTooltip('<b>' + tsFromMins(state.date, s).slice(11, 16) + '–'
      + tsFromMins(state.date, en).slice(11, 16) + '</b> · ' + fmtDur((en - s) * 60),
      e.clientX, e.clientY);
    const chip = drag.mode === 'move' ? blockUnderChip(e.clientX, e.clientY) : null;
    document.querySelectorAll('.chip.drop').forEach((c) => c.classList.remove('drop'));
    if (chip) chip.classList.add('drop');
  }

  async function onPointerUp(e) {
    if (!drag) return;
    const d = drag;
    drag = null;
    hideTooltip();
    d.block.classList.remove('dragging');
    document.querySelectorAll('.chip.drop').forEach((c) => c.classList.remove('drop'));
    if (!d.moved) {
      const additive = e.shiftKey || e.ctrlKey || e.metaKey;
      selectSegment(d.id, additive);
      if (!additive) {
        if (state.drawerId === d.id && $('#drawer').classList.contains('open')) {
          closeDrawer();
        } else {
          openDrawer(d.id);
        }
      }
      return;
    }
    const chip = d.mode === 'move' ? blockUnderChip(e.clientX, e.clientY) : null;
    if (chip) {
      await applyLabel([d.id], null, chip.dataset.matter,
        '已标为事项「' + chip.dataset.matter + '」');
      return;
    }
    if (d.lastStart === d.origStart && d.lastEnd === d.origEnd) { render(); return; }
    pushUndo({ type: 'time', id: d.id, start: d.origStartIso, end: d.origEndIso });
    const res = await fetch('/api/segment/time', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: d.id,
        start: tsFromMins(state.date, d.lastStart),
        end: tsFromMins(state.date, d.lastEnd),
      }),
    });
    const out = await res.json();
    if (!out.ok) toast('调整失败：' + (out.error || ''));
    else toast('时间已调整为 ' + tsFromMins(state.date, d.lastStart).slice(11, 16)
      + '–' + tsFromMins(state.date, d.lastEnd).slice(11, 16));
    await load(state.date);
  }

  // ---------- selection ----------
  function selectSegment(id, additive) {
    if (additive) {
      if (state.selected.has(id)) state.selected.delete(id); else state.selected.add(id);
    } else {
      state.selected.clear();
      state.selected.add(id);
    }
    applySelection();
    renderTable();
    updateBulk();
  }

  function updateBulk() {
    const n = state.selected.size;
    $('#selCount').textContent = n;
    $('#bulkBar').style.visibility = n ? 'visible' : 'hidden';
    $('#checkAll').checked = n > 0 && n === state.segments.length;
  }

  // ---------- labeling ----------
  function pushUndo(entry) {
    state.undo.push(entry);
    if (state.undo.length > 50) state.undo.shift();
    $('#btnUndo').disabled = false;
  }

  async function applyLabel(ids, task, matter, message) {
    if (!ids.length) return;
    const prev = ids.map((id) => {
      const s = segById(id);
      return { id, task: s ? (s.final_task || '') : '', matter: s ? (s.final_matter || '') : '' };
    });
    pushUndo({ type: 'label', items: prev });
    const payload = { ids, learn: true };
    if (task !== null && task !== undefined) payload.task = task;
    if (matter !== null && matter !== undefined) payload.matter = matter;
    const res = await fetch('/api/label', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const out = await res.json();
    if (!out.ok) { toast('保存失败：' + (out.error || '')); return; }
    toast(message || ('已更新 ' + ids.length + ' 段'));
    state.selected.clear();
    await load(state.date);
  }

  async function undoLast() {
    const entry = state.undo.pop();
    if (!entry) return;
    if (entry.type === 'time') {
      await fetch('/api/segment/time', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: entry.id, start: entry.start, end: entry.end }),
      });
    } else if (entry.type === 'label') {
      for (const item of entry.items) {
        await fetch('/api/label', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids: [item.id], task: item.task, matter: item.matter, learn: false }),
        });
      }
    }
    $('#btnUndo').disabled = state.undo.length === 0;
    toast('已撤销');
    await load(state.date);
  }

  // ---------- chips (hierarchical matters) ----------
  function renderChips() {
    const topTotals = new Map();
    const children = new Map(); // top -> Map(full path -> seconds)
    state.segments.forEach((s) => {
      const matter = matterOf(s);
      const top = matterTop(matter);
      topTotals.set(top, (topTotals.get(top) || 0) + s.duration_s);
      if (!children.has(top)) children.set(top, new Map());
      if (matter !== top) {
        const bucket = children.get(top);
        bucket.set(matter, (bucket.get(matter) || 0) + s.duration_s);
      }
    });
    const tops = Array.from(topTotals.entries()).sort((a, b) => b[1] - a[1]);
    $('#matterChips').innerHTML = tops.map(([top, seconds]) => {
      const kids = Array.from((children.get(top) || new Map()).entries())
        .sort((a, b) => b[1] - a[1]);
      return '<span class="chip-group">'
        + '<button class="chip parent" data-matter="' + esc(top) + '" title="点击选中该事项全部时间段">'
        + '<span class="dot" style="background:' + colorFor(top) + '"></span>'
        + '<span>' + esc(top) + '</span><span class="t">' + fmtDur(seconds) + '</span></button>'
        + kids.map(([path, sec]) => (
          '<button class="chip child" data-matter="' + esc(path) + '" title="' + esc(path) + '">'
          + '└ ' + esc(matterLeaf(path)) + '<span class="t">' + fmtDur(sec) + '</span></button>'
        )).join('')
        + '</span>';
    }).join('') || '<span class="hint">还没有标签</span>';
  }

  // ---------- charts ----------
  function renderCharts() {
    const totals = new Map();
    state.segments.forEach((s) => {
      const top = matterTop(matterOf(s));
      totals.set(top, (totals.get(top) || 0) + s.duration_s);
    });
    const total = Array.from(totals.values()).reduce((a, b) => a + b, 0) || 1;
    const items = Array.from(totals.entries()).sort((a, b) => b[1] - a[1]);
    let acc = 0;
    const stops = items.map(([m, sec]) => {
      const start = acc / total * 100;
      acc += sec;
      const end = acc / total * 100;
      return colorFor(m) + ' ' + start.toFixed(2) + '% ' + end.toFixed(2) + '%';
    });
    $('#donut').innerHTML = '<div class="donut" style="background:conic-gradient('
      + (stops.length ? stops.join(',') : '#e2e8f0 0 100%') + ')">'
      + '<div class="center"><div><b>' + fmtDur(total) + '</b><span>活跃</span></div></div></div>'
      + '<div class="legend">' + items.slice(0, 8).map(([m, sec]) => (
        '<div class="row" data-matter="' + esc(m) + '">'
        + '<span class="dot" style="background:' + colorFor(m) + '"></span>'
        + '<span class="name" title="' + esc(m) + '">' + esc(m) + '</span>'
        + '<span class="val">' + fmtDur(sec) + '</span></div>'
      )).join('') + '</div>';

    const appTotals = new Map();
    state.segments.forEach((s) => {
      appTotals.set(s.app, (appTotals.get(s.app) || 0) + s.duration_s);
    });
    const apps = Array.from(appTotals.entries()).sort((a, b) => b[1] - a[1]).slice(0, 8);
    const maxApp = Math.max(...apps.map((x) => x[1]), 1);
    $('#appBars').innerHTML = apps.map(([app, sec]) => (
      '<div class="bar-row" data-app="' + esc(app) + '">'
      + '<div class="label">' + appIcon(app) + '<span>' + esc(app) + '</span></div>'
      + '<div class="bar-track"><div class="bar-fill" style="width:'
      + (sec / maxApp * 100).toFixed(1) + '%"></div></div>'
      + '<div class="val">' + fmtDur(sec) + '</div></div>'
    )).join('') || '<div class="hint">暂无数据</div>';

    const hours = new Array(24).fill(0);
    state.segments.forEach((s) => {
      const start = mins(s.start_ts);
      const end = mins(s.end_ts);
      for (let h = Math.floor(start / 60); h <= Math.floor((end - 1) / 60); h += 1) {
        const lo = Math.max(start, h * 60);
        const hi = Math.min(end, h * 60 + 60);
        if (hi > lo) hours[h] += (hi - lo) * 60;
      }
    });
    const maxHour = Math.max(...hours, 1);
    $('#hourBars').innerHTML = hours.map((sec, h) => {
      const height = Math.round(sec / maxHour * 92);
      const hot = h >= 8 && h <= 20 ? ' hot' : '';
      return '<div class="hour" title="' + String(h).padStart(2, '0') + ':00 · '
        + fmtDur(sec) + '"><div class="bar' + hot + '" style="height:' + height + 'px"></div>'
        + '<span class="t">' + String(h).padStart(2, '0') + '</span></div>';
    }).join('');
  }

  // ---------- table ----------
  function renderTable() {
    const rows = $('#rows');
    if (!state.segments.length) {
      rows.innerHTML = '<tr><td colspan="9" class="empty">这个日期还没有数据。先运行 process-today.bat，或在右上角换一个日期。</td></tr>';
      updateBulk();
      return;
    }
    rows.innerHTML = state.segments.map((s) => {
      const selected = state.selected.has(s.id);
      const ctx = (s.page_title || s.title || '').replace(/\s+/g, ' ');
      return '<tr data-id="' + s.id + '" data-seg-id="' + s.id + '" class="'
        + (selected ? 'selected' : '') + '">'
        + '<td class="c"><input type="checkbox" class="pick" '
        + (selected ? 'checked' : '') + '></td>'
        + '<td class="time">' + clock(s.start_ts) + ' – ' + clock(s.end_ts) + '</td>'
        + '<td class="dur">' + fmtDur(s.duration_s) + '</td>'
        + '<td>' + appIcon(s.app) + ' ' + esc(s.app)
        + (state.interrupts.has(s.id) ? ' <span class="badge">⚡ 打断</span>' : '')
        + '</td>'
        + '<td><input class="cell task" value="' + esc(s.final_task || s.auto_task || '') + '"></td>'
        + '<td><input class="cell matter" value="' + esc(matterOf(s)) + '"></td>'
        + '<td class="conf">' + (s.confidence || 0).toFixed(2) + '</td>'
        + '<td class="ctx" title="' + esc(s.evidence || '') + '">' + esc(ctx) + '</td>'
        + '<td><button class="ico-btn open">详情</button></td>'
        + '</tr>';
    }).join('');
    updateBulk();
  }

  async function saveRow(tr) {
    const id = Number(tr.dataset.id);
    const task = tr.querySelector('input.task').value.trim();
    const matter = tr.querySelector('input.matter').value.trim();
    const seg = segById(id);
    if (!seg) return;
    if ((seg.final_task || '') === task && (seg.final_matter || '') === matter) return;
    await applyLabel([id], task, matter, '已保存');
  }

  // ---------- drawer ----------
  async function openDrawer(id) {
    const res = await fetch('/api/detail?segment=' + id);
    const data = await res.json();
    if (!data.segment) { toast('找不到该段'); return; }
    state.drawerId = id;
    state.detail = data;
    renderDrawer();
    $('#drawer').classList.add('open');
  }

  function closeDrawer() {
    $('#drawer').classList.remove('open');
    state.drawerId = null;
    state.detail = null;
  }

  function contentSection(title, inner) {
    return '<div class="section"><h3>' + title + '</h3>' + inner + '</div>';
  }

  function collectDetailEvents(d, s) {
    const start = mins(s.start_ts);
    const end = mins(s.end_ts);
    const evs = [];
    (d.web || []).forEach((w) => {
      if (!w.url) return;
      evs.push({
        t: mins(w.ts), kind: 'web', kindName: '网页', app: w.browser || s.app || '',
        title: w.page_title || '', url: w.url,
        text: w.visible_text || '', selection: w.selection || '',
        key: 'web|' + (w.url || ''),
      });
    });
    (d.focus || []).forEach((f) => {
      evs.push({
        t: mins(f.ts), kind: 'focus', kindName: '焦点', app: f.app || '',
        text: f.text || '', key: 'focus|' + (f.app || '') + '|' + (f.text || ''),
      });
    });
    (d.clipboard || []).forEach((c) => {
      evs.push({
        t: mins(c.ts), kind: 'clip', kindName: '剪切板', app: c.app || '',
        text: c.preview || '', chars: c.chars || 0,
        key: 'clip|' + (c.preview || ''),
      });
    });
    return evs
      .filter((e) => e.t >= start && e.t <= end)
      .filter((e) => String(e.text || e.url || e.title || '').trim())
      .sort((a, b) => a.t - b.t);
  }

  function appTag(app) {
    const meta = appMeta(app);
    return '<span class="app-tag"><span class="dot" style="background:' + meta.c + '"></span>'
      + esc(app) + '</span>';
  }

  function groupDetailEvents(events) {
    const groups = [];
    events.forEach((e) => {
      const last = groups[groups.length - 1];
      if (last && last.key === e.key && e.t - last.lastT <= 3) {
        last.lastT = e.t;
        return;
      }
      groups.push({ ...e, lastT: e.t });
    });
    return groups;
  }

  function vtlRowContent(g) {
    if (!state.showContent) return '<span class="hint">内容已隐藏</span>';
    if (g.kind === 'web') {
      return (g.title ? '<div class="vtl-title">' + esc(g.title) + '</div>' : '')
        + (g.url ? '<a class="link" href="' + esc(g.url) + '" target="_blank" rel="noopener">'
          + esc(g.url) + '</a>' : '')
        + (g.text ? '<div class="vtl-body">' + esc(g.text.slice(0, 220)) + '</div>' : '')
        + (g.selection ? '<div class="vtl-body hint">选中：' + esc(g.selection.slice(0, 120))
          + '</div>' : '');
    }
    if (g.kind === 'clip') {
      return '<div class="vtl-body">' + esc((g.text || '').slice(0, 220)) + '</div>'
        + '<div class="hint">复制 · ' + (g.chars || 0) + ' 字</div>';
    }
    return '<div class="vtl-body">' + esc((g.text || '').slice(0, 220)) + '</div>';
  }

  function vtlHtml(groups, split) {
    let inserted = false;
    let html = '<div class="vtl">';
    groups.forEach((g) => {
      if (!inserted && g.t >= split) {
        html += '<div class="vtl-split"><span>✂ 拆分点 '
          + clock(tsFromMins(state.date, split)) + '</span></div>';
        inserted = true;
      }
      html += '<div class="vtl-item' + (g.t === split ? ' picked' : '')
        + '" data-t="' + g.t + '"><div class="vtl-meta">'
        + clock(tsFromMins(state.date, g.t)) + ' ' + appTag(g.app)
        + ' <span class="kind">' + esc(g.kindName) + '</span></div>'
        + '<div class="vtl-content">' + vtlRowContent(g) + '</div></div>';
    });
    if (!inserted) {
      html += '<div class="vtl-split"><span>✂ 拆分点 '
        + clock(tsFromMins(state.date, split)) + '</span></div>';
    }
    return html + '</div>';
  }

  function renderDrawer() {
    const d = state.detail;
    if (!d || !d.segment) return;
    const s = d.segment;
    const segs = state.segments;
    const start = mins(s.start_ts);
    const end = mins(s.end_ts);
    const idx = segs.findIndex((x) => x.id === s.id);
    const next = idx >= 0 && idx + 1 < segs.length ? segs[idx + 1] : null;
    const interrupt = state.interrupts.get(s.id);
    const groups = groupDetailEvents(collectDetailEvents(d, s));
    const mid = Math.round((start + end) / 2);

    const banner = interrupt ? (
      '<div class="banner">⚡ 可能是「被打断」：<b>' + esc(taskOf(interrupt.prev)) + '</b>（'
      + fmtDur(interrupt.prev.duration_s) + '）→ 本段 <b>' + esc(taskOf(s)) + '</b>（'
      + fmtDur(s.duration_s) + '）→ 之后回到 <b>' + esc(taskOf(interrupt.next)) + '</b>（'
      + fmtDur(interrupt.next.duration_s) + '）<br>'
      + '主线任务会被自动记录成后面新的段；如果这段其实属于同一事项，可沿用前段事项。'
      + '<button class="btn ghost" id="inheritPrev">沿用前段事项</button></div>'
    ) : '';

    const splitSectionHtml = groups.length ? (
      '<div class="section"><h3>拆分小时间线 <span class="hint">'
      + groups.length + ' 个内容断点 · 点一行或拖动右侧把手</span></h3>'
      + '<div class="vtl-wrap"><div id="vtlList"></div>'
      + '<div class="vtl-rail" id="splitRail"><div class="vtl-thumb" id="splitThumb"'
      + ' title="上下拖动设置拆分点"></div></div></div>'
      + '<div class="actions"><button class="btn primary" id="doSplit">在 <span id="splitAt2">'
      + clock(tsFromMins(state.date, mid)) + '</span> 拆分</button>'
      + '<button class="btn ghost" id="splitHalf">对半</button></div></div>'
    ) : '';
    const fallbackSplitHtml = groups.length ? '' : (
      '<div class="actions" style="margin-top:12px">'
      + '<button class="btn ghost" id="dSplitHalf">对半拆分</button></div>'
    );

    $('#drawerTitle').innerHTML = '<div class="seg-title">' + esc(s.title || s.app) + '</div>'
      + '<div class="seg-meta">' + clock(s.start_ts) + '–' + clock(s.end_ts) + ' · '
      + fmtDur(s.duration_s) + ' · ' + esc(s.app) + ' · 置信度 '
      + (s.confidence || 0).toFixed(2) + '</div>';

    $('#drawerBody').innerHTML =
      '<div class="form-row"><input id="dTask" placeholder="任务" value="'
      + esc(s.final_task || s.auto_task || '') + '"><input id="dMatter" placeholder="事项（可用 / 分层）" value="'
      + esc(matterOf(s)) + '"></div>'
      + '<div class="actions"><button id="dSave" class="btn primary">保存标签</button>'
      + '<button id="dParent" class="btn ghost">设置上级</button>'
      + '<button id="dRule" class="btn ghost" title="把这段的标题/域名变成自动归类规则">存为规则</button>'
      + (next ? '<button id="dMerge" class="btn ghost">与下一段合并</button>' : '')
      + '</div>'
      + banner
      + splitSectionHtml
      + fallbackSplitHtml
      + '<details class="section"><summary>原始证据</summary>'
      + '<div class="content-box">' + esc(s.evidence || '') + '</div></details>';

    $('#dSave').onclick = async () => {
      await applyLabel([s.id], $('#dTask').value.trim(), $('#dMatter').value.trim(), '已保存');
    };
    $('#dParent').onclick = () => {
      const current = $('#dMatter').value.trim() || matterOf(s);
      const parts = matterParts(current);
      const tops = Array.from(new Set(state.segments.map((x) => matterTop(matterOf(x)))))
        .filter((top) => top !== '未归类');
      const parent = prompt(
        '上级事项（已有：' + (tops.slice(0, 8).join('、') || '无') + '）\n输入后变成“上级 / ' + esc(matterLeaf(current)) + '”',
        tops[0] || '',
      );
      if (!parent || !parent.trim()) return;
      const rest = parts.length > 1 ? parts.slice(1) : parts;
      const next = [parent.trim()].concat(rest).join(' / ');
      applyLabel([s.id], null, next, '已设置层级：' + next);
    };
    $('#dRule').onclick = async () => {
      const res = await fetch('/api/rules/suggest', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: s.id,
          matter: $('#dMatter').value.trim() || matterOf(s),
          task: $('#dTask').value.trim() || taskOf(s),
        }),
      });
      const out = await res.json();
      if (!out.ok) { toast('无法生成规则'); return; }
      state.pendingRule = out.rule;
      await openSettings('rules');
      toast('已填入规则，确认后点「添加规则」');
    };
    const doSplit = async (value) => {
      const res = await fetch('/api/segment/split', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: s.id, ts: tsFromMins(state.date, value) }),
      });
      const out = await res.json();
      toast(out.ok ? '已拆分为两段' : ('拆分失败：' + (out.error || '')));
      if (out.ok) { closeDrawer(); await load(state.date); }
    };
    if (groups.length) {
      let splitValue = mid;
      const list = $('#vtlList');
      const rail = $('#splitRail');
      const thumb = $('#splitThumb');
      const refreshVtl = () => {
        list.innerHTML = vtlHtml(groups, splitValue);
        const at = $('#splitAt2');
        if (at) at.textContent = clock(tsFromMins(state.date, splitValue));
        const ratio = (splitValue - start) / Math.max(end - start, 1);
        if (thumb) thumb.style.top = (ratio * 100) + '%';
        list.querySelectorAll('.vtl-item[data-t]').forEach((el) => {
          el.classList.toggle('picked', Number(el.dataset.t) === splitValue);
          el.onclick = () => { splitValue = Number(el.dataset.t); refreshVtl(); };
        });
      };
      refreshVtl();
      if (rail) {
        const setFromY = (clientY) => {
          const rect = rail.getBoundingClientRect();
          const ratio = Math.min(1, Math.max(0, (clientY - rect.top) / rect.height));
          splitValue = Math.max(start + 1, Math.min(end - 1,
            Math.round(start + ratio * (end - start))));
          refreshVtl();
        };
        let dragging = false;
        rail.addEventListener('pointerdown', (e) => {
          dragging = true;
          try { rail.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
          setFromY(e.clientY);
          e.preventDefault();
        });
        rail.addEventListener('pointermove', (e) => {
          if (dragging) setFromY(e.clientY);
        });
        rail.addEventListener('pointerup', () => { dragging = false; });
        rail.addEventListener('pointercancel', () => { dragging = false; });
      }
      $('#splitHalf').onclick = () => { splitValue = mid; refreshVtl(); };
      $('#doSplit').onclick = () => doSplit(splitValue);
    } else if ($('#dSplitHalf')) {
      $('#dSplitHalf').onclick = () => doSplit(mid);
    }
    if (interrupt) {
      $('#inheritPrev').onclick = () => {
        applyLabel([s.id], null, matterOf(interrupt.prev), '已沿用前段事项');
      };
    }
    if (next) {
      $('#dMerge').onclick = async () => {
        const res = await fetch('/api/segment/merge', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids: [s.id, next.id] }),
        });
        const out = await res.json();
        toast(out.ok ? '已合并' : ('合并失败：' + (out.error || '')));
        if (out.ok) { closeDrawer(); await load(state.date); }
      };
    }
  }

  // ---------- report modal ----------
  function inlineMd(text) {
    return esc(text)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');
  }

  function mdToHtml(markdown) {
    const lines = String(markdown || '').replace(/\r\n/g, '\n').split('\n');
    const cells = (row) => row.replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
    let html = '';
    let i = 0;
    let listOpen = false;
    const closeList = () => {
      if (listOpen) { html += '</ul>'; listOpen = false; }
    };
    while (i < lines.length) {
      const line = lines[i];
      if (/^\s*$/.test(line)) { closeList(); i += 1; continue; }
      if (/^\|/.test(line) && lines[i + 1] && /^\|[\s:|-]+\|?$/.test(lines[i + 1])) {
        closeList();
        const rows = [];
        while (i < lines.length && /^\|/.test(lines[i])) { rows.push(lines[i]); i += 1; }
        const head = cells(rows[0]);
        const body = rows.slice(2).map(cells);
        html += '<table><thead><tr>' + head.map((c) => '<th>' + inlineMd(c) + '</th>').join('')
          + '</tr></thead><tbody>'
          + body.map((r) => '<tr>' + r.map((c) => '<td>' + inlineMd(c) + '</td>').join('') + '</tr>').join('')
          + '</tbody></table>';
        continue;
      }
      const heading = line.match(/^(#{1,3})\s+(.*)$/);
      if (heading) {
        closeList();
        const level = heading[1].length;
        html += '<h' + level + '>' + inlineMd(heading[2]) + '</h' + level + '>';
        i += 1;
        continue;
      }
      if (/^[-*]\s+/.test(line)) {
        if (!listOpen) { html += '<ul>'; listOpen = true; }
        html += '<li>' + inlineMd(line.replace(/^[-*]\s+/, '')) + '</li>';
        i += 1;
        continue;
      }
      if (/^>\s?/.test(line)) {
        closeList();
        html += '<blockquote>' + inlineMd(line.replace(/^>\s?/, '')) + '</blockquote>';
        i += 1;
        continue;
      }
      closeList();
      html += '<p>' + inlineMd(line) + '</p>';
      i += 1;
    }
    closeList();
    return html;
  }

  function reportChartsHtml(stats, period) {
    if (!stats) return '';
    const active = stats.active_s || 0;
    const kpis = [
      ['活跃时间', fmtDur(active)],
      ['日均', fmtDur(stats.avg_s || 0)],
      ['有数据天数', String(stats.days || 0) + ' 天'],
      ['覆盖工作日', (stats.coverage * 100).toFixed(0) + '%'],
    ];
    const matterTotals = new Map();
    (stats.by_matter || []).forEach((item) => {
      const top = matterTop(item.matter);
      matterTotals.set(top, (matterTotals.get(top) || 0) + (item.seconds || 0));
    });
    const matters = Array.from(matterTotals.entries()).sort((a, b) => b[1] - a[1]);
    const total = matters.reduce((sum, item) => sum + item[1], 0) || 1;
    let acc = 0;
    const stops = matters.map(([matter, sec]) => {
      const from = acc / total * 100;
      acc += sec;
      const to = acc / total * 100;
      return colorFor(matter) + ' ' + from.toFixed(2) + '% ' + to.toFixed(2) + '%';
    });
    const donut = '<div class="report-chart-box"><h4>事项占比</h4>'
      + '<div class="report-donut"><div class="donut" style="background:conic-gradient('
      + (stops.length ? stops.join(',') : '#e2e8f0 0 100%') + ')">'
      + '<div class="center"><div><b>' + fmtDur(active) + '</b><span>活跃</span></div></div></div>'
      + '<div class="report-legend">' + matters.slice(0, 7).map(([matter, sec]) => (
        '<div class="row"><span class="dot" style="background:' + colorFor(matter) + '"></span>'
        + '<span class="name" title="' + esc(matter) + '">' + esc(matter) + '</span>'
        + '<span class="val">' + fmtDur(sec) + '</span></div>'
      )).join('') + '</div></div></div>';

    const apps = (stats.by_app || []).slice(0, 8);
    const maxApp = Math.max(...apps.map((x) => x.seconds), 1);
    const appBars = '<div class="report-chart-box"><h4>应用用时</h4><div class="report-bars">'
      + apps.map((item) => (
        '<div class="bar-row"><div class="label">' + appIcon(item.app)
        + '<span>' + esc(item.app) + '</span></div>'
        + '<div class="bar-track"><div class="bar-fill" style="width:'
        + (item.seconds / maxApp * 100).toFixed(1) + '%"></div></div>'
        + '<div class="val">' + fmtDur(item.seconds) + '</div></div>'
      )).join('') + '</div></div>';

    const series = period === 'year'
      ? (stats.by_month || []).map((x) => ({ label: x.month.slice(5) + '月', v: x.seconds }))
      : (stats.by_day || []).map((x) => ({ label: x.date.slice(5), v: x.seconds }));
    const maxDay = Math.max(...series.map((x) => x.v), 1);
    const dayBars = series.length > 1
      ? '<div class="report-chart-box" style="grid-column:1/-1"><h4>'
        + (period === 'year' ? '按月活跃' : '按天活跃') + '</h4>'
        + '<div class="report-daybars' + (series.length <= 8 ? ' compact' : '') + '">'
        + series.map((item) => (
          '<div class="report-daybar" title="' + esc(item.label + ' · ' + fmtDur(item.v)) + '">'
          + '<div class="bar' + (item.v === maxDay ? ' hot' : '') + '" style="height:'
          + Math.max(2, Math.round(item.v / maxDay * 100)) + '%"></div>'
          + '<span class="t">' + esc(item.label) + '</span></div>'
        )).join('') + '</div></div>'
      : '';

    return '<div class="report-kpis">' + kpis.map(([k, v]) => (
      '<div class="report-kpi"><div class="k">' + k + '</div><div class="v">' + v + '</div></div>'
    )).join('') + '</div>'
      + '<div class="report-charts-grid">' + donut + appBars + dayBars + '</div>';
  }

  async function openReport(period) {
    reportPeriod = period || reportPeriod || 'day';
    const url = '/api/report?date=' + encodeURIComponent(state.date)
      + '&period=' + encodeURIComponent(reportPeriod);
    const res = await fetch(url);
    const data = await res.json();
    reportMarkdown = data.markdown || '';
    const label = { day: '日报', week: '周报', month: '月报', year: '年报' }[reportPeriod] || '报告';
    const range = data.start === data.end ? data.start : data.start + ' ~ ' + data.end;
    $('#modalTitle').textContent = range + ' ' + label;
    $('#reportCharts').innerHTML = reportChartsHtml(data.stats, reportPeriod);
    $('#modalBody').innerHTML = mdToHtml(reportMarkdown);
    document.querySelectorAll('#reportTabs button').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.period === reportPeriod);
    });
    $('#modal').classList.remove('hidden');
    $('#modalBody').scrollTop = 0;
  }

  function downloadReport() {
    const blob = new Blob([reportMarkdown], { type: 'text/markdown;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = state.date + '-' + reportPeriod + '.md';
    link.click();
    URL.revokeObjectURL(link.href);
  }

  // ---------- render all ----------
  function render() {
    renderStats();
    renderDateChips();
    renderStrip();
    renderTimeline();
    renderCharts();
    renderTable();
    renderChips();
    if (state.drawerId) openDrawer(state.drawerId);
  }

  // ---------- events ----------
  function bind() {
    $('#btnLoad').onclick = () => load($('#date').value);
    $('#date').onchange = () => load($('#date').value);
    $('#dateChips').addEventListener('click', (e) => {
      const chip = e.target.closest('.chip[data-date]');
      if (chip) load(chip.dataset.date);
    });
    $('#btnReprocess').onclick = reprocess;
    $('#btnReport').onclick = () => openReport('day');
    $('#reportTabs').addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-period]');
      if (btn) openReport(btn.dataset.period);
    });
    $('#reportDownload').onclick = downloadReport;
    $('#btnSettings').onclick = openSettings;
    $('#settingsClose').onclick = () => $('#settingsModal').classList.add('hidden');
    $('#settingsSave').onclick = saveSettings;
    $('#btnUndo').onclick = undoLast;
    $('#showContent').onchange = (e) => {
      state.showContent = e.target.checked;
      if (state.drawerId) renderDrawer();
    };
    $('#zoomIn').onclick = () => {
      state.zoom = Math.min(6, state.zoom * 1.4);
      $('#zoomLabel').textContent = Math.round(state.zoom * 100) + '%';
      renderTimeline();
    };
    $('#zoomOut').onclick = () => {
      state.zoom = Math.max(1, state.zoom / 1.4);
      $('#zoomLabel').textContent = Math.round(state.zoom * 100) + '%';
      renderTimeline();
    };
    $('#drawerClose').onclick = closeDrawer;
    $('#modalClose').onclick = () => $('#modal').classList.add('hidden');
    $('#settingsTabs').addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-tab]');
      if (btn) setSettingsTab(btn.dataset.tab);
    });
    $('#btnPause').onclick = togglePause;

    const lanes = $('#lanes');
    lanes.addEventListener('pointerdown', onPointerDown);
    lanes.addEventListener('pointermove', onPointerMove);
    lanes.addEventListener('pointerup', onPointerUp);
    lanes.addEventListener('pointercancel', onPointerUp);
    lanes.addEventListener('mouseover', (e) => {
      const block = e.target.closest('.block');
      if (!block || drag) return;
      const seg = segById(Number(block.dataset.id));
      if (seg) {
        hoverSegment(seg.id);
        showTooltip(blockTooltip(seg), e.clientX, e.clientY);
      }
    });
    lanes.addEventListener('mousemove', (e) => {
      if (drag) return;
      const block = e.target.closest('.block');
      if (!block) {
        hoverSegment(null);
        hideTooltip();
        return;
      }
      const seg = segById(Number(block.dataset.id));
      if (seg && $('#tooltip').classList.contains('show')) {
        showTooltip(blockTooltip(seg), e.clientX, e.clientY);
      }
    });
    lanes.addEventListener('mouseleave', () => {
      hoverSegment(null);
      hideTooltip();
    });
    lanes.addEventListener('click', (e) => {
      if (!e.target.closest('.block')) closeDrawer();
    });

    const dayStrip = $('#dayStrip');
    dayStrip.addEventListener('mouseover', (e) => {
      const block = e.target.closest('.strip-block');
      if (!block) return;
      const seg = segById(Number(block.dataset.segId));
      if (seg) {
        hoverSegment(seg.id);
        showTooltip(blockTooltip(seg), e.clientX, e.clientY);
      }
    });
    dayStrip.addEventListener('mousemove', (e) => {
      const block = e.target.closest('.strip-block');
      if (block && $('#tooltip').classList.contains('show')) {
        const seg = segById(Number(block.dataset.segId));
        if (seg) showTooltip(blockTooltip(seg), e.clientX, e.clientY);
      }
    });
    dayStrip.addEventListener('mouseleave', () => {
      hoverSegment(null);
      hideTooltip();
    });
    dayStrip.addEventListener('click', (e) => {
      const block = e.target.closest('.strip-block');
      if (!block) return;
      focusSegment(Number(block.dataset.segId));
    });

    $('#rows').addEventListener('change', (e) => {
      if (e.target.classList.contains('pick')) {
        const tr = e.target.closest('tr');
        const id = Number(tr.dataset.id);
        if (e.target.checked) state.selected.add(id); else state.selected.delete(id);
        tr.classList.toggle('selected', e.target.checked);
        applySelection();
        updateBulk();
        return;
      }
      if (e.target.classList.contains('cell')) {
        const tr = e.target.closest('tr');
        if (tr) saveRow(tr);
      }
    });
    $('#rows').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && e.target.classList.contains('cell')) e.target.blur();
    });
    $('#rows').addEventListener('mouseover', (e) => {
      const tr = e.target.closest('tr[data-seg-id]');
      if (tr) hoverSegment(Number(tr.dataset.segId));
    });
    $('#rows').addEventListener('mouseleave', () => hoverSegment(null));
    $('#rows').addEventListener('click', (e) => {
      const tr = e.target.closest('tr[data-seg-id]');
      if (!tr) return;
      if (e.target.closest('input, button, a, .pick')) return;
      if (e.target.closest('.open')) {
        selectSegment(Number(tr.dataset.segId), false);
        openDrawer(Number(tr.dataset.segId));
      } else {
        focusSegment(Number(tr.dataset.segId));
      }
    });

    const appBars = $('#appBars');
    appBars.addEventListener('mouseover', (e) => {
      const row = e.target.closest('.bar-row[data-app]');
      if (row) highlightWhere((s) => s.app === row.dataset.app, true);
    });
    appBars.addEventListener('mouseleave', () => highlightWhere(() => true, false));
    appBars.addEventListener('click', (e) => {
      const row = e.target.closest('.bar-row[data-app]');
      if (!row) return;
      state.selected.clear();
      state.segments.filter((s) => s.app === row.dataset.app)
        .forEach((s) => state.selected.add(s.id));
      applySelection();
      renderTable();
      updateBulk();
    });

    const donut = $('#donut');
    donut.addEventListener('mouseover', (e) => {
      const row = e.target.closest('.legend .row[data-matter]');
      if (row) highlightWhere((s) => matterTop(matterOf(s)) === row.dataset.matter, true);
    });
    donut.addEventListener('mouseleave', () => highlightWhere(() => true, false));
    donut.addEventListener('click', (e) => {
      const row = e.target.closest('.legend .row[data-matter]');
      if (!row) return;
      state.selected.clear();
      state.segments.filter((s) => matterTop(matterOf(s)) === row.dataset.matter)
        .forEach((s) => state.selected.add(s.id));
      applySelection();
      renderTable();
      updateBulk();
    });
    $('#checkAll').onchange = (e) => {
      state.selected.clear();
      if (e.target.checked) state.segments.forEach((s) => state.selected.add(s.id));
      applySelection();
      renderTable();
    };
    $('#btnBulk').onclick = () => {
      const task = $('#bulkTask').value.trim();
      const matter = $('#bulkMatter').value.trim();
      if (!task && !matter) { toast('先填写任务或事项'); return; }
      applyLabel(Array.from(state.selected), task, matter,
        '已批量更新 ' + state.selected.size + ' 段');
      $('#bulkTask').value = '';
      $('#bulkMatter').value = '';
    };
    $('#matterChips').addEventListener('click', (e) => {
      const chip = e.target.closest('.chip[data-matter]');
      if (!chip) return;
      const matter = chip.dataset.matter;
      const isParent = chip.classList.contains('parent');
      state.selected.clear();
      state.segments.filter((s) => (isParent
        ? matterTop(matterOf(s)) === matter
        : matterOf(s) === matter)).forEach((s) => state.selected.add(s.id));
      applySelection();
      renderTable();
      updateBulk();
    });
    $('#btnNewMatter').onclick = () => {
      const name = prompt('新事项名称（会应用到已选中的时间段；可用 “父级 / 子级” 分层）');
      if (!name) return;
      if (!state.selected.size) { toast('先在时间线或表格里选中时间段'); return; }
      applyLabel(Array.from(state.selected), null, name.trim(), '已标为「' + name.trim() + '」');
    };
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeDrawer();
        $('#modal').classList.add('hidden');
        $('#settingsModal').classList.add('hidden');
      }
    });
    window.addEventListener('resize', () => renderTimeline());
  }

  // ---------- self test (headless verification, ?selftest=drag|chip) ----------
  async function runSelftest(mode) {
    try {
      const block = document.querySelector('.block');
      if (!block) return 'NO_BLOCK';
      const id = Number(block.dataset.id);
      const dayUrl = '/api/day?date=' + encodeURIComponent(state.date);
      const before = (await (await fetch(dayUrl)).json()).segments.find((s) => s.id === id);
      const rect = block.getBoundingClientRect();
      const cx = rect.x + Math.min(rect.width / 2, 6);
      const cy = rect.y + rect.height / 2;
      const ev = (x, y) => ({
        bubbles: true, cancelable: true, clientX: x, clientY: y,
        button: 0, buttons: 1, pointerId: 1, pointerType: 'mouse',
      });
      let chipMatter = '';
      let hitClass = '';
      block.dispatchEvent(new PointerEvent('pointerdown', ev(cx, cy)));
      if (mode === 'chip') {
        const chips = Array.from(document.querySelectorAll('.chip[data-matter]'));
        const chip = chips.find((c) => c.dataset.matter !== (before.final_matter || ''));
        if (!chip) return 'NO_CHIP';
        chipMatter = chip.dataset.matter;
        const cr = chip.getBoundingClientRect();
        block.dispatchEvent(new PointerEvent('pointermove', ev(cr.x + cr.width / 2, cr.y + cr.height / 2)));
        block.dispatchEvent(new PointerEvent('pointerup', ev(cr.x + cr.width / 2, cr.y + cr.height / 2)));
        const hit = document.elementFromPoint(cr.x + cr.width / 2, cr.y + cr.height / 2);
        hitClass = hit ? (hit.className || hit.tagName) : 'null';
      } else {
        for (const dx of [20, 40, 60]) {
          block.dispatchEvent(new PointerEvent('pointermove', ev(cx + dx, cy)));
        }
        block.dispatchEvent(new PointerEvent('pointerup', ev(cx + 60, cy)));
      }
      await new Promise((r) => setTimeout(r, 1800));
      const after = (await (await fetch(dayUrl)).json()).segments.find((s) => s.id === id);
      if (!after) return 'NO_AFTER';
      if (mode === 'chip') {
        return (after.final_matter || '') !== (before.final_matter || '')
          ? 'CHIP_OK:' + chipMatter
          : 'CHIP_FAIL:' + JSON.stringify({
            chip: chipMatter, before: before.final_matter || '', after: after.final_matter || '',
            hit: hitClass,
          });
      }
      return after.start_ts !== before.start_ts ? 'DRAG_OK' : 'DRAG_FAIL';
    } catch (err) {
      return 'ERR:' + err.message;
    }
  }

  // ---------- capture settings / permissions ----------
  const PRESET_INFO = {
    strict: ['严格', '仅应用名与时长；不存标题/URL/正文/剪贴板'],
    metadata: ['仅元数据', '窗口标题 + URL；不存正文、焦点文本、剪贴板'],
    standard: ['标准', '标题 + URL + 网页正文 + 焦点文本 + 剪贴板预览'],
    full: ['完整', '同标准但预览更长、保留更久（个人使用）'],
    enterprise: ['企业受限', '只记窗口标题与时长；不装扩展、不读输入框、不碰剪贴板'],
  };

  function applyDisplayPolicy() {
    const pol = state.policy || {};
    const allow = pol.allow_content_toggle !== false;
    state.showContent = allow ? !!pol.show_content_default : false;
    const box = $('#showContent');
    if (box) {
      box.checked = state.showContent;
      box.disabled = !allow;
      box.parentElement.title = allow ? '' : '当前采集策略不允许显示内容';
    }
    const btn = $('#btnSettings');
    if (btn) btn.textContent = '⚙ 采集设置 · ' + (pol.preset || 'standard');
  }

  function switchRow(id, label, checked, disabled) {
    return '<label class="switch-row"><input type="checkbox" id="' + id + '"'
      + (checked ? ' checked' : '') + (disabled ? ' disabled' : '') + '> '
      + label + '</label>';
  }

  async function openSettings(tab) {
    if (tab) state.settingsTab = tab;
    const res = await fetch('/api/settings');
    const data = await res.json();
    renderSettings(data);
    $('#settingsModal').classList.remove('hidden');
  }

  function setSettingsTab(tab) {
    state.settingsTab = tab;
    document.querySelectorAll('#settingsTabs button').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    const map = { capture: '#settingsBody', rules: '#rulesBody',
                  sync: '#syncBody', billing: '#billingBody' };
    Object.keys(map).forEach((key) => {
      const el = $(map[key]);
      if (el) el.classList.toggle('hidden', key !== tab);
    });
    $('#settingsSave').classList.toggle('hidden', tab !== 'capture');
    if (tab === 'sync') refreshSyncStatus();
  }

  function renderSettings(data) {
    state.settingsData = data;
    renderCapturePanel(data);
    renderRulesPanel(data.rules || []);
    renderSyncPanel((data.effective || {}).sync || {});
    renderBillingPanel(data.matters || []);
    setSettingsTab(state.settingsTab || 'capture');
  }

  function renderCapturePanel(data) {
    const eff = data.effective || {};
    const cap = eff.capture || {};
    const disp = eff.display || {};
    const pri = eff.privacy || {};
    const pol = data.policy || {};
    const locked = !!pol.locked;
    const dis = locked ? ' disabled' : '';
    const presets = data.presets || ['strict', 'metadata', 'standard', 'full'];
    const enabled = (pol.enabled || []).join('、') || '仅应用名与时长';

    $('#settingsBody').innerHTML =
      (locked ? '<div class="locked-note">采集策略已被管理员锁定（config.json 中 '
        + 'policy.locked = true），以下开关不可修改。</div>' : '')
      + '<div class="settings-group"><h4>权限预设</h4>'
      + '<div class="preset-grid">'
      + presets.map((name) => {
        const info = PRESET_INFO[name] || [name, ''];
        return '<button class="preset-card' + (pol.preset === name ? ' active' : '')
          + '" data-preset="' + esc(name) + '"' + dis + '><b>' + esc(info[0])
          + '</b><span>' + esc(info[1]) + '</span></button>';
      }).join('')
      + '</div><div class="hint">当前生效：' + esc(enabled)
      + '。预设点击后立即保存，采集进程重启后生效。</div></div>'
      + '<div class="settings-group"><h4>采集内容</h4>'
      + '<div class="hint">关闭的项目不会写入数据库；已采集的历史数据不受影响。</div>'
      + switchRow('cap-window_titles', '窗口标题', cap.window_titles, locked)
      + switchRow('cap-browser_titles', '浏览器页面标题', cap.browser_titles, locked)
      + switchRow('cap-browser_urls', '浏览器 URL', cap.browser_urls, locked)
      + switchRow('cap-browser_page_text', '网页正文 / 选中文字', cap.browser_page_text, locked)
      + switchRow('cap-focused_text', '焦点输入内容（Excel 单元格、邮件正文等）', cap.focused_text, locked)
      + switchRow('cap-clipboard', '剪贴板内容（只存前 N 字符）', cap.clipboard, locked)
      + '<div class="field-row"><label>剪贴板预览字符数'
      + '<input type="number" id="cap-preview" min="0" max="2000" value="'
      + Number(cap.clipboard_preview_chars || 0) + '"' + dis + '></label>'
      + switchRow('cap-idle', '空闲/离开检测', cap.idle, locked)
      + '</div></div>'
      + '<div class="settings-group"><h4>显示与保留</h4>'
      + switchRow('disp-show_content_default', '默认显示内容（默认关闭）',
        disp.show_content_default, locked)
      + switchRow('disp-allow_content_toggle', '允许用户切换“显示内容”开关',
        disp.allow_content_toggle, locked)
      + '<div class="field-row"><label>原始数据保留天数'
      + '<input type="number" id="priv-retention" min="1" max="3650" value="'
      + Number(pri.retention_days || 30) + '"' + dis + '></label>'
      + '<label>剪贴板记录保留天数'
      + '<input type="number" id="priv-clipdays" min="0" max="3650" value="'
      + Number(pri.store_raw_clipboard_days || 0) + '"' + dis + '></label></div>'
      + '<div class="field-row"><label style="flex-direction:column;align-items:stretch">'
      + '排除的程序（每行一个 app/proc 名）'
      + '<textarea id="priv-apps"' + dis + '>' + esc((pri.excluded_apps || []).join('\n'))
      + '</textarea></label></div>'
      + '<div class="field-row"><label style="flex-direction:column;align-items:stretch">'
      + '排除的网站域名（每行一个，如 bank.example.com）'
      + '<textarea id="priv-domains"' + dis + '>' + esc((pri.excluded_domains || []).join('\n'))
      + '</textarea></label></div></div>';

    document.querySelectorAll('.preset-card').forEach((btn) => {
      btn.onclick = () => applyPreset(btn.dataset.preset);
    });
    $('#settingsSave').disabled = locked;
    $('#settingsNote').textContent = '采集类开关需重启采集进程（run-collector.bat）后生效；显示类刷新页面生效。';
  }

  function splitList(text) {
    return String(text || '').split(/[\n,;]+/).map((x) => x.trim()).filter(Boolean);
  }

  async function applyPreset(name) {
    const res = await fetch('/api/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preset: name }),
    });
    const out = await res.json();
    if (!out.ok) { toast('应用失败：' + (out.error || '')); return; }
    toast('已应用预设「' + name + '」，采集进程重启后生效');
    state.policy = out.policy;
    applyDisplayPolicy();
    renderSettings(out);
  }

  async function saveSettings() {
    const capture = {};
    ['window_titles', 'browser_titles', 'browser_urls', 'browser_page_text',
      'focused_text', 'clipboard', 'idle'].forEach((key) => {
      const el = $('#cap-' + key);
      if (el) capture[key] = el.checked;
    });
    const preview = Number($('#cap-preview').value);
    if (!Number.isNaN(preview)) capture.clipboard_preview_chars = preview;
    const display = {
      show_content_default: $('#disp-show_content_default').checked,
      allow_content_toggle: $('#disp-allow_content_toggle').checked,
    };
    const privacy = {
      retention_days: Number($('#priv-retention').value) || 30,
      store_raw_clipboard_days: Number($('#priv-clipdays').value) || 0,
      excluded_apps: splitList($('#priv-apps').value),
      excluded_domains: splitList($('#priv-domains').value),
    };
    const res = await fetch('/api/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ capture, display, privacy }),
    });
    const out = await res.json();
    if (!out.ok) { toast('保存失败：' + (out.error || '')); return; }
    toast('已保存；采集进程重启后生效');
    state.policy = out.policy;
    applyDisplayPolicy();
    renderSettings(out);
    setTimeout(() => location.reload(), 900);
  }

  // ---------- rules ----------
  function renderRulesPanel(rules) {
    state.rules = rules || [];
    const rows = state.rules.map((rule) => {
      const cond = [
        rule.app ? 'app ' + rule.app : '',
        rule.title ? 'title ' + rule.title : '',
        rule.url_domain ? 'url ' + rule.url_domain : '',
        rule.focused ? 'focus ' + rule.focused : '',
      ].filter(Boolean).join(' · ') || '（无条件，不会命中）';
      return '<tr>'
        + '<td><input type="checkbox" data-rule-toggle="' + rule.id + '"'
        + (rule.enabled ? ' checked' : '') + '></td>'
        + '<td>' + esc(rule.priority) + '</td>'
        + '<td>' + esc(rule.name) + '</td>'
        + '<td class="mono">' + esc(cond) + '</td>'
        + '<td>' + esc(rule.matter || '—') + '</td>'
        + '<td>' + esc(rule.task || '—') + '</td>'
        + '<td>' + Number(rule.matches || 0) + '</td>'
        + '<td><button class="btn tiny" data-rule-del="' + rule.id + '">删</button></td>'
        + '</tr>';
    }).join('');
    const pre = state.pendingRule || {};
    $('#rulesBody').innerHTML =
      '<div class="settings-group"><h4>自动规则</h4>'
      + '<div class="hint">命中即归入事项，优先于自动聚类；你手动打的标签仍然优先。'
      + '条件留空 = 任意，多个条件同时满足才命中。前缀 <code>re:</code> 正则，'
      + '<code>=</code> 精确匹配。</div>'
      + (state.rules.length
        ? '<table class="rule-table"><thead><tr><th>开</th><th>优先级</th><th>名称</th>'
          + '<th>条件</th><th>事项</th><th>任务</th><th>命中</th><th></th></tr></thead>'
          + '<tbody>' + rows + '</tbody></table>'
        : '<div class="hint">还没有规则。比如：<b>app = excel</b> → 事项「客户A / 对账」。</div>')
      + '</div>'
      + '<div class="settings-group"><h4>新增规则</h4>'
      + '<div class="rule-form">'
      + '<label>名称<input id="rule-name" value="' + esc(pre.name || '') + '" placeholder="对账类活动"></label>'
      + '<label>应用<input id="rule-app" value="' + esc(pre.app || '') + '" placeholder="excel / chrome"></label>'
      + '<label>标题<input id="rule-title" value="' + esc(pre.title || '') + '" placeholder="对账"></label>'
      + '<label>网址/域名<input id="rule-domain" value="' + esc(pre.url_domain || '') + '" placeholder="example.com"></label>'
      + '<label>焦点文本<input id="rule-focused" value="' + esc(pre.focused || '') + '" placeholder="可选"></label>'
      + '<label>事项<input id="rule-matter" value="' + esc(pre.matter || '') + '" placeholder="客户A / 对账"></label>'
      + '<label>任务<input id="rule-task" value="' + esc(pre.task || '') + '" placeholder="可留空"></label>'
      + '<label>优先级<input id="rule-priority" type="number" value="'
      + Number(pre.priority || 100) + '"></label>'
      + '</div>'
      + '<div class="actions"><button id="ruleAdd" class="btn primary">添加规则</button>'
      + '<button id="ruleTest" class="btn ghost">测试命中</button>'
      + '<span class="hint" id="ruleResult"></span></div></div>';

    state.pendingRule = null;
    $('#rulesBody').querySelectorAll('[data-rule-del]').forEach((btn) => {
      btn.onclick = () => deleteRule(Number(btn.dataset.ruleDel));
    });
    $('#rulesBody').querySelectorAll('[data-rule-toggle]').forEach((box) => {
      box.onchange = () => saveRule({
        id: Number(box.dataset.ruleToggle), enabled: box.checked,
      }, true);
    });
    $('#ruleAdd').onclick = () => {
      const rule = ruleFromForm();
      if (!rule.app && !rule.title && !rule.url_domain && !rule.focused) {
        toast('至少填一个匹配条件'); return;
      }
      saveRule(rule, false);
    };
    $('#ruleTest').onclick = async () => {
      const res = await fetch('/api/rules/preview', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...ruleFromForm(), date: state.date }),
      });
      const out = await res.json();
      if (!out.ok) { toast('预览失败'); return; }
      $('#ruleResult').textContent = '命中 ' + out.count + ' 段 / '
        + fmtDur(out.seconds || 0) + '（' + state.date + '）';
    };
  }

  function ruleFromForm() {
    return {
      name: ($('#rule-name') || {}).value || '',
      app: (($('#rule-app') || {}).value || '').trim(),
      title: (($('#rule-title') || {}).value || '').trim(),
      url_domain: (($('#rule-domain') || {}).value || '').trim(),
      focused: (($('#rule-focused') || {}).value || '').trim(),
      matter: (($('#rule-matter') || {}).value || '').trim(),
      task: (($('#rule-task') || {}).value || '').trim(),
      priority: Number((($('#rule-priority') || {}).value || 100)) || 100,
      enabled: true,
    };
  }

  async function saveRule(rule, quiet) {
    const res = await fetch('/api/rules', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(rule),
    });
    const out = await res.json();
    if (!out.ok) { toast('保存规则失败：' + (out.error || '')); return; }
    renderRulesPanel(out.rules || []);
    if (!quiet) {
      toast('规则已保存，下次「重新处理」生效');
      if (state.settingsData) state.settingsData.rules = out.rules;
    }
  }

  async function deleteRule(id) {
    if (!id) return;
    if (!confirm('删除这条规则？已归类的时间线不会改变。')) return;
    const res = await fetch('/api/rules/delete', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }),
    });
    const out = await res.json();
    if (out.ok) renderRulesPanel(out.rules || []);
  }

  // ---------- sync ----------
  const SYNC_CHANNELS = [
    ['times', '时间段与应用名（必需）', '任何同步的基础，不能关闭'],
    ['matters', '事项 / 任务名称与费率', '关掉后对方只看到时间，不知道你在做什么'],
    ['window_titles', '窗口标题', '文件名的客户/项目名可能泄露给另一台设备'],
    ['urls', '网页地址与页面标题', '内网地址、搜索关键词'],
    ['page_text', '网页正文', '内容最敏感的一档'],
    ['focused_text', '焦点输入框文本', 'Excel 单元格、邮件正文'],
    ['clipboard', '剪贴板预览', '前 240 字'],
  ];

  function renderSyncPanel(sync) {
    const channels = sync.channels || {};
    const rows = SYNC_CHANNELS.map(([key, label, hint]) => {
      const locked = key === 'times';
      return '<label class="sync-channel"><input type="checkbox" id="sync-ch-' + key + '"'
        + (channels[key] ? ' checked' : '') + (locked ? ' disabled' : '') + '>'
        + '<span><b>' + label + '</b><i>' + hint + '</i></span></label>';
    }).join('');
    $('#syncBody').innerHTML =
      '<div class="settings-group"><h4>多端同步（默认关闭）</h4>'
      + '<div class="hint">同步包写到你自己选的文件夹（OneDrive / 坚果云 / U 盘），'
      + '不经过任何服务器，也不联网。只有下面勾选的通道会离开本机；'
      + '导入的数据单独存放（<code>foreign_days</code>），不会混进本机时间线。</div>'
      + switchRow('sync-enabled', '启用多端同步', !!sync.enabled, false)
      + '<div class="field-row"><label style="flex-direction:column;align-items:stretch">'
      + '同步文件夹（绝对路径）'
      + '<input id="sync-folder" value="' + esc(sync.folder || '')
      + '" placeholder="D:\\OneDrive\\worktime-sync 或 \\\\nas\\share\\worktime"></label></div>'
      + switchRow('sync-encrypt', '用口令加密同步包（推荐）', sync.encrypt !== false, false)
      + '<div class="field-row"><label>口令（不写进配置，仅本次使用）'
      + '<input id="sync-passphrase" type="password" autocomplete="off"'
      + ' placeholder="留空 = 用环境变量 WT_SYNC_PASSPHRASE"></label></div>'
      + '<div class="settings-group"><h4>允许离开本机的数据</h4>' + rows + '</div>'
      + '<div class="actions"><button id="syncSave" class="btn primary">保存同步设置</button>'
      + '<button id="syncPreview" class="btn ghost">预览会同步什么</button>'
      + '<button id="syncPush" class="btn ghost">导出到文件夹</button>'
      + '<button id="syncPull" class="btn ghost">从文件夹导入</button></div>'
      + '<div id="syncStatus" class="hint"></div>'
      + '<div id="syncPreviewOut" class="sync-preview"></div></div>';

    $('#syncSave').onclick = saveSyncSettings;
    $('#syncPreview').onclick = previewSync;
    $('#syncPush').onclick = () => syncAction('push');
    $('#syncPull').onclick = () => syncAction('pull');
  }

  function syncForm() {
    const channels = {};
    SYNC_CHANNELS.forEach(([key]) => {
      const el = $('#sync-ch-' + key);
      if (el) channels[key] = el.checked;
    });
    channels.times = true;
    return {
      enabled: $('#sync-enabled').checked,
      folder: $('#sync-folder').value.trim(),
      encrypt: $('#sync-encrypt').checked,
      channels,
      passphrase: ($('#sync-passphrase') || {}).value || '',
    };
  }

  async function saveSyncSettings() {
    const form = syncForm();
    const res = await fetch('/api/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sync: {
        enabled: form.enabled, folder: form.folder,
        encrypt: form.encrypt, channels: form.channels,
      } }),
    });
    const out = await res.json();
    if (!out.ok) { toast('保存失败：' + (out.error || '')); return; }
    toast(form.enabled ? '已开启同步（只同步勾选的通道）' : '已关闭同步');
    await refreshSyncStatus();
  }

  async function refreshSyncStatus() {
    if (!state.settingsTab || state.settingsTab !== 'sync') return;
    try {
      const res = await fetch('/api/sync/status');
      const data = await res.json();
      const el = $('#syncStatus');
      if (el) {
        el.innerHTML = '设备：' + esc(data.device.name || data.device.id || '—')
          + ' · 本机近 7 天 ' + (data.local_days || 0) + ' 天'
          + ' · 已导入 ' + (data.foreign_days || 0) + ' 天'
          + (data.foreign_range && data.foreign_range.devices.length
            ? '（' + esc(data.foreign_range.devices.join('、')) + '）' : '');
      }
    } catch (e) { /* ignore */ }
  }

  async function previewSync() {
    const res = await fetch('/api/sync/preview?days=7');
    const data = await res.json();
    const channels = data.channels || {};
    const rows = SYNC_CHANNELS.map(([key, label]) =>
      '<div class="pv-row' + (channels[key] ? ' on' : '') + '">'
      + '<span>' + (channels[key] ? '✓' : '·') + '</span>'
      + '<span>' + label + '</span></div>').join('');
    const samples = (data.samples || []).map((s) =>
      '<div class="pv-sample">' + esc(s.day) + ' ' + esc(s.start) + ' · '
      + esc(s.app) + ' · ' + esc(s.title || '') + ' · ' + esc(s.matter || '') + '</div>'
    ).join('');
    $('#syncPreviewOut').innerHTML =
      '<div class="pv-head">最近 7 天将导出：<b>' + data.segments + '</b> 段 / '
      + data.days + ' 天，约 ' + Math.ceil((data.bytes || 0) / 1024) + ' KB</div>'
      + rows + (samples ? '<div class="pv-head">样例</div>' + samples : '');
  }

  async function syncAction(action) {
    const form = syncForm();
    const res = await fetch('/api/sync/' + action, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ days: 7, passphrase: form.passphrase }),
    });
    const out = await res.json();
    if (!out.ok) { toast('失败：' + (out.error || '未知错误')); return; }
    if (action === 'push') {
      toast('已导出到同步文件夹：' + (out.path || ''));
    } else {
      toast('已导入 ' + (out.days || 0) + ' 天 / ' + (out.files || 0) + ' 个文件');
    }
    await refreshSyncStatus();
  }

  // ---------- billing ----------
  function renderBillingPanel(matters) {
    state.matters = matters || [];
    const rows = state.matters.map((matter, idx) =>
      '<tr>'
      + '<td>' + esc(matter.path) + '</td>'
      + '<td><input type="number" min="0" step="10" class="rate-input" '
      + 'data-rate-idx="' + idx + '" value="' + Number(matter.rate || 0) + '"></td>'
      + '<td><input class="cur-input" data-cur-idx="' + idx + '" value="'
      + esc(matter.currency || 'CNY') + '" size="4"></td>'
      + '<td><input type="checkbox" data-bill-idx="' + idx + '"'
      + (matter.billable ? ' checked' : '') + '></td>'
      + '</tr>').join('');
    $('#billingBody').innerHTML =
      '<div class="settings-group"><h4>事项费率</h4>'
      + '<div class="hint">路径用 <code>客户 / 项目 / 子任务</code> 分层，父级费率自动继承。'
      + '只在本机保存；不会随同步默认外发（同步里「事项 / 费率」那一项可关）。</div>'
      + (state.matters.length
        ? '<table class="rule-table"><thead><tr><th>事项</th><th>每小时单价</th>'
          + '<th>币种</th><th>计费</th></tr></thead><tbody>' + rows + '</tbody></table>'
        : '<div class="hint">还没有事项费率。先在上方时间线里给事项打标签，'
          + '再回来加单价。</div>')
      + '<div class="rule-form" style="margin-top:10px">'
      + '<label>新增事项<input id="rate-new-path" placeholder="客户A / 项目B"></label>'
      + '<label>单价<input id="rate-new-rate" type="number" min="0" value="0"></label>'
      + '<label>币种<input id="rate-new-cur" value="CNY"></label>'
      + '</div>'
      + '<div class="actions"><button id="ratesSave" class="btn primary">保存费率</button>'
      + '<button id="invoicePreview" class="btn ghost">查看本月费用</button></div>'
      + '<div id="invoiceOut" class="sync-preview"></div></div>';

    $('#ratesSave').onclick = saveRates;
    $('#invoicePreview').onclick = previewInvoice;
  }

  async function saveRates() {
    const rows = Array.from($('#billingBody').querySelectorAll('[data-rate-idx]'));
    for (const input of rows) {
      const idx = Number(input.dataset.rateIdx);
      const matter = state.matters[idx];
      if (!matter) continue;
      const rate = Number(input.value) || 0;
      const cur = ($('#billingBody').querySelector('[data-cur-idx="' + idx + '"]') || {}).value;
      const bill = ($('#billingBody').querySelector('[data-bill-idx="' + idx + '"]') || {}).checked;
      await fetch('/api/matters', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: matter.path, rate, currency: cur || 'CNY',
                               billable: bill ? 1 : 0 }),
      });
    }
    const newPath = ($('#rate-new-path') || {}).value;
    if (newPath && newPath.trim()) {
      await fetch('/api/matters', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: newPath.trim(),
                               rate: Number(($('#rate-new-rate') || {}).value) || 0,
                               currency: (($('#rate-new-cur') || {}).value || 'CNY') }),
      });
    }
    toast('费率已保存');
    const res = await fetch('/api/settings');
    const data = await res.json();
    renderBillingPanel(data.matters || []);
  }

  async function previewInvoice() {
    const res = await fetch('/api/invoice?date=' + encodeURIComponent(state.date)
      + '&period=month');
    const data = await res.json();
    if (!data.rows || !data.rows.length) {
      $('#invoiceOut').innerHTML = '<div class="hint">本月还没有计费数据。</div>';
      return;
    }
    const rows = data.rows.map((row) =>
      '<tr><td>' + esc(row.matter) + '</td><td>'
      + (row.billable ? row.hours.toFixed(2) : '—') + '</td><td>'
      + (row.billable ? row.amount.toFixed(2) : '—') + '</td><td>'
      + (row.billable ? '计费' : '不计费') + '</td></tr>').join('');
    $('#invoiceOut').innerHTML =
      '<div class="pv-head">' + esc(data.start) + ' ~ ' + esc(data.end)
      + '：<b>' + data.total_hours.toFixed(2) + '</b> 小时 / <b>'
      + data.total_amount.toFixed(2) + '</b> ' + esc(data.currency) + '</div>'
      + '<table class="rule-table"><thead><tr><th>事项</th><th>工时(h)</th>'
      + '<th>金额</th><th>状态</th></tr></thead><tbody>' + rows + '</tbody></table>';
  }

  // ---------- live status ----------
  async function pollLive() {
    try {
      const res = await fetch('/api/live');
      state.live = await res.json();
    } catch (e) {
      state.live = null;
    }
    renderLive();
  }

  function renderLive() {
    const live = state.live || {};
    const pill = $('#livePill');
    const text = $('#liveText');
    if (!pill || !text) return;
    const paused = !!live.paused;
    pill.classList.toggle('ok', !!live.alive && !paused);
    pill.classList.toggle('warn', paused);
    pill.classList.toggle('bad', !live.alive && !paused);
    if (paused) {
      text.textContent = '采集已暂停';
    } else if (live.alive) {
      text.textContent = '采集中 · ' + (live.age_s != null ? live.age_s + 's 前' : '');
    } else {
      text.textContent = '采集器未运行';
    }
    const btn = $('#btnPause');
    if (btn) btn.textContent = paused ? '恢复采集' : '暂停采集';
  }

  async function togglePause() {
    const paused = !(state.live && state.live.paused);
    await fetch('/api/collector/pause', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paused }),
    });
    toast(paused ? '已暂停采集（正在跑的时间段不会丢）' : '已恢复采集');
    await pollLive();
  }

  // ---------- boot ----------
  (async function boot() {
    const params = new URLSearchParams(location.search);
    if (params.get('content') === '1') {
      state.showContent = true;
      $('#showContent').checked = true;
    }
    $('#date').value = localToday();
    bind();
    await load(params.get('date') || '');
    await pollLive();
    setInterval(pollLive, 10000);
    // Live (today) view: refresh the timeline while the collector is running.
    setInterval(() => {
      if (!state.live || !state.live.alive || state.live.paused) return;
      if (state.date !== localToday()) return;
      if (!$('#settingsModal').classList.contains('hidden')) return;
      if (drag) return;
      load(state.date);
    }, 60000);
    const openId = Number(params.get('open') || 0);
    if (openId) await openDrawer(openId);
    if (params.get('settings') === '1') await openSettings();
    if (params.get('report')) await openReport(params.get('report'));
    const selftest = params.get('selftest');
    if (selftest === 'link') {
      const strip = document.querySelector('.strip-block');
      if (!strip) {
        document.title = 'SELFTEST:NO_STRIP';
        return;
      }
      strip.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
      const hovered = document.querySelectorAll('.hl').length;
      strip.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      await new Promise((r) => setTimeout(r, 700));
      const drawerOpen = document.querySelector('#drawer').classList.contains('open');
      const selected = document.querySelectorAll('.block.selected').length;
      const bar = document.querySelector('.bar-row[data-app]');
      let chartHl = 0;
      if (bar) {
        bar.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
        chartHl = document.querySelectorAll('.hl').length;
      }
      document.title = 'SELFTEST:'
        + (drawerOpen && selected && hovered && chartHl ? 'LINK_OK' : 'LINK_FAIL')
        + ':' + hovered + '/' + selected + '/' + chartHl;
      return;
    }
    if (selftest === 'toggle') {
      const block = document.querySelector('.block');
      if (!block) {
        document.title = 'SELFTEST:NO_BLOCK';
        return;
      }
      const rect = block.getBoundingClientRect();
      const opts = {
        bubbles: true, cancelable: true,
        clientX: rect.x + Math.min(rect.width / 2, 10), clientY: rect.y + rect.height / 2,
        button: 0, buttons: 1, pointerId: 1, pointerType: 'mouse',
      };
      block.dispatchEvent(new PointerEvent('pointerdown', opts));
      block.dispatchEvent(new PointerEvent('pointerup', opts));
      await new Promise((r) => setTimeout(r, 500));
      const open1 = document.querySelector('#drawer').classList.contains('open');
      block.dispatchEvent(new PointerEvent('pointerdown', opts));
      block.dispatchEvent(new PointerEvent('pointerup', opts));
      await new Promise((r) => setTimeout(r, 500));
      const open2 = document.querySelector('#drawer').classList.contains('open');
      document.title = 'SELFTEST:' + (open1 && !open2 ? 'TOGGLE_OK' : 'TOGGLE_FAIL');
      return;
    }
    if (selftest === 'rail') {
      const rail = document.querySelector('#splitRail');
      const label = document.querySelector('#splitAt2');
      if (!rail || !label) {
        document.title = 'SELFTEST:NO_RAIL';
        return;
      }
      const before = label.textContent;
      const rect = rail.getBoundingClientRect();
      const ev = (y) => ({
        bubbles: true, cancelable: true,
        clientX: rect.x + rect.width / 2, clientY: y,
        button: 0, buttons: 1, pointerId: 1, pointerType: 'mouse',
      });
      rail.dispatchEvent(new PointerEvent('pointerdown', ev(rect.top + rect.height * 0.2)));
      rail.dispatchEvent(new PointerEvent('pointermove', ev(rect.top + rect.height * 0.8)));
      rail.dispatchEvent(new PointerEvent('pointerup', ev(rect.top + rect.height * 0.8)));
      await new Promise((r) => setTimeout(r, 120));
      document.title = 'SELFTEST:'
        + (label.textContent !== before ? 'RAIL_DRAG_OK' : 'RAIL_DRAG_FAIL');
      return;
    }
    if (selftest) {
      const result = await runSelftest(selftest);
      document.title = 'SELFTEST:' + result;
      const tag = document.createElement('div');
      tag.id = 'selftest-result';
      tag.textContent = result;
      tag.style.cssText = 'position:fixed;left:8px;bottom:8px;z-index:999;background:#fff;padding:4px 8px;border:1px solid #ccc;font-size:11px';
      document.body.appendChild(tag);
    }
  }()).catch((err) => {
    document.body.insertAdjacentHTML('beforeend',
      '<pre style="color:#b91c1c;padding:20px">' + esc(String(err)) + '</pre>');
  });
})();
