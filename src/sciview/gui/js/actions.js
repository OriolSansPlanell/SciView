// Editing actions on one or several objects: group, ungroup, move, align, distribute, stagger,
// duplicate, delete, copy and paste. Shared by the inspector, the preview and the shortcuts.
import {
  S, commit, objById, schemaOf, valueAt, setValue, setKey, select, isGroup, descendants, ancestors,
  uniqueId, span, duration, fps, currentScene,
} from './state.js';
import { dragDelta, drag3dProps, scale2 } from './geom.js';
import { toast } from './ui.js';

const round2 = (v) => Math.round(v * 100) / 100;
const selectedObjects = () => S.selection.map(objById).filter((o) => o && o.type !== 'camera');

/** Selected objects without the ones already inside another selected group. */
export function topSelected() {
  const objs = selectedObjects();
  const ids = new Set(objs.map((o) => o.id));
  return objs.filter((o) => !ancestors(o).some((g) => ids.has(g.id)));
}

// ------------------------------------------------------------------ moving in the picture
function movableProps(o) {
  if (isGroup(o)) return ['offset'];
  const names = schemaOf(o).props.filter((p) => p.kind === 'vec2').map((p) => p.name);
  if (names.includes('position')) return ['position'];
  if (o.type === 'ellipse') return ['center'];
  if (o.type === 'arrow') return ['tail', 'tip'];
  if (names.includes('source') && (o.type === 'rays' || o.type === 'wavefront')) return ['source'];
  return [];
}

function dataScale(o) {
  const ref = isGroup(o) ? '' : valueAt(o, 'axes', S.time);
  if (!ref) return [1, 1];
  const ax = objById(ref);
  if (!ax) return [1, 1];
  const xr = valueAt(ax, 'x_range', S.time), yr = valueAt(ax, 'y_range', S.time), sz = valueAt(ax, 'size', S.time);
  return [(xr[1] - xr[0]) / sz[0], -(yr[1] - yr[0]) / sz[1]];
}

/** How each object moves when it is dragged by a screen offset (design px). */
export function movePlan(ids) {
  const plan = [];
  for (const id of ids) {
    const o = objById(id);
    if (!o || o.locked || id === 'camera') continue;
    if (ancestors(o).some((g) => ids.includes(g.id))) continue;    // its group moves it
    const kids = isGroup(o) ? descendants(id).filter((d) => !isGroup(d)) : [];
    const only3d = isGroup(o) && kids.length > 0 && kids.every((d) => schemaOf(d).is3d);
    if (schemaOf(o).is3d || only3d) {
      const d3 = drag3dProps(o);
      if (!d3) continue;
      const start = Object.fromEntries(d3.props.map((p) => [p, [...valueAt(o, p, S.time)].map(Number)]));
      plan.push({ id, kind: '3d', props: d3.props, start, anchor: d3.anchor.map(Number), space: o.parent || null });
    } else {
      const props = movableProps(o);
      if (!props.length) continue;
      const start = Object.fromEntries(props.map((p) => [p, [...valueAt(o, p, S.time)].map(Number)]));
      const [sx, sy] = dataScale(o);
      const a = scale2(o.parent || null);
      plan.push({ id, kind: '2d', props, start, sx: sx / a, sy: sy / a });
    }
  }
  return plan;
}

/** Apply one plan entry for a screen offset; call inside commit(). */
export function applyMove(m, dx, dy, lockAxis = false) {
  const x = objById(m.id);
  if (!x) return;
  if (m.kind === '2d') {
    for (const p of m.props) setValue(x, p, [round2(m.start[p][0] + dx * m.sx), round2(m.start[p][1] + dy * m.sy)]);
  } else {
    const d = dragDelta(m.anchor, m.space, dx, dy, lockAxis);
    for (const p of m.props) setValue(x, p, m.start[p].map((v, i) => round2(v + d[i])));
  }
}

const boxOf = (id) => S.boxes.find((b) => b.id === id);

/** Align the selection's boxes: mode is left, center, right, top, middle or bottom. */
export function align(mode) {
  const objs = topSelected();
  const items = objs.map((o) => ({ o, b: boxOf(o.id) })).filter((x) => x.b);
  if (items.length < 2) { toast('Select two or more objects that are visible at this time.'); return; }
  const x0 = Math.min(...items.map((i) => i.b.x0)), x1 = Math.max(...items.map((i) => i.b.x1));
  const y0 = Math.min(...items.map((i) => i.b.y0)), y1 = Math.max(...items.map((i) => i.b.y1));
  const plan = movePlan(items.map((i) => i.o.id));
  let moved = 0;
  commit(() => {
    for (const m of plan) {
      const b = boxOf(m.id);
      let dx = 0, dy = 0;
      if (mode === 'left') dx = x0 - b.x0;
      else if (mode === 'right') dx = x1 - b.x1;
      else if (mode === 'center') dx = (x0 + x1) / 2 - (b.x0 + b.x1) / 2;
      else if (mode === 'top') dy = y0 - b.y0;
      else if (mode === 'bottom') dy = y1 - b.y1;
      else if (mode === 'middle') dy = (y0 + y1) / 2 - (b.y0 + b.y1) / 2;
      if (Math.abs(dx) + Math.abs(dy) > 1e-6) { applyMove(m, dx, dy); moved += 1; }
    }
  }, { source: 'align' });
  skippedNote(objs.length - items.length, plan.length < items.length);
  return moved;
}

