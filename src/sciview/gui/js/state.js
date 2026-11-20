// Central state, undo history, value interpolation and server sync.
import { api } from './api.js';

export const S = {
  project: null,
  types: {},            // type name -> schema
  typeList: [],
  cameraSchema: null,
  settingsSchema: [],
  categories: [],
  fonts: [],
  defaultPalette: {},
  lightPalette: {},
  path: '',
  name: 'untitled',
  baseDir: '',
  untitled: true,
  saved: true,
  assets: [],
  templates: [],
  formats: {},
  ffmpeg: true,
  version: '',
  selected: null,       // object id, 'camera', or null (film settings)
  selKey: null,         // {id, t} selected keyframe group in the timeline
  time: 0,
  playing: false,
  scale: 0.5,
  loop: true,
  issues: [],
  warnings: [],
  boxes: [],
  lastMs: 80,
};

// ------------------------------------------------------------------ events
const listeners = {};
export function on(evt, fn) { (listeners[evt] ||= []).push(fn); }
export function emit(evt, data) { (listeners[evt] || []).forEach((fn) => fn(data)); }

// ------------------------------------------------------------------ lookup
export const fps = () => S.project.settings.fps || 30;
export const duration = () => Number(S.project.settings.duration) || 1;
export const frameDt = () => 1 / fps();

export function normalize() {
  const p = S.project;
  p.settings ||= {};
  p.palette ||= { ...S.defaultPalette };
  p.camera ||= { props: {}, keys: {} };
  Object.assign(p.camera, { id: 'camera', type: 'camera', name: 'Camera' });
  p.camera.props ||= {};
  p.camera.keys ||= {};
  p.objects ||= [];
  for (const o of p.objects) {
    o.props ||= {};
    o.keys ||= {};
    o.enter ||= { effect: 'fade', duration: 0.6 };
    o.exit ||= { effect: 'fade', duration: 0.6 };
    if (o.start == null) o.start = 0;
  }
  for (const s of S.settingsSchema) if (!(s.name in p.settings)) p.settings[s.name] = s.default;
}

export function objById(id) {
  if (!S.project || id == null) return null;
  if (id === 'camera') return S.project.camera;
  return S.project.objects.find((o) => o.id === id) || null;
}

export function schemaOf(obj) {
  if (!obj) return null;
  return obj.type === 'camera' ? S.cameraSchema : S.types[obj.type];
}

export function propSchema(obj, name) {
  const sc = schemaOf(obj);
  return sc ? sc.props.find((p) => p.name === name) : null;
}

export function uniqueId(base) {
  const used = new Set(S.project.objects.map((o) => o.id));
  let i = 1;
  while (used.has(`${base}${i}`)) i += 1;
  return `${base}${i}`;
}

export function span(obj) {
  return [Number(obj.start) || 0, obj.end == null ? duration() : Number(obj.end)];
}

// ------------------------------------------------------------------ values
const EASE = {
  linear: (u) => u,
  smooth: (u) => u * u * (3 - 2 * u),
  smoother: (u) => u * u * u * (u * (u * 6 - 15) + 10),
  in: (u) => u ** 3,
  out: (u) => 1 - (1 - u) ** 3,
  in_out: (u) => (u < 0.5 ? 4 * u ** 3 : 1 - (-2 * u + 2) ** 3 / 2),
  overshoot: (u) => 1 + 2.70158 * (u - 1) ** 3 + 1.70158 * (u - 1) ** 2,
  sine: (u) => 0.5 - 0.5 * Math.cos(Math.PI * u),
  hold: (u) => (u < 1 ? 0 : 1),
};
export const EASINGS = Object.keys(EASE);

