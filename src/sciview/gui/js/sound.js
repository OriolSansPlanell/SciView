// Narration: waveforms of voice clips, phrase points for snapping, recording in the browser, captions from
// a script and reading captions aloud (text-to-speech on the server).
import { S, commit, currentScene, sceneObjects, select, uniqueId, emit, applyProjectJson } from './state.js';
import { api } from './api.js';
import { el, toast, openModal, fmtTime } from './ui.js';

const waves = new Map();      // key -> Promise of {peaks, seconds, segments, clip}
const loaded = new Map();     // key -> resolved waveform

const waveKey = (o) => `${o.props.audio}|${o.props.trim || 0}|${o.end == null ? '' : (o.end - o.start).toFixed(3)}`;

export function waveformFor(o) {
  if (!o.props.audio) return Promise.resolve(null);
  const key = waveKey(o);
  if (!waves.has(key)) {
    const length = o.end == null ? null : o.end - o.start;
    waves.set(key, api.waveform(o.props.audio, 600, o.props.trim || 0, length)
      .then((w) => { const r = { ...w, clip: length || w.seconds }; loaded.set(key, r); return r; })
      .catch((e) => { waves.delete(key); throw e; }));
  }
  return waves.get(key);
}

/** Scene times where phrases in the current scene's voice clips begin or end. */
export function snapPoints() {
  const pts = [];
  for (const o of sceneObjects()) {
    if (o.type !== 'voice' || !o.props.audio) continue;
    const w = loaded.get(waveKey(o));
    if (!w) { waveformFor(o).catch(() => {}); continue; }
    for (const [a, b] of w.segments || []) pts.push(o.start + a, o.start + b);
  }
  return pts;
}

// ------------------------------------------------------------------ recording
let rec = null;

export const isRecording = () => !!rec;

/** Record from the microphone while the film plays from the playhead; the take becomes a voice clip. */
export async function toggleRecording({ play, pause } = {}) {
  if (rec) { rec.stop(); return; }
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    toast('This browser cannot record sound here. Upload a recording instead.', 'err');
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  } catch (e) {
    toast('The microphone is not available: allow it for this page in the browser.', 'err');
    return;
  }
  const types = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4', 'audio/webm'];
  const mime = types.find((t) => MediaRecorder.isTypeSupported(t)) || '';
  const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  const chunks = [];
  const scene = currentScene().id;
  const startAt = S.time;
  const t0 = performance.now();
  mr.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
  mr.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    const seconds = (performance.now() - t0) / 1000;
    rec = null;
    emit('recording', false);
    if (pause) pause();
    const blob = new Blob(chunks, { type: mr.mimeType || 'audio/webm' });
    if (!blob.size || seconds < 0.3) { toast('Nothing was recorded.'); return; }
    const ext = (mr.mimeType || '').includes('ogg') ? 'ogg' : (mr.mimeType || '').includes('mp4') ? 'm4a' : 'webm';
    const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14);
    try {
      const info = await api.upload(new File([blob], `narration-${stamp}.${ext}`, { type: blob.type }));
      S.assets.push(info);
      addVoiceClip(info.path, startAt, seconds, scene);
      toast(`Recorded ${seconds.toFixed(1)} s of narration. Its phrases now snap captions into place.`);
    } catch (e) {
      toast(`Could not save the recording: ${e.message}`, 'err');
    }
  };
  rec = mr;
  mr.start(250);
  emit('recording', true);
  if (play) play();
}

export function addVoiceClip(path, start, seconds, scene = currentScene().id, extra = {}) {
  const id = uniqueId('voice');
  commit((p) => {
    p.objects.push({
      id, type: 'voice', name: extra.name || 'Narration', scene, props: { audio: path, ...(extra.props || {}) }, keys: {},
      start: Math.round(start * 100) / 100,
      end: Math.round(Math.min(start + seconds, p.scenes.find((x) => x.id === scene).duration) * 100) / 100,
      enter: { effect: 'none', duration: 0.6 }, exit: { effect: 'none', duration: 0.6 },
    });
  }, { source: 'sound' });
  select(id);
  return id;
}

// ------------------------------------------------------------------ captions from a script, reading aloud
export function scriptDialog(voice = null) {
  const ta = el('textarea', { rows: 8, class: 'script', 'aria-label': 'Script', spellcheck: 'true',
    placeholder: 'One caption per line. Long lines are split at the ends of sentences.' });
  ta.value = voice ? (voice.props.script || '') : '';
  const styleSel = el('select', { 'aria-label': 'Caption style' },
    ['plain', 'box', 'band', 'outline', 'shadow'].map((x) => el('option', { value: x, selected: x === 'box' }, x)));
  const how = voice
    ? `The captions follow the phrases of “${voice.name}” in order.`
    : `The captions follow each other at reading speed from the playhead (${fmtTime(S.time)} s).`;
  const go = el('button', { class: 'btn primary' }, 'Add captions');
  const close = openModal({
    title: 'Captions from a script',
    body: el('div', { class: 'form' }, el('p', { class: 'muted' }, how), ta,
      el('label', { class: 'field' }, el('span', {}, 'Style'), styleSel)),
    footer: [el('button', { class: 'btn', onclick: () => close() }, 'Cancel'), go],
  });
  go.addEventListener('click', async () => {
    if (!ta.value.trim()) { ta.focus(); return; }
    go.disabled = true;
    try {
      // the recording keeps its script too, in the same undo step as the captions
      const film = JSON.parse(JSON.stringify(S.project));
      const v = voice && film.objects.find((o) => o.id === voice.id);
      if (v && !v.props.script) v.props.script = ta.value;
      const r = await api.transform('script_captions', film, {
        text: ta.value, scene: currentScene().id, voice: voice ? voice.id : null, start: S.time,
        props: { style: styleSel.value },
      });
      applyProjectJson(r.project, 'Captions from the script');
      toast(`Added ${r.added} caption${r.added === 1 ? '' : 's'}.`);
      close();
    } catch (e) {
      toast(e.message, 'err');
      go.disabled = false;
    }
  });
  ta.focus();
}

export async function readAloud(ids) {
  let eng;
  try { eng = await api.tts(); } catch (e) { eng = { engines: [] }; }
  if (!eng.engines.length) {
    toast(eng.hint || 'No text-to-speech engine: pip install pyttsx3, or install espeak-ng on Linux.', 'err');
    return;
  }
  toast('Reading aloud…');
  try {
    const r = await api.transform('read_aloud', S.project, { ids });
    applyProjectJson(r.project, 'Read aloud');
    toast(`Made ${r.added} voice clip${r.added === 1 ? '' : 's'} with ${eng.engines[0]}.`);
  } catch (e) {
    toast(e.message, 'err');
  }
}

