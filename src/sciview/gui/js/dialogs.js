// Dialogs: start a film, open, save as, export, help.
import { S, emit, applyState, resetHistory, synced, duration, select, objById } from './state.js';
import { api } from './api.js';
import { el, openModal, toast, fmtTime } from './ui.js';
import { icon } from './icons.js';

// ------------------------------------------------------------------ new film
export function newFilmDialog({ first = false } = {}) {
  const grid = el('div', { class: 'tpl-grid' });
  let close;
  const choose = async (name) => {
    if (!S.saved && !first && !confirm('Discard unsaved changes to the current film?')) return;
    try {
      const st = await api.newFilm(name);
      applyState(st);
      resetHistory();
      select(null);
      close();
      emit('loaded');
    } catch (e) { toast(e.message, 'err'); }
  };
  grid.append(el('button', { class: 'tpl', onclick: () => choose('blank') },
    el('div', { class: 'thumb blank', html: icon('film') }),
    el('div', { class: 'meta' }, el('strong', {}, 'Empty film'), el('span', {}, 'A dark stage and a camera. Add objects from the left.'))));
  for (const t of S.templates) {
    grid.append(el('button', { class: 'tpl', onclick: () => choose(t.name) },
      el('div', { class: 'thumb', style: { backgroundImage: `url(/api/template-thumb?name=${encodeURIComponent(t.name)})` } }),
      el('div', { class: 'meta' }, el('strong', {}, t.title), el('span', {}, t.description))));
  }
  const body = el('div', {},
    el('p', { class: 'lead' }, 'Pick a starting point. Every template is an ordinary project: change anything, delete what you do not need.'),
    grid);
  const files = el('div', {});
  body.append(files);
  api.files().then((r) => {
    if (!r.files.length) return;
    files.append(el('div', { class: 'section-title' }, `Or open a film in ${r.base_dir}`),
      el('div', { class: 'file-list' }, r.files.map((f) => el('button', { onclick: () => { close(); openPath(f); } }, f))));
  }).catch(() => {});
  close = openModal({ title: first ? 'Start a film' : 'New film', body, wide: true });
}

// ------------------------------------------------------------------ open
export async function openPath(path) {
  if (!S.saved && !confirm('Discard unsaved changes to the current film?')) return;
  try {
    const st = await api.open(path);
    applyState(st);
    resetHistory();
    select(null);
    emit('loaded');
    toast(`Opened ${st.name}`);
    if (S.recovery) recoveryDialog();
  } catch (e) { toast(`Could not open ${path}: ${e.message}`, 'err'); }
}

export function openDialog() {
  const list = el('div', { class: 'file-list' }, 'Looking for project files…');
  const pathInput = el('input', { type: 'text', placeholder: 'path/to/film.sciview.json', spellcheck: 'false' });
  let close;
  api.files().then((r) => {
    list.innerHTML = '';
    if (!r.files.length) list.append(el('span', { class: 'lead' }, `No .sciview.json files in ${r.base_dir}.`));
    for (const f of r.files) list.append(el('button', { onclick: () => { close(); openPath(f); } }, f));
  });
  const body = el('div', {},
    el('p', { class: 'lead' }, 'Films saved in the project folder:'), list,
    el('div', { class: 'section-title' }, 'Or type a path'),
    el('label', { class: 'field' }, el('span', {}, 'Relative to the project folder, or absolute'), pathInput));
  const footer = [el('button', { class: 'btn', onclick: () => close() }, 'Cancel'),
    el('button', { class: 'btn primary', onclick: () => { if (pathInput.value.trim()) { close(); openPath(pathInput.value.trim()); } } }, 'Open')];
  close = openModal({ title: 'Open a film', body, footer });
}

// ------------------------------------------------------------------ save
export async function save({ as = false } = {}) {
  if (as || S.untitled) return saveAsDialog();
  try {
    await synced();
    const r = await api.save(null, S.project);
    S.saved = true;
    S.untitled = false;
    S.name = r.name;
    emit('saved');
    toast(`Saved ${r.name}`);
  } catch (e) { toast(`Could not save: ${e.message}`, 'err'); }
}

