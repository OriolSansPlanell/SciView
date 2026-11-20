// Preview: shows rendered frames, selection outlines, drag-to-move for 2D objects and camera orbit.
import {
  S, on, emit, commit, objById, schemaOf, valueAt, setValue, select, isSelected, ancestors,
} from './state.js';
import { movePlan, applyMove } from './actions.js';
import { addObject } from './inspector.js';
import { api } from './api.js';
import { toast, drag } from './ui.js';

const viewport = document.getElementById('viewport');
const wrap = document.getElementById('frameWrap');
const img = document.getElementById('frame');
const overlay = document.getElementById('overlay');
const busy = document.getElementById('busy');
const dropHint = document.getElementById('dropHint');
let hover = null;
let dragging = false;

export function layoutViewport() {
  if (!S.project) return;
  const W = S.project.settings.width || 1920, H = S.project.settings.height || 1080;
  const r = viewport.getBoundingClientRect();
  const aw = r.width - 36, ah = r.height - 36;
  const k = Math.max(0.05, Math.min(aw / W, ah / H));
  wrap.style.width = `${Math.floor(W * k)}px`;
  wrap.style.height = `${Math.floor(H * k)}px`;
  const dpr = window.devicePixelRatio || 1;
  overlay.width = Math.floor(W * k * dpr);
  overlay.height = Math.floor(H * k * dpr);
  drawOverlay();
}

const designToCss = () => wrap.clientWidth / (S.project.settings.width || 1920);
let marquee = null;   // {x0, y0, x1, y1} in design px while box-selecting

export function drawOverlay() {
  const g = overlay.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.clearRect(0, 0, overlay.width, overlay.height);
  if (!S.project) return;
  const k = designToCss() * dpr;
  const box = (b, color, dash, w, pad = 4) => {
    g.save();
    g.strokeStyle = color;
    g.lineWidth = w * dpr;
    g.setLineDash(dash.map((d) => d * dpr));
    const p = pad * dpr;
    g.strokeRect(b.x0 * k - p, b.y0 * k - p, (b.x1 - b.x0) * k + 2 * p, (b.y1 - b.y0) * k + 2 * p);
    g.restore();
  };
  if (hover && !isSelected(hover)) {
    const b = S.boxes.find((x) => x.id === hover);
    if (b) box(b, 'rgba(226,232,243,.35)', [], 1);
  }
  for (const id of S.selection) {
    const b = S.boxes.find((x) => x.id === id);
    if (!b) continue;
    const primary = id === S.selected;
    if (b.group) box(b, '#4fd1c5', [2, 4], primary ? 1.5 : 1, 10);
    else box(b, primary ? '#4fd1c5' : 'rgba(79,209,197,.6)', [5, 4], primary ? 1.5 : 1);
  }
  if (marquee) {
    g.save();
    g.fillStyle = 'rgba(79,209,197,.08)';
    g.strokeStyle = '#4fd1c5';
    g.lineWidth = dpr;
    const x = Math.min(marquee.x0, marquee.x1) * k, y = Math.min(marquee.y0, marquee.y1) * k;
    const w = Math.abs(marquee.x1 - marquee.x0) * k, h = Math.abs(marquee.y1 - marquee.y0) * k;
    g.fillRect(x, y, w, h);
    g.strokeRect(x, y, w, h);
    g.restore();
  }
}

function designPoint(e) {
  const r = overlay.getBoundingClientRect();
  const k = designToCss();
  return [(e.clientX - r.left) / k, (e.clientY - r.top) / k];
}

function hit(e) {
  const [x, y] = designPoint(e);
  // members, not their group boxes; prefer 2D (drawn on top), then the smallest box
  const hits = S.boxes.filter((b) => !b.group && x >= b.x0 - 4 && x <= b.x1 + 4 && y >= b.y0 - 4 && y <= b.y1 + 4);
  if (!hits.length) return null;
  const top2d = hits.filter((b) => { const o = objById(b.id); return o && !schemaOf(o).is3d; });
  const pool = top2d.length ? top2d : hits;
  pool.sort((a, b) => (a.x1 - a.x0) * (a.y1 - a.y0) - (b.x1 - b.x0) * (b.y1 - b.y0));
  return pool[0].id;
}

/**
 * The object a click on ``id`` acts on. A click on a grouped object picks its outermost group,
 * unless the object or one of its groups is already selected, or the selection is already
 * inside one of those groups (then it stays at that level). Double-click goes one level in.
 */
function target(id) {
  const o = id ? objById(id) : null;
  if (!o) return null;
  const chain = [o, ...ancestors(o)];               // nearest first
  const sel = chain.find((x) => isSelected(x.id));
  if (sel) return sel.id;
  const cur = objById(S.selected);
  const ctx = cur && cur.parent ? objById(cur.parent) : null;
  if (ctx) {
    const i = chain.findIndex((x) => x.id === ctx.id);
    if (i > 0) return chain[i - 1].id;
  }
  return chain[chain.length - 1].id;
}

overlay.addEventListener('dblclick', (e) => {
  const h = hit(e);
  if (!h) return;
  const chain = [objById(h), ...ancestors(objById(h))];
  const i = chain.findIndex((x) => isSelected(x.id));
  select(i > 0 ? chain[i - 1].id : h);
});

overlay.addEventListener('pointermove', (e) => {
  if (dragging) return;
  const h = target(hit(e));
  if (h !== hover) { hover = h; drawOverlay(); }
  overlay.className = h ? 'move' : 'grab';
});
overlay.addEventListener('pointerleave', () => { hover = null; drawOverlay(); });

