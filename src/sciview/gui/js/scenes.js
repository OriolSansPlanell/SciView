// Scenes: the strip above the timeline, switching scenes and the scene's own panel in the inspector.
import {
  S, emit, commit, scenes, currentScene, sceneCamera, overlap, sceneStart, filmDuration, syncDuration, select,
} from './state.js';
import { el, toast, fmtTime } from './ui.js';
import { icon } from './icons.js';

const $ = (id) => document.getElementById(id);

const TRANSITION_ICONS = { cut: 'cut', crossfade: 'crossfade', dip: 'crossfade', zoom: 'crossfade' };
const transIcon = (kind) => TRANSITION_ICONS[kind] || (kind.startsWith('push') ? 'push' : 'wipe');

/** Show another scene in the timeline (its own clock starts at 0). */
export function switchScene(id, { keepSelection = false, time = null } = {}) {
  if (!scenes().some((sc) => sc.id === id)) return;
  const changed = id !== S.scene;
  S.scene = id;
  if (time != null) S.time = time;
  if (changed && !keepSelection) {
    S.selection = [];
    S.selected = null;
    S.selKey = null;
  }
  if (changed) emit('scene');
}

function uniqueSceneId() {
  const used = new Set(scenes().map((sc) => sc.id));
  let i = scenes().length + 1;
  while (used.has(`scene${i}`)) i += 1;
  return `scene${i}`;
}

/** The camera at the end of a scene, as plain values (a new scene starts there). */
function endCamera(sc) {
  const cam = sceneCamera(sc);
  const props = JSON.parse(JSON.stringify(cam.props || {}));
  for (const [name, keys] of Object.entries(cam.keys || {})) {
    if (keys && keys.length) props[name] = JSON.parse(JSON.stringify(keys[keys.length - 1].v ?? keys[keys.length - 1].value));
  }
  return { id: 'camera', type: 'camera', name: 'Camera', props, keys: {} };
}

export function addScene(after = currentScene()) {
  const id = uniqueSceneId();
  commit((p) => {
    const i = p.scenes.indexOf(p.scenes.find((sc) => sc.id === after.id)) + 1;
    p.scenes.splice(i, 0, { id, name: `Scene ${p.scenes.length + 1}`, duration: 6, transition: 'crossfade',
      transition_duration: 0.8, camera: endCamera(after) });
    syncDuration();
  }, { source: 'scenes' });
  switchScene(id, { time: 0 });
  select('scene');
  toast('Added a scene. Objects you add now go into it.');
}

export function duplicateScene(sc = currentScene()) {
  const id = uniqueSceneId();
  commit((p) => {
    const i = p.scenes.findIndex((x) => x.id === sc.id);
    const copy = JSON.parse(JSON.stringify(p.scenes[i]));
    copy.id = id;
    copy.name = `${sc.name} (copy)`;
    copy.camera = JSON.parse(JSON.stringify(sceneCamera(p.scenes[i])));
    if (i === 0) { copy.transition = 'crossfade'; copy.transition_duration = 0.8; }
    p.scenes.splice(i + 1, 0, copy);
    // copy the objects, with new ids and their groups and references remapped
    const used = new Set(p.objects.map((o) => o.id));
    const map = {};
    for (const o of p.objects.filter((x) => x.scene === sc.id)) {
      let k = 1;
      const base = o.id.replace(/\d+$/, '');
      while (used.has(`${base}${k}`)) k += 1;
      map[o.id] = `${base}${k}`;
      used.add(map[o.id]);
    }
    const made = p.objects.filter((x) => x.scene === sc.id).map((o) => {
      const c = JSON.parse(JSON.stringify(o));
      c.id = map[o.id];
      c.scene = id;
      if (c.parent) c.parent = map[c.parent] || null;
      for (const [k, v] of Object.entries(c.props)) if (typeof v === 'string' && map[v] && k !== 'text') c.props[k] = map[v];
      return c;
    });
    p.objects.push(...made);
    syncDuration();
  }, { source: 'scenes' });
  switchScene(id, { time: 0 });
  select('scene');
}

