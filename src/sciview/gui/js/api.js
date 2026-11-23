// Thin client for the local SciView server. Mutating requests carry X-SciView: 1.
async function request(method, url, body, headers = {}) {
  const opts = { method, headers: { ...headers } };
  if (method !== 'GET') opts.headers['X-SciView'] = '1';
  if (body !== undefined) {
    if (body instanceof Blob || body instanceof ArrayBuffer) {
      opts.body = body;
    } else {
      opts.body = JSON.stringify(body);
      opts.headers['Content-Type'] = 'application/json';
    }
  }
  const res = await fetch(url, opts);
  const type = res.headers.get('Content-Type') || '';
  const data = type.includes('json') ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = (data && data.error) || res.statusText || 'request failed';
    const err = new Error(msg);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

export const api = {
  state: () => request('GET', '/api/state'),
  putProject: (project, base) => request('PUT', base == null ? '/api/project' : `/api/project?base=${base}`, project),
  project: () => request('GET', '/api/project'),
  changes: () => request('GET', '/api/changes'),
  frame: async (t, scale, play = false) => {
    const res = await fetch(`/api/frame?t=${t.toFixed(4)}&scale=${scale}${play ? '&play=1' : ''}`);
    if (!res.ok) {
      let msg = res.statusText;
      try { msg = (await res.json()).error || msg; } catch (e) { /* not JSON */ }
      throw new Error(msg);
    }
    const raw = atob(res.headers.get('X-Frame-Info') || 'e30=');
    const meta = JSON.parse(new TextDecoder().decode(Uint8Array.from(raw, (c) => c.charCodeAt(0))));
    meta.image = URL.createObjectURL(await res.blob());
    return meta;
  },
  recover: (action) => request('POST', '/api/recover', { action }),
  save: (path, project) => request('POST', '/api/save', { path, project }),
  open: (path) => request('POST', '/api/open', { path }),
  newFilm: (template) => request('POST', '/api/new', { template }),
  files: () => request('GET', '/api/files'),
  upload: (file) => request('POST', '/api/assets', file, { 'X-Filename': encodeURIComponent(file.name) }),
  columns: (path) => request('POST', '/api/columns', { path }),
  startExport: (opts) => request('POST', '/api/export', opts),
  exportStatus: () => request('GET', '/api/export'),
  cancelExport: () => request('POST', '/api/export/cancel', {}),
  waveform: (path, bins = 600, trim = 0, length = null) => request('GET',
    `/api/waveform?path=${encodeURIComponent(path)}&bins=${bins}&trim=${trim}${length != null ? `&length=${length}` : ''}`),
  transform: (op, project, args = {}) => request('POST', '/api/transform', { op, project, ...args }),
  themes: () => request('GET', '/api/themes'),
  checks: () => request('GET', '/api/checks'),
  tts: () => request('GET', '/api/tts'),
  assistantConfig: () => request('GET', '/api/assistant/config'),
  saveAssistantConfig: (cfg) => request('POST', '/api/assistant/config', cfg),
  assistantStart: (body) => request('POST', '/api/assistant', body),
  assistantStatus: (id, since) => request('GET', `/api/assistant?id=${encodeURIComponent(id)}&since=${since}`),
  assistantStop: (id) => request('POST', '/api/assistant/stop', { id }),
};
