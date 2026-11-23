// The assistant panel: a chat with a local (or hosted) language model that builds the film with the same
// tools as the MCP server. The server runs each request; the editor shows changes as they come and records
// the whole request as one undo step.
import {
  S, emit, on, synced, pullQuiet, pushUndo, currentScene, objById, select,
} from './state.js';
import { api } from './api.js';
import { el, toast } from './ui.js';
import { icon } from './icons.js';

const $ = (id) => document.getElementById(id);
let panel = null;
let log = null;
let input = null;
let sendBtn = null;
let scopeSel = null;
let cfg = null;
let presets = [];
const history = [];     // {role, content}: the person's requests and the assistant's answers
let running = null;     // {id, seq, before}

const EXAMPLES = [
  'Add captions from this script, one per line: …',
  'Make the camera orbit slowly around the sample during this scene',
  'Add a title card scene at the start called “How a tomograph sees inside”',
  'Line up the panels in this scene and space them evenly',
  'Check this film for text that is hard to read and fix it',
];

export function initAssistant() {
  panel = $('assistant');
  $('btnAssistant').addEventListener('click', () => toggle());
  on('selection', () => syncScope());
  on('scene', () => syncScope());
}

function toggle(open = panel.hidden) {
  panel.hidden = !open;
  $('app').classList.toggle('assist-open', open);
  $('btnAssistant').setAttribute('aria-expanded', String(open));
  if (open && !panel.dataset.built) build();
  if (open && input) input.focus();
  window.dispatchEvent(new Event('resize'));
  emit('layout');
}

async function build() {
  panel.dataset.built = '1';
  try {
    const r = await api.assistantConfig();
    cfg = r.config;
    presets = r.presets;
  } catch (e) {
    cfg = { base_url: 'http://localhost:11434/v1', model: '' };
  }
  render();
}

function render() {
  panel.innerHTML = '';
  const model = el('span', { class: 'as-model', title: cfg.model ? `${cfg.model} at ${cfg.base_url}` : 'No model chosen' },
    cfg.model || 'no model');
  panel.append(el('div', { class: 'as-head' },
    el('span', { class: 'lib-icon', html: icon('spark') }), el('h2', {}, 'Assistant'), model,
    el('button', { class: 'icon-btn small', title: 'Model server settings', 'aria-label': 'Assistant settings', html: icon('settings'), onclick: settings }),
    el('button', { class: 'icon-btn small', title: 'Close the assistant', 'aria-label': 'Close the assistant', html: icon('close'), onclick: () => toggle(false) })));
  log = el('div', { class: 'as-log', role: 'log', 'aria-live': 'polite' });
  panel.append(log);
  if (!history.length) log.append(emptyState());
  else for (const m of history) log.append(el('div', { class: `as-msg ${m.role}` }, m.content));
  scopeSel = el('select', { 'aria-label': 'What the assistant may change' });
  input = el('textarea', { rows: 2, 'aria-label': 'Ask the assistant', placeholder: 'Ask for a change, e.g. “add a caption that explains the sinogram”', spellcheck: 'true' });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    e.stopPropagation();
  });
  input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = `${Math.min(160, input.scrollHeight)}px`; });
  sendBtn = el('button', { class: 'icon-btn', title: 'Send (Enter)', 'aria-label': 'Send', html: icon('send'), onclick: () => (running ? stop() : send()) });
  panel.append(el('div', { class: 'as-form' },
    el('div', { class: 'as-scope' }, el('span', {}, 'May change'), scopeSel),
    el('div', { class: 'as-input' }, input, sendBtn)));
  syncScope();
  if (!cfg.model) settings();
}

function emptyState() {
  return el('div', { class: 'as-empty' },
    el('p', {}, 'Describe what you want and the assistant builds it with SciView’s own tools. You see each change as it happens; Ctrl+Z undoes a whole request.'),
    el('p', {}, 'It uses your numbers and text; values it chose itself are listed for you to check.'),
    el('ul', {}, EXAMPLES.map((x) => el('li', {}, el('button', { class: 'link', onclick: () => { input.value = x; input.focus(); } }, x)))));
}