export function saveAsDialog() {
  const suggested = (S.project.settings.title || 'film').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'film';
  const inp = el('input', { type: 'text', value: S.untitled ? `${suggested}.sciview.json` : S.name, spellcheck: 'false' });
  let close;
  const go = async () => {
    const name = inp.value.trim();
    if (!name) return;
    try {
      await synced();
      const r = await api.save(name, S.project);
      S.saved = true;
      S.untitled = false;
      S.name = r.name;
      S.path = r.path;
      close();
      emit('saved');
      toast(`Saved ${r.name}`);
    } catch (e) { toast(`Could not save: ${e.message}`, 'err'); }
  };
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
  close = openModal({
    title: 'Save film',
    body: el('div', {},
      el('label', { class: 'field' }, el('span', {}, `File name (saved in ${S.baseDir})`), inp),
      el('p', { class: 'lead' }, 'Images and data you add are kept in the assets folder next to this file. Share the file and that folder together.')),
    footer: [el('button', { class: 'btn', onclick: () => close() }, 'Cancel'), el('button', { class: 'btn primary', onclick: go }, 'Save')],
  });
}

// ------------------------------------------------------------------ export
let exportTimer = null;

export function exportDialog() {
  const fmts = Object.entries(S.formats);
  const labels = { mp4: 'MP4', webm: 'WebM', mov: 'ProRes', gif: 'GIF', png: 'PNG frames' };
  const radios = el('div', { class: 'formats' }, fmts.map(([k, desc], i) => el('label', { class: 'fmt' },
    el('input', { type: 'radio', name: 'fmt', value: k, checked: i === 0 }), el('b', {}, labels[k] || k), el('span', {}, desc.split(' - ')[1] || desc))));
  const W = S.project.settings.width, H = S.project.settings.height;
  const scale = el('select', {}, [[0.25, 'Quarter'], [0.5, 'Half'], [1, 'Full'], [2, 'Double']].map(([v, n]) =>
    el('option', { value: v, selected: v === 1 }, `${n} (${Math.round(W * v / 2) * 2} × ${Math.round(H * v / 2) * 2})`)));
  const crf = el('select', {}, [[14, 'Very high'], [18, 'High'], [23, 'Standard'], [28, 'Small file']].map(([v, n]) =>
    el('option', { value: v, selected: v === 18 }, n)));
  const base = (S.untitled ? (S.project.settings.title || 'film') : S.name.split('.')[0]).toLowerCase().replace(/[^a-z0-9]+/g, '_');
  const name = el('input', { type: 'text', value: `${base}.mp4`, spellcheck: 'false' });
  const subs = el('input', { type: 'checkbox', checked: S.project.objects.some((o) => o.type === 'caption') });
  radios.addEventListener('change', () => {
    const f = radios.querySelector('input:checked').value;
    name.value = name.value.replace(/(\.[a-z0-9]+|_frames)?$/i, f === 'png' ? '_frames' : `.${f}`);
    if (f === 'gif' && Number(scale.value) > 0.5) scale.value = '0.5';
    crf.disabled = !(f === 'mp4' || f === 'webm');
  });
  const bar = el('div', { class: 'progress' }, el('div'));
  const status = el('div', { class: 'export-status' }, S.ffmpeg ? `${fmtTime(duration())} s at ${S.project.settings.fps} frames per second.` : 'ffmpeg was not found: only PNG frames can be written. Install ffmpeg or run pip install imageio-ffmpeg.');
  const startBtn = el('button', { class: 'btn primary' }, 'Export');
  const cancelBtn = el('button', { class: 'btn', hidden: true }, 'Stop');
  const download = el('a', { class: 'btn', hidden: true }, 'Download');
  const body = el('div', {},
    el('div', { class: 'field' }, el('span', {}, 'Format'), radios),
    el('div', { class: 'two' },
      el('label', { class: 'field' }, el('span', {}, 'Size'), scale),
      el('label', { class: 'field' }, el('span', {}, 'Quality'), crf)),
    el('label', { class: 'field' }, el('span', {}, `File name (in ${S.baseDir})`), name),
    el('label', { class: 'check' }, subs, 'Also write the captions as a subtitle file (.srt)'),
    bar, status);
  const poll = async () => {
    try {
      const st = await api.exportStatus();
      const pct = st.total ? (100 * st.done) / st.total : 0;
      bar.firstChild.style.width = `${pct}%`;
      if (st.state === 'running') {
        const eta = st.eta != null ? `${Math.floor(st.eta / 60)}:${String(Math.round(st.eta % 60)).padStart(2, '0')} left` : 'starting…';
        status.textContent = `Rendering frame ${st.done} of ${st.total || '…'} · ${eta}`;
        status.classList.remove('err');
        exportTimer = setTimeout(poll, 500);
        return;
      }
      startBtn.disabled = false;
      cancelBtn.hidden = true;
      if (st.state === 'done') {
        bar.firstChild.style.width = '100%';
        const mb = st.size ? ` (${(st.size / 1e6).toFixed(1)} MB)` : '';
        status.textContent = `Exported ${st.output}${mb}`;
        if (st.size) {
          download.hidden = false;
          download.href = `/api/download?path=${encodeURIComponent(st.output)}`;
          download.setAttribute('download', '');
        }
      } else if (st.state === 'error') {
        status.textContent = `Export failed: ${st.error}`;
        status.classList.add('err');
      } else if (st.state === 'cancelled') {
        status.textContent = 'Export stopped.';
      }
    } catch (e) {
      status.textContent = e.message;
    }
  };
  startBtn.addEventListener('click', async () => {
    const fmt = radios.querySelector('input:checked').value;
    try {
      await synced();
      download.hidden = true;
      startBtn.disabled = true;
      cancelBtn.hidden = false;
      await api.startExport({ format: fmt, filename: name.value.trim(), scale: Number(scale.value), crf: Number(crf.value), subtitles: subs.checked });
      poll();
    } catch (e) {
      startBtn.disabled = false;
      cancelBtn.hidden = true;
      status.textContent = e.message;
      status.classList.add('err');
    }
  });
  cancelBtn.addEventListener('click', () => api.cancelExport());
  const close = openModal({
    title: 'Export video', body,
    footer: [el('span', { class: 'spacer' }, 'Rendering uses all but one processor core.'), download, cancelBtn, startBtn],
    onClose: () => clearTimeout(exportTimer),
  });
  api.exportStatus().then((st) => { if (st.state === 'running') { startBtn.disabled = true; cancelBtn.hidden = false; poll(); } });
  return close;
}

