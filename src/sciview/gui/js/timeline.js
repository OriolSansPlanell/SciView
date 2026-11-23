// Timeline: one row per object (top-most first), clips for visibility, gold diamonds for keyframes.
import {
  S, on, emit, commit, objById, schemaOf, span, keyTimes, duration, fps, breakCoalesce, select, isSelected,
  isGroup, children, descendants, issuesFor, sceneObjects, sceneCamera, currentScene,
} from './state.js';
import { snapPoints, waveformFor } from './sound.js';
import { el, drag, clamp, fmtTime } from './ui.js';
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

const labelW = () => parseFloat(getComputedStyle(document.getElementById('app')).getPropertyValue('--lib-w')) || 236;
const xOf = (t) => PAD + t * pps;
const catClass = { '3D scene': 'cat-3d', Text: 'cat-text', Charts: 'cat-charts', 'Shapes & media': 'cat-shapes',
  Imaging: 'cat-charts', Optics: 'cat-3d', Sound: 'cat-sound' };

function snap(t, { toPlayhead = true, speech = true } = {}) {
  const f = fps();
  let s = Math.round(t * f) / f;
  if (toPlayhead && Math.abs(s - S.time) * pps < 7) s = S.time;
  if (Math.abs(s) * pps < 6) s = 0;
  if (Math.abs(s - duration()) * pps < 6) s = duration();
  // the beginnings and ends of phrases in the scene's voice clips
  if (speech) {
    let best = null;
    for (const p of snapPoints()) if (Math.abs(p - t) * pps < 8 && (best == null || Math.abs(p - t) < Math.abs(best - t))) best = p;
    if (best != null) s = Math.round(best * 100) / 100;
  }
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
  // keep the keyboard focus on the same row when the rows are drawn again
  const focusedRow = document.activeElement?.classList?.contains('tl-label')
    ? document.activeElement.closest('.tl-row')?.dataset.id : null;
  rowsEl.innerHTML = '';
  rowsEl.style.width = `${labelW() + width}px`;
  rowsEl.append(makeRow(sceneCamera(currentScene()), width, 0));
  const objs = sceneObjects();
  const ids = new Set(objs.map((o) => o.id));
  // top-level objects: no parent, or a parent that is not a usable group
  const isTop = (o) => !o.parent || !ids.has(o.parent) || !isGroup(objById(o.parent));
  const shown = new Set();
  const addRows = (list, depth) => {
    for (const o of [...list].reverse()) {
      if (shown.has(o.id)) continue;
      shown.add(o.id);
      rowsEl.append(makeRow(o, width, depth));
      if (isGroup(o) && !S.collapsed.has(o.id)) addRows(children(o.id), depth + 1);
    }
  };
  addRows(objs.filter(isTop), 0);
  // objects in groups that contain each other in a circle have no top: list them anyway
  const inCycle = (o) => {
    const seen = new Set([o.id]);
    let x = o;
    while (x.parent && ids.has(x.parent) && isGroup(objById(x.parent))) {
      if (seen.has(x.parent)) return true;
      seen.add(x.parent);
      x = objById(x.parent);
    }
    return false;
  };
  const left = objs.filter((o) => !shown.has(o.id) && inCycle(o));
  if (left.length) addRows(left, 0);
  if (!objs.length) {
    rowsEl.append(el('div', { class: 'tl-empty' }, S.project.scenes.length > 1
      ? 'This scene is empty. Objects you add go into it; times count from the start of the scene.'
      : 'Objects you add appear here. Drag clips to change when they appear.'));
  }
  if (focusedRow) rowsEl.querySelector(`.tl-row[data-id="${CSS.escape(focusedRow)}"] .tl-label`)?.focus();
  placePlayhead();
  drawRuler();
}

