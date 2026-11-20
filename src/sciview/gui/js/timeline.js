// Timeline: one row per object (top-most first), clips for visibility, gold diamonds for keyframes.
import { S, on, emit, commit, objById, schemaOf, span, keyTimes, duration, fps, breakCoalesce } from './state.js';
import { el, drag, clamp } from './ui.js';
import { icon } from './icons.js';

const body = document.getElementById('tlBody');
const rowsEl = document.getElementById('tlRows');
const ruler = document.getElementById('tlRuler');
const rulerCanvas = document.getElementById('rulerCanvas');
const playhead = document.getElementById('tlPlayhead');
const zoomEl = document.getElementById('tlZoom');
const PAD = 14;
let pps = 60;
let fitted = false;
let autoFit = true; // until the user zooms by hand

const labelW = () => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--lib-w')) || 236;
const xOf = (t) => PAD + t * pps;
const catClass = { '3D scene': 'cat-3d', Text: 'cat-text', Charts: 'cat-charts', 'Shapes & media': 'cat-shapes' };

function snap(t, { toPlayhead = true } = {}) {
  const f = fps();
  let s = Math.round(t * f) / f;
  if (toPlayhead && Math.abs(s - S.time) * pps < 7) s = S.time;
  if (Math.abs(s) * pps < 6) s = 0;
  if (Math.abs(s - duration()) * pps < 6) s = duration();
  return s;
}

export function fit() {
  const avail = body.clientWidth - labelW() - PAD * 2 - 8;
  if (avail > 50) {
    pps = clamp(avail / duration(), 4, 400);
    zoomEl.value = Math.min(400, Math.max(10, pps));
    fitted = true;
    renderTimeline();
  }
}

export function renderTimeline() {
  if (!S.project) return;
  if (!fitted) { fitted = true; requestAnimationFrame(fit); }
  const width = PAD * 2 + duration() * pps;
  rowsEl.innerHTML = '';
  rowsEl.style.width = `${labelW() + width}px`;
  rowsEl.append(makeRow(S.project.camera, width));
  const objs = [...S.project.objects].reverse();
  for (const o of objs) rowsEl.append(makeRow(o, width));
  if (!objs.length) rowsEl.append(el('div', { class: 'tl-empty' }, 'Objects you add appear here. Drag clips to change when they appear.'));
  placePlayhead();
  drawRuler();
}

function makeRow(o, width) {
  const sc = schemaOf(o);
  const isCam = o.type === 'camera';
  const row = el('div', { class: `tl-row ${S.selected === o.id ? 'sel' : ''} ${o.visible === false ? 'hidden-obj' : ''}`, dataset: { id: o.id } });
  const grip = isCam ? el('span', { style: { width: '8px' } }) : el('span', { class: 'grip', title: 'Drag to change the drawing order' });
  const eye = isCam ? null : el('button', {
    class: `icon-btn small eye ${o.visible === false ? 'off' : ''}`, title: o.visible === false ? 'Show' : 'Hide',
    'aria-label': o.visible === false ? `Show ${o.name}` : `Hide ${o.name}`, html: icon(o.visible === false ? 'eyeoff' : 'eye'),
  });
  const label = el('div', { class: 'tl-label', title: `${o.name} (${sc ? sc.label : o.type})` },
    grip, el('span', { class: 'ic', html: icon(sc ? sc.icon : 'square') }), el('span', { class: 'nm' }, o.name || o.id), eye);
  label.addEventListener('click', (e) => { if (!e.target.closest('.eye')) emit('select', o.id); });
  if (eye) eye.addEventListener('click', () => commit(() => { const x = objById(o.id); x.visible = x.visible === false; }, { source: 'timeline' }));
  if (!isCam) grip.addEventListener('pointerdown', (e) => reorderDrag(e, o.id, row));

  const track = el('div', { class: 'tl-track', style: { width: `${width}px` } });
  track.addEventListener('pointerdown', (e) => {
    if (e.target !== track) return;
    emit('select', o.id);
    scrubFrom(e);
  });
  if (!isCam) {
    const [s, e] = span(o);
    const clip = el('div', { class: `clip ${catClass[sc ? sc.category : ''] || ''}`, style: { left: `${xOf(s)}px`, width: `${Math.max(4, (e - s) * pps)}px` } });
    const ein = o.enter && o.enter.effect !== 'none' ? o.enter.duration : 0;
    const eout = o.end != null && o.exit && o.exit.effect !== 'none' ? o.exit.duration : 0;
    if (ein > 0) clip.append(el('div', { class: 'ramp in', style: { width: `${Math.min(ein, e - s) * pps}px` } }));
    if (eout > 0) clip.append(el('div', { class: 'ramp out', style: { width: `${Math.min(eout, e - s) * pps}px` } }));
    const text = o.type === 'caption' || o.type === 'title' || o.type === 'text' ? (o.props.text ?? '') : '';
    clip.append(el('div', { class: 'txt' }, String(text).replace(/\n/g, ' ')));
    const l = el('div', { class: 'edge l', title: 'Drag to change when it appears' });
    const r = el('div', { class: 'edge r', title: 'Drag to change when it disappears' });
    clip.append(l, r);
    clip.addEventListener('pointerdown', (ev) => clipDrag(ev, o.id, ev.target === l ? 'start' : ev.target === r ? 'end' : 'move'));
    track.append(clip);
  }
  for (const t of keyTimes(o)) {
    const sel = S.selKey && S.selKey.id === o.id && Math.abs(S.selKey.t - t) < 1e-6;
    const d = el('div', { class: `diamond-k ${sel ? 'sel' : ''}`, style: { left: `${xOf(t)}px` }, title: `Keyframe at ${t.toFixed(2)} s` });
    d.addEventListener('pointerdown', (ev) => keyDrag(ev, o.id, t));
    track.append(d);
  }
  row.append(label, track);
  return row;
}