// ------------------------------------------------------------------ help
export function helpDialog() {
  const keys = [
    ['Space', 'Play / pause'], ['← →', 'Previous / next frame (Shift: one second)'], ['Home / End', 'Start / end of the film'],
    ['K', 'Keyframe every animatable value of the selection at this time'], ['Del', 'Delete the selected keyframe or object'],
    ['Ctrl+D', 'Duplicate'], ['Ctrl+C / Ctrl+X / Ctrl+V', 'Copy, cut, paste objects (or the keyframe picked in the timeline). Pasted objects keep their timing relative to the playhead'],
    ['Ctrl+G / Ctrl+Shift+G', 'Group the selection / ungroup'], ['Ctrl+A', 'Select every object'],
    ['Shift-click', 'Add an object to the selection, or take it out (preview and timeline)'],
    ['Ctrl-drag on empty space', 'Select everything inside a box'], ['Double-click', 'Select an object inside its group'],
    ['Ctrl+Z / Ctrl+Shift+Z', 'Undo / redo'], ['Ctrl+S', 'Save'], ['Esc', 'Leave the group, then select nothing (film settings)'],
    ['Drag in the preview', 'Move objects, 2D and 3D (Shift: along one axis); drag empty space to orbit the camera'],
    ['Alt-drag', 'Orbit the camera even over an object'], ['Shift-drag on empty space', 'Shift the view'], ['Scroll in the preview', 'Zoom the camera'],
    ['Drag a value’s label', 'Change a number (Shift: faster, Alt: finer)'], ['Ctrl+scroll on the timeline', 'Zoom the timeline'],
  ];
  const markup = [
    ['H_2O, ^6Li', 'one character lowered / raised'], ['x_{max}, e^{-x/2}', 'groups'], ['\\alpha \\mu \\AA \\deg \\to \\pm', 'symbols (Greek, Å, °, →, ±)'],
    ['**bold**', 'bold text'], ['{value:.1f}', 'in Text objects: the animated Value, e.g. a counter'],
  ];
  const dl = (rows, codeLeft) => el('dl', { class: 'keys' }, rows.flatMap(([a, b]) => [el('dt', {}, codeLeft ? el('code', {}, a) : el('kbd', {}, a)), el('dd', {}, b)]));
  openModal({
    title: 'Shortcuts and text markup',
    body: el('div', {}, dl(keys, false), el('div', { class: 'section-title' }, 'Text markup (any text field)'), dl(markup, true),
      el('div', { class: 'section-title' }, 'Curves'),
      el('p', { class: 'lead' }, 'Curve expressions use x and the film time t: sin(x - 2*t) is a travelling wave. Functions: sin, cos, exp, log, sqrt, abs, gauss(x, mu, sigma), step, where, clip.'),
      el('p', { class: 'lead' }, `SciView ${S.version}. Equations use matplotlib’s mathtext. Command line: sciview render film.sciview.json`)),
  });
}

