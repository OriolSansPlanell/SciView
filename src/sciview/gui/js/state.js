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
  targets: {},          // export presets
  guides: 'none',       // safe-area guides in the preview: none, title, square, vertical
  ffmpeg: true,
  version: '',
  scene: null,          // id of the scene shown in the timeline; S.time is that scene's own time
  transitions: {},      // transition name -> label
  selected: null,       // primary selection: object id, 'camera', 'scene', or null (film settings)
  selection: [],        // all selected object ids (primary last)
  problems: [],         // {id, prop, message} from the project checks
  frameIssues: [],      // {id, prop, message} from the last rendered frame
  recovery: null,
  collapsed: new Set(), // collapsed groups in the timeline
  selKey: null,         // {id, t} selected keyframe group in the timeline
  time: 0,
  playing: false,
  scale: 0.5,
  loop: true,
  issues: [],
  warnings: [],
  boxes: [],
  lastMs: 80,
  assistantBusy: false,
};

// ------------------------------------------------------------------ events
const listeners = {};
export function on(evt, fn) { (listeners[evt] ||= []).push(fn); }
export function emit(evt, data) { (listeners[evt] || []).forEach((fn) => fn(data)); }

// ------------------------------------------------------------------ lookup
export const fps = () => S.project.settings.fps || 30;
export const frameDt = () => 1 / fps();

// ------------------------------------------------------------------ scenes
// Objects belong to a scene and their times count from its start. A scene's transition overlaps the end
// of the scene before it (mirrors sciview.model.project.Project.timeline).
export const scenes = () => S.project.scenes;
export const currentScene = () => scenes().find((sc) => sc.id === S.scene) || scenes()[0];
export const sceneCamera = (sc) => (sc === scenes()[0] ? S.project.camera : sc.camera);
/** Length of the current scene: the timeline's span. */
export const duration = () => Number(currentScene().duration) || 1;

export function overlap(sc) {
  const list = scenes();
  const i = list.indexOf(sc);
  if (i <= 0 || sc.transition === 'cut') return 0;
  const prev = list[i - 1];
  return Math.max(0, Math.min(Number(sc.transition_duration) || 0, prev.duration * 0.95, sc.duration * 0.95));
}

export function sceneStart(sc) {
  let t = 0;
  for (const x of scenes()) {
    if (x === sc) return t - overlap(x);
    t += x.duration - overlap(x);
  }
  return 0;
}

export const filmDuration = () => { const l = scenes()[scenes().length - 1]; return sceneStart(l) + l.duration; };
export const filmTime = () => sceneStart(currentScene()) + S.time;
export const sceneObjects = () => S.project.objects.filter((o) => o.scene === currentScene().id);
export const sceneOf = (o) => scenes().find((sc) => sc.id === o.scene) || scenes()[0];

/** The scene coming in at film time t (the later one during a transition) and its own time. */
export function sceneAt(t) {
  const list = scenes();
  let found = null;
  for (const sc of list) {
    const a = sceneStart(sc);
    if (a <= t + 1e-9 && t < a + sc.duration) found = { scene: sc, t: t - a };
  }
  if (found) return found;
  const last = list[list.length - 1];
  return t < 0 ? { scene: list[0], t: 0 } : { scene: last, t: Math.min(t - sceneStart(last), last.duration) };
}

export function syncDuration() { if (S.project) S.project.settings.duration = Math.round(filmDuration() * 1000) / 1000; }

function normalizeCamera(c) {
  const cam = c || { props: {}, keys: {} };
  Object.assign(cam, { id: 'camera', type: 'camera', name: 'Camera' });
  cam.props ||= {};
  cam.keys ||= {};
  return cam;
}

export function normalize() {
  const p = S.project;
  p.settings ||= {};
  p.palette ||= { ...S.defaultPalette };
  p.camera = normalizeCamera(p.camera);
  p.objects ||= [];
  if (!Array.isArray(p.scenes) || !p.scenes.length) {
    p.scenes = [{ id: 'scene1', name: 'Scene 1', duration: Number(p.settings.duration) || 10, transition: 'cut',
      transition_duration: 1 }];
  }
  p.scenes.forEach((sc, i) => {
    sc.duration = Math.max(0.1, Number(sc.duration) || 10);
    sc.transition ||= 'cut';
    if (sc.transition_duration == null) sc.transition_duration = 1;
    if (i === 0) delete sc.camera;            // the first scene's camera is the project's camera
    else sc.camera = normalizeCamera(sc.camera);
  });
  const ids = new Set(p.scenes.map((sc) => sc.id));
  p.styles ||= {};
  for (const o of p.objects) {
    o.props ||= {};
    o.keys ||= {};
    o.enter ||= { effect: 'fade', duration: 0.6 };
    o.exit ||= { effect: 'fade', duration: 0.6 };
    if (o.start == null) o.start = 0;
    if (!o.scene || !ids.has(o.scene)) o.scene = p.scenes[0].id;
  }
  for (const s of S.settingsSchema) if (!(s.name in p.settings)) p.settings[s.name] = s.default;
  if (!S.scene || !ids.has(S.scene)) S.scene = p.scenes[0].id;
  syncDuration();
}

