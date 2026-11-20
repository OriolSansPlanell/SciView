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
    throw new Error(msg);
  }
  return data;
}

export const api = {
  state: () => request('GET', '/api/state'),
  putProject: (project) => request('PUT', '/api/project', project),
  frame: (t, scale) => request('GET', `/api/frame?t=${t.toFixed(4)}&scale=${scale}`),
  save: (path, project) => request('POST', '/api/save', { path, project }),
  open: (path) => request('POST', '/api/open', { path }),
  newFilm: (template) => request('POST', '/api/new', { template }),
  files: () => request('GET', '/api/files'),
  upload: (file) => request('POST', '/api/assets', file, { 'X-Filename': encodeURIComponent(file.name) }),
  columns: (path) => request('POST', '/api/columns', { path }),
  startExport: (opts) => request('POST', '/api/export', opts),
  exportStatus: () => request('GET', '/api/export'),
  cancelExport: () => request('POST', '/api/export/cancel', {}),
};