// ------------------------------------------------------------------ interactions
function clipDrag(ev, id, mode) {
  ev.stopPropagation();
  emit('select', id);
  const o0 = JSON.parse(JSON.stringify(objById(id)));
  const [s0, e0] = span(o0);
  const tag = `clip-${id}-${Date.now()}`;
  breakCoalesce();
  drag(ev, (dx) => {
    const dt = dx / pps;
    commit(() => {
      const o = objById(id);
      if (mode === 'move') {
        const len = e0 - s0;
        let ns = snap(s0 + dt);
        ns = clamp(ns, 0, Math.max(0, duration() - 0.05));
        const shift = ns - s0;
        o.start = ns;
        o.end = o0.end == null ? null : Math.min(duration(), ns + len);
        o.keys = JSON.parse(JSON.stringify(o0.keys || {}));
        for (const ks of Object.values(o.keys)) for (const k of ks) k.t = Math.round((k.t + shift) * fps()) / fps();
      } else if (mode === 'start') {
        o.start = clamp(snap(s0 + dt), 0, e0 - 0.05);
      } else {
        const ne = clamp(snap(e0 + dt), s0 + 0.05, duration());
        o.end = Math.abs(ne - duration()) < 1e-6 && o0.end == null ? null : ne;
      }
    }, { coalesce: tag, source: 'timeline' });
  });
}

function keyDrag(ev, id, t0) {
  ev.stopPropagation();
  emit('select', id);
  S.selKey = { id, t: t0 };
  const o0 = JSON.parse(JSON.stringify(objById(id)));
  const tag = `key-${id}-${Date.now()}`;
  breakCoalesce();
  drag(ev, (dx) => {
    const nt = clamp(snap(t0 + dx / pps), 0, duration());
    commit(() => {
      const o = objById(id);
      o.keys = JSON.parse(JSON.stringify(o0.keys));
      for (const ks of Object.values(o.keys)) {
        for (const k of ks) if (Math.abs(k.t - t0) < 1e-6) k.t = nt;
        // a moved key replaces any key already at the new time
        const seen = new Map();
        for (const k of ks) seen.set(Math.round(k.t * 1e6), k);
        ks.splice(0, ks.length, ...[...seen.values()].sort((a, b) => a.t - b.t));
      }
    }, { coalesce: tag, source: 'timeline' });
    S.selKey = { id, t: nt };
  }, (moved) => {
    if (!moved) emit('seek', t0);
    renderTimeline();
  });
}

function reorderDrag(ev, id, rowEl) {
  ev.stopPropagation();
  ev.preventDefault();
  rowEl.classList.add('dragging');
  let target = null;
  drag(ev, (_dx, _dy, e) => {
    rowsEl.querySelectorAll('.drop-above, .drop-below').forEach((r) => r.classList.remove('drop-above', 'drop-below'));
    const rows = [...rowsEl.querySelectorAll('.tl-row')].filter((r) => r.dataset.id !== 'camera');
    target = null;
    for (const r of rows) {
      const b = r.getBoundingClientRect();
      if (e.clientY >= b.top && e.clientY < b.bottom) {
        const above = e.clientY < b.top + b.height / 2;
        r.classList.add(above ? 'drop-above' : 'drop-below');
        target = { id: r.dataset.id, above };
      }
    }
  }, () => {
    rowEl.classList.remove('dragging');
    if (!target || target.id === id) { renderTimeline(); return; }
    commit((p) => {
      const i = p.objects.findIndex((o) => o.id === id);
      const [o] = p.objects.splice(i, 1);
      let j = p.objects.findIndex((x) => x.id === target.id);
      // rows are shown top-most first, i.e. reversed list order
      if (target.above) j += 1;
      p.objects.splice(j, 0, o);
    }, { source: 'reorder' });
  });
}

function timeFromClient(clientX) {
  const r = body.getBoundingClientRect();
  const x = clientX - r.left - labelW() + body.scrollLeft - PAD;
  return clamp(x / pps, 0, duration());
}