/** Spread the selection so the gaps between neighbouring boxes are equal. axis: 'h' or 'v'. */
export function distribute(axis) {
  const objs = topSelected();
  const items = objs.map((o) => ({ o, b: boxOf(o.id) })).filter((x) => x.b);
  if (items.length < 3) { toast('Select three or more objects that are visible at this time.'); return; }
  const lo = axis === 'h' ? 'x0' : 'y0', hi = axis === 'h' ? 'x1' : 'y1';
  items.sort((a, b) => (a.b[lo] + a.b[hi]) - (b.b[lo] + b.b[hi]));
  const first = items[0].b, last = items[items.length - 1].b;
  const total = items.reduce((s, i) => s + (i.b[hi] - i.b[lo]), 0);
  const gap = (last[hi] - first[lo] - total) / (items.length - 1);
  const plan = Object.fromEntries(movePlan(items.map((i) => i.o.id)).map((m) => [m.id, m]));
  commit(() => {
    let pos = first[hi] + gap;
    for (const it of items.slice(1, -1)) {
      const d = pos - it.b[lo];
      const m = plan[it.o.id];
      if (m) applyMove(m, axis === 'h' ? d : 0, axis === 'h' ? 0 : d);
      pos += it.b[hi] - it.b[lo] + gap;
    }
  }, { source: 'distribute' });
  skippedNote(objs.length - items.length, Object.keys(plan).length < items.length);
}

function skippedNote(hidden, fixed) {
  if (hidden > 0) toast(`${hidden} selected object${hidden > 1 ? 's are' : ' is'} not visible at this time and stayed in place.`);
  else if (fixed) toast('Some selected objects have no position to change and stayed in place.');
}

// ------------------------------------------------------------------ timing
function shiftTiming(o, dt) {
  o.start = Math.max(0, Math.min((o.start || 0) + dt, duration() - 0.05));
  if (o.end != null) o.end = Math.min(duration(), Math.max(o.end + dt, o.start + 0.05));
  for (const ks of Object.values(o.keys || {})) for (const k of ks) k.t = Math.max(0, Math.round((k.t + dt) * fps()) / fps());
}

/** Start each selected object ``step`` seconds after the previous one (earlier start first, ties in drawing order). */
/** Move the selected clips (with their keyframes and group members) by dt seconds: Alt+arrow keys. */
export function nudgeSelected(dt) {
  const ids = topSelected().map((o) => o.id);
  if (!ids.length) return false;
  commit(() => {
    for (const id of ids) {
      const members = [objById(id), ...(isGroup(objById(id)) ? descendants(id) : [])].map((x) => objById(x.id));
      const step = Math.max(dt, -Math.min(...members.map((x) => x.start || 0)));
      for (const x of members) shiftTiming(x, step);
    }
  }, { source: 'timeline', coalesce: `nudge:${ids.join(',')}` });
  return true;
}

/** Start ([) or end (]) the selected clips at the playhead. */
export function trimSelected(edge) {
  const ids = S.selection.filter((id) => id !== 'camera' && objById(id));
  if (!ids.length) return false;
  commit(() => {
    for (const id of ids) {
      const o = objById(id);
      if (edge === 'start') o.start = Math.round(Math.min(S.time, o.end != null ? o.end - 0.05 : S.time) * 1000) / 1000;
      else o.end = Math.round(Math.max(S.time, o.start + 0.05) * 1000) / 1000;
    }
  }, { source: 'timeline' });
  return true;
}

export function stagger(step) {
  const objs = topSelected();
  if (objs.length < 2) { toast('Select two or more objects to stagger.'); return; }
  const order = S.project.objects;
  objs.sort((a, b) => span(a)[0] - span(b)[0] || order.indexOf(a) - order.indexOf(b));
  const t0 = span(objs[0])[0];
  commit(() => {
    objs.forEach((o, i) => {
      const dt = t0 + i * step - span(o)[0];
      if (Math.abs(dt) < 1e-9) return;
      for (const x of [o, ...(isGroup(o) ? descendants(o.id) : [])]) shiftTiming(objById(x.id), dt);
    });
  }, { source: 'stagger' });
}

