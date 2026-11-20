// Right-hand panel: properties of the selected object, the camera, or the film.
import {
  S, on, emit, commit, objById, schemaOf, valueAt, isAnimated, keyIndexAt, setValue, setKey, removeKey,
  colorCss, fps, duration, EASINGS, uniqueId, span,
} from './state.js';
import { el, iconEl, toast, popover, closePopover, round, drag, fmtTime } from './ui.js';
import { icon } from './icons.js';
import { api } from './api.js';

const root = document.getElementById('inspector');
let syncers = [];
const collapsed = new Set(['Label', 'Sound', 'Scattering']);

const EFFECT_LABEL = {
  none: 'None', fade: 'Fade', slide_up: 'Slide up', slide_down: 'Slide down', slide_left: 'Slide left',
  slide_right: 'Slide right', pop: 'Pop', draw: 'Draw on', typewriter: 'Type on',
};

export function renderInspector() {
  closePopover();
  root.innerHTML = '';
  syncers = [];
  const obj = objById(S.selected);
  if (!obj) renderFilm();
  else renderObject(obj);
}

export function refreshInspector() {
  for (const f of syncers) f();
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

  if (!isCam) root.append(timingGroup(obj, sc));

  const groups = [];
  for (const p of sc.props) {
    let g = groups.find((x) => x.name === p.group);
    if (!g) groups.push(g = { name: p.group, props: [] });
    g.props.push(p);
  }
  for (const g of groups) {
    const body = el('div', { class: 'group-body' });
    for (const p of g.props) body.append(makeRow(p, objBinding(id, p.name)));
    root.append(group(g.name, body));
  }

  const kf = keyframeList(obj);
  if (kf) root.append(group('Keyframes', kf));

  if (!isCam) {
    root.append(el('div', { class: 'insp-actions' },
      el('button', { class: 'btn', onclick: () => duplicate(id), title: 'Duplicate (Ctrl+D)' }, 'Duplicate'),
      el('button', { class: 'btn', onclick: () => move(id, -1), title: 'Draw above the object before it' }, 'Bring forward'),
      el('button', { class: 'btn', onclick: () => move(id, 1) }, 'Send back'),
      el('button', { class: 'btn danger', onclick: () => removeObject(id), title: 'Delete (Del)' }, 'Delete')));
  }
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
    const ease = el('select', { 'aria-label': 'Easing into this keyframe', title: 'How the value eases into this keyframe' },
      EASINGS.map((e) => el('option', { value: e, selected: e === (r.k.ease || 'smooth') }, e.replace('_', ' '))));
    ease.addEventListener('change', () => commit(() => { const o = objById(id); o.keys[r.name][r.idx].ease = ease.value; }, { source: 'inspector' }));
    list.append(el('div', { class: 'kfrow' },
      el('span', { class: 'diamond', html: icon('diamond') }),
      el('span', { class: 'nm', title: r.label }, r.label),
      el('button', { class: 't', title: 'Go to this keyframe', onclick: () => emit('seek', r.k.t) }, fmtTime(r.k.t)),
      ease,
      el('button', { class: 'kf', title: 'Delete keyframe', html: icon('close'),
        onclick: () => commit(() => removeKey(objById(id), r.name, r.idx), { source: 'kf-list' }) })));
  }
  return el('div', { class: 'group-body' }, list,
    el('div', { class: 'help' }, 'Gold labels mark animated values. Change one at another time to add a keyframe there.'));
}

