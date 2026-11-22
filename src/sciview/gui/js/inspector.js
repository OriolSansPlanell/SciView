// Right-hand panel: properties of the selected object, the camera, or the film.
import {
  S, on, emit, commit, objById, schemaOf, valueAt, isAnimated, keyIndexAt, setValue, setKey, removeKey,
  colorCss, duration, EASINGS, BEZIER_PRESETS, cubicBezier, uniqueId, select, isGroup, children, descendants,
  issuesFor,
} from './state.js';
import {
  groupSelection, ungroup, align, distribute, stagger, removeSelected, duplicateSelected, setParent, topSelected,
} from './actions.js';
import { el, toast, popover, closePopover, round, drag, fmtTime } from './ui.js';
import { icon } from './icons.js';
import { api } from './api.js';

const root = document.getElementById('inspector');
let syncers = [];
const collapsed = new Set(['Label', 'Sound', 'Scattering']);

const EFFECT_LABEL = {
  none: 'None', fade: 'Fade', slide_up: 'Slide up', slide_down: 'Slide down', slide_left: 'Slide left',
  slide_right: 'Slide right', pop: 'Pop', draw: 'Draw on', typewriter: 'Type on',
};

let rowsByProp = new Map();
let issueBox = null;
let issueKey = '';

export function renderInspector() {
  closePopover();
  root.innerHTML = '';
  syncers = [];
  rowsByProp = new Map();
  issueBox = null;
  issueKey = '';
  const many = S.selection.filter((id) => id !== 'camera' && objById(id));
  const obj = objById(S.selected);
  if (many.length > 1) renderMulti(many.map(objById));
  else if (!obj) renderFilm();
  else renderObject(obj);
  syncIssues();
}

export function refreshInspector() {
  for (const f of syncers) f();
}

/** Show the selected object's problems in the header and under the fields they concern. */
export function syncIssues() {
  const id = S.selection.length === 1 ? S.selected : null;
  const list = id && id !== 'camera' ? issuesFor(id) : [];
  const key = JSON.stringify(list.map((p) => [p.prop, p.message]));
  if (key === issueKey) return;
  issueKey = key;
  for (const [, row] of rowsByProp) {
    row.classList.remove('has-issue');
    row.querySelector('.field-issue')?.remove();
  }
  if (issueBox) {
    issueBox.innerHTML = '';
    issueBox.hidden = !list.length;
    for (const p of list) {
      issueBox.append(el('div', { class: 'issue' }, el('span', { class: 'ic', html: icon('warning') }), el('span', {}, p.message)));
    }
  }
  for (const p of list) {
    const row = p.prop && rowsByProp.get(p.prop);
    if (!row) continue;
    row.classList.add('has-issue');
    if (!row.querySelector('.field-issue')) row.append(el('div', { class: 'field-issue', role: 'note' }, p.message));
  }
}

// ------------------------------------------------------------------ bindings
function objBinding(id, name) {
  return {
    animatable: true,
    get: () => { const o = objById(id); return o ? valueAt(o, name, S.time) : undefined; },
    set: (v, live = true) => commit(() => { const o = objById(id); if (o) setValue(o, name, v); },
      { coalesce: `${id}.${name}`, source: 'inspector', live }),
    obj: () => objById(id),
    name,
  };
}

function settingBinding(name) {
  return {
    animatable: false,
    get: () => S.project.settings[name],
    set: (v) => commit((p) => { p.settings[name] = v; }, { coalesce: `settings.${name}`, source: 'inspector', settings: true }),
    name,
  };
}

// ------------------------------------------------------------------ object panel
function renderObject(obj) {
  const sc = schemaOf(obj);
  const id = obj.id;
  const isCam = obj.type === 'camera';
  const nameInput = el('input', {
    class: 'insp-name', value: obj.name || sc.label, 'aria-label': 'Object name', disabled: isCam,
    oninput: (e) => commit(() => { const o = objById(id); if (o) o.name = e.target.value; }, { coalesce: `${id}.name`, source: 'inspector' }),
  });
  root.append(el('div', { class: 'insp-head' }, el('span', { class: 'lib-icon', html: icon(sc.icon) }), nameInput));
  root.append(el('div', { class: 'insp-type' }, isCam ? 'Drag in the preview to orbit, scroll to zoom. Keyframe the values to move the camera.' : sc.description || sc.label));
  issueBox = el('div', { class: 'insp-issues', role: 'status', hidden: true });
  root.append(issueBox);

  if (isGroup(obj)) root.append(membersGroup(obj));
  if (!isCam) root.append(timingGroup(obj, sc));

  const groups = [];
  for (const p of sc.props) {
    let g = groups.find((x) => x.name === p.group);
    if (!g) groups.push(g = { name: p.group, props: [] });
    g.props.push(p);
  }
  for (const g of groups) {
    const body = el('div', { class: 'group-body' });
    for (const p of g.props) {
      const row = makeRow(p, objBinding(id, p.name));
      rowsByProp.set(p.name, row);
      body.append(row);
    }
    root.append(group(g.name, body));
  }

  const kf = keyframeList(obj);
  if (kf) root.append(group('Keyframes', kf));
  if (!isCam) root.append(group('Data tracks', trackList(obj)));

  if (!isCam) {
    root.append(el('div', { class: 'insp-actions' },
      isGroup(obj) ? el('button', { class: 'btn', onclick: () => ungroup([id]), title: 'Ungroup (Ctrl+Shift+G)' }, 'Ungroup') : null,
      el('button', { class: 'btn', onclick: () => duplicate(id), title: 'Duplicate (Ctrl+D)' }, 'Duplicate'),
      el('button', { class: 'btn', onclick: () => move(id, -1), title: 'Draw above the object before it' }, 'Bring forward'),
      el('button', { class: 'btn', onclick: () => move(id, 1) }, 'Send back'),
      el('button', { class: 'btn danger', onclick: () => removeObject(id), title: 'Delete (Del)' }, 'Delete')));
  }
}