// ------------------------------------------------------------------ groups
/** Put the selected objects in a new group (members become neighbours, at the top-most place). */
export function groupSelection() {
  const members = topSelected();
  if (!members.length) return null;
  const ids = new Set(members.map((m) => m.id));
  const parents = new Set(members.map((m) => m.parent || null));
  let parent = parents.size === 1 ? [...parents][0] : null;
  if (parent && (ids.has(parent) || !isGroup(objById(parent)))) parent = null;
  const gid = uniqueId('group');
  const g = {
    id: gid, type: 'group', name: nextName('Group'), props: {}, keys: {}, start: 0, end: null, parent,
    enter: { effect: 'none', duration: 0.6 }, exit: { effect: 'none', duration: 0.6 },
  };
  commit((p) => {
    // members of the selected objects come along, so a nested group stays in one block
    const block = new Set(ids);
    for (const m of members) if (isGroup(m)) for (const d of descendants(m.id)) block.add(d.id);
    const top = Math.max(...p.objects.map((o, i) => (block.has(o.id) ? i : -1)));
    const before = p.objects.slice(0, top).filter((o) => !block.has(o.id)).length;
    const rest = p.objects.filter((o) => !block.has(o.id));
    const ordered = p.objects.filter((o) => block.has(o.id));
    p.objects = [...rest.slice(0, before), ...ordered, g, ...rest.slice(before)];
    for (const o of p.objects) if (ids.has(o.id)) o.parent = gid;
  }, { source: 'group' });
  select(gid);
  return gid;
}

/** Dissolve groups: their members keep their place and move up one level. */
export function ungroup(ids = S.selection) {
  const groups = ids.map(objById).filter(isGroup);
  if (!groups.length) return;
  const freed = [];
  commit((p) => {
    for (const g of groups) {
      for (const c of p.objects) if (c.parent === g.id) { c.parent = g.parent || null; freed.push(c.id); }
      p.objects = p.objects.filter((o) => o.id !== g.id);
    }
  }, { source: 'ungroup' });
  select(null);
  for (const id of freed) if (objById(id)) select(id, 'add');
}

/** Move an object into a group (or out of all groups with null), next to the group's other members. */
export function setParent(id, gid) {
  const o = objById(id);
  if (!o || (gid && (gid === id || descendants(id).some((d) => d.id === gid)))) return;
  commit((p) => {
    const x = p.objects.find((y) => y.id === id);
    x.parent = gid || null;
    if (gid) {
      const block = new Set([id, ...descendants(id).map((d) => d.id)]);
      const moving = p.objects.filter((y) => block.has(y.id));
      const rest = p.objects.filter((y) => !block.has(y.id));
      const gi = rest.findIndex((y) => y.id === gid);
      rest.splice(gi, 0, ...moving);                  // just below the group's row: its top member
      p.objects = rest;
    }
  }, { source: 'parent' });
}

function nextName(base) {
  const used = new Set(S.project.objects.map((o) => o.name));
  if (!used.has(base)) return base;
  let i = 2;
  while (used.has(`${base} ${i}`)) i += 1;
  return `${base} ${i}`;
}

// ------------------------------------------------------------------ delete, duplicate
/** Delete the selected objects (a group goes with its members). */
export function removeSelected() {
  const objs = selectedObjects();
  if (!objs.length) return;
  const gone = new Set();
  for (const o of objs) {
    gone.add(o.id);
    if (isGroup(o)) for (const d of descendants(o.id)) gone.add(d.id);
  }
  commit((p) => { p.objects = p.objects.filter((o) => !gone.has(o.id)); }, { source: 'delete' });
  select(null);
}

/** Objects (with members of groups), in drawing order, as plain JSON. */
function gather(objs) {
  const ids = new Set();
  for (const o of objs) {
    ids.add(o.id);
    if (isGroup(o)) for (const d of descendants(o.id)) ids.add(d.id);
  }
  return S.project.objects.filter((o) => ids.has(o.id)).map((o) => JSON.parse(JSON.stringify(o)));
}

/**
 * Add copies of ``list`` to the project: new ids, references and groups between the copies
 * follow the copies, timing shifted by ``dt``. Inserted after ``afterId`` (or on top).
 */