function scrubFrom(ev) {
  const go = (cx) => emit('seek', snap(timeFromClient(cx), { toPlayhead: false }));
  go(ev.clientX);
  drag(ev, (_dx, _dy, e) => go(e.clientX));
}

ruler.addEventListener('pointerdown', (ev) => {
  const go = (cx) => {
    const r = ruler.getBoundingClientRect();
    emit('seek', snap(clamp((cx - r.left + body.scrollLeft - PAD) / pps, 0, duration()), { toPlayhead: false }));
  };
  go(ev.clientX);
  drag(ev, (_dx, _dy, e) => go(e.clientX));
});

// ------------------------------------------------------------------ ruler and playhead
export function placePlayhead() {
  if (!S.project) return;
  playhead.style.left = `${labelW() + xOf(S.time)}px`;
  playhead.style.height = `${Math.max(body.clientHeight, rowsEl.offsetHeight)}px`;
  drawRuler();
}

function drawRuler() {
  const dpr = window.devicePixelRatio || 1;
  const w = ruler.clientWidth, h = ruler.clientHeight;
  if (!w || !h) return;
  rulerCanvas.width = w * dpr;
  rulerCanvas.height = h * dpr;
  const g = rulerCanvas.getContext('2d');
  g.scale(dpr, dpr);
  g.clearRect(0, 0, w, h);
  const off = body.scrollLeft;
  const steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120];
  const major = steps.find((s) => s * pps >= 64) || 120;
  const minor = major / (major >= 1 && major % 5 === 0 ? 5 : 2);
  const dur = duration();
  g.fillStyle = 'rgba(255,255,255,.035)';
  g.fillRect(PAD - off, 0, dur * pps, h);
  g.strokeStyle = '#2b3a58';
  g.fillStyle = '#8f9cb3';
  g.font = '11px Inter, system-ui, sans-serif';
  g.textBaseline = 'middle';
  const t0 = Math.max(0, Math.floor((off - PAD) / pps / minor) * minor);
  for (let t = t0; t <= dur + 1e-9; t += minor) {
    const x = Math.round(PAD + t * pps - off) + 0.5;
    if (x > w + 2) break;
    const isMajor = Math.abs(t / major - Math.round(t / major)) < 1e-6;
    g.beginPath();
    g.moveTo(x, isMajor ? h - 11 : h - 6);
    g.lineTo(x, h);
    g.stroke();
    if (isMajor) g.fillText(`${+t.toFixed(2)}s`, x + 4, h / 2 - 3);
  }
  const px = PAD + S.time * pps - off;
  g.fillStyle = '#ffcf4a';
  g.beginPath();
  g.moveTo(px - 6, 0);
  g.lineTo(px + 6, 0);
  g.lineTo(px + 6, h - 9);
  g.lineTo(px, h);
  g.lineTo(px - 6, h - 9);
  g.closePath();
  g.fill();
}

body.addEventListener('scroll', drawRuler);
zoomEl.addEventListener('input', () => {
  autoFit = false;
  const center = timeFromClient(body.getBoundingClientRect().left + labelW() + (body.clientWidth - labelW()) / 2);
  pps = Number(zoomEl.value);
  renderTimeline();
  body.scrollLeft = Math.max(0, xOf(center) - (body.clientWidth - labelW()) / 2);
});
document.getElementById('tlFit').addEventListener('click', () => { autoFit = true; fit(); });
body.addEventListener('wheel', (e) => {
  if (!(e.ctrlKey || e.metaKey)) return;
  e.preventDefault();
  autoFit = false;
  const t = timeFromClient(e.clientX);
  pps = clamp(pps * (e.deltaY < 0 ? 1.15 : 1 / 1.15), 4, 400);
  zoomEl.value = Math.min(400, Math.max(10, pps));
  renderTimeline();
  body.scrollLeft = Math.max(0, xOf(t) - (e.clientX - body.getBoundingClientRect().left - labelW()));
}, { passive: false });
let resizeTimer = null;
window.addEventListener('resize', () => {
  placePlayhead();
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (autoFit) fit(); }, 120);
});

export function ensurePlayheadVisible() {
  const x = xOf(S.time);
  const vis0 = body.scrollLeft, vis1 = body.scrollLeft + body.clientWidth - labelW();
  if (x < vis0 + 10 || x > vis1 - 10) body.scrollLeft = Math.max(0, x - (body.clientWidth - labelW()) * 0.2);
}

export function deleteSelectedKey() {
  const k = S.selKey;
  if (!k) return false;
  const o = objById(k.id);
  if (!o) return false;
  commit(() => {
    const x = objById(k.id);
    for (const [name, ks] of Object.entries(x.keys)) {
      const rest = ks.filter((kk) => Math.abs(kk.t - k.t) > 1e-6);
      if (!rest.length) { x.props[name] = ks[0].v; delete x.keys[name]; } else x.keys[name] = rest;
    }
  }, { source: 'timeline' });
  S.selKey = null;
  return true;
}

on('time', () => placePlayhead());
