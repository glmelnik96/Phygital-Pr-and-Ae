import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createApi } from '../../client/lib/api.js';

describe('api.getHealth', () => {
  let fetchMock;
  let api;
  beforeEach(() => {
    fetchMock = vi.fn();
    api = createApi({ fetch: fetchMock, baseUrl: 'http://127.0.0.1:8765' });
  });

  it('returns parsed body on 200', async () => {
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify({ ok: true, jwt_ttl_sec: 3600 }),
      { status: 200, headers: { 'content-type': 'application/json' } }
    ));
    const out = await api.getHealth();
    expect(out).toEqual({ ok: true, jwt_ttl_sec: 3600 });
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8765/health',
      expect.objectContaining({ method: 'GET' })
    );
  });

  it('throws ApiError kind=network on fetch reject', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    await expect(api.getHealth()).rejects.toMatchObject({ kind: 'network' });
  });

  it('throws ApiError kind=http with status on 5xx', async () => {
    fetchMock.mockResolvedValueOnce(new Response('boom', { status: 503 }));
    await expect(api.getHealth()).rejects.toMatchObject({ kind: 'http', status: 503 });
  });
});

describe('api.listVideoNodes', () => {
  it('GETs /nodes/video and returns body', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(
      JSON.stringify({ nodes: [{ node_id: 74 }] }),
      { status: 200, headers: { 'content-type': 'application/json' } }
    ));
    const api = createApi({ fetch: fetchMock, baseUrl: 'http://h' });
    const out = await api.listVideoNodes();
    expect(out.nodes[0].node_id).toBe(74);
    expect(fetchMock).toHaveBeenCalledWith('http://h/nodes/video', expect.objectContaining({ method: 'GET' }));
  });
});

describe('api.uploadAsset', () => {
  it('POSTs multipart with file blob and returns AssetEntry', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(
      JSON.stringify({ sha256: 'abc', file_obj_id: 999, height: 2048, width: 2048, uploaded_at: '2026-05-21T10:00:00Z' }),
      { status: 200, headers: { 'content-type': 'application/json' } }
    ));
    const api = createApi({ fetch: fetchMock, baseUrl: 'http://h' });
    const blob = new Blob(['data'], { type: 'image/jpeg' });
    const entry = await api.uploadAsset({ blob, filename: 'x.jpg' });
    expect(entry.sha256).toBe('abc');
    expect(entry.file_obj_id).toBe(999);
    const [u, init] = fetchMock.mock.calls[0];
    expect(u).toBe('http://h/assets');
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
  });
});

describe('api job endpoints', () => {
  it('createJob POSTs JSON body and returns job_id', async () => {
    const fm = vi.fn().mockResolvedValueOnce(new Response(
      JSON.stringify({ job_id: 'J123' }),
      { status: 200, headers: { 'content-type': 'application/json' } }
    ));
    const api = createApi({ fetch: fm, baseUrl: 'http://h' });
    const out = await api.createJob({ node_id: 94, params: { prompt: 'hi' }, init_files: { init_img: ['/a.jpg'] } });
    expect(out.job_id).toBe('J123');
    const [u, init] = fm.mock.calls[0];
    expect(u).toBe('http://h/jobs');
    expect(init.method).toBe('POST');
    expect(init.headers['content-type']).toBe('application/json');
    const body = JSON.parse(init.body);
    expect(body.node_id).toBe(94);
    expect(body.init_files.init_img).toEqual(['/a.jpg']);
  });

  it('listJobs GETs /jobs and returns array', async () => {
    const fm = vi.fn().mockResolvedValueOnce(new Response(
      JSON.stringify({ jobs: [{ job_id: 'A', status: 'running' }] }),
      { status: 200, headers: { 'content-type': 'application/json' } }
    ));
    const api = createApi({ fetch: fm, baseUrl: 'http://h' });
    const out = await api.listJobs();
    expect(out.jobs[0].status).toBe('running');
  });

  it('downloadJob fetches blob', async () => {
    const fm = vi.fn().mockResolvedValueOnce(new Response(
      new Blob(['BIN'], { type: 'image/jpeg' }),
      { status: 200, headers: { 'content-type': 'image/jpeg' } }
    ));
    const api = createApi({ fetch: fm, baseUrl: 'http://h' });
    const blob = await api.downloadJob('J123', 0);
    expect(blob).toBeInstanceOf(Blob);
    expect(fm.mock.calls[0][0]).toBe('http://h/jobs/J123/download?index=0');
  });
});

describe('api.getBalance', () => {
  it('GETs /account/balance and returns body', async () => {
    const fm = vi.fn().mockResolvedValueOnce(new Response(
      JSON.stringify({ ok: true, balance: 188505, currency: 'credits', is_infinity: false }),
      { status: 200, headers: { 'content-type': 'application/json' } }
    ));
    const api = createApi({ fetch: fm, baseUrl: 'http://h' });
    const out = await api.getBalance();
    expect(out.balance).toBe(188505);
    expect(fm.mock.calls[0][0]).toBe('http://h/account/balance');
  });

  it('surfaces 503 session_not_ready as ApiError kind=http status=503', async () => {
    const fm = vi.fn().mockResolvedValueOnce(new Response(
      JSON.stringify({ detail: 'session_not_ready' }),
      { status: 503, headers: { 'content-type': 'application/json' } }
    ));
    const api = createApi({ fetch: fm, baseUrl: 'http://h' });
    await expect(api.getBalance()).rejects.toMatchObject({ kind: 'http', status: 503 });
  });
});

describe('api.extractFrame', () => {
  it('POSTs JSON with source_path+at_sec', async () => {
    const fm = vi.fn().mockResolvedValueOnce(new Response(
      JSON.stringify({ path: '/tmp/x.jpg' }),
      { status: 200, headers: { 'content-type': 'application/json' } }
    ));
    const api = createApi({ fetch: fm, baseUrl: 'http://h' });
    const out = await api.extractFrame({ source_path: '/foo.mp4', at_sec: 1.5 });
    expect(out.path).toBe('/tmp/x.jpg');
    const body = JSON.parse(fm.mock.calls[0][1].body);
    expect(body).toEqual({ source_path: '/foo.mp4', at_sec: 1.5 });
  });
});

describe('api.previewCost', () => {
  it('POSTs JSON with node_id+params, init_files=empty', async () => {
    const fm = vi.fn().mockResolvedValueOnce(new Response(
      JSON.stringify({ price: 120, currency: 'credits' }),
      { status: 200, headers: { 'content-type': 'application/json' } }
    ));
    const api = createApi({ fetch: fm, baseUrl: 'http://h' });
    const out = await api.previewCost({ node_id: 74, params: { prompt: 'hi', duration: 5 } });
    expect(out.price).toBe(120);
    const body = JSON.parse(fm.mock.calls[0][1].body);
    expect(body.node_id).toBe(74);
    expect(body.params.duration).toBe(5);
    expect(body.init_files).toEqual({});
  });
});