overlay.addEventListener('pointerdown', (e) => {
  if (e.button !== 0) return;
  const k = designToCss();
  const id = target(hit(e));
  // Ctrl/Cmd + drag on empty space: box selection
  if (!id && (e.ctrlKey || e.metaKey)) {
    const [x0, y0] = designPoint(e);
    marquee = { x0, y0, x1: x0, y1: y0 };
    const before = [...S.selection].filter((x) => x !== 'camera');
    dragging = true;
    drag(e, (_dx, _dy, ev) => {
      [marquee.x1, marquee.y1] = designPoint(ev);
      drawOverlay();
    }, () => {
      dragging = false;
      const mx0 = Math.min(marquee.x0, marquee.x1), mx1 = Math.max(marquee.x0, marquee.x1);
      const my0 = Math.min(marquee.y0, marquee.y1), my1 = Math.max(marquee.y0, marquee.y1);
      marquee = null;
      const picked = S.boxes.filter((b) => !b.group && b.x1 >= mx0 && b.x0 <= mx1 && b.y1 >= my0 && b.y0 <= my1)
        .map((b) => target(b.id)).filter((x, i, arr) => arr.indexOf(x) === i);
      select(null);
      for (const pid of [...before, ...picked]) select(pid, 'add');
      drawOverlay();
    });
    return;
  }
  if (id && !e.altKey) {
    // Shift: a click adds or removes the object, a drag moves along one axis
    const wasSelected = isSelected(id);
    if (!e.shiftKey && !wasSelected) select(id);
    const ids = e.shiftKey && !wasSelected ? [...S.selection, id] : [...S.selection];
    const plan = movePlan(ids);
    const tag = `vp-${Date.now()}`;
    dragging = true;
    drag(e, (dx, dy, ev) => {
      if (!plan.length) return;
      let ddx = dx / k, ddy = dy / k;
      const lock = ev.shiftKey;
      if (lock) { if (Math.abs(ddx) > Math.abs(ddy)) ddy = 0; else ddx = 0; }
      commit(() => {
        for (const m of plan) applyMove(m, m.kind === '2d' ? ddx : dx / k, m.kind === '2d' ? ddy : dy / k, lock);
      }, { coalesce: tag, source: 'viewport' });
    }, (moved) => {
      dragging = false;
      if (e.shiftKey && !moved) select(id, 'toggle');
      else if (e.shiftKey && !wasSelected) select(id, 'add');
    });
    return;
  }
  // empty space (or Alt): click clears the selection, drag orbits the camera (Shift: shift the view)
  const cam = S.project.camera;
  const az0 = valueAt(cam, 'azimuth', S.time), el0 = valueAt(cam, 'elevation', S.time);
  const off0 = [...valueAt(cam, 'offset', S.time)];
  const tag = `orbit-${Date.now()}`;
  dragging = true;
  overlay.className = 'grab';
  drag(e, (dx, dy, ev) => {
    commit(() => {
      const c = S.project.camera;
      if (ev.shiftKey) {
        setValue(c, 'offset', [Math.round(off0[0] + dx / k), Math.round(off0[1] + dy / k)]);
      } else {
        setValue(c, 'azimuth', Math.round((az0 - dx * 0.35) * 10) / 10);
        setValue(c, 'elevation', Math.round(Math.max(-89, Math.min(89, el0 + dy * 0.25)) * 10) / 10);
      }
    }, { coalesce: tag, source: 'viewport' });
  }, (moved) => {
    dragging = false;
    if (!moved && !e.altKey) select(null);
  });
});

overlay.addEventListener('wheel', (e) => {
  e.preventDefault();
  const cam = S.project.camera;
  const d = valueAt(cam, 'distance', S.time);
  const nd = Math.max(0.5, d * (e.deltaY > 0 ? 1.08 : 1 / 1.08));
  commit(() => setValue(S.project.camera, 'distance', Math.round(nd * 10) / 10), { coalesce: 'wheel-zoom', source: 'viewport' });
}, { passive: false });

// ------------------------------------------------------------------ frames
let lastUrl = null;
on('frame', (r) => {
  img.src = r.image;
  if (lastUrl) URL.revokeObjectURL(lastUrl);
  lastUrl = r.image;
  emit('warnings');
  drawOverlay();
});
on('busy', (b) => { busy.hidden = !b; });
on('selection', () => drawOverlay());

// ------------------------------------------------------------------ drop files
let dragDepth = 0;
viewport.addEventListener('dragenter', (e) => { if (e.dataTransfer.types.includes('Files')) { dragDepth++; dropHint.hidden = false; } });
viewport.addEventListener('dragleave', () => { dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) dropHint.hidden = true; });
viewport.addEventListener('dragover', (e) => { if (e.dataTransfer.types.includes('Files')) e.preventDefault(); });
viewport.addEventListener('drop', async (e) => {
  e.preventDefault();
  dragDepth = 0;
  dropHint.hidden = true;
  for (const f of e.dataTransfer.files) await addFile(f);
});

export async function addFile(f) {
  try {
    const info = await api.upload(f);
    if (!S.assets.some((a) => a.path === info.path)) S.assets.push(info);
    if (info.kind === 'image' || info.kind === 'array') addObject('image', { image: info.path });
    else if (info.kind === 'mesh') addObject('mesh', { model: info.path });
    else if (info.kind === 'audio') {
      commit((p) => { p.settings.audio = info.path; }, { source: 'drop' });
      toast(`${f.name} will play under the film. Change it in Film settings.`);
    } else if (info.kind === 'table') {
      toast(`Added ${f.name}${info.columns ? ` (columns: ${info.columns.slice(0, 6).join(', ')})` : ''}. Pick it in a Data field.`);
    } else toast(`Added ${f.name}`);
  } catch (err) {
    toast(`Could not add ${f.name}: ${err.message}`, 'err');
  }
}

new ResizeObserver(() => layoutViewport()).observe(viewport);