function syncScope() {
  if (!scopeSel) return;
  const cur = scopeSel.value;
  const sel = S.selection.filter((id) => id !== 'camera' && objById(id));
  scopeSel.innerHTML = '';
  scopeSel.append(el('option', { value: 'film' }, 'The whole film'));
  if (S.project.scenes.length > 1) scopeSel.append(el('option', { value: 'scene' }, `Only ${currentScene().name}`));
  if (sel.length) scopeSel.append(el('option', { value: 'selection' }, `Only the ${sel.length} selected object${sel.length === 1 ? '' : 's'}`));
  if ([...scopeSel.options].some((o) => o.value === cur)) scopeSel.value = cur;
}

function scope() {
  const v = scopeSel ? scopeSel.value : 'film';
  if (v === 'scene') return { scene: currentScene().id };
  if (v === 'selection') return { ids: S.selection.filter((id) => id !== 'camera' && objById(id)), scene: currentScene().id };
  return {};
}

function add(node) {
  log.querySelector('.as-empty')?.remove();
  log.append(node);
  log.scrollTop = log.scrollHeight;
}

async function send() {
  const prompt = input.value.trim();
  if (!prompt || running) return;
  if (!cfg.model) { settings(); return; }
  input.value = '';
  input.style.height = '';
  add(el('div', { class: 'as-msg user' }, prompt));
  try {
    await synced();
    const before = JSON.stringify(S.project);
    const r = await api.assistantStart({ prompt, history: history.slice(-12), scope: scope(), project: S.project,
      scene: currentScene().id });
    history.push({ role: 'user', content: prompt });
    running = { id: r.id, seq: 0, before, rev: r.rev, thinking: null };
    S.assistantBusy = true;
    emit('assistant-busy', true);
    sendBtn.innerHTML = icon('stop');
    sendBtn.title = 'Stop';
    sendBtn.setAttribute('aria-label', 'Stop the assistant');
    poll();
  } catch (e) {
    add(el('div', { class: 'as-step err' }, e.message));
  }
}

async function stop() {
  if (!running) return;
  try { await api.assistantStop(running.id); } catch (e) { /* finishing anyway */ }
}

async function poll() {
  if (!running) return;
  let st;
  try {
    st = await api.assistantStatus(running.id, running.seq);
  } catch (e) {
    finish(`Lost contact with the editor: ${e.message}`);
    return;
  }
  for (const ev of st.events) {
    running.seq = ev.seq + 1;
    show(ev);
  }
  if (st.rev !== S.rev) await pullQuiet();
  if (st.status === 'running') { setTimeout(poll, 600); return; }
  finish();
}

function show(ev) {
  if (running.thinking) { running.thinking.remove(); running.thinking = null; }
  if (ev.kind === 'thinking') {
    running.thinking = el('div', { class: 'as-step' }, 'Thinking…');
    add(running.thinking);
  } else if (ev.kind === 'tool') {
    add(el('div', { class: `as-step ${ev.ok ? '' : 'err'}` }, el('b', {}, ev.ok ? '✓' : '✗'),
      ev.ok ? (ev.note || ev.name) : `${ev.name}: ${ev.message}`));
  } else if (ev.kind === 'say') {
    add(el('div', { class: 'as-step' }, ev.text));
  } else if (ev.kind === 'check') {
    add(el('div', { class: 'as-step' }, el('b', {}, 'Check'), `${ev.messages.length} thing${ev.messages.length === 1 ? '' : 's'} to fix: ${ev.messages[0]}`));
  } else if (ev.kind === 'answer') {
    history.push({ role: 'assistant', content: ev.text });
    add(el('div', { class: 'as-msg assistant' }, ev.text));
  } else if (ev.kind === 'error') {
    add(el('div', { class: 'as-step err' }, ev.message));
  } else if (ev.kind === 'done') {
    if (ev.changes && ev.changes.length) add(changesBox(ev.changes, ev.flags || []));
  }
}

function changesBox(changes, flags) {
  const box = el('div', { class: 'as-changes' }, el('h3', {}, 'What changed'));
  for (const c of changes) {
    const name = c.id ? el('button', { class: 'link', onclick: () => goTo(c.id) }, c.name) : el('span', {}, c.name);
    box.append(el('div', {}, name, `: ${c.what.join(', ')}`));
  }
  if (flags.length) {
    box.append(el('h3', { style: { marginTop: '6px' } }, 'Please check'));
    for (const f of flags) {
      const o = objById(f.id);
      const val = typeof f.value === 'string' ? `“${f.value.length > 60 ? `${f.value.slice(0, 57)}…` : f.value}”` : JSON.stringify(f.value);
      box.append(el('div', { class: 'flag' }, o ? el('button', { class: 'link', onclick: () => goTo(f.id) }, o.name) : f.id,
        ` ${f.prop} = ${val}: ${f.reason}`));
    }
  }
  return box;
}

