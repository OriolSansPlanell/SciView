// Entry point: wires the library, preview, timeline, inspector, transport and shortcuts together.
import {
  S, on, emit, commit, objById, schemaOf, applyState, requestFrame, undo, redo, canUndo, canRedo,
  duration, fps, frameDt, setKey, valueAt, keyIndexAt, select, isGroup,
} from './state.js';
import {
  groupSelection, ungroup, removeSelected, duplicateSelected, copySelection, cutSelection, pasteText, lastCopied,
} from './actions.js';
import { api } from './api.js';
import { el, toast, fmtTime, clamp, modalOpen } from './ui.js';
import { icon, hydrateIcons } from './icons.js';
import { renderInspector, refreshInspector, addObject } from './inspector.js';
import { renderTimeline, placePlayhead, ensurePlayheadVisible, deleteSelectedKey, fit } from './timeline.js';
import { layoutViewport, drawOverlay } from './viewport.js';
import {
  newFilmDialog, openDialog, save, saveAsDialog, exportDialog, helpDialog, issuesDialog, recoveryDialog,
} from './dialogs.js';

const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------------ library
function renderLibrary(filter = '') {
  const list = $('libraryList');
  list.innerHTML = '';
  const f = filter.trim().toLowerCase();
  for (const cat of S.categories) {
    const items = S.typeList.filter((t) => t.category === cat &&
      (!f || t.label.toLowerCase().includes(f) || t.description.toLowerCase().includes(f) || t.type.includes(f)));
    if (!items.length) continue;
    list.append(el('div', { class: 'lib-group' }, el('h3', {}, cat),
      items.map((t) => el('button', { class: 'lib-item', title: t.description, onclick: () => addObject(t.type) },
        el('span', { class: 'lib-icon', html: icon(t.icon) }), el('span', { class: 'lib-label' }, t.label)))));
  }
  if (!list.children.length) list.append(el('p', { class: 'insp-hint' }, `Nothing matches “${filter}”.`));
}
$('libSearch').addEventListener('input', (e) => renderLibrary(e.target.value));

// ------------------------------------------------------------------ top bar
function updateTitle() {
  $('fileName').textContent = S.untitled ? 'Untitled film (not saved yet)' : S.name;
  $('fileName').title = S.untitled ? 'Save to choose a file name' : S.path;
  $('dirtyDot').hidden = S.saved;
  document.title = `${S.saved ? '' : '• '}${S.untitled ? 'Untitled' : S.name} – SciView`;
  $('btnUndo').disabled = !canUndo();
  $('btnRedo').disabled = !canRedo();
}
$('btnNew').addEventListener('click', () => newFilmDialog());
$('btnOpen').addEventListener('click', () => openDialog());
$('btnSave').addEventListener('click', () => save());
$('fileName').addEventListener('click', () => saveAsDialog());
$('btnUndo').addEventListener('click', () => undo());
$('btnRedo').addEventListener('click', () => redo());
$('btnHelp').addEventListener('click', () => helpDialog());
$('btnExport').addEventListener('click', () => exportDialog());
$('btnIssues').addEventListener('click', () => issuesDialog());

// ------------------------------------------------------------------ time and playback
const audio = $('audio');
let lastAudio = '';

function setTime(t, { fromPlayback = false } = {}) {
  const f = fps();
  S.time = clamp(fromPlayback ? t : Math.round(t * f) / f, 0, duration());
  $('timeInput').value = fmtTime(S.time);
  emit('time');
  requestFrame();
  if (!fromPlayback && S.playing) syncAudio(true);
}

function syncAudio(seek) {
  const src = S.project.settings.audio;
  if (!src) { audio.pause(); return; }
  const url = `/files/${src.split('/').map(encodeURIComponent).join('/')}`;
  if (lastAudio !== url) { audio.src = url; lastAudio = url; }
  audio.volume = clamp(Number(S.project.settings.audio_volume) || 1, 0, 1);
  const at = S.time - (Number(S.project.settings.audio_offset) || 0);
  if (seek || Math.abs(audio.currentTime - at) > 0.25) {
    if (at >= 0) audio.currentTime = at;
  }
  if (S.playing && at >= 0) audio.play().catch(() => {});
  else audio.pause();
}

let rafId = null;
let lastTs = 0;
function play() {
  if (S.playing) return;
  if (S.time >= duration() - frameDt() / 2) setTime(0);
  S.playing = true;
  $('btnPlay').innerHTML = icon('pause');
  $('btnPlay').title = 'Pause (Space)';
  lastTs = performance.now();
  syncAudio(true);
  const tick = (ts) => {
    if (!S.playing) return;
    const dt = (ts - lastTs) / 1000;
    lastTs = ts;
    let t = S.time + dt;
    if (t >= duration()) {
      if (S.loop) { t = 0; syncAudio(true); } else { setTime(duration()); pause(); return; }
    }
    setTime(t, { fromPlayback: true });
    ensurePlayheadVisible();
    if (S.project.settings.audio) syncAudio(false);
    rafId = requestAnimationFrame(tick);
  };
  rafId = requestAnimationFrame(tick);
}
function pause() {
  S.playing = false;
  cancelAnimationFrame(rafId);
  audio.pause();
  $('btnPlay').innerHTML = icon('play');
  $('btnPlay').title = 'Play (Space)';
  setTime(S.time);
}
const togglePlay = () => (S.playing ? pause() : play());