function membersGroup(g) {
  const list = el('div', { class: 'members' });
  const kids = children(g.id).reverse();
  for (const c of kids) {
    const csc = schemaOf(c);
    list.append(el('button', { class: 'member', onclick: () => select(c.id), title: `Select ${c.name}` },
      el('span', { class: 'ic', html: icon(csc ? csc.icon : 'square') }), el('span', {}, c.name || c.id)));
  }
  if (!kids.length) list.append(el('div', { class: 'help' }, 'This group is empty. Move objects into it with “In group” in their Timing section.'));
  return group('Members', el('div', { class: 'group-body' }, list,
    el('div', { class: 'help' }, 'The group moves, scales, fades and times all of its members together. Double-click a member in the preview to select it.')));
}

// ------------------------------------------------------------------ several objects
function renderMulti(objs) {
  const tops = topSelected();
  const types = new Set(objs.map((o) => o.type));
  root.append(el('div', { class: 'insp-head' }, el('span', { class: 'lib-icon', html: icon('group') }),
    el('span', { class: 'insp-title' }, `${objs.length} objects selected`)));
  root.append(el('div', { class: 'insp-type' }, 'Shift-click to add or remove objects. Changes below apply to all of them.'));

  const btn = (label, ic, fn, title) => el('button', { class: 'btn icon-label', onclick: fn, title: title || label },
    el('span', { class: 'ic', html: icon(ic) }), label);
  const arrange = el('div', { class: 'group-body arrange' },
    el('div', { class: 'btn-row', role: 'group', 'aria-label': 'Align' },
      btn('Left', 'alignLeft', () => align('left'), 'Align left edges'),
      btn('Centre', 'alignCenter', () => align('center'), 'Align centres horizontally'),
      btn('Right', 'alignRight', () => align('right'), 'Align right edges')),
    el('div', { class: 'btn-row', role: 'group', 'aria-label': 'Align vertically' },
      btn('Top', 'alignTop', () => align('top'), 'Align top edges'),
      btn('Middle', 'alignMiddle', () => align('middle'), 'Align centres vertically'),
      btn('Bottom', 'alignBottom', () => align('bottom'), 'Align bottom edges')),
    el('div', { class: 'btn-row', role: 'group', 'aria-label': 'Distribute' },
      btn('Spread across', 'distH', () => distribute('h'), 'Equal gaps from left to right (three or more objects)'),
      btn('Spread down', 'distV', () => distribute('v'), 'Equal gaps from top to bottom (three or more objects)')),
    el('div', { class: 'help' }, 'Uses where the objects are in the picture at the playhead.'));
  root.append(group('Arrange', arrange));

  const step = el('input', { type: 'number', step: 0.05, min: 0, value: 0.3, 'aria-label': 'Delay between objects (s)' });
  root.append(group('Timing', el('div', { class: 'group-body' },
    el('div', { class: 'row' }, el('span', { class: 'lbl' }, 'Delay (s)'), el('div', { class: 'ctl' }, step), el('span')),
    el('div', { class: 'insp-actions', style: { padding: '6px 0 0' } },
      el('button', { class: 'btn', onclick: () => stagger(Math.max(0, Number(step.value) || 0)) }, 'Stagger')),
    el('div', { class: 'help' }, 'Starts each object this long after the one before: earlier ones first, then in the order they were added. Keyframes move with them.'))));

  if (types.size === 1) {
    const sc = schemaOf(objs[0]);
    const ids = objs.map((o) => o.id);
    const groups = [];
    for (const p of sc.props) {
      let g = groups.find((x) => x.name === p.group);
      if (!g) groups.push(g = { name: p.group, props: [] });
      g.props.push(p);
    }
    for (const g of groups) {
      const body = el('div', { class: 'group-body' });
      for (const p of g.props) body.append(makeRow(p, multiBinding(ids, p.name)));
      root.append(group(g.name, body));
    }
  } else {
    root.append(el('p', { class: 'insp-hint' }, 'Select objects of one kind to edit their values together.'));
  }

  root.append(el('div', { class: 'insp-actions' },
    el('button', { class: 'btn primary', onclick: () => groupSelection(), title: 'Group (Ctrl+G)', disabled: !tops.length }, 'Group'),
    objs.some(isGroup) ? el('button', { class: 'btn', onclick: () => ungroup(), title: 'Ungroup (Ctrl+Shift+G)' }, 'Ungroup') : null,
    el('button', { class: 'btn', onclick: () => duplicateSelected(), title: 'Duplicate (Ctrl+D)' }, 'Duplicate'),
    el('button', { class: 'btn danger', onclick: () => removeSelected(), title: 'Delete (Del)' }, 'Delete')));
}

function multiBinding(ids, name) {
  const primary = () => objById(S.selected) || objById(ids[0]);
  return {
    animatable: true,
    ids,
    get: () => { const o = primary(); return o ? valueAt(o, name, S.time) : undefined; },
    set: (v, live = true) => commit(() => {
      for (const id of ids) { const o = objById(id); if (o) setValue(o, name, JSON.parse(JSON.stringify(v))); }
    }, { coalesce: `multi.${name}`, source: 'inspector', live }),
    obj: primary,
    name,
  };
}

function group(name, body) {
  const d = el('details', { class: 'group', open: !collapsed.has(name) }, el('summary', {}, name), body);
  d.addEventListener('toggle', () => { if (d.open) collapsed.delete(name); else collapsed.add(name); });
  return d;
}