function insertCopies(list, { dt = 0, afterId = null, rename = true } = {}) {
  const used = new Set(S.project.objects.map((o) => o.id));
  const names = new Set(S.project.objects.map((o) => o.name));
  const map = {};
  for (const o of list) {
    let base = String(o.type || 'object').replace(/[^a-z0-9_]/gi, '') || 'object';
    let i = 1;
    while (used.has(`${base}${i}`)) i += 1;
    map[o.id] = `${base}${i}`;
    used.add(map[o.id]);
  }
  const copies = list.map((o) => {
    const c = JSON.parse(JSON.stringify(o));
    c.id = map[o.id];
    c.scene = currentScene().id;                 // pasted into the scene in view
    if (rename && names.has(c.name)) c.name = `${c.name} copy`;
    if (c.parent && map[c.parent]) c.parent = map[c.parent];
    else if (c.parent && !isGroup(objById(c.parent))) c.parent = null;
    const sc = S.types[c.type];
    for (const p of sc ? sc.props : []) {
      if (p.kind !== 'ref') continue;
      if (typeof c.props?.[p.name] === 'string' && map[c.props[p.name]]) c.props[p.name] = map[c.props[p.name]];
      for (const k of c.keys?.[p.name] || []) if (map[k.v]) k.v = map[k.v];
    }
    if (dt) {
      c.start = Math.max(0, Math.min((c.start || 0) + dt, duration() - 0.05));
      if (c.end != null) c.end = Math.max(c.start + 0.05, c.end + dt);
      for (const ks of Object.values(c.keys || {})) for (const k of ks) k.t = Math.max(0, Math.round((k.t + dt) * fps()) / fps());
    }
    return c;
  });
  commit((p) => {
    const at = afterId ? p.objects.findIndex((o) => o.id === afterId) + 1 : p.objects.length;
    p.objects.splice(at > 0 ? at : p.objects.length, 0, ...copies);
  }, { source: 'paste' });
  const copyIds = new Set(copies.map((c) => c.id));
  const tops = copies.filter((c) => !c.parent || !copyIds.has(c.parent));
  select(null);
  for (const c of tops) select(c.id, 'add');
  return copies;
}

export function duplicateSelected() {
  const objs = topSelected();
  if (!objs.length) return;
  const list = gather(objs);
  const lastId = list[list.length - 1].id;
  insertCopies(list, { afterId: lastId });
}

// ------------------------------------------------------------------ clipboard
let memory = null;      // fallback when the system clipboard is not available
export const lastCopied = () => memory;

/** The clipboard text for the current selection (a keyframe if one is picked in the timeline). */
export function copyText() {
  if (S.selKey) {
    const o = objById(S.selKey.id);
    if (o) {
      const keys = {};
      for (const [name, ks] of Object.entries(o.keys || {})) {
        const k = ks.find((x) => Math.abs(x.t - S.selKey.t) < 1e-6);
        if (k) keys[name] = { v: k.v, ease: k.ease, ...(k.bez ? { bez: k.bez } : {}) };
      }
      if (Object.keys(keys).length) return JSON.stringify({ sciview: 'keys', type: o.type, keys });
    }
  }
  const objs = topSelected();
  if (!objs.length) return null;
  return JSON.stringify({ sciview: 'objects', version: S.version, t0: S.time, objects: gather(objs) });
}

export function copySelection(clipboardData) {
  const text = copyText();
  if (!text) return false;
  memory = text;
  if (clipboardData) clipboardData.setData('text/plain', text);
  const n = JSON.parse(text);
  toast(n.sciview === 'keys' ? 'Copied the keyframe' : `Copied ${topSelected().length === 1 ? '1 object' : `${topSelected().length} objects`}`);
  return true;
}

export function cutSelection(clipboardData) {
  if (S.selKey) return copySelection(clipboardData);     // keys: copy only
  if (!copySelection(clipboardData)) return false;
  removeSelected();
  return true;
}

/** Paste objects (timing kept relative to the playhead) or keyframes (at the playhead). */
export function pasteText(text) {
  let data;
  try { data = JSON.parse(text ?? memory ?? ''); } catch { return false; }
  if (!data || typeof data !== 'object') return false;
  if (data.sciview === 'keys') {
    const targets = selectedObjects();
    if (!targets.length) { toast('Select an object to paste the keyframe into.'); return true; }
    let n = 0;
    commit(() => {
      for (const o of targets) {
        const sc = schemaOf(o);
        for (const [name, k] of Object.entries(data.keys || {})) {
          if (!sc.props.some((p) => p.name === name && p.animatable)) continue;
          setKey(o, name, S.time, JSON.parse(JSON.stringify(k.v)), k.ease, k.bez);
          n += 1;
        }
      }
    }, { source: 'paste-keys' });
    toast(n ? 'Pasted the keyframe at the playhead' : 'Nothing to paste: the keyframe is for other values.');
    return true;
  }
  if (data.sciview !== 'objects' || !Array.isArray(data.objects)) return false;
  const known = data.objects.filter((o) => o && S.types[o.type]);
  if (!known.length) { toast('Nothing to paste: these objects are unknown to this version.', 'err'); return true; }
  const dt = Number.isFinite(data.t0) ? S.time - data.t0 : 0;
  insertCopies(known, { dt });
  toast(known.length === 1 ? 'Pasted 1 object' : `Pasted ${known.length} objects`);
  return true;
}

export { selectedObjects };
