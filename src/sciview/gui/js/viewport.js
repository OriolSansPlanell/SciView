// Preview: shows rendered frames, selection outlines, drag-to-move for 2D objects and camera orbit.
import { S, on, emit, commit, objById, schemaOf, valueAt, setValue } from './state.js';
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

export function drawOverlay() {
  const g = overlay.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.clearRect(0, 0, overlay.width, overlay.height);
  if (!S.project) return;
  const k = designToCss() * dpr;
  const box = (b, color, dash, w) => {
    g.save();
    g.strokeStyle = color;
    g.lineWidth = w * dpr;
    g.setLineDash(dash.map((d) => d * dpr));
    const pad = 4 * dpr;
    g.strokeRect(b.x0 * k - pad, b.y0 * k - pad, (b.x1 - b.x0) * k + 2 * pad, (b.y1 - b.y0) * k + 2 * pad);
    g.restore();
  };
  if (hover && hover !== S.selected) {
    const b = S.boxes.find((x) => x.id === hover);
    if (b) box(b, 'rgba(226,232,243,.35)', [], 1);
  }
  const sb = S.boxes.find((x) => x.id === S.selected);
  if (sb) box(sb, '#4fd1c5', [5, 4], 1.5);
}

function hit(e) {
  const r = overlay.getBoundingClientRect();
  const k = designToCss();
  const x = (e.clientX - r.left) / k, y = (e.clientY - r.top) / k;
  // last drawn = top-most; prefer the smallest box among overlapping ones for precision
  const hits = S.boxes.filter((b) => x >= b.x0 - 4 && x <= b.x1 + 4 && y >= b.y0 - 4 && y <= b.y1 + 4);
  if (!hits.length) return null;
  const top2d = hits.filter((b) => { const o = objById(b.id); return o && !schemaOf(o).is3d; });
  const pool = top2d.length ? top2d : hits;
  pool.sort((a, b) => (a.x1 - a.x0) * (a.y1 - a.y0) - (b.x1 - b.x0) * (b.y1 - b.y0));
  return pool[0].id;
}

function movableProps(o) {
  const names = schemaOf(o).props.filter((p) => p.kind === 'vec2').map((p) => p.name);
  if (names.includes('position')) return ['position'];
  if (o.type === 'ellipse') return ['center'];
  if (o.type === 'arrow') return ['tail', 'tip'];
  return [];
}

function dataScale(o) {
  const ref = valueAt(o, 'axes', S.time);
  if (!ref) return [1, 1];
  const ax = objById(ref);
  if (!ax) return [1, 1];
  const xr = valueAt(ax, 'x_range', S.time), yr = valueAt(ax, 'y_range', S.time), sz = valueAt(ax, 'size', S.time);
  return [(xr[1] - xr[0]) / sz[0], -(yr[1] - yr[0]) / sz[1]];
}

overlay.addEventListener('pointermove', (e) => {
  if (dragging) return;
  const h = hit(e);
  if (h !== hover) { hover = h; drawOverlay(); }
  const o = h && objById(h);
  overlay.className = o && !schemaOf(o).is3d && movableProps(o).length ? 'move' : 'grab';
});
overlay.addEventListener('pointerleave', () => { hover = null; drawOverlay(); });

overlay.addEventListener('pointerdown', (e) => {
  if (e.button !== 0) return;
  const id = hit(e);
  const o = id && objById(id);
  const k = designToCss();
  if (o && !schemaOf(o).is3d && movableProps(o).length && !o.locked) {
    emit('select', id);
    const props = movableProps(o);
    const start = Object.fromEntries(props.map((p) => [p, [...valueAt(o, p, S.time)]]));
    const [sx, sy] = dataScale(o);
    const tag = `vp-${id}-${Date.now()}`;
    dragging = true;
    drag(e, (dx, dy, ev) => {
      let ddx = dx / k, ddy = dy / k;
      if (ev.shiftKey) { if (Math.abs(ddx) > Math.abs(ddy)) ddy = 0; else ddx = 0; }
      commit(() => {
        const x = objById(id);
        for (const p of props) setValue(x, p, [Math.round((start[p][0] + ddx * sx) * 100) / 100, Math.round((start[p][1] + ddy * sy) * 100) / 100]);
      }, { coalesce: tag, source: 'viewport' });
    }, () => { dragging = false; });
    return;
  }
  // 3D object or empty space: click selects / deselects, drag orbits the camera (Shift: shift the view)
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
    if (!moved) emit('select', id || null);
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
on('frame', (r) => {
  img.src = r.image;
  S.boxes = r.boxes || [];
  S.warnings = r.warnings || [];
  emit('warnings');
  drawOverlay();
});
on('busy', (b) => { busy.hidden = !b; });
on('select', () => drawOverlay());

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
