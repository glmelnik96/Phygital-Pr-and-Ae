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

export function createApi({ fetch, baseUrl, getAuthHeaders }) {
  if (!fetch) throw new Error('createApi: fetch required');
  if (!baseUrl) throw new Error('createApi: baseUrl required');
  const url = (p) => `${baseUrl}${p}`;
  // getAuthHeaders is a () → object factory so panel can rotate the token
  // (e.g. after sidecar re-spawn that regenerated sidecar.token) without
  // re-creating the api instance. Returns {} when not provided (tests, dev).
  const authHeaders = typeof getAuthHeaders === 'function'
    ? getAuthHeaders
    : () => ({});

  async function request(path, { method = 'GET', body, headers, signal } = {}) {
    const mergedHeaders = { ...authHeaders(), ...(headers || {}) };
    let res;
    try {
      res = await fetch(url(path), { method, body, headers: mergedHeaders, signal });
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
    // POST /auth/recon — стартует headed Playwright login в фоне. Возвращает
    // {started:true,...} сразу; готовность определяем по /health
    // (session_ok=true, jwt_ttl_sec>0). 409 = recon уже идёт — это не ошибка
    // для UI, кнопка просто остаётся в "logging in…" состоянии.
    startRecon: () => request('/auth/recon', { method: 'POST' }),
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
    // POST /enhance — V1.2 prompt enhancer (preview-and-confirm flow).
    // Возвращает {enhanced_prompt, target_node_id, system_prompt_file}.
    // init_img_ids/init_img_dims пока всегда пустые (V1.2 ограничение);
    // V1.3: пробрасывать референс-картинку из активного image-slot для
    // более точного i2i/i2v энхансинга.
    enhancePrompt: ({ node_id, prompt, init_img_ids = [], init_img_dims = [] }) =>
      request('/enhance', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ node_id, prompt, init_img_ids, init_img_dims }),
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
      // Bypass `request()` because we need the raw Blob, not JSON. The auth
      // header must still be attached — without it the sidecar middleware
      // returns 401 and the user's auto-import dies silently.
      const res = await fetch(url(`/jobs/${encodeURIComponent(id)}/download?index=${index}`), {
        headers: authHeaders(),
      });
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
    // Disk-cache management — для UI «Очистить asset_uploads/».
    // /assets/disk-usage возвращает {count, total_bytes} (preview перед чисткой).
    // /assets/disk-cache (DELETE) удаляет файлы и возвращает {cleared_count, freed_bytes}.
    getDiskUsage: () => request('/assets/disk-usage'),
    clearDiskCache: () => request('/assets/disk-cache', { method: 'DELETE' }),
    _request: request,
  };
}