// ------------------------------------------------------------------ film panel
function renderFilm() {
  root.append(el('div', { class: 'insp-head' }, el('span', { class: 'lib-icon', html: icon('film') }),
    el('span', { class: 'insp-title' }, 'Film settings')));
  root.append(el('p', { class: 'insp-hint' }, S.project.objects.length
    ? 'Select an object in the preview or the timeline to edit it.'
    : 'Add objects from the list on the left, or start from a template with New.'));
  if (S.issues.length) {
    root.append(group('Problems', el('ul', { class: 'issue-list' }, S.issues.map((i) => el('li', {}, i)))));
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
  const id = b.obj().id;
  const name = b.name;
  commit(() => {
    const o = objById(id);
    const i = keyIndexAt(o, name, S.time);
    if (i >= 0) removeKey(o, name, i);
    else setKey(o, name, S.time, valueAt(o, name, S.time));
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
    const up = el('button', { class: 'icon-btn small', title: 'Upload a file', html: icon('upload') });
    const fill = () => {
      const cur = b.get() || '';
      const kinds = p.accept === 'image' ? ['image', 'array'] : p.accept === 'table' ? ['table', 'array'] : [p.accept];
      const opts = S.assets.filter((a) => !p.accept || kinds.includes(a.kind));
      s.innerHTML = '';
      s.append(el('option', { value: '' }, 'None'));
      for (const a of opts) s.append(el('option', { value: a.path }, a.path.replace(/^assets\//, '') + (a.missing ? ' (missing)' : '')));
      if (cur && !opts.some((a) => a.path === cur)) s.append(el('option', { value: cur }, cur));
      s.value = cur;
    };
    s.addEventListener('change', () => b.set(s.value));
    up.addEventListener('click', async () => {
      const files = await pickFiles(p.accept);
      for (const f of files) {
        try {
          const info = await api.upload(f);
          S.assets.push(info);
          b.set(info.path);
          toast(`Added ${f.name}`);
        } catch (e) { toast(`Upload failed: ${e.message}`, 'err'); }
      }
      fill();
    });
    wrap.append(s, up);
    sync = fill;
  } else if (k === 'ref') {
    const s = el('select', { 'aria-label': p.label });
    const fill = () => {
      const cur = b.get() || '';
      s.innerHTML = '';
      s.append(el('option', { value: '' }, 'None'));
      for (const o of S.project.objects.filter((x) => !p.ref || x.type === p.ref)) s.append(el('option', { value: o.id }, o.name || o.id));
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

export function pickFiles(accept) {
  const map = { image: '.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp,.npy', table: '.csv,.tsv,.txt,.dat,.npy,.npz', mesh: '.stl,.obj', audio: '.wav,.mp3,.m4a,.aac,.ogg,.flac' };
  return new Promise((resolve) => {
    const fi = document.getElementById('fileInput');
    fi.value = '';
    fi.accept = map[accept] || '';
    fi.onchange = () => resolve([...fi.files]);
    fi.click();
  });
}

// ------------------------------------------------------------------ object actions
export function duplicate(id) {
  const o = objById(id);
  if (!o || id === 'camera') return;
  const copy = JSON.parse(JSON.stringify(o));
  copy.id = uniqueId(o.type);
  copy.name = `${o.name} copy`;
  commit((p) => { p.objects.splice(p.objects.indexOf(objById(id)) + 1, 0, copy); }, { source: 'dup' });
  emit('select', copy.id);
}

export function removeObject(id) {
  if (!id || id === 'camera') return;
  commit((p) => { p.objects = p.objects.filter((o) => o.id !== id); }, { source: 'delete' });
  emit('select', null);
}

/** dir -1 = draw later (on top), +1 = draw earlier. The timeline lists the top-most object first. */
export function move(id, dir) {
  commit((p) => {
    const i = p.objects.findIndex((o) => o.id === id);
    const j = i - dir;
    if (i < 0 || j < 0 || j >= p.objects.length) return;
    const [o] = p.objects.splice(i, 1);
    p.objects.splice(j, 0, o);
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
  commit((p) => { p.objects.push(obj); }, { source: 'add' });
  emit('select', id);
  if (axesProp && !obj.props.axes) toast('Add a Chart axes object, then pick it in this series’ Axes field.');
  return obj;
}

on('time', () => refreshInspector());