function timingGroup(obj, sc) {
  const id = obj.id;
  const num = (val, placeholder, onset, step = 0.1) => {
    const i = el('input', { type: 'number', step, value: val == null ? '' : round(val, 0.001), placeholder });
    i.addEventListener('change', () => onset(i.value === '' ? null : Number(i.value)));
    return i;
  };
  const effSel = (cur, onset) => {
    const s = el('select', { 'aria-label': 'Effect' }, sc.effects.map((e) => el('option', { value: e, selected: e === cur }, EFFECT_LABEL[e] || e)));
    s.addEventListener('change', () => onset(s.value));
    return s;
  };
  const upd = (fn) => commit(() => { const o = objById(id); if (o) fn(o); }, { source: 'inspector-timing' });
  const body = el('div', { class: 'timing' },
    el('label', { class: 'cell' }, el('span', {}, 'Appears at (s)'),
      num(obj.start, '0', (v) => upd((o) => { o.start = Math.max(0, v || 0); }))),
    el('label', { class: 'cell' }, el('span', {}, 'Disappears at (s)'),
      num(obj.end, 'end of film', (v) => upd((o) => { o.end = v == null ? null : Math.max(v, (o.start || 0) + 0.05); }))),
    el('div', { class: 'cell' }, el('span', {}, 'Enter with'),
      el('div', { class: 'pair' }, effSel(obj.enter.effect, (v) => upd((o) => { o.enter.effect = v; })),
        num(obj.enter.duration, 's', (v) => upd((o) => { o.enter.duration = Math.max(0, v || 0); }), 0.1))),
    el('div', { class: 'cell' }, el('span', {}, 'Exit with'),
      el('div', { class: 'pair' }, effSel(obj.exit.effect, (v) => upd((o) => { o.exit.effect = v; })),
        num(obj.exit.duration, 's', (v) => upd((o) => { o.exit.duration = Math.max(0, v || 0); }), 0.1))));
  const note = obj.end == null ? el('div', { class: 'help', style: { padding: '0 14px 10px' } }, 'The exit effect plays only when a disappear time is set.') : null;
  const inside = new Set([id, ...descendants(id).map((d) => d.id)]);
  const groupsList = S.project.objects.filter((o) => isGroup(o) && !inside.has(o.id));
  let parentRow = null;
  if (groupsList.length || obj.parent) {
    const sel = el('select', { 'aria-label': 'In group' },
      el('option', { value: '' }, 'None'),
      groupsList.map((g) => el('option', { value: g.id, selected: g.id === obj.parent }, g.name || g.id)));
    if (obj.parent && !groupsList.some((g) => g.id === obj.parent)) sel.append(el('option', { value: obj.parent, selected: true }, `${obj.parent} (missing)`));
    sel.addEventListener('change', () => setParent(id, sel.value || null));
    parentRow = el('label', { class: 'cell wide' }, el('span', {}, 'In group'), sel);
    body.append(parentRow);
    rowsByProp.set('parent', parentRow);
  }
  return group('Timing', el('div', {}, body, note));
}

function keyframeList(obj) {
  const rows = [];
  const sc = schemaOf(obj);
  for (const [name, ks] of Object.entries(obj.keys || {})) {
    const p = sc.props.find((x) => x.name === name);
    ks.forEach((k, idx) => rows.push({ name, label: p ? p.label : name, k, idx }));
  }
  if (!rows.length) return null;
  rows.sort((a, b) => a.k.t - b.k.t || a.label.localeCompare(b.label));
  const id = obj.id;
  const list = el('div', { class: 'kflist' });
  for (const r of rows) {
    const cur = r.k.ease || 'smooth';
    const ease = el('select', { 'aria-label': 'Easing into this keyframe', title: 'How the value eases into this keyframe' },
      EASINGS.map((e) => el('option', { value: e, selected: e === cur }, e === 'bezier' ? 'custom' : e.replace('_', ' '))));
    const curve = el('button', { class: 'icon-btn small curve-btn', title: 'Edit the easing curve', 'aria-label': `Edit the easing curve of ${r.label}` });
    const showCurve = () => {
      const o = objById(id);
      const k = o && o.keys[r.name] ? o.keys[r.name].find((x) => Math.abs(x.t - r.k.t) < 1e-6) : null;
      const e = k ? k.ease || 'smooth' : cur;
      curve.innerHTML = curveSvg(e === 'bezier' ? k.bez : null, e);
      curve.classList.toggle('dim', e !== 'bezier');
      if (document.activeElement !== ease) ease.value = e;
    };
    showCurve();
    ease.addEventListener('change', () => {
      commit(() => {
        const k = objById(id).keys[r.name][r.idx];
        k.ease = ease.value;
        if (ease.value === 'bezier' && !k.bez) k.bez = [...BEZIER_PRESETS.ease];
      }, { source: 'inspector' });
      showCurve();
      if (ease.value === 'bezier') curveEditor(curve, id, r.name, r.k.t, showCurve);
    });
    curve.addEventListener('click', () => curveEditor(curve, id, r.name, r.k.t, showCurve));
    list.append(el('div', { class: 'kfrow' },
      el('span', { class: 'diamond', html: icon('diamond') }),
      el('span', { class: 'nm', title: r.label }, r.label),
      el('button', { class: 't', title: 'Go to this keyframe', onclick: () => emit('seek', r.k.t) }, fmtTime(r.k.t)),
      ease, curve,
      el('button', { class: 'kf', title: 'Delete keyframe', html: icon('close'),
        onclick: () => commit(() => removeKey(objById(id), r.name, r.idx), { source: 'kf-list' }) })));
  }
  return el('div', { class: 'group-body' }, list,
    el('div', { class: 'help' }, 'Gold labels mark animated values. Change one at another time to add a keyframe there. The easing sets how the value moves into each keyframe.'));
}