export function deleteScene(sc = currentScene()) {
  if (scenes().length === 1) { toast('A film needs at least one scene', 'err'); return; }
  const i = scenes().indexOf(sc);
  const n = S.project.objects.filter((o) => o.scene === sc.id).length;
  commit((p) => {
    if (i === 0) {
      // the second scene becomes the first: its camera moves to the project's camera
      p.camera = p.scenes[1].camera;
      delete p.scenes[1].camera;
    }
    p.scenes.splice(i, 1);
    p.objects = p.objects.filter((o) => o.scene !== sc.id);
    syncDuration();
  }, { source: 'scenes' });
  switchScene(scenes()[Math.max(0, i - 1)].id, { time: 0 });
  toast(`Deleted ${sc.name}${n ? ` and its ${n} object${n === 1 ? '' : 's'}` : ''}. Ctrl+Z brings it back.`);
}

export function moveScene(sc, delta) {
  const i = scenes().indexOf(sc);
  const j = i + delta;
  if (j < 0 || j >= scenes().length) return;
  commit((p) => {
    // keep "the first scene's camera is the project's camera" true while swapping
    const cams = p.scenes.map((x, k) => (k === 0 ? p.camera : x.camera));
    const [m] = p.scenes.splice(i, 1);
    const [c] = cams.splice(i, 1);
    p.scenes.splice(j, 0, m);
    cams.splice(j, 0, c);
    p.scenes.forEach((x, k) => { if (k === 0) { p.camera = cams[0]; delete x.camera; } else x.camera = cams[k]; });
    syncDuration();
  }, { source: 'scenes' });
  emit('scene');
}

function editScene(id, fn, coalesce) {
  commit((p) => { fn(p.scenes.find((x) => x.id === id)); syncDuration(); },
    { source: 'scenes', coalesce: coalesce ? `scene.${id}.${coalesce}` : undefined });
}

// ------------------------------------------------------------------ the strip
export function renderScenes() {
  const root = $('scenes');
  if (!root || !S.project) return;
  root.innerHTML = '';
  const list = scenes();
  const cur = currentScene();
  list.forEach((sc, i) => {
    if (i > 0) {
      const kind = sc.transition || 'cut';
      const d = overlap(sc);
      root.append(el('button', {
        class: `scene-trans ${kind === 'cut' ? 'is-cut' : ''}`,
        title: `Into ${sc.name}: ${S.transitions[kind] || kind}${kind === 'cut' ? '' : `, ${d.toFixed(1)} s`}. Click to change.`,
        'aria-label': `Transition into ${sc.name}: ${S.transitions[kind] || kind}`,
        onclick: () => { switchScene(sc.id, { time: 0 }); select('scene'); },
      }, el('span', { class: 'ic', html: icon(transIcon(kind)) }), kind === 'cut' ? '' : el('span', {}, `${d.toFixed(1)} s`)));
    }
    const chip = el('button', {
      class: `scene-chip ${sc === cur ? 'current' : ''}`,
      'aria-pressed': String(sc === cur),
      title: `${sc.name}: ${sc.duration.toFixed(1)} s, starts at ${fmtTime(sceneStart(sc))} s in the film. Double-click to rename.`,
      onclick: () => { switchScene(sc.id); if (S.selected !== 'scene' || sc !== cur) select('scene'); },
      ondblclick: () => rename(chip, sc),
    }, el('span', { class: 'n' }, sc.name), el('span', { class: 'd' }, `${sc.duration.toFixed(1)} s`));
    root.append(chip);
  });
  root.append(el('button', { class: 'scene-add', title: 'Add a scene after this one', 'aria-label': 'Add a scene',
    onclick: () => addScene() }, el('span', { class: 'ic', html: icon('plus') }), 'Scene'));
  root.append(el('span', { class: 'scene-total', title: 'Length of the whole film' },
    `Film ${fmtTime(filmDuration())} s`));
}

function rename(chip, sc) {
  const inp = el('input', { class: 'scene-rename', value: sc.name, 'aria-label': 'Scene name', spellcheck: 'false' });
  chip.replaceWith(inp);
  inp.focus();
  inp.select();
  let done = false;
  const finish = (ok) => {
    if (done) return;
    done = true;
    const v = inp.value.trim();
    if (ok && v && v !== sc.name) editScene(sc.id, (x) => { x.name = v; });
    else renderScenes();
  };
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') finish(true); if (e.key === 'Escape') finish(false); });
  inp.addEventListener('blur', () => finish(true));
}