$('btnPlay').addEventListener('click', togglePlay);
$('btnStart').addEventListener('click', () => setTime(0));
$('btnEnd').addEventListener('click', () => setTime(duration()));
$('btnPrev').addEventListener('click', () => setTime(S.time - frameDt()));
$('btnNext').addEventListener('click', () => setTime(S.time + frameDt()));
$('btnLoop').addEventListener('click', () => {
  S.loop = !S.loop;
  $('btnLoop').setAttribute('aria-pressed', String(S.loop));
});
$('timeInput').addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === 'Escape') e.target.blur(); });
$('timeInput').addEventListener('change', (e) => {
  const v = parseFloat(e.target.value);
  if (Number.isFinite(v)) setTime(v); else e.target.value = fmtTime(S.time);
});
$('quality').addEventListener('change', (e) => { S.scale = Number(e.target.value); requestFrame(); });
$('btnSnap').addEventListener('click', () => {
  const a = el('a', { href: `/api/still?t=${S.time.toFixed(4)}&scale=1`, download: '' });
  document.body.append(a);
  a.click();
  a.remove();
  toast('Saving the frame as PNG…');
});

// ------------------------------------------------------------------ events between panels
on('seek', (t) => setTime(t));
let lastSelection = '';
on('selection', () => {
  const key = `${S.selected}|${S.selection.join(',')}`;
  if (key === lastSelection) return;
  lastSelection = key;
  renderInspector();
  renderTimeline();
  drawOverlay();
});
on('project', (opts = {}) => {
  updateTitle();
  renderTimeline();
  if (opts.source !== 'inspector') renderInspector();
  else refreshInspector();
  if (opts.settings) { layoutViewport(); $('durLabel').textContent = fmtTime(duration()); }
  if (S.time > duration()) setTime(duration());
});
on('dirty', updateTitle);
on('saved', updateTitle);
on('error', (msg) => toast(msg, 'err'));
on('issues', updateIssues);
on('warnings', updateIssues);
on('loaded', () => {
  $('durLabel').textContent = fmtTime(duration());
  renderLibrary($('libSearch').value);
  renderInspector();
  layoutViewport();
  fit();
  renderTimeline();
  updateTitle();
  updateIssues();
  setTime(S.time);
});

function updateIssues() {
  const n = new Set([...S.problems.map((p) => p.message), ...S.warnings]).size;
  $('issues').hidden = n === 0;
  $('btnIssues').textContent = n === 1 ? '1 thing to check' : `${n} things to check`;
}
let lastFrameIssues = '';
on('frame', (r) => {
  $('renderMs').textContent = `${Math.round(r.ms)} ms${r.cached ? ' (cached)' : ''}`;
  const key = JSON.stringify(r.issues || []);
  if (key !== lastFrameIssues) { lastFrameIssues = key; renderTimeline(); }
});

// ------------------------------------------------------------------ keyboard
function keyAll() {
  const o = objById(S.selected);
  if (!o) return;
  const sc = schemaOf(o);
  commit(() => {
    const x = objById(S.selected);
    for (const p of sc.props) if (p.animatable && keyIndexAt(x, p.name, S.time) < 0) setKey(x, p.name, S.time, valueAt(x, p.name, S.time));
  }, { source: 'key-all' });
  toast('Keyframed every value at this time');
}

