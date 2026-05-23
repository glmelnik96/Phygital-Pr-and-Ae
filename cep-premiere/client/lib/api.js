// Single fetch surface for the sidecar.
// Pure factory taking {fetch, baseUrl} so tests pass mocks easily.

export class ApiError extends Error {
  constructor({ kind, status, body, message }) {
    super(message || `${kind}${status ? ` ${status}` : ''}`);
    this.kind = kind;       // 'network' | 'http' | 'parse'
    this.status = status;
    this.body = body;
  }
}

export function createApi({ fetch, baseUrl }) {
  if (!fetch) throw new Error('createApi: fetch required');
  if (!baseUrl) throw new Error('createApi: baseUrl required');
  const url = (p) => `${baseUrl}${p}`;

  async function request(path, { method = 'GET', body, headers, signal } = {}) {
    let res;
    try {
      res = await fetch(url(path), { method, body, headers, signal });
    } catch (e) {
      throw new ApiError({ kind: 'network', message: e.message });
    }
    const ct = res.headers.get('content-type') || '';
    let parsed = null;
    if (ct.includes('application/json')) {
      try { parsed = await res.json(); }
      catch (e) { throw new ApiError({ kind: 'parse', status: res.status, message: e.message }); }
    }
    if (!res.ok) {
      throw new ApiError({ kind: 'http', status: res.status, body: parsed });
    }
    return parsed;
  }

  return {
    getHealth: () => request('/health'),
    getBalance: () => request('/account/balance'),
    listVideoNodes: () => request('/nodes/video'),
    listNodes: () => request('/nodes'),
    uploadAsset: async ({ blob, filename }) => {
      const fd = new FormData();
      fd.append('file', blob, filename);
      return request('/assets', { method: 'POST', body: fd });
    },
    createJob: ({ node_id, params, init_files }) =>
      request('/jobs', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ node_id, params, init_files }),
      }),
    previewCost: ({ node_id, params }) =>
      request('/jobs/preview-cost', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ node_id, params, init_files: {} }),
      }),
    listJobs: (opts = {}) => {
      const qs = [];
      if (opts.status) qs.push(`status=${encodeURIComponent(opts.status)}`);
      if (opts.limit) qs.push(`limit=${opts.limit}`);
      return request(`/jobs${qs.length ? '?' + qs.join('&') : ''}`);
    },
    getJob: (id) => request(`/jobs/${encodeURIComponent(id)}`),
    deleteJob: (id) => request(`/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    downloadJob: async (id, index = 0) => {
      const res = await fetch(url(`/jobs/${encodeURIComponent(id)}/download?index=${index}`));
      if (!res.ok) throw new ApiError({ kind: 'http', status: res.status });
      return res.blob();
    },
    clipVideo: ({ source_path, in_sec, out_sec }) =>
      request('/clip-video', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ source_path, in_sec, out_sec }),
      }),
    extractFrame: ({ source_path, at_sec }) =>
      request('/extract-frame', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ source_path, at_sec }),
      }),
    _request: request,
  };
}