export function resolveColor(c) {
  if (Array.isArray(c)) return c;
  const s = String(c || '').trim().toLowerCase();
  const pal = (S.project && S.project.palette) || S.defaultPalette;
  const hex = pal[s] || S.defaultPalette[s] || s;
  const h = hex.replace('#', '');
  const full = h.length === 3 ? h.split('').map((x) => x + x).join('') : h;
  if (!/^[0-9a-f]{6}$/i.test(full)) return [0.55, 0.58, 0.65];
  return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16) / 255);
}
export function toHex(rgb) {
  return '#' + rgb.map((v) => Math.round(Math.max(0, Math.min(1, v)) * 255).toString(16).padStart(2, '0')).join('');
}
export function colorCss(c) { return toHex(resolveColor(c)); }

export function staticValue(obj, name) {
  if (obj.props && name in obj.props) return obj.props[name];
  const p = propSchema(obj, name);
  return p ? p.default : undefined;
}

export function valueAt(obj, name, t) {
  const ks = obj.keys && obj.keys[name];
  if (!ks || !ks.length) return staticValue(obj, name);
  const p = propSchema(obj, name);
  if (t <= ks[0].t) return ks[0].v;
  if (t >= ks[ks.length - 1].t) return ks[ks.length - 1].v;
  for (let i = 0; i < ks.length - 1; i++) {
    const a = ks[i], b = ks[i + 1];
    if (a.t <= t && t < b.t) {
      const f = EASE[b.ease] || EASE.smooth;
      const u = f(Math.max(0, Math.min(1, (t - a.t) / Math.max(b.t - a.t, 1e-9))));
      return lerp(p ? p.kind : 'number', a.v, b.v, u);
    }
  }
  return ks[ks.length - 1].v;
}

function lerp(kind, a, b, u) {
  if (kind === 'number') return Number(a) + (Number(b) - Number(a)) * u;
  if (kind === 'int') return Math.round(Number(a) + (Number(b) - Number(a)) * u);
  if (kind === 'vec2' || kind === 'vec3') return a.map((x, i) => Number(x) + (Number(b[i]) - Number(x)) * u);
  if (kind === 'color') {
    const ca = resolveColor(a), cb = resolveColor(b);
    return toHex(ca.map((x, i) => x + (cb[i] - x) * u));
  }
  return u < 1 ? a : b;
}

export function keyIndexAt(obj, name, t) {
  const ks = obj.keys && obj.keys[name];
  if (!ks) return -1;
  const tol = frameDt() * 0.5;
  return ks.findIndex((k) => Math.abs(k.t - t) < tol);
}

export function isAnimated(obj, name) {
  return !!(obj.keys && obj.keys[name] && obj.keys[name].length);
}

/** Set a property value at the current time: keyframes it if the property is animated. */
export function setValue(obj, name, value, t = S.time) {
  if (isAnimated(obj, name)) {
    setKey(obj, name, t, value);
  } else {
    obj.props[name] = value;
  }
}

export function setKey(obj, name, t, value, ease) {
  obj.keys ||= {};
  const ks = obj.keys[name] ||= [];
  const tt = Math.round(t * fps()) / fps();
  const i = keyIndexAt(obj, name, tt);
  if (i >= 0) {
    ks[i].v = value;
    if (ease) ks[i].ease = ease;
  } else {
    ks.push({ t: tt, v: value, ease: ease || 'smooth' });
    ks.sort((a, b) => a.t - b.t);
  }
}

export function removeKey(obj, name, idx) {
  const ks = obj.keys[name];
  if (!ks) return;
  const [k] = ks.splice(idx, 1);
  if (!ks.length) {
    delete obj.keys[name];
    if (k) obj.props[name] = k.v;
  }
}

/** All keyframe times of an object, merged (for the timeline). */
export function keyTimes(obj) {
  const times = [];
  for (const ks of Object.values(obj.keys || {})) for (const k of ks) {
    if (!times.some((x) => Math.abs(x - k.t) < 1e-6)) times.push(k.t);
  }
  return times.sort((a, b) => a - b);
}

// ------------------------------------------------------------------ history
const undoStack = [];
const redoStack = [];
let lastCoalesce = null;
let lastCommit = 0;