function goTo(id) {
  const o = objById(id);
  if (!o) return;
  if (o.scene && o.scene !== currentScene().id) import('./scenes.js').then((m) => { m.switchScene(o.scene); select(id); });
  else select(id);
}

async function finish(err) {
  if (running && running.thinking) running.thinking.remove();
  await pullQuiet();
  const before = running ? running.before : null;
  running = null;
  S.assistantBusy = false;
  emit('assistant-busy', false);
  if (before && pushUndo(before)) toast('The assistant’s changes are one step: Ctrl+Z undoes them.');
  if (err) add(el('div', { class: 'as-step err' }, err));
  sendBtn.innerHTML = icon('send');
  sendBtn.title = 'Send (Enter)';
  sendBtn.setAttribute('aria-label', 'Send');
}

// ------------------------------------------------------------------ settings
function settings() {
  const box = el('div', { class: 'as-changes as-settings' }, el('h3', {}, 'Model server'));
  const preset = el('select', { 'aria-label': 'Server' }, presets.map((p) => el('option', { value: p.base_url, selected: p.base_url === cfg.base_url }, p.name)),
    el('option', { value: '', selected: !presets.some((p) => p.base_url === cfg.base_url) }, 'Other'));
  const url = el('input', { type: 'text', value: cfg.base_url || '', spellcheck: 'false', 'aria-label': 'Server address' });
  const model = el('input', { type: 'text', value: cfg.model || '', spellcheck: 'false', 'aria-label': 'Model', list: 'asModels', placeholder: 'e.g. gemma4:31b' });
  const models = el('datalist', { id: 'asModels' });
  const key = el('input', { type: 'password', value: cfg.api_key || '', 'aria-label': 'API key', placeholder: 'Only for hosted servers', autocomplete: 'off' });
  const vision = el('input', { type: 'checkbox', checked: cfg.vision !== false, 'aria-label': 'Send frames to the model' });
  const status = el('div', { class: 'muted' });
  const refresh = async () => {
    status.textContent = 'Looking for models…';
    try {
      const r = await fetch(`/api/assistant/models?base_url=${encodeURIComponent(url.value.trim())}`).then((x) => x.json());
      models.innerHTML = '';
      for (const m of r.models || []) models.append(el('option', { value: m }));
      status.textContent = r.error ? r.error : r.models.length ? `${r.models.length} model${r.models.length === 1 ? '' : 's'} on this server.` : 'The server lists no models.';
      if (!model.value && r.models && r.models.length) model.value = r.models[0];
    } catch (e) { status.textContent = e.message; }
  };
  preset.addEventListener('change', () => { if (preset.value) { url.value = preset.value; refresh(); } });
  const save = el('button', { class: 'btn primary' }, 'Save');
  save.addEventListener('click', async () => {
    try {
      const r = await api.saveAssistantConfig({ base_url: url.value.trim(), model: model.value.trim(), api_key: key.value, vision: vision.checked });
      cfg = r.config;
      render();
      toast(cfg.model ? `The assistant uses ${cfg.model}.` : 'Choose a model to use the assistant.');
    } catch (e) { toast(e.message, 'err'); }
  });
  const field = (label, ctl) => el('label', { class: 'field' }, el('span', {}, label), ctl);
  box.append(
    field('Server', preset), field('Address', url), field('Model', model), models, field('API key', key),
    el('label', { class: 'check', title: 'The model sees the frames it renders; needs a model with image input (Gemma 4, Qwen-VL …)' }, vision, ' Let the model see frames'),
    status,
    el('p', { class: 'muted' }, 'Runs on your computer with Ollama, LM Studio, llama.cpp or vLLM; nothing leaves it unless you give a hosted server. Choose a model that can call tools.'),
    el('div', { class: 'insp-actions', style: { padding: 0 } }, save, el('button', { class: 'btn', onclick: refresh }, 'Find models')));
  add(box);
  refresh();
}