// ------------------------------------------------------------------ inspector
export function renderSceneInspector(root) {
  const sc = currentScene();
  const i = scenes().indexOf(sc);
  const id = sc.id;
  root.append(el('div', { class: 'insp-head' }, el('span', { class: 'lib-icon', html: icon('scene') }),
    el('span', { class: 'insp-title' }, sc.name), el('span', { class: 'insp-type' }, `Scene ${i + 1} of ${scenes().length}`)));
  const row = (label, ctl, help) => el('div', { class: 'row' }, el('span', { class: 'lbl', title: help || label }, label), el('div', { class: 'ctl' }, ctl));
  const name = el('input', { type: 'text', value: sc.name, 'aria-label': 'Scene name' });
  name.addEventListener('change', () => { if (name.value.trim()) editScene(id, (x) => { x.name = name.value.trim(); }); });
  const dur = el('input', { type: 'number', min: 0.1, step: 0.1, value: sc.duration, 'aria-label': 'Scene length in seconds' });
  dur.addEventListener('change', () => {
    const v = Number(dur.value);
    if (Number.isFinite(v) && v > 0) editScene(id, (x) => { x.duration = Math.max(0.1, v); });
  });
  const body = el('div', { class: 'group-body' },
    row('Name', name),
    row('Length (s)', dur, 'Objects keep their times inside the scene when you change its length'));
  if (i > 0) {
    const trans = el('select', { 'aria-label': 'Transition into this scene' },
      Object.entries(S.transitions).map(([k, label]) => el('option', { value: k, selected: k === sc.transition }, label)));
    trans.addEventListener('change', () => editScene(id, (x) => { x.transition = trans.value; }));
    const td = el('input', { type: 'number', min: 0, step: 0.1, value: sc.transition_duration, disabled: sc.transition === 'cut',
      'aria-label': 'Transition length in seconds' });
    td.addEventListener('change', () => {
      const v = Number(td.value);
      if (Number.isFinite(v) && v >= 0) editScene(id, (x) => { x.transition_duration = v; });
    });
    body.append(row('Comes in with', trans), row('Transition (s)', td,
      'The transition overlaps the end of the scene before; it is shortened if a scene is shorter'));
  }
  const chap = el('input', { type: 'checkbox', checked: sc.chapter !== false, 'aria-label': 'Chapter marker' });
  chap.addEventListener('change', () => editScene(id, (x) => { if (chap.checked) delete x.chapter; else x.chapter = false; }));
  body.append(row('Chapter', el('label', { class: 'check' }, chap, ' Marker in the video'),
    'Players show the scene names as chapters of exported videos'));
  const notes = el('textarea', { rows: 4, 'aria-label': 'Speaker notes', placeholder: 'What to say during this scene', spellcheck: 'true' });
  notes.value = sc.notes || '';
  notes.addEventListener('change', () => editScene(id, (x) => { if (notes.value.trim()) x.notes = notes.value; else delete x.notes; }));
  body.append(el('div', { class: 'row wide' }, el('span', { class: 'lbl' }, 'Notes'), el('div', { class: 'ctl' }, notes)));
  root.append(el('details', { class: 'group', open: true }, el('summary', {}, 'Scene'), body));
  const info = el('p', { class: 'insp-hint' },
    `Starts at ${fmtTime(sceneStart(sc))} s in the film. Times in the timeline count from the start of this scene. `
    + 'Notes become speaker notes when you export to PowerPoint.');
  root.append(info);
  root.append(el('div', { class: 'insp-actions' },
    el('button', { class: 'btn', onclick: () => moveScene(sc, -1), disabled: i === 0 }, 'Move earlier'),
    el('button', { class: 'btn', onclick: () => moveScene(sc, 1), disabled: i === scenes().length - 1 }, 'Move later'),
    el('button', { class: 'btn', onclick: () => duplicateScene(sc) }, 'Duplicate'),
    el('button', { class: 'btn danger', onclick: () => deleteScene(sc), disabled: scenes().length === 1 }, 'Delete scene')));
}