export function commit(fn, opts = {}) {
  const before = JSON.stringify(S.project);
  fn(S.project);
  const now = performance.now();
  const merge = opts.coalesce && opts.coalesce === lastCoalesce && now - lastCommit < 1500;
  if (!merge) {
    undoStack.push(before);
    if (undoStack.length > 300) undoStack.shift();
  }
  lastCoalesce = opts.coalesce || null;
  lastCommit = now;
  redoStack.length = 0;
  markDirty();
  scheduleSync();
  emit('project', opts);
}

export function breakCoalesce() { lastCoalesce = null; }

export function undo() {
  if (!undoStack.length) return false;
  redoStack.push(JSON.stringify(S.project));
  S.project = JSON.parse(undoStack.pop());
  afterHistory();
  return true;
}

export function redo() {
  if (!redoStack.length) return false;
  undoStack.push(JSON.stringify(S.project));
  S.project = JSON.parse(redoStack.pop());
  afterHistory();
  return true;
}

function afterHistory() {
  normalize();
  lastCoalesce = null;
  if (S.selected && !objById(S.selected)) S.selected = null;
  markDirty();
  scheduleSync();
  emit('project', { external: true });
}

export function resetHistory() {
  undoStack.length = 0;
  redoStack.length = 0;
  lastCoalesce = null;
}
export const canUndo = () => undoStack.length > 0;
export const canRedo = () => redoStack.length > 0;

export function markDirty() {
  S.saved = false;
  emit('dirty');
}

// ------------------------------------------------------------------ server sync
let syncTimer = null;
let syncing = null;
let needSync = false;

export function scheduleSync(delay = 30) {
  needSync = true;
  clearTimeout(syncTimer);
  syncTimer = setTimeout(doSync, delay);
}

async function doSync() {
  if (syncing) await syncing;
  if (!needSync) return;
  needSync = false;
  syncing = api.putProject(S.project)
    .then((r) => { S.issues = r.issues || []; emit('issues'); })
    .catch((e) => emit('error', `Could not update the preview: ${e.message}`))
    .finally(() => { syncing = null; });
  await syncing;
  requestFrame();
}

export async function synced() {
  for (let i = 0; i < 20 && (needSync || syncing); i++) {
    if (syncing) await syncing;
    else { clearTimeout(syncTimer); await doSync(); }
  }
}

let inflight = false;
let pendingFrame = false;

export function requestFrame() {
  pendingFrame = true;
  pump();
}

async function pump() {
  if (inflight || !pendingFrame) return;
  pendingFrame = false;
  inflight = true;
  emit('busy', true);
  try {
    await synced();
    const scale = S.playing ? (S.lastMs < 70 ? Math.min(S.scale, 0.5) : 0.25) : S.scale;
    const t = S.time;
    const r = await api.frame(t, scale);
    if (!S.playing || scale === S.scale) S.lastMs = r.ms;
    else S.lastMs = Math.min(S.lastMs, r.ms * 1.2);
    emit('frame', r);
  } catch (e) {
    emit('error', `Preview failed: ${e.message}`);
  } finally {
    inflight = false;
    emit('busy', false);
  }
  if (pendingFrame) pump();
}

// ------------------------------------------------------------------ loading
export function applyState(st, { keepTime = false } = {}) {
  const sc = st.schema;
  S.types = Object.fromEntries(sc.types.map((t) => [t.type, t]));
  S.typeList = sc.types;
  S.cameraSchema = sc.camera;
  S.settingsSchema = sc.settings;
  S.categories = sc.categories;
  S.fonts = sc.fonts;
  S.defaultPalette = sc.palette;
  S.lightPalette = sc.light_palette;
  S.project = st.project;
  S.path = st.path;
  S.name = st.name;
  S.baseDir = st.base_dir;
  S.untitled = st.untitled;
  S.saved = st.saved;
  S.assets = st.assets;
  S.templates = st.templates;
  S.formats = st.formats;
  S.ffmpeg = st.ffmpeg;
  S.version = st.version;
  S.issues = st.issues || [];
  normalize();
  if (!keepTime) S.time = 0;
  S.time = Math.min(S.time, duration());
  if (S.selected && !objById(S.selected)) S.selected = null;
}