document.addEventListener('keydown', (e) => {
  const tag = (e.target.tagName || '').toLowerCase();
  const typing = ['input', 'textarea', 'select'].includes(tag) || e.target.isContentEditable;
  const mod = e.ctrlKey || e.metaKey;
  if (mod && e.key.toLowerCase() === 's') { e.preventDefault(); save({ as: e.shiftKey }); return; }
  if (mod && e.key.toLowerCase() === 'z' && !typing) { e.preventDefault(); if (e.shiftKey) redo(); else undo(); return; }
  if (mod && e.key.toLowerCase() === 'y' && !typing) { e.preventDefault(); redo(); return; }
  if (typing || modalOpen()) return;
  const key = e.key.toLowerCase();
  if (mod && key === 'd') { e.preventDefault(); duplicateSelected(); return; }
  if (mod && key === 'g') {
    e.preventDefault();
    if (e.shiftKey) ungroup();
    else if (S.selection.length > 1 || (S.selected && S.selected !== 'camera' && !isGroup(objById(S.selected)))) groupSelection();
    else if (isGroup(objById(S.selected))) toast('Select two or more objects to group them, or press Ctrl+Shift+G to ungroup.');
    return;
  }
  if (mod && (key === 'c' || key === 'x' || key === 'v') && !e.shiftKey && !e.altKey) { keyClipboard(e, key); return; }
  if (mod && key === 'a') {
    e.preventDefault();
    select(null);
    for (const o of [...S.project.objects].reverse()) if (!o.parent || !objById(o.parent)) select(o.id, 'add');
    return;
  }
  switch (e.key) {
    case ' ': e.preventDefault(); togglePlay(); break;
    case 'ArrowLeft': e.preventDefault(); setTime(S.time - (e.shiftKey ? 1 : frameDt())); break;
    case 'ArrowRight': e.preventDefault(); setTime(S.time + (e.shiftKey ? 1 : frameDt())); break;
    case 'Home': setTime(0); break;
    case 'End': setTime(duration()); break;
    case 'Escape': {
      // first leave the group the selection is in, then clear it
      const o = objById(S.selected);
      if (S.selection.length === 1 && o && o.parent && isGroup(objById(o.parent))) select(o.parent);
      else select(null);
      break;
    }
    case 'Delete':
    case 'Backspace':
      if (!deleteSelectedKey()) removeSelected();
      break;
    case 'k': case 'K': keyAll(); break;
    case '?': helpDialog(); break;
    default: break;
  }
});

// ------------------------------------------------------------------ clipboard
// The copy/cut/paste events carry the system clipboard. Some browsers (Safari, headless ones) do not
// fire them when no text is selected, so the shortcuts also act from keydown, with the last copy
// kept in memory as a fallback.
const editingText = () => {
  const t = document.activeElement;
  const tag = (t && t.tagName || '').toLowerCase();
  return ['input', 'textarea', 'select'].includes(tag) || (t && t.isContentEditable) || modalOpen()
    || (window.getSelection && String(window.getSelection()).length > 0);
};
let keyCopyAt = 0;
let pasteTimer = null;
let copiedText = null;
function keyClipboard(e, key) {
  if (key === 'c' || key === 'x') {
    const ok = key === 'c' ? copySelection(null) : cutSelection(null);
    if (!ok) return;
    keyCopyAt = performance.now();
    copiedText = lastCopied();
    if (navigator.clipboard && copiedText) navigator.clipboard.writeText(copiedText).catch(() => {});
  } else if (key === 'v') {
    clearTimeout(pasteTimer);
    pasteTimer = setTimeout(() => { pasteTimer = null; pasteText(null); }, 80);   // no paste event came
  }
}
document.addEventListener('copy', (e) => {
  if (editingText()) return;
  if (performance.now() - keyCopyAt < 500) {
    if (copiedText && e.clipboardData) { e.clipboardData.setData('text/plain', copiedText); e.preventDefault(); }
    return;
  }
  if (copySelection(e.clipboardData)) e.preventDefault();
});
document.addEventListener('cut', (e) => {
  if (editingText()) return;
  if (performance.now() - keyCopyAt < 500) {
    if (copiedText && e.clipboardData) { e.clipboardData.setData('text/plain', copiedText); e.preventDefault(); }
    return;
  }
  if (cutSelection(e.clipboardData)) e.preventDefault();
});
document.addEventListener('paste', (e) => {
  if (editingText()) return;
  clearTimeout(pasteTimer);
  pasteTimer = null;
  const text = e.clipboardData ? e.clipboardData.getData('text/plain') : null;
  if (pasteText(text || null)) e.preventDefault();
});

window.addEventListener('beforeunload', (e) => {
  if (!S.saved) { e.preventDefault(); e.returnValue = ''; }
});

// ------------------------------------------------------------------ resizable timeline
$('tlResize').addEventListener('pointerdown', (e) => {
  const h0 = $('timeline').getBoundingClientRect().height;
  const handle = $('tlResize');
  handle.classList.add('active');
  const mm = (ev) => {
    const h = clamp(h0 - (ev.clientY - e.clientY), 120, window.innerHeight - 260);
    document.documentElement.style.setProperty('--tl-h', `${h}px`);
    placePlayhead();
  };
  const mu = () => {
    handle.classList.remove('active');
    window.removeEventListener('pointermove', mm);
    window.removeEventListener('pointerup', mu);
  };
  window.addEventListener('pointermove', mm);
  window.addEventListener('pointerup', mu);
});

// ------------------------------------------------------------------ start
async function start() {
  hydrateIcons();
  try {
    const st = await api.state();
    applyState(st);
  } catch (e) {
    document.body.innerHTML = `<p style="padding:40px;color:#ff7a7a">Could not reach the SciView server (${e.message}). Is <code>sciview edit</code> still running?</p>`;
    return;
  }
  emit('loaded');
  if (S.recovery) recoveryDialog();
  else if (S.untitled && S.project.objects.length === 0) newFilmDialog({ first: true });
}

start();