export function objById(id) {
  if (!S.project || id == null) return null;
  if (id === 'camera') return sceneCamera(currentScene());
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

export const isGroup = (o) => !!o && o.type === 'group';
export const children = (gid) => S.project.objects.filter((o) => o.parent === gid);

export function descendants(gid) {
  const out = [];
  const todo = [gid];
  const seen = new Set([gid]);
  while (todo.length) {
    const g = todo.pop();
    for (const o of S.project.objects) {
      if (o.parent === g && !seen.has(o.id)) {
        seen.add(o.id);
        out.push(o);
        if (isGroup(o)) todo.push(o.id);
      }
    }
  }
  return out;
}

/** Groups containing obj, nearest first (stops on broken or circular chains). */
export function ancestors(obj) {
  const out = [];
  const seen = new Set([obj && obj.id]);
  let o = obj;
  while (o && o.parent) {
    const g = objById(o.parent);
    if (!g || !isGroup(g) || seen.has(g.id)) break;
    seen.add(g.id);
    out.push(g);
    o = g;
  }
  return out;
}

export const isSelected = (id) => S.selection.includes(id);

/** Change the selection. mode: 'set' (default), 'toggle' or 'add'. */
export function select(id, mode = 'set') {
  if (id == null || id === 'camera' || id === 'scene') {
    S.selection = id === 'camera' ? ['camera'] : [];
    S.selected = id;
  } else if (mode === 'toggle') {
    S.selection = S.selection.filter((x) => x !== 'camera');
    if (S.selection.includes(id)) S.selection = S.selection.filter((x) => x !== id);
    else S.selection.push(id);
    S.selected = S.selection.length ? S.selection[S.selection.length - 1] : null;
  } else if (mode === 'add') {
    S.selection = S.selection.filter((x) => x !== 'camera' && x !== id);
    S.selection.push(id);
    S.selected = id;
  } else {
    S.selection = [id];
    S.selected = id;
  }
  if (!S.selKey || S.selKey.id !== S.selected) S.selKey = null;
  emit('selection');
}

/** Problems for an object (or the film when id is null), from the checks and the last frame. */
export function issuesFor(id) {
  const seen = new Set();
  const out = [];
  for (const p of [...S.problems, ...S.frameIssues]) {
    if ((p.id ?? null) === (id ?? null) && !seen.has(p.message)) {
      seen.add(p.message);
      out.push(p);
    }
  }
  return out;
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
export const EASINGS = [...Object.keys(EASE), 'bezier'];
export const BEZIER_PRESETS = {
  ease: [0.25, 0.1, 0.25, 1], 'ease in': [0.42, 0, 1, 1], 'ease out': [0, 0, 0.58, 1],
  'ease in-out': [0.42, 0, 0.58, 1], back: [0.34, 1.56, 0.64, 1], linear: [0, 0, 1, 1],
};

/** CSS-style cubic-bezier, the same algorithm as sciview.engine.easing.cubic_bezier. */
export function cubicBezier(x1, y1, x2, y2, u) {
  u = Math.max(0, Math.min(1, u));
  if (u === 0 || u === 1) return u;
  x1 = Math.min(Math.max(x1, 0), 1);
  x2 = Math.min(Math.max(x2, 0), 1);
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const fx = (s) => ((ax * s + bx) * s + cx) * s;
  let s = u;
  for (let i = 0; i < 8; i++) {
    const d = (3 * ax * s + 2 * bx) * s + cx;
    const err = fx(s) - u;
    if (Math.abs(err) < 1e-7 || Math.abs(d) < 1e-6) break;
    s -= err / d;
  }
  if (!(s >= 0 && s <= 1) || Math.abs(fx(s) - u) > 1e-5) {
    let lo = 0, hi = 1;
    s = u;
    for (let i = 0; i < 40; i++) {
      if (fx(s) < u) lo = s; else hi = s;
      s = (lo + hi) / 2;
    }
  }
  return ((ay * s + by) * s + cy) * s;
}

export function easeValue(name, u, bez) {
  u = Math.max(0, Math.min(1, u));
  if (name === 'bezier') return bez && bez.length === 4 ? cubicBezier(...bez, u) : EASE.smooth(u);
  return (EASE[name] || EASE.smooth)(u);
}

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
      const u = easeValue(b.ease, (t - a.t) / Math.max(b.t - a.t, 1e-9), b.bez);
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

export function setKey(obj, name, t, value, ease, bez) {
  obj.keys ||= {};
  const ks = obj.keys[name] ||= [];
  const tt = Math.round(t * fps()) / fps();
  const i = keyIndexAt(obj, name, tt);
  if (i >= 0) {
    ks[i].v = value;
    if (ease) ks[i].ease = ease;
    if (bez) ks[i].bez = [...bez];
  } else {
    const k = { t: tt, v: value, ease: ease || 'smooth' };
    if (bez) k.bez = [...bez];
    ks.push(k);
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

let busyToast = 0;
export function commit(fn, opts = {}) {
  if (S.assistantBusy && opts.source !== 'assistant') {
    if (performance.now() - busyToast > 2500) {
      busyToast = performance.now();
      emit('error', 'The assistant is changing the film. Wait for it to finish, or stop it.');
    }
    return;
  }
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

/** Replace the film with a version worked out on the server (a theme, captions from a script ...): one undo step. */
export function applyProjectJson(json, note = '') {
  commit((p) => {
    for (const k of Object.keys(p)) delete p[k];
    Object.assign(p, JSON.parse(JSON.stringify(json)));
    normalize();
  }, { source: 'transform', note, settings: true });
}

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
  S.selection = S.selection.filter((id) => objById(id));
  if (S.selected && S.selected !== 'scene' && !objById(S.selected)) S.selected = S.selection.length ? S.selection[S.selection.length - 1] : null;
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
  syncing = api.putProject(S.project, S.rev)
    .then((r) => { S.rev = r.rev; S.issues = r.issues || []; S.problems = r.problems || []; emit('issues'); })
    .catch(async (e) => {
      if (e.status === 409) await pullExternal();          // an assistant changed the film first
      else emit('error', `Could not update the preview: ${e.message}`);
    })
    .finally(() => { syncing = null; });
  await syncing;
  requestFrame();
}

// ------------------------------------------------------------------ changes from an assistant (MCP)
/** Take the film from the server after an agent changed it: one undo step, preview updated. */
export async function pullExternal() {
  let r;
  try { r = await api.project(); } catch (e) { return; }
  if (!r || r.rev === S.rev) return;
  undoStack.push(JSON.stringify(S.project));
  if (undoStack.length > 300) undoStack.shift();
  redoStack.length = 0;
  lastCoalesce = null;
  S.project = r.project;
  S.rev = r.rev;
  normalize();
  S.selection = S.selection.filter((id) => objById(id));
  if (S.selected && S.selected !== 'scene' && !objById(S.selected)) S.selected = S.selection.length ? S.selection[S.selection.length - 1] : null;
  markDirty();
  let note = '';
  try { note = (await api.changes()).note; } catch (e) { /* ignore */ }
  emit('project', { external: true, source: 'agent' });
  emit('agent', note || 'The assistant changed the film');
  requestFrame();
}

/** Take the film from the server without an undo step (the assistant's request is recorded as one step at the end). */
export async function pullQuiet() {
  let r;
  try { r = await api.project(); } catch (e) { return false; }
  if (!r || r.rev === S.rev) return false;
  S.project = r.project;
  S.rev = r.rev;
  normalize();
  S.selection = S.selection.filter((id) => objById(id));
  if (S.selected && S.selected !== 'scene' && !objById(S.selected)) S.selected = S.selection.length ? S.selection[S.selection.length - 1] : null;
  emit('project', { external: true, source: 'assistant' });
  requestFrame();
  return true;
}

/** Record the state before an assistant request as one undo step. */
export function pushUndo(beforeJson) {
  if (beforeJson === JSON.stringify(S.project)) return false;
  undoStack.push(beforeJson);
  if (undoStack.length > 300) undoStack.shift();
  redoStack.length = 0;
  lastCoalesce = null;
  markDirty();
  emit('project', { source: 'assistant' });
  return true;
}

let watching = false;
export function watchExternal(interval = 1200) {
  if (watching) return;
  watching = true;
  const tick = async () => {
    try {
      if (!needSync && !syncing && !document.hidden && !S.assistantBusy) {
        const c = await api.changes();
        if (c.external_rev > S.rev && c.rev !== S.rev) await pullExternal();
      }
    } catch (e) { /* server stopped: try again later */ }
    setTimeout(tick, interval);
  };
  setTimeout(tick, interval);
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
    const t = Math.round(filmTime() * fps()) / fps();
    const r = await api.frame(t, scale, S.playing);
    if (!S.playing || scale === S.scale) S.lastMs = r.ms;
    else S.lastMs = Math.min(S.lastMs, r.ms * 1.2);
    S.boxes = r.boxes || [];
    S.frameIssues = r.issues || [];
    S.warnings = r.warnings || [];
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
  S.transitions = sc.transitions || { cut: 'Cut' };
  S.project = st.project;
  S.path = st.path;
  S.name = st.name;
  S.baseDir = st.base_dir;
  S.untitled = st.untitled;
  S.saved = st.saved;
  S.assets = st.assets;
  S.templates = st.templates;
  S.formats = st.formats;
  S.targets = st.targets || {};
  S.ffmpeg = st.ffmpeg;
  S.version = st.version;
  S.issues = st.issues || [];
  S.problems = st.problems || [];
  S.recovery = st.recovery || null;
  S.rev = st.rev;
  if (!keepTime) S.scene = null;
  normalize();
  if (!keepTime) S.time = 0;
  S.time = Math.min(S.time, duration());
  S.selection = S.selection.filter((id) => objById(id));
  if (S.selected && S.selected !== 'scene' && !objById(S.selected)) S.selected = null;
}