export function issuesDialog() {
  const seen = new Set();
  const items = [];
  for (const p of [...S.problems, ...S.frameIssues]) {
    if (seen.has(p.message)) continue;
    seen.add(p.message);
    items.push(p);
  }
  for (const w of S.warnings) if (!seen.has(w)) { seen.add(w); items.push({ id: null, message: w }); }
  let close;
  const li = (p) => {
    const o = p.id ? objById(p.id) : null;
    return el('li', {}, o ? el('button', { class: 'link', onclick: () => { close(); select(o.id); } }, o.name || o.id) : null, o ? ': ' : '', p.message);
  };
  close = openModal({
    title: 'Things to check',
    body: el('div', {}, el('ul', { class: 'issue-list', style: { paddingLeft: '18px' } }, items.map(li)),
      el('p', { class: 'lead', style: { marginTop: '12px' } }, 'Objects with a problem carry a warning sign in the timeline; the field to fix is marked in the inspector.')),
  });
}

// ------------------------------------------------------------------ recovery
export function recoveryDialog() {
  const r = S.recovery;
  if (!r) return;
  let close;
  const act = async (action) => {
    try {
      const st = await api.recover(action);
      applyState(st, { keepTime: true });
      resetHistory();
      select(null);
      close();
      emit('loaded');
      toast(action === 'restore' ? 'Restored the unsaved changes. Save to keep them.' : 'Discarded the unsaved changes.');
      if (action !== 'restore' && S.untitled && !S.project.objects.length) newFilmDialog({ first: true });
    } catch (e) { toast(e.message, 'err'); }
  };
  const restore = el('button', { class: 'btn primary', onclick: () => act('restore') }, 'Restore changes');
  const discard = el('button', { class: 'btn', onclick: () => act('discard') }, 'Discard them');
  close = openModal({
    title: 'Restore unsaved changes?',
    body: el('div', {},
      el('p', { class: 'lead' }, `SciView found changes to ${S.untitled ? 'an untitled film' : S.name} that were not saved (last kept ${r.time}). This happens when the editor stops before you save.`),
      el('p', { class: 'help' }, 'Restore opens those changes; the film is not saved until you press Save. Discard deletes them and keeps the saved file.')),
    footer: [el('span', { class: 'spacer' }), discard, restore],
    dismissable: false,
  });
}