// ------------------------------------------------------------------ data tracks
function trackList(obj) {
  const id = obj.id;
  const sc = schemaOf(obj);
  const numeric = sc.props.filter((p) => ['number', 'int', 'vec2', 'vec3'].includes(p.kind));
  const tables = S.assets.filter((a) => ['table', 'array', 'sequence'].includes(a.kind));
  const body = el('div', { class: 'group-body tracks' });
  const tracks = obj.tracks || {};
  const edit = (name, patch) => commit(() => {
    const o = objById(id);
    o.tracks ||= {};
    o.tracks[name] = { ...o.tracks[name], ...patch };
  }, { source: 'tracks' });
  for (const [name, tr] of Object.entries(tracks)) {
    const p = sc.props.find((x) => x.name === name);
    const need = p && p.kind === 'vec3' ? 3 : p && p.kind === 'vec2' ? 2 : 1;
    const file = el('select', { 'aria-label': `Data file for ${name}` },
      el('option', { value: '' }, 'Choose a table…'),
      tables.map((a) => el('option', { value: a.path, selected: a.path === tr.data }, a.path.replace(/^assets\//, ''))));
    if (tr.data && !tables.some((a) => a.path === tr.data)) file.append(el('option', { value: tr.data, selected: true }, tr.data));
    file.addEventListener('change', () => edit(name, { data: file.value }));
    const txt = (key, label, ph) => {
      const inp = el('input', { type: 'text', value: tr[key] ?? '', placeholder: ph, 'aria-label': `${label} (${name})`, spellcheck: 'false' });
      inp.addEventListener('change', () => edit(name, { [key]: inp.value.trim() }));
      if (tr.data) api.columns(tr.data).then((r) => {
        const dl = el('datalist', { id: `cols-${id}-${name}-${key}` }, r.columns.map((c) => el('option', { value: c })));
        inp.setAttribute('list', dl.id);
        inp.after(dl);
      }).catch(() => {});
      return el('label', { class: 'cell' }, el('span', {}, label), inp);
    };
    const num = (key, label) => {
      const inp = el('input', { type: 'number', step: 'any', value: tr[key] ?? (key.endsWith('scale') ? 1 : 0), 'aria-label': `${label} (${name})` });
      inp.addEventListener('change', () => { const v = Number(inp.value); if (Number.isFinite(v)) edit(name, { [key]: v }); });
      return el('label', { class: 'cell' }, el('span', {}, label), inp);
    };
    const remove = el('button', { class: 'icon-btn small', title: 'Remove this data track', 'aria-label': `Remove the data track of ${name}`, html: icon('close') });
    remove.addEventListener('click', () => commit(() => {
      const o = objById(id);
      delete o.tracks[name];
      if (!Object.keys(o.tracks).length) delete o.tracks;
    }, { source: 'tracks' }));
    body.append(el('div', { class: 'track' },
      el('div', { class: 'track-head' }, el('span', { class: 'ic', html: icon('streamlines') }),
        el('strong', {}, p ? p.label : name), el('span', { class: 'spacer' }), remove),
      el('div', { class: 'track-file' }, file),
      el('div', { class: 'timing' },
        txt('time', 'Time column', 't'), txt('column', need > 1 ? `Columns (${need})` : 'Value column', need > 1 ? 'x, y' : 'value'),
        num('scale', 'Scale'), num('offset', 'Offset'), num('time_offset', 'Starts at (s)'), num('time_scale', 'Time scale'))));
  }
  const free = numeric.filter((p) => !(p.name in tracks));
  if (free.length) {
    const pick = el('select', { 'aria-label': 'Property to drive from data' }, free.map((p) => el('option', { value: p.name }, p.label)));
    const add = el('button', { class: 'btn small' }, 'Add');
    add.addEventListener('click', () => commit(() => {
      const o = objById(id);
      o.tracks ||= {};
      o.tracks[pick.value] = { data: tables.length ? tables[0].path : '', column: '', time: 't', scale: 1, offset: 0,
        time_scale: 1, time_offset: 0, smooth: true };
    }, { source: 'tracks' }));
    body.append(el('div', { class: 'track-add' }, pick, add));
  }
  body.append(el('div', { class: 'help' }, 'Drive a value from a table column over time: a temperature log, a simulation, a scan. '
    + 'The time column is in seconds of the film (shift it with Starts at).'));
  return body;
}

// ------------------------------------------------------------------ easing curve editor
function curvePoints(bez, name) {
  const pts = [];
  for (let i = 0; i <= 24; i++) {
    const u = i / 24;
    let v;
    if (bez) v = cubicBezier(...bez, u);
    else if (name === 'linear') v = u;
    else if (name === 'hold') v = u < 1 ? 0 : 1;
    else if (name === 'in') v = u ** 3;
    else if (name === 'out') v = 1 - (1 - u) ** 3;
    else if (name === 'sine') v = 0.5 - 0.5 * Math.cos(Math.PI * u);
    else if (name === 'overshoot') v = 1 + 2.70158 * (u - 1) ** 3 + 1.70158 * (u - 1) ** 2;
    else if (name === 'smoother') v = u * u * u * (u * (u * 6 - 15) + 10);
    else v = u * u * (3 - 2 * u);
    pts.push([u, v]);
  }
  return pts;
}

function curveSvg(bez, name) {
  const pts = curvePoints(bez, name).map(([u, v]) => `${(2 + u * 16).toFixed(2)},${(16 - v * 12).toFixed(2)}`).join(' ');
  return `<svg viewBox="0 0 20 20" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`;
}

function curveEditor(anchor, id, name, t, onChange = () => {}) {
  const W = 220, H = 220, PAD = 30;
  const Y0 = -0.5, Y1 = 1.5;                       // vertical room for overshoot
  const keyNow = () => {
    const o = objById(id);
    const ks = o && o.keys[name];
    return ks ? ks.find((k) => Math.abs(k.t - t) < 1e-6) : null;
  };
  if (!keyNow()) return;
  const dpr = window.devicePixelRatio || 1;
  const cv = el('canvas', { width: W * dpr, height: H * dpr, style: { width: `${W}px`, height: `${H}px` }, class: 'curve-canvas',
    'aria-label': 'Easing curve. Drag the two round handles.', role: 'img' });
  const px = (x, y) => [PAD + x * (W - 2 * PAD), PAD + (Y1 - y) / (Y1 - Y0) * (H - 2 * PAD)];
  const ux = (cx, cy) => [(cx - PAD) / (W - 2 * PAD), Y1 - ((cy - PAD) / (H - 2 * PAD)) * (Y1 - Y0)];
  const inputs = [0, 1, 2, 3].map((i) => el('input', { type: 'number', step: 0.01, 'aria-label': ['x1', 'y1', 'x2', 'y2'][i] }));
  const bez = () => {
    const k = keyNow();
    return k && k.ease === 'bezier' && Array.isArray(k.bez) ? k.bez.map(Number) : [...BEZIER_PRESETS.ease];
  };
  const tag = `bez-${id}-${name}-${t}-${Date.now()}`;
  const setBez = (b, live = true) => {
    const v = [Math.min(1, Math.max(0, b[0])), Math.min(Y1, Math.max(Y0, b[1])), Math.min(1, Math.max(0, b[2])), Math.min(Y1, Math.max(Y0, b[3]))]
      .map((x) => Math.round(x * 1000) / 1000);
    commit(() => { const k = keyNow(); if (k) { k.ease = 'bezier'; k.bez = v; } }, { coalesce: tag, source: 'inspector', live });
    draw();
    onChange();
  };
  const draw = () => {
    const b = bez();
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    g.strokeStyle = 'rgba(226,232,243,.12)';
    g.lineWidth = 1;
    const [ax, ay] = px(0, 0), [bx, by] = px(1, 1);
    g.strokeRect(ax, by, bx - ax, ay - by);
    g.setLineDash([3, 3]);
    g.beginPath(); g.moveTo(ax, ay); g.lineTo(bx, by); g.stroke();
    g.setLineDash([]);
    const [h1x, h1y] = px(b[0], b[1]), [h2x, h2y] = px(b[2], b[3]);
    g.strokeStyle = 'rgba(79,209,197,.55)';
    g.beginPath(); g.moveTo(ax, ay); g.lineTo(h1x, h1y); g.moveTo(bx, by); g.lineTo(h2x, h2y); g.stroke();
    g.strokeStyle = '#f2c14e';
    g.lineWidth = 2;
    g.beginPath();
    for (let i = 0; i <= 60; i++) {
      const u = i / 60;
      const [x, y] = px(u, cubicBezier(...b, u));
      if (i) g.lineTo(x, y); else g.moveTo(x, y);
    }
    g.stroke();
    for (const [x, y] of [[h1x, h1y], [h2x, h2y]]) {
      g.fillStyle = '#4fd1c5';
      g.beginPath(); g.arc(x, y, 6, 0, Math.PI * 2); g.fill();
    }
    inputs.forEach((inp, i) => { if (document.activeElement !== inp) inp.value = b[i]; });
  };
  cv.addEventListener('pointerdown', (e) => {
    const r = cv.getBoundingClientRect();
    const cx = e.clientX - r.left, cy = e.clientY - r.top;
    const b = bez();
    const d1 = Math.hypot(cx - px(b[0], b[1])[0], cy - px(b[0], b[1])[1]);
    const d2 = Math.hypot(cx - px(b[2], b[3])[0], cy - px(b[2], b[3])[1]);
    const which = d1 <= d2 ? 0 : 2;
    if (Math.min(d1, d2) > 24) return;
    e.preventDefault();
    const move = (ev) => {
      const [u, v] = ux(ev.clientX - r.left, ev.clientY - r.top);
      const nb = bez();
      nb[which] = u;
      nb[which + 1] = v;
      setBez(nb);
    };
    move(e);
    drag(e, (_dx, _dy, ev) => move(ev));
  });
  inputs.forEach((inp, i) => inp.addEventListener('change', () => {
    const v = Number(inp.value);
    if (!Number.isFinite(v)) return;
    const b = bez();
    b[i] = v;
    setBez(b, false);
  }));
  const presets = el('div', { class: 'curve-presets' }, Object.entries(BEZIER_PRESETS).map(([nm, b]) =>
    el('button', { class: 'chip', title: b.join(', '), onclick: () => setBez(b, false) }, nm)));
  popover(anchor, el('div', { class: 'curve-pop' },
    el('div', { class: 'curve-title' }, 'Easing into this keyframe'),
    cv,
    el('div', { class: 'curve-nums' }, inputs.map((inp, i) => el('label', {}, el('span', {}, ['x1', 'y1', 'x2', 'y2'][i]), inp))),
    presets,
    el('div', { class: 'help' }, 'Horizontal: time between the two keyframes. Vertical: how far the value has moved. Above the box overshoots.')));
  draw();
}

// ------------------------------------------------------------------ film panel
function renderFilm() {
  root.append(el('div', { class: 'insp-head' }, el('span', { class: 'lib-icon', html: icon('film') }),
    el('span', { class: 'insp-title' }, 'Film settings')));
  root.append(el('p', { class: 'insp-hint' }, S.project.objects.length
    ? 'Select an object in the preview or the timeline to edit it.'
    : 'Add objects from the list on the left, or start from a template with New.'));
  if (S.problems.length) {
    root.append(group('Problems', el('ul', { class: 'issue-list' }, S.problems.map((p) => {
      const o = p.id ? objById(p.id) : null;
      return el('li', {}, o ? el('button', { class: 'link', onclick: () => select(o.id) }, o.name || o.id) : null, o ? ': ' : '', p.message);
    }))));
  }
  const groups = [];
  for (const p of S.settingsSchema) {
    let g = groups.find((x) => x.name === p.group);
    if (!g) groups.push(g = { name: p.group, props: [] });
    g.props.push(p);
  }
  for (const g of groups) {
    const body = el('div', { class: 'group-body' });
    for (const p of g.props) body.append(makeRow(p, settingBinding(p.name)));
    if (g.name === 'Look') {
      body.append(el('div', { class: 'insp-actions', style: { padding: '8px 0 0' } },
        el('button', { class: 'btn', onclick: () => applyTheme('dark') }, 'Neon on navy'),
        el('button', { class: 'btn', onclick: () => applyTheme('light') }, 'Light for papers')));
    }
    root.append(group(g.name, body));
  }
  // palette
  const grid = el('div', { class: 'palette-grid' });
  for (const [name, hex] of Object.entries(S.project.palette)) {
    const inp = el('input', { type: 'color', value: colorCss(hex), 'aria-label': `Palette colour ${name}` });
    inp.addEventListener('input', () => commit((p) => { p.palette[name] = inp.value; }, { coalesce: `pal.${name}`, source: 'inspector', settings: true }));
    grid.append(el('label', {}, inp, name));
  }
  root.append(group('Palette', el('div', { class: 'group-body' }, grid,
    el('div', { class: 'help' }, 'Objects that use a colour name follow the palette, so changing it here recolours the whole film.'))));
  root.append(el('div', { class: 'insp-actions' },
    el('a', { class: 'btn', href: '/api/captions.srt', download: 'captions.srt', title: 'Captions as a subtitle file' }, 'Download subtitles (.srt)')));
}

function applyTheme(kind) {
  commit((p) => {
    if (kind === 'light') {
      p.palette = { ...S.lightPalette };
      Object.assign(p.settings, { background: '#ffffff', background2: '#f4f6fa', background_style: 'vertical', stars: 0, vignette: 0, bloom: 0.15 });
    } else {
      p.palette = { ...S.defaultPalette };
      Object.assign(p.settings, { background: '#03070e', background2: '#111a2c', background_style: 'radial', stars: 0.4, vignette: 0.35, bloom: 0.7 });
    }
  }, { source: 'theme' });
}

// ------------------------------------------------------------------ rows and controls
function makeRow(p, b) {
  const wide = p.kind === 'longtext' || p.kind === 'array';
  const row = el('div', { class: `row ${wide ? 'wide' : ''}` });
  const lbl = el('span', { class: 'lbl', title: p.help ? `${p.label}: ${p.help}` : p.label }, p.label);
  const ctl = control(p, b, lbl);
  row.append(lbl, ctl.node);
  let kfBtn = null;
  if (b.animatable && p.animatable) {
    kfBtn = el('button', { class: 'kf', 'aria-label': `Keyframe ${p.label}` });
    kfBtn.addEventListener('click', () => toggleKey(b));
    row.append(kfBtn);
  } else {
    row.append(el('span'));
  }
  if (wide && p.help) row.append(el('div', { class: 'help' }, p.help));
  const sync = () => {
    if (b.obj) {
      const o = b.obj();
      if (!o) return;
      const anim = isAnimated(o, p.name);
      row.classList.toggle('animated', anim);
      const tracked = !!(o.tracks && o.tracks[p.name]);
      row.classList.toggle('tracked', tracked);
      lbl.title = tracked ? `${p.label}: follows a data track (see Data tracks)` : (p.help ? `${p.label}: ${p.help}` : p.label);
      if (kfBtn) {
        const on = keyIndexAt(o, p.name, S.time) >= 0;
        kfBtn.className = `kf ${on ? 'on' : anim ? 'has' : ''}`;
        kfBtn.innerHTML = icon(on ? 'diamond' : 'diamondo');
        kfBtn.title = on ? 'Remove the keyframe at this time' : anim ? 'Add a keyframe at this time' : 'Animate: add a keyframe at this time';
      }
    }
    ctl.sync();
  };
  sync();
  syncers.push(sync);
  return row;
}

function toggleKey(b) {
  const ids = b.ids || [b.obj().id];
  const name = b.name;
  const on = keyIndexAt(b.obj(), name, S.time) >= 0;
  commit(() => {
    for (const id of ids) {
      const o = objById(id);
      if (!o) continue;
      const i = keyIndexAt(o, name, S.time);
      if (on && i >= 0) removeKey(o, name, i);
      else if (!on && i < 0) setKey(o, name, S.time, valueAt(o, name, S.time));
    }
  }, { source: 'kf-toggle' });
}

function focused(node) { return node.contains(document.activeElement); }

function numberInput(p, getter, setter, lbl, extra = {}) {
  const step = p.step || (p.kind === 'int' ? 1 : 0.1);
  const inp = el('input', { type: 'number', step, ...extra });
  const parse = (v) => {
    let x = Number(v);
    if (!Number.isFinite(x)) return null;
    if (p.kind === 'int') x = Math.round(x);
    if (p.min != null) x = Math.max(p.min, x);
    if (p.max != null) x = Math.min(p.max, x);
    return x;
  };
  inp.addEventListener('input', () => { const x = parse(inp.value); if (x != null && inp.value !== '') setter(x); });
  inp.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      const mult = e.shiftKey ? 10 : e.altKey ? 0.1 : 1;
      const x = parse(Number(getter() || 0) + (e.key === 'ArrowUp' ? 1 : -1) * step * mult);
      if (x != null) { setter(round(x, step * (e.altKey ? 0.1 : 1))); inp.value = round(x, step * 0.1); }
    }
  });
  if (lbl) {
    lbl.classList.add('scrub');
    lbl.addEventListener('pointerdown', (e) => {
      const v0 = Number(getter() || 0);
      document.body.style.cursor = 'ew-resize';
      drag(e, (dx, _dy, ev) => {
        const mult = ev.shiftKey ? 10 : ev.altKey ? 0.1 : 1;
        const x = parse(v0 + dx * step * 0.5 * mult);
        if (x != null) { const r = round(x, step * (ev.altKey ? 0.1 : 1)); setter(r); inp.value = r; }
      }, () => { document.body.style.cursor = ''; });
    });
  }
  return inp;
}

function control(p, b, lbl) {
  const wrap = el('div', { class: 'ctl' });
  let sync = () => {};
  const k = p.kind;
  if (k === 'number' || k === 'int') {
    const inp = numberInput(p, b.get, (v) => b.set(v), lbl, { 'aria-label': p.label });
    wrap.append(inp);
    sync = () => { if (!focused(inp)) inp.value = round(Number(b.get()), (p.step || 0.1) * 0.1); };
  } else if (k === 'bool') {
    const t = el('button', { class: 'toggle-switch', role: 'switch', 'aria-label': p.label });
    t.addEventListener('click', () => b.set(!b.get()));
    wrap.append(t);
    sync = () => t.setAttribute('aria-checked', b.get() ? 'true' : 'false');
  } else if (k === 'text') {
    const inp = el('input', { type: 'text', 'aria-label': p.label, spellcheck: 'false' });
    inp.addEventListener('input', () => b.set(inp.value));
    wrap.append(inp);
    if (/(_column|^column|color_by)$/.test(p.name) && b.obj) attachColumns(inp, b);
    sync = () => { if (!focused(inp)) inp.value = b.get() ?? ''; };
  } else if (k === 'longtext' || k === 'array') {
    const ta = el('textarea', { class: k === 'array' ? 'data' : '', rows: k === 'array' ? 2 : 3, 'aria-label': p.label, spellcheck: k === 'longtext' ? 'true' : 'false' });
    ta.addEventListener('input', () => b.set(ta.value));
    wrap.append(ta);
    sync = () => {
      if (focused(ta)) return;
      const v = b.get();
      ta.value = Array.isArray(v) ? v.join(', ') : (v ?? '');
    };
  } else if (k === 'enum') {
    const s = el('select', { 'aria-label': p.label }, (p.options || []).map((o) => el('option', { value: o }, o.replace(/_/g, ' '))));
    s.addEventListener('change', () => b.set(s.value));
    wrap.append(s);
    sync = () => { s.value = b.get(); };
  } else if (k === 'color') {
    const sw = el('button', { class: 'swatch', 'aria-label': `Pick ${p.label}` });
    const inp = el('input', { type: 'text', 'aria-label': p.label, spellcheck: 'false' });
    inp.addEventListener('change', () => b.set(inp.value.trim()));
    sw.addEventListener('click', () => colorPopover(sw, b));
    wrap.append(sw, inp);
    sync = () => {
      const v = b.get();
      sw.style.background = colorCss(v);
      if (!focused(inp)) inp.value = v;
    };
  } else if (k === 'vec2' || k === 'vec3') {
    const n = k === 'vec2' ? 2 : 3;
    const axes = n === 2 ? ['x', 'y'] : ['x', 'y', 'z'];
    const box = el('div', { class: `vec n${n}` });
    const inputs = axes.map((a, i) => {
      const getter = () => (b.get() || [])[i];
      const setter = (v) => { const cur = [...(b.get() || [0, 0, 0])]; cur[i] = v; b.set(cur.slice(0, n)); };
      const tag = el('span', {}, a);
      const inp = numberInput({ ...p, kind: 'number', min: null, max: null }, getter, setter, tag, { 'aria-label': `${p.label} ${a}` });
      box.append(el('label', {}, tag, inp));
      return inp;
    });
    wrap.append(box);
    sync = () => {
      const v = b.get() || [];
      inputs.forEach((inp, i) => { if (!focused(inp)) inp.value = round(Number(v[i] ?? 0), (p.step || 0.1) * 0.1); });
    };
  } else if (k === 'asset') {
    const s = el('select', { 'aria-label': p.label });
    const up = el('button', { class: 'icon-btn small', title: 'Upload files (several make a sequence, one file per step)', html: icon('upload') });
    const pattern = el('input', { type: 'text', class: 'pattern', placeholder: 'assets/scan/*.tif', spellcheck: 'false', hidden: true,
      'aria-label': `${p.label} file pattern`, title: 'A file pattern shows one file per step: assets/run/step_*.csv' });
    const isPattern = (v) => /[*?[]/.test(v || '');
    const fill = () => {
      const cur = b.get() || '';
      const kinds = ASSET_KINDS[p.accept] || [p.accept];
      const opts = S.assets.filter((a) => !p.accept || kinds.includes(a.kind));
      s.innerHTML = '';
      s.append(el('option', { value: '' }, 'None'));
      for (const a of opts) s.append(el('option', { value: a.path }, a.path.replace(/^assets\//, '') + (a.missing ? ' (missing)' : '')));
      if (cur && !isPattern(cur) && !opts.some((a) => a.path === cur)) s.append(el('option', { value: cur }, cur));
      if (p.accept !== 'molecule' && p.accept !== 'mesh' && p.accept !== 'audio') s.append(el('option', { value: '__pattern__' }, 'File pattern…'));
      s.value = isPattern(cur) ? '__pattern__' : cur;
      pattern.hidden = !isPattern(cur) && s.value !== '__pattern__';
      if (!focused(pattern) && isPattern(cur)) pattern.value = cur;
    };
    s.addEventListener('change', () => {
      if (s.value === '__pattern__') { pattern.hidden = false; pattern.focus(); return; }
      b.set(s.value);
    });
    pattern.addEventListener('change', () => { if (pattern.value.trim()) b.set(pattern.value.trim()); });
    up.addEventListener('click', async () => {
      const files = await pickFiles(p.accept, true);
      const added = [];
      for (const f of files) {
        try {
          const info = await api.upload(f);
          S.assets.push(info);
          added.push(info.path);
        } catch (e) { toast(`Upload failed: ${e.message}`, 'err'); }
      }
      if (added.length === 1) { b.set(added[0]); toast(`Added ${files[0].name}`); }
      else if (added.length > 1) {
        const pat = commonPattern(added);
        b.set(pat);
        toast(`Added ${added.length} files as a sequence: ${pat}`);
      }
      fill();
    });
    wrap.append(el('div', { class: 'asset-ctl' }, s, up), pattern);
    sync = fill;
  } else if (k === 'ref') {
    const s = el('select', { 'aria-label': p.label });
    const fill = () => {
      const cur = b.get() || '';
      s.innerHTML = '';
      s.append(el('option', { value: '' }, 'None'));
      const self = b.obj ? b.obj() : null;
      for (const o of S.project.objects.filter((x) => (p.ref ? x.type === p.ref : x.type !== 'group') && (!self || x.id !== self.id))) {
        s.append(el('option', { value: o.id }, p.ref ? (o.name || o.id) : `${o.name || o.id} (${(S.types[o.type] || {}).label || o.type})`));
      }
      if (cur && !S.project.objects.some((x) => x.id === cur)) s.append(el('option', { value: cur }, `${cur} (missing)`));
      s.value = cur;
    };
    s.addEventListener('change', () => b.set(s.value));
    wrap.append(s);
    sync = fill;
  } else if (k === 'font') {
    const s = el('select', { 'aria-label': p.label }, [...S.fonts, 'Custom font file'].map((f) => el('option', { value: f }, f)));
    const inp = el('input', { type: 'text', placeholder: '/path/to/font.ttf', spellcheck: 'false' });
    s.addEventListener('change', () => { if (s.value !== 'Custom font file') b.set(s.value); else { inp.hidden = false; inp.focus(); } });
    inp.addEventListener('change', () => b.set(inp.value.trim()));
    const box = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '4px', width: '100%' } }, s, inp);
    wrap.append(box);
    sync = () => {
      const v = b.get();
      const custom = !S.fonts.includes(v);
      s.value = custom ? 'Custom font file' : v;
      inp.hidden = !custom;
      if (custom && !focused(inp)) inp.value = v;
    };
  } else {
    wrap.append(el('span', {}, String(b.get())));
  }
  return { node: wrap, sync };
}

function colorPopover(anchor, b) {
  const cur = String(b.get() || '').toLowerCase();
  const grid = el('div', { class: 'sw-grid' });
  for (const name of Object.keys(S.project.palette)) {
    grid.append(el('button', {
      class: `sw ${cur === name ? 'sel' : ''}`, title: name, 'aria-label': name, style: { background: colorCss(name) },
      onclick: () => { b.set(name); closePopover(); },
    }));
  }
  const native = el('input', { type: 'color', value: colorCss(cur) });
  native.addEventListener('input', () => b.set(native.value));
  popover(anchor, el('div', {}, grid, el('label', { class: 'custom' }, native, 'Custom colour'),
    el('div', { class: 'help', style: { marginTop: '8px' } }, 'Palette colours follow the film palette.')));
}

const columnCache = new Map();
function attachColumns(inp, b) {
  const listId = `cols-${Math.random().toString(36).slice(2)}`;
  const dl = el('datalist', { id: listId });
  inp.setAttribute('list', listId);
  inp.after(dl);
  const o = b.obj();
  const data = o && valueAt(o, 'data', S.time);
  if (!data) return;
  const fill = (cols) => { dl.innerHTML = ''; cols.forEach((c) => dl.append(el('option', { value: c }))); };
  if (columnCache.has(data)) fill(columnCache.get(data));
  else api.columns(data).then((r) => { columnCache.set(data, r.columns); fill(r.columns); }).catch(() => {});
}

const ASSET_KINDS = {
  image: ['image', 'array', 'sequence'], table: ['table', 'array', 'sequence'],
  volume: ['volume', 'image', 'array', 'sequence'], molecule: ['molecule'], mesh: ['mesh'], audio: ['audio'],
};

/** "assets/step_001.csv", "assets/step_002.csv" -> "assets/step_*.csv" */
export function commonPattern(paths) {
  let pre = paths[0];
  for (const x of paths) while (!x.startsWith(pre)) pre = pre.slice(0, -1);
  const exts = new Set(paths.map((x) => (x.match(/\.[^./]+$/) || [''])[0]));
  pre = pre.replace(/\d+$/, '');
  return `${pre}*${exts.size === 1 ? [...exts][0] : ''}`;
}

export function pickFiles(accept, multiple = false) {
  const map = {
    image: '.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp,.npy', table: '.csv,.tsv,.txt,.dat,.npy,.npz', mesh: '.stl,.obj',
    audio: '.wav,.mp3,.m4a,.aac,.ogg,.flac', volume: '.npy,.tif,.tiff,.h5,.hdf5,.nxs,.png', molecule: '.pdb,.xyz,.ent',
  };
  return new Promise((resolve) => {
    const fi = document.getElementById('fileInput');
    fi.value = '';
    fi.multiple = multiple;
    fi.accept = map[accept] || '';
    fi.onchange = () => resolve([...fi.files]);
    fi.click();
  });
}

// ------------------------------------------------------------------ object actions
export function duplicate(id) {
  const o = objById(id);
  if (!o || id === 'camera') return;
  if (S.selection.length > 1 || isGroup(o)) { duplicateSelected(); return; }
  const copy = JSON.parse(JSON.stringify(o));
  copy.id = uniqueId(o.type);
  copy.name = `${o.name} copy`;
  commit((p) => { p.objects.splice(p.objects.indexOf(objById(id)) + 1, 0, copy); }, { source: 'dup' });
  select(copy.id);
}

export function removeObject(id) {
  if (!id || id === 'camera') return;
  if (!S.selection.includes(id)) select(id);
  removeSelected();
}

/**
 * dir -1 = draw later (on top), +1 = draw earlier. The timeline lists the top-most object first.
 * Moves past the neighbour at the same group level; a group moves with its members.
 */
export function move(id, dir) {
  commit((p) => {
    const me = p.objects.find((o) => o.id === id);
    if (!me) return;
    const blockOf = (o) => new Set([o.id, ...(isGroup(o) ? descendants(o.id).map((d) => d.id) : [])]);
    const mine = blockOf(me);
    const level = p.objects.filter((o) => (o.parent || null) === (me.parent || null) || (me.parent && !objById(me.parent) && !o.parent));
    const k = level.indexOf(me);
    const other = level[k - dir];
    if (!other) return;
    const theirs = blockOf(other);
    const a = p.objects.filter((o) => mine.has(o.id));
    const b = p.objects.filter((o) => theirs.has(o.id));
    const rest = p.objects.filter((o) => !mine.has(o.id) && !theirs.has(o.id));
    const firstIdx = Math.min(...[...mine, ...theirs].map((x) => p.objects.findIndex((o) => o.id === x)));
    const at = p.objects.slice(0, firstIdx).filter((o) => !mine.has(o.id) && !theirs.has(o.id)).length;
    rest.splice(at, 0, ...(dir < 0 ? [...b, ...a] : [...a, ...b]));
    p.objects = rest;
  }, { source: 'move' });
}

export function addObject(type, extra = {}) {
  const sc = S.types[type];
  if (!sc) return null;
  const id = uniqueId(type);
  const start = Math.round(Math.min(S.time, Math.max(0, duration() - 0.5)) * 10) / 10;
  const obj = {
    id, type, name: sc.label, props: {}, keys: {}, start,
    end: sc.default_duration ? Math.min(duration(), start + sc.default_duration) : null,
    enter: { effect: sc.default_enter, duration: 0.6 }, exit: { effect: sc.default_exit, duration: 0.6 },
  };
  // sensible links: series go into the most recent chart
  const axesProp = sc.props.find((p) => p.kind === 'ref' && p.ref === 'axes' && p.group === 'Axes');
  if (axesProp) {
    const ax = [...S.project.objects].reverse().find((o) => o.type === 'axes');
    if (ax) obj.props.axes = ax.id;
  }
  Object.assign(obj.props, extra);
  // inside the open group when a group (or one of its members) is selected
  const cur = objById(S.selected);
  const into = cur && cur.type !== 'camera' ? (isGroup(cur) ? cur.id : cur.parent || null) : null;
  if (into && isGroup(objById(into))) obj.parent = into;
  commit((p) => {
    if (obj.parent) {
      const gi = p.objects.findIndex((o) => o.id === obj.parent);
      p.objects.splice(gi, 0, obj);
    } else p.objects.push(obj);
  }, { source: 'add' });
  select(id);
  if (axesProp && !obj.props.axes) toast('Add a Chart axes object, then pick it in this series’ Axes field.');
  return obj;
}

on('time', () => refreshInspector());
on('issues', () => syncIssues());
on('frame', () => syncIssues());