function makeRow(o, width, depth) {
  const sc = schemaOf(o);
  const isCam = o.type === 'camera';
  const group = isGroup(o);
  const problems = isCam ? [] : issuesFor(o.id);
  const row = el('div', {
    class: `tl-row ${isSelected(o.id) ? 'sel' : ''} ${S.selected === o.id ? 'primary' : ''} ${o.visible === false ? 'hidden-obj' : ''} ${group ? 'is-group' : ''}`,
    dataset: { id: o.id },
  });
  const grip = isCam ? el('span', { style: { width: '8px' } }) : el('span', { class: 'grip', title: 'Drag to change the drawing order' });
  const eye = isCam ? null : el('button', {
    class: `icon-btn small eye ${o.visible === false ? 'off' : ''}`, title: o.visible === false ? 'Show' : 'Hide',
    'aria-label': o.visible === false ? `Show ${o.name}` : `Hide ${o.name}`, html: icon(o.visible === false ? 'eyeoff' : 'eye'),
  });
  const twist = group ? el('button', {
    class: `icon-btn small twist ${S.collapsed.has(o.id) ? 'closed' : ''}`, 'aria-label': S.collapsed.has(o.id) ? `Expand ${o.name}` : `Collapse ${o.name}`,
    'aria-expanded': String(!S.collapsed.has(o.id)), html: icon('down'),
  }) : el('span', { class: 'twist-space' });
  const badge = problems.length ? el('span', { class: 'warn-badge', title: problems.map((p) => p.message).join('\n'), html: icon('warning') }) : null;
  const [r0, r1] = isCam ? [0, duration()] : span(o);
  const label = el('div', {
    class: 'tl-label', title: `${o.name} (${sc ? sc.label : o.type})`, style: { paddingLeft: `${8 + depth * 16}px` },
    tabindex: '0', role: 'button', 'aria-pressed': String(isSelected(o.id)),
    'aria-label': `${o.name || o.id}, ${sc ? sc.label : o.type}${isCam ? '' : `, from ${fmtTime(r0)} to ${fmtTime(r1)} s`}${problems.length ? `, ${problems.length} problem${problems.length > 1 ? 's' : ''}` : ''}`,
  }, grip, twist, el('span', { class: 'ic', html: icon(sc ? sc.icon : 'square') }), el('span', { class: 'nm' }, o.name || o.id), badge, eye);
  label.addEventListener('click', (e) => {
    if (e.target.closest('.eye') || e.target.closest('.twist')) return;
    if (e.shiftKey || e.metaKey || e.ctrlKey) select(o.id, 'toggle');
    else select(o.id);
  });
  label.addEventListener('keydown', (e) => {               // keyboard: Enter or Space selects, arrows move between rows
    if (e.target !== label) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      e.stopPropagation();
      select(o.id, e.shiftKey ? 'toggle' : 'set');
    } else if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && !e.altKey) {
      e.preventDefault();
      e.stopPropagation();
      const all = [...document.querySelectorAll('#tlRows .tl-label')];
      all[Math.max(0, Math.min(all.length - 1, all.indexOf(label) + (e.key === 'ArrowDown' ? 1 : -1)))]?.focus();
    }
  });
  if (twist && group) twist.addEventListener('click', () => {
    if (S.collapsed.has(o.id)) S.collapsed.delete(o.id); else S.collapsed.add(o.id);
    renderTimeline();
  });
  if (eye) eye.addEventListener('click', () => commit(() => { const x = objById(o.id); x.visible = x.visible === false; }, { source: 'timeline' }));
  if (!isCam) grip.addEventListener('pointerdown', (e) => reorderDrag(e, o.id, row));

  const track = el('div', { class: 'tl-track', style: { width: `${width}px` } });
  track.addEventListener('pointerdown', (e) => {
    if (e.target !== track) return;
    if (e.shiftKey) select(o.id, 'toggle'); else select(o.id);
    scrubFrom(e);
  });
  if (!isCam) {
    const [s, e] = span(o);
    const clip = el('div', { class: `clip ${group ? 'cat-group' : catClass[sc ? sc.category : ''] || ''}`, style: { left: `${xOf(s)}px`, width: `${Math.max(4, (e - s) * pps)}px` } });
    const ein = o.enter && o.enter.effect !== 'none' ? o.enter.duration : 0;
    const eout = o.end != null && o.exit && o.exit.effect !== 'none' ? o.exit.duration : 0;
    if (ein > 0) clip.append(el('div', { class: 'ramp in', style: { width: `${Math.min(ein, e - s) * pps}px` } }));
    if (eout > 0) clip.append(el('div', { class: 'ramp out', style: { width: `${Math.min(eout, e - s) * pps}px` } }));
    let text = o.type === 'caption' || o.type === 'title' || o.type === 'text' ? (o.props.text ?? '') : '';
    if (group) text = `${descendants(o.id).length} objects`;
    if (o.type === 'voice') {
      text = o.props.script || (o.props.audio ? o.props.audio.replace(/^.*\//, '') : 'No recording');
      const cv = el('canvas', { class: 'wave', 'aria-hidden': 'true' });
      clip.append(cv);
      waveformFor(o).then((w) => drawWave(cv, w, (e - s) * pps)).catch(() => {});
    }
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
  if (ev.shiftKey) { select(id, 'toggle'); return; }
  if (!isSelected(id)) select(id);
  // moving one selected clip moves every selected clip (and a group's members with it)
  const ids = mode === 'move' ? movingIds(id) : [id];
  const starts = Object.fromEntries(ids.map((x) => [x, JSON.parse(JSON.stringify(objById(x)))]));
  const o0 = starts[id];
  const [s0, e0] = span(o0);
  const minStart = Math.min(...ids.map((x) => span(starts[x])[0]));
  const tag = `clip-${id}-${Date.now()}`;
  breakCoalesce();
  drag(ev, (dx) => {
    const dt = dx / pps;
    commit(() => {
      if (mode === 'move') {
        let shift = snap(s0 + dt) - s0;
        shift = Math.max(shift, -minStart);
        for (const x of ids) {
          const o = objById(x), a = starts[x];
          if (!o) continue;
          const [as, ae] = span(a);
          o.start = Math.max(0, Math.min(as + shift, duration() - 0.05));
          o.end = a.end == null ? null : Math.min(duration(), ae + shift);
          o.keys = JSON.parse(JSON.stringify(a.keys || {}));
          for (const ks of Object.values(o.keys)) for (const k of ks) k.t = Math.round((k.t + shift) * fps()) / fps();
        }
      } else if (mode === 'start') {
        const o = objById(id);
        o.start = clamp(snap(s0 + dt), 0, e0 - 0.05);
      } else {
        const o = objById(id);
        const ne = clamp(snap(e0 + dt), s0 + 0.05, duration());
        o.end = Math.abs(ne - duration()) < 1e-6 && o0.end == null ? null : ne;
      }
    }, { coalesce: tag, source: 'timeline' });
  });
}

function movingIds(id) {
  const base = isSelected(id) ? S.selection.filter((x) => x !== 'camera') : [id];
  const out = new Set(base);
  for (const x of base) if (isGroup(objById(x))) for (const d of descendants(x)) out.add(d.id);
  return [...out];
}

function keyDrag(ev, id, t0) {
  ev.stopPropagation();
  select(id);
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
      const moving = new Set([id, ...(isGroup(objById(id)) ? descendants(id).map((d) => d.id) : [])]);
      if (moving.has(target.id)) return;
      const block = p.objects.filter((o) => moving.has(o.id));
      const rest = p.objects.filter((o) => !moving.has(o.id));
      const tgt = rest.find((x) => x.id === target.id);
      let j = rest.indexOf(tgt);
      let parent = tgt.parent || null;            // a dropped row joins its neighbour's group
      if (isGroup(tgt) && !target.above) {
        if (S.collapsed.has(tgt.id)) {
          // below a collapsed group: under its whole block
          const inside = new Set(descendants(tgt.id).map((d) => d.id));
          const first = rest.findIndex((x) => inside.has(x.id));
          if (first >= 0 && first < j) j = first;
        } else {
          parent = tgt.id;                         // just under an open group's row: its top member
        }
      } else if (target.above) {
        j += 1;                                    // rows are shown top-most first (reversed list)
      }
      rest.splice(j, 0, ...block);
      p.objects = rest;
      const moved = p.objects.find((o) => o.id === id);
      if (moved) {
        if (parent === moved.id || descendants(moved.id).some((d) => d.id === parent)) parent = moved.parent || null;
        moved.parent = parent;
      }
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
on('layout', () => renderTimeline());
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

function drawWave(cv, w, widthPx) {
  if (!w || !w.peaks) return;
  const h = 22;
  const dpr = window.devicePixelRatio || 1;
  cv.width = Math.max(1, Math.round(widthPx * dpr));
  cv.height = Math.round(h * dpr);
  cv.style.width = `${widthPx}px`;
  cv.style.height = `${h}px`;
  const g = cv.getContext('2d');
  g.scale(dpr, dpr);
  g.fillStyle = 'rgba(190, 230, 255, 0.55)';
  const n = w.peaks.length;
  // the recording may be shorter than the clip
  const span = w.clip > 0 ? Math.min(1, w.seconds / w.clip) : 1;
  for (let i = 0; i < n; i++) {
    const x = (i / n) * widthPx * span;
    const a = w.peaks[i] * (h / 2 - 1);
    g.fillRect(x, h / 2 - a, Math.max(1, (widthPx * span) / n - 0.5), 2 * a);
  }
  g.fillStyle = 'rgba(255, 207, 74, 0.9)';
  for (const [a, b] of w.segments || []) {
    g.fillRect((a / (w.clip || w.seconds)) * widthPx, h - 2, Math.max(2, ((b - a) / (w.clip || w.seconds)) * widthPx), 2);
  }
}
