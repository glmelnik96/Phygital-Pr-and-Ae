import { describe, it, expect, beforeEach } from 'vitest';
import { createStore, DEFAULT_STATE, createDraftActions, makeInitialDraft } from '../../client/lib/state.js';
import { createUploadActions, isAssetCacheHit } from '../../client/lib/state.js';
import { diffJobs, mergeJobs } from '../../client/lib/state.js';

describe('state draft actions', () => {
  let store, actions;
  beforeEach(() => {
    store = createStore({ ...DEFAULT_STATE, draft: makeInitialDraft() });
    actions = createDraftActions(store);
  });

  it('makeInitialDraft picks Nano Banana generate (t2i) by default', () => {
    // V1.2: дефолт = первый сценарий из meta.scenarios. Для Nano Banana
    // и GPT Image это 'generate' (text→image), не требующий слотов —
    // cold-start превращается в zero-friction t2i.
    const d = makeInitialDraft();
    expect(d.model_id).toBe(94);
    expect(d.scenario).toBe('generate');
    expect(d.slots).toEqual({});
    expect(d.prompt).toBe('');
  });

  it('setModel switches model + picks first scenario from meta', () => {
    actions.setModel(74, { videoNodes: [{ node_id: 74, model: 'Kling', slots: {}, scenarios: ['start_prompt', 'start_end_prompt'], scenario_slots: { start_prompt: [], start_end_prompt: [] }, default_params: {} }] });
    expect(store.get().draft.model_id).toBe(74);
    expect(store.get().draft.scenario).toBe('start_prompt');
  });

  it('setScenario clears slots not in new schema', () => {
    actions.setSlot('init_img', [{ path: '/a.jpg', name: 'a.jpg', source: 'disk' }]);
    actions.setSlot('image_tail', { path: '/b.jpg', name: 'b.jpg', source: 'disk' });
    actions.setScenario('start_prompt', {
      videoNodes: [{ node_id: 94, slots: { init_img: 'array' }, scenarios: ['start_prompt'], scenario_slots: { start_prompt: ['init_img'] } }],
    });
    const d = store.get().draft;
    expect(d.slots.init_img).toBeDefined();
    expect(d.slots.image_tail).toBeUndefined();
  });

  it('setPrompt mutates prompt only', () => {
    actions.setPrompt('hello world');
    expect(store.get().draft.prompt).toBe('hello world');
  });
});

describe('upload history / dedup', () => {
  it('first time sha256 → not cached', () => {
    const history = {};
    const entry = { sha256: 'abc', uploaded_at: new Date().toISOString() };
    expect(isAssetCacheHit({ history, entry, now: Date.now() })).toBe(false);
  });
  it('repeat sha256 within session → cached', () => {
    const history = { abc: { firstSeenAt: Date.now() - 60_000 } };
    const entry = { sha256: 'abc', uploaded_at: new Date(Date.now() - 50_000).toISOString() };
    expect(isAssetCacheHit({ history, entry, now: Date.now() })).toBe(true);
  });
  it('uploaded_at older than session window → cached', () => {
    const history = {};
    const entry = { sha256: 'def', uploaded_at: new Date(Date.now() - 10_000).toISOString() };
    expect(isAssetCacheHit({ history, entry, now: Date.now() })).toBe(true);
  });
});

describe('jobs reducer', () => {
  const J = (id, status, updated) => ({ job_id: id, status, updated_at: updated, node_id: 94, progress: 0, result_paths: [], error: null });

  it('mergeJobs replaces local snapshot in id order', () => {
    const prev = [J('A', 'queued', '1')];
    const remote = [J('A', 'running', '2'), J('B', 'queued', '3')];
    const merged = mergeJobs(prev, remote);
    expect(merged.find(j => j.job_id === 'A').status).toBe('running');
    expect(merged.find(j => j.job_id === 'B')).toBeTruthy();
  });

  it('mergeJobs preserves local-only fields (e.g. projectItemId)', () => {
    const prev = [{ ...J('A', 'completed', '1'), projectItemId: 'PI-1', resultBlobUrl: 'blob:abc' }];
    const remote = [J('A', 'completed', '1')];
    const merged = mergeJobs(prev, remote);
    expect(merged[0].projectItemId).toBe('PI-1');
    expect(merged[0].resultBlobUrl).toBe('blob:abc');
  });

  it('diffJobs returns entered/changed status transitions', () => {
    const prev = [J('A', 'queued', '1')];
    const remote = [J('A', 'completed', '2'), J('B', 'running', '3')];
    const diff = diffJobs(prev, remote);
    expect(diff.completedNow.map(j => j.job_id)).toEqual(['A']);
    expect(diff.newJobs.map(j => j.job_id)).toEqual(['B']);
  });
});
