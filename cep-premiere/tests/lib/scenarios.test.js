// V1.2 e2e-style scenario tests: drive the same store + actions the panel
// uses, simulate every interactive surface, and assert no stale state
// survives across transitions (family/model/scenario/prompt/enhance).
//
// These tests do NOT mount Preact components — they target the *logical*
// behaviour that the UI relies on. If a regression makes Submit forever
// disabled or leaks enhance-preview into a fresh model, these will fail.

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  createStore, DEFAULT_STATE, createDraftActions,
  makeInitialDraft, loadDraftFromStorage, saveDraftToStorage,
  isEnhancedFresh, DRAFT_LS_KEY,
} from '../../client/lib/state.js';
import { validateDraft } from '../../client/lib/validation.js';
import {
  getNodeMeta, getNodeFamily, listNodesByFamily,
  nodeHasPrompt, FAMILIES,
} from '../../client/lib/slot_schema.js';
import { createApi } from '../../client/lib/api.js';

// Fixture mirrors the shape /nodes/video returns (4 video nodes).
const VIDEO_NODES = [
  {
    node_id: 74, model: 'Kling',
    slots: { init_img: 'array', image_tail: 'scalar' },
    scenarios: ['start_prompt', 'start_end_prompt'],
    scenario_slots: { start_prompt: ['init_img'], start_end_prompt: ['init_img', 'image_tail'] },
    default_params: { ratio: 'r_16_9', duration: 5 },
    param_options: {
      ratio: { kind: 'enum', options: ['r_16_9', 'r_1_1'] },
      duration: { kind: 'number', min: 5, max: 10, step: 5 },
    },
  },
  {
    node_id: 100, model: 'Seedance',
    slots: { start_img: 'scalar', ref_vid: 'scalar' },
    scenarios: ['t2v', 'i2v', 'v2v'],
    scenario_slots: { t2v: [], i2v: ['start_img'], v2v: ['ref_vid'] },
    default_params: { aspect_ratio: '16_9' },
    param_options: { aspect_ratio: { kind: 'enum', options: ['16_9', '1_1'] } },
  },
  {
    node_id: 121, model: 'Kling Omni',
    slots: { ref_img: 'scalar' },
    scenarios: ['t2v'],
    scenario_slots: { t2v: [] },
    default_params: {},
  },
  {
    node_id: 124, model: 'Kling Motion',
    slots: { char_ref: 'scalar', ref_vid: 'scalar' },
    scenarios: ['char_video_prompt'],
    scenario_slots: { char_video_prompt: ['char_ref', 'ref_vid'] },
    default_params: {},
  },
];

const HEALTH_ONLINE = { status: 'online', jwt_ttl_sec: 3600 };
const BAL_INF = { value: null, infinity: true, error: null, loading: false };

function makeFixture() {
  const store = createStore({
    ...DEFAULT_STATE,
    health: HEALTH_ONLINE,
    videoNodes: VIDEO_NODES,
    balance: BAL_INF,
    draft: makeInitialDraft(),
  });
  const actions = createDraftActions(store);
  return { store, actions };
}

// Replica of SubmitButton's disabled-computation. Keeps test independent of
// React/Preact mount lifecycle, but mirrors prod logic exactly. If SubmitButton
// changes its rules, this helper must be updated in lockstep.
function submitDisabled(snap, { localBusy = false } = {}) {
  const { draft, videoNodes, health, balance } = snap;
  const v = validateDraft({ videoNodes, draft });
  const meta = getNodeMeta({ videoNodes, nodeId: draft.model_id });
  const enhanceRequired = draft.enhance_prompt && nodeHasPrompt(meta);
  const needsEnhancePreview = enhanceRequired && !isEnhancedFresh(draft);
  const insufficient = false; // balance=infinity in tests
  return (
    localBusy ||
    health.status !== 'online' ||
    !v.ok ||
    insufficient ||
    needsEnhancePreview ||
    !!draft.enhanced_busy
  );
}

// ─── 1. Cold-boot defaults ──────────────────────────────────────────────────

describe('cold boot', () => {
  beforeEach(() => { try { localStorage.clear(); } catch {} });

  it('initial draft is Image / Nano Banana / generate (t2i)', () => {
    // V1.2: cold-start = text→image, чтобы юзеру не нужно было сначала
    // прикладывать референс (см. slot_schema.NANO_BANANA_META.scenarios).
    const { store } = makeFixture();
    const d = store.get().draft;
    expect(d.family).toBe('image');
    expect(d.model_id).toBe(94);
    expect(d.scenario).toBe('generate');
    expect(d.enhance_prompt).toBe(false);
    expect(d.enhanced_prompt).toBeNull();
  });

  it('FAMILIES list is exactly the 3 V1.2 buckets', () => {
    expect(FAMILIES).toEqual(['image', 'video', 'upscale']);
  });

  it('listNodesByFamily routes nodes correctly', () => {
    const img = listNodesByFamily({ videoNodes: VIDEO_NODES, family: 'image' });
    const vid = listNodesByFamily({ videoNodes: VIDEO_NODES, family: 'video' });
    const ups = listNodesByFamily({ videoNodes: VIDEO_NODES, family: 'upscale' });
    const num = (a, b) => a - b;
    expect(img.map(n => n.node_id).sort(num)).toEqual([94, 98]);
    expect(vid.map(n => n.node_id).sort(num)).toEqual([74, 100, 121, 124]);
    expect(ups.map(n => n.node_id)).toEqual([87]);
  });
});

// ─── 2. Family switching: every transition is clean ─────────────────────────

describe('family switching', () => {
  it('image → video picks first video node + resets slots/params', () => {
    const { store, actions } = makeFixture();
    actions.setSlot('init_img', [{ path: '/a.jpg', name: 'a.jpg', source: 'disk' }]);
    actions.setParam('ratio', 'default');
    actions.setFamily('video', { videoNodes: VIDEO_NODES });
    const d = store.get().draft;
    expect(d.family).toBe('video');
    expect(d.model_id).toBe(74); // first video node
    expect(d.scenario).toBe('start_prompt');
    expect(d.slots).toEqual({});
    expect(d.params).toEqual({});
  });

  it('image → upscale picks Topaz', () => {
    const { store, actions } = makeFixture();
    actions.setFamily('upscale', { videoNodes: VIDEO_NODES });
    const d = store.get().draft;
    expect(d.family).toBe('upscale');
    expect(d.model_id).toBe(87);
    expect(d.scenario).toBe('upscale');
  });

  it('video → upscale → image returns to Nano Banana', () => {
    const { store, actions } = makeFixture();
    actions.setFamily('video', { videoNodes: VIDEO_NODES });
    actions.setFamily('upscale', { videoNodes: VIDEO_NODES });
    actions.setFamily('image', { videoNodes: VIDEO_NODES });
    const d = store.get().draft;
    expect(d.family).toBe('image');
    expect(d.model_id).toBe(94);
    expect(d.scenario).toBe('generate');
  });

  it('setFamily to current family preserves model_id (no spurious reset)', () => {
    const { store, actions } = makeFixture();
    actions.setFamily('video', { videoNodes: VIDEO_NODES });
    actions.setModel(121, { videoNodes: VIDEO_NODES });
    actions.setPrompt('a man dancing');
    actions.setFamily('video', { videoNodes: VIDEO_NODES }); // same family
    const d = store.get().draft;
    expect(d.model_id).toBe(121);          // unchanged
    expect(d.prompt).toBe('a man dancing'); // prompt preserved (no model swap)
  });

  it('family=video with empty videoNodes does not crash, leaves model_id', () => {
    const store = createStore({
      ...DEFAULT_STATE, health: HEALTH_ONLINE, videoNodes: null,
      draft: makeInitialDraft(),
    });
    const actions = createDraftActions(store);
    actions.setFamily('video', { videoNodes: null });
    expect(store.get().draft.family).toBe('video');
    expect(store.get().draft.model_id).toBe(94); // untouched
  });
});

// ─── 3. Model switching within a family ─────────────────────────────────────

describe('model switching', () => {
  it('setModel resets slots/params and re-derives family', () => {
    const { store, actions } = makeFixture();
    actions.setModel(74, { videoNodes: VIDEO_NODES });
    actions.setSlot('init_img', [{ path: '/x.jpg', name: 'x.jpg', source: 'disk' }]);
    actions.setParam('ratio', 'r_1_1');
    actions.setModel(100, { videoNodes: VIDEO_NODES });
    const d = store.get().draft;
    expect(d.model_id).toBe(100);
    expect(d.family).toBe('video'); // re-derived from meta
    expect(d.slots).toEqual({});    // wiped — schemas differ between 74/100
    expect(d.params).toEqual({});
    expect(d.scenario).toBe('t2v'); // first scenario from 100
  });

  it('setModel(98) flips family to image', () => {
    const { store, actions } = makeFixture();
    actions.setModel(74, { videoNodes: VIDEO_NODES });
    actions.setModel(98, { videoNodes: VIDEO_NODES });
    expect(store.get().draft.family).toBe('image');
    expect(store.get().draft.model_id).toBe(98);
  });

  it('setModel(87 Topaz) flips family to upscale + scenario "upscale"', () => {
    const { store, actions } = makeFixture();
    actions.setModel(87, { videoNodes: VIDEO_NODES });
    const d = store.get().draft;
    expect(d.family).toBe('upscale');
    expect(d.scenario).toBe('upscale');
  });
});

// ─── 4. Scenario switching ──────────────────────────────────────────────────

describe('scenario switching', () => {
  it('setScenario keeps only slots in new schema (drops stale slot)', () => {
    const { store, actions } = makeFixture();
    actions.setModel(74, { videoNodes: VIDEO_NODES });
    actions.setSlot('init_img', [{ path: '/a.jpg', name: 'a.jpg', source: 'disk' }]);
    actions.setSlot('image_tail', { path: '/b.jpg', name: 'b.jpg', source: 'disk' });
    actions.setScenario('start_prompt', { videoNodes: VIDEO_NODES });
    const d = store.get().draft;
    expect(d.slots.init_img).toBeDefined();
    expect(d.slots.image_tail).toBeUndefined();
  });

  it('setScenario preserves params (schema is per-node, not per-scenario)', () => {
    const { store, actions } = makeFixture();
    actions.setModel(74, { videoNodes: VIDEO_NODES });
    actions.setParam('ratio', 'r_1_1');
    actions.setScenario('start_end_prompt', { videoNodes: VIDEO_NODES });
    expect(store.get().draft.params.ratio).toBe('r_1_1');
  });
});

// ─── 5. Enhance preview lifecycle ───────────────────────────────────────────

describe('enhance preview flow', () => {
  beforeEach(() => { try { localStorage.clear(); } catch {} });

  it('toggle OFF: no preview, no busy, no error', () => {
    const { store, actions } = makeFixture();
    actions.setPrompt('a cat');
    expect(isEnhancedFresh(store.get().draft)).toBe(false);
    expect(store.get().draft.enhance_prompt).toBe(false);
  });

  it('toggle ON → setEnhancedResult marks preview fresh', () => {
    const { store, actions } = makeFixture();
    actions.setPrompt('a cat');
    actions.setEnhanceToggle(true);
    actions.setEnhancedBusy(true);
    actions.setEnhancedResult({ prompt: 'a cat', model_id: 94, text: 'ENHANCED a cat' });
    const d = store.get().draft;
    expect(d.enhanced_busy).toBe(false);
    expect(d.enhanced_prompt).toBe('ENHANCED a cat');
    expect(isEnhancedFresh(d)).toBe(true);
  });

  it('editEnhancedPrompt keeps preview fresh (enhanced_for unchanged)', () => {
    const { store, actions } = makeFixture();
    actions.setPrompt('a cat');
    actions.setEnhanceToggle(true);
    actions.setEnhancedResult({ prompt: 'a cat', model_id: 94, text: 'ENHANCED a cat' });
    actions.editEnhancedPrompt('ENHANCED a cat, with editing');
    expect(isEnhancedFresh(store.get().draft)).toBe(true);
    expect(store.get().draft.enhanced_prompt).toBe('ENHANCED a cat, with editing');
  });

  it('changing prompt invalidates preview (becomes stale → cleared)', () => {
    const { store, actions } = makeFixture();
    actions.setPrompt('a cat');
    actions.setEnhanceToggle(true);
    actions.setEnhancedResult({ prompt: 'a cat', model_id: 94, text: 'ENHANCED a cat' });
    actions.setPrompt('a dog'); // setPrompt resets preview via resetEnhancedPreview()
    const d = store.get().draft;
    expect(d.enhanced_prompt).toBeNull();
    expect(d.enhanced_for).toBeNull();
    expect(d.enhance_prompt).toBe(true); // toggle stays ON
    expect(isEnhancedFresh(d)).toBe(false);
  });

  it('changing model invalidates preview', () => {
    const { store, actions } = makeFixture();
    actions.setPrompt('a cat');
    actions.setEnhanceToggle(true);
    actions.setEnhancedResult({ prompt: 'a cat', model_id: 94, text: 'ENHANCED a cat' });
    actions.setModel(98, { videoNodes: VIDEO_NODES });
    expect(store.get().draft.enhanced_prompt).toBeNull();
  });

  it('changing family clears preview', () => {
    const { store, actions } = makeFixture();
    actions.setPrompt('a cat');
    actions.setEnhanceToggle(true);
    actions.setEnhancedResult({ prompt: 'a cat', model_id: 94, text: 'ENHANCED' });
    actions.setFamily('video', { videoNodes: VIDEO_NODES });
    expect(store.get().draft.enhanced_prompt).toBeNull();
  });

  it('clearEnhancedPreview wipes preview but keeps toggle', () => {
    const { store, actions } = makeFixture();
    actions.setPrompt('a cat');
    actions.setEnhanceToggle(true);
    actions.setEnhancedResult({ prompt: 'a cat', model_id: 94, text: 'ENHANCED' });
    actions.clearEnhancedPreview();
    const d = store.get().draft;
    expect(d.enhanced_prompt).toBeNull();
    expect(d.enhanced_for).toBeNull();
    expect(d.enhance_prompt).toBe(true); // toggle untouched
  });

  it('setEnhancedError clears busy, keeps message', () => {
    const { store, actions } = makeFixture();
    actions.setEnhancedBusy(true);
    actions.setEnhancedError('upstream 502');
    const d = store.get().draft;
    expect(d.enhanced_busy).toBe(false);
    expect(d.enhanced_error).toBe('upstream 502');
  });

  it('Topaz: nodeHasPrompt(meta)=false ⇒ enhance flow not applicable', () => {
    const meta = getNodeMeta({ videoNodes: VIDEO_NODES, nodeId: 87 });
    expect(nodeHasPrompt(meta)).toBe(false);
  });
});

// ─── 6. Submit button enablement matrix ─────────────────────────────────────

describe('submit button enablement', () => {
  function snapOf(draft) {
    return { draft, videoNodes: VIDEO_NODES, health: HEALTH_ONLINE, balance: BAL_INF, cost: {} };
  }

  it('disabled when health offline', () => {
    const draft = makeInitialDraft();
    draft.prompt = 'a cat';
    draft.slots = { init_img: [{ path: '/x.jpg' }] };
    const snap = { ...snapOf(draft), health: { status: 'offline' } };
    expect(submitDisabled(snap)).toBe(true);
  });

  it('disabled with empty prompt for prompt-bearing node (Nano Banana)', () => {
    const draft = makeInitialDraft();
    draft.slots = { init_img: [{ path: '/x.jpg' }] };
    expect(submitDisabled(snapOf(draft))).toBe(true);
  });

  it('enabled for Nano Banana with prompt + slot', () => {
    const draft = makeInitialDraft();
    draft.prompt = 'a cat';
    draft.slots = { init_img: [{ path: '/x.jpg' }] };
    expect(submitDisabled(snapOf(draft))).toBe(false);
  });

  it('Topaz: no prompt required — enabled with just init_video', () => {
    const draft = makeInitialDraft();
    draft.family = 'upscale';
    draft.model_id = 87;
    draft.scenario = 'upscale';
    draft.slots = { init_video: { path: '/v.mp4', name: 'v.mp4', source: 'disk' } };
    expect(submitDisabled(snapOf(draft))).toBe(false);
  });

  it('Topaz: missing init_video keeps Submit disabled', () => {
    const draft = makeInitialDraft();
    draft.family = 'upscale';
    draft.model_id = 87;
    draft.scenario = 'upscale';
    expect(submitDisabled(snapOf(draft))).toBe(true);
  });

  it('enhance ON without preview ⇒ disabled', () => {
    const draft = makeInitialDraft();
    draft.prompt = 'a cat';
    draft.slots = { init_img: [{ path: '/x.jpg' }] };
    draft.enhance_prompt = true;
    expect(submitDisabled(snapOf(draft))).toBe(true);
  });

  it('enhance ON with stale preview (prompt changed after enhance) ⇒ disabled', () => {
    const draft = makeInitialDraft();
    draft.prompt = 'a dog'; // current
    draft.slots = { init_img: [{ path: '/x.jpg' }] };
    draft.enhance_prompt = true;
    draft.enhanced_prompt = 'ENHANCED a cat';
    draft.enhanced_for = { prompt: 'a cat', model_id: 94 }; // mismatched
    expect(isEnhancedFresh(draft)).toBe(false);
    expect(submitDisabled(snapOf(draft))).toBe(true);
  });

  it('enhance ON with fresh preview ⇒ enabled', () => {
    const draft = makeInitialDraft();
    draft.prompt = 'a cat';
    draft.slots = { init_img: [{ path: '/x.jpg' }] };
    draft.enhance_prompt = true;
    draft.enhanced_prompt = 'ENHANCED a cat';
    draft.enhanced_for = { prompt: 'a cat', model_id: 94 };
    expect(submitDisabled(snapOf(draft))).toBe(false);
  });

  it('enhanced_busy ⇒ disabled (in-flight enhance call)', () => {
    const draft = makeInitialDraft();
    draft.prompt = 'a cat';
    draft.slots = { init_img: [{ path: '/x.jpg' }] };
    draft.enhance_prompt = true;
    draft.enhanced_busy = true;
    expect(submitDisabled(snapOf(draft))).toBe(true);
  });

  it('Topaz with enhance toggle ON: NOT blocked (enhance N/A)', () => {
    const draft = makeInitialDraft();
    draft.family = 'upscale';
    draft.model_id = 87;
    draft.scenario = 'upscale';
    draft.slots = { init_video: { path: '/v.mp4' } };
    draft.enhance_prompt = true; // toggle leak from previous family
    expect(submitDisabled(snapOf(draft))).toBe(false);
  });
});

// ─── 7. Draft persistence (localStorage round-trip + backfill) ──────────────

describe('persistence + backfill', () => {
  beforeEach(() => { try { localStorage.clear(); } catch {} });

  it('save → load round-trip preserves all V1.2 fields', () => {
    const d = makeInitialDraft();
    d.enhance_prompt = true;
    d.enhanced_prompt = 'pre-enhanced';
    d.enhanced_for = { prompt: '', model_id: 94 };
    saveDraftToStorage(d);
    const loaded = loadDraftFromStorage();
    expect(loaded).toMatchObject({
      family: 'image', model_id: 94, scenario: 'generate',
      enhance_prompt: true, enhanced_prompt: 'pre-enhanced',
    });
  });

  it('legacy draft (no family field) is loadable, GenerateTab can backfill', () => {
    // Simulate a pre-V1.2 draft from someone's localStorage.
    const legacy = {
      model_id: 100, scenario: 't2v', prompt: 'hello',
      slots: {}, params: { aspect_ratio: '16_9' },
    };
    localStorage.setItem(DRAFT_LS_KEY, JSON.stringify(legacy));
    const loaded = loadDraftFromStorage();
    expect(loaded.model_id).toBe(100);
    // GenerateTab does: family = draft.family || getNodeFamily(meta) || 'image'
    const meta = getNodeMeta({ videoNodes: VIDEO_NODES, nodeId: loaded.model_id });
    const backfilled = loaded.family || getNodeFamily(meta) || 'image';
    expect(backfilled).toBe('video');
  });

  it('loadDraftFromStorage handles corrupt JSON gracefully', () => {
    localStorage.setItem(DRAFT_LS_KEY, '{not json');
    expect(loadDraftFromStorage()).toBeNull();
  });

  it('loadDraftFromStorage rejects payload without model_id', () => {
    localStorage.setItem(DRAFT_LS_KEY, JSON.stringify({ family: 'image' }));
    expect(loadDraftFromStorage()).toBeNull();
  });
});

// ─── 8. PromptInput → api.enhancePrompt wiring (network contract) ───────────

describe('api.enhancePrompt', () => {
  it('POSTs JSON to /enhance with node_id, prompt, init_img_ids, init_img_dims', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(
      JSON.stringify({ enhanced_prompt: 'ENHANCED', target_node_id: 94, system_prompt_file: 'enh_nano_banana.md' }),
      { status: 200, headers: { 'content-type': 'application/json' } },
    ));
    const api = createApi({ fetch: fetchMock, baseUrl: 'http://h' });
    const out = await api.enhancePrompt({ node_id: 94, prompt: 'a cat' });
    expect(out.enhanced_prompt).toBe('ENHANCED');
    expect(out.target_node_id).toBe(94);
    const [u, init] = fetchMock.mock.calls[0];
    expect(u).toBe('http://h/enhance');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({
      node_id: 94, prompt: 'a cat', init_img_ids: [], init_img_dims: [],
    });
  });

  it('400 enhancer_not_supported propagates as ApiError with parsed body', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(
      JSON.stringify({ detail: { error: 'enhancer_not_supported', node_id: 87, message: 'не настроен' } }),
      { status: 400, headers: { 'content-type': 'application/json' } },
    ));
    const api = createApi({ fetch: fetchMock, baseUrl: 'http://h' });
    await expect(api.enhancePrompt({ node_id: 87, prompt: 'x' }))
      .rejects.toMatchObject({ kind: 'http', status: 400 });
  });

  it('502 enhancer_failed propagates with status', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(
      JSON.stringify({ detail: { error: 'enhancer_failed', message: 'upstream rejected' } }),
      { status: 502, headers: { 'content-type': 'application/json' } },
    ));
    const api = createApi({ fetch: fetchMock, baseUrl: 'http://h' });
    await expect(api.enhancePrompt({ node_id: 94, prompt: 'x' }))
      .rejects.toMatchObject({ kind: 'http', status: 502 });
  });
});

// ─── 9. End-to-end user journey: cold boot → upscale workflow ───────────────

describe('e2e user journey', () => {
  beforeEach(() => { try { localStorage.clear(); } catch {} });

  it('happy path: image → fill slot → write prompt → submit-ready', () => {
    const { store, actions } = makeFixture();
    actions.setPrompt('a watercolor mountain at dawn');
    actions.setSlot('init_img', [{ path: '/m.jpg', name: 'm.jpg', source: 'disk' }]);
    expect(submitDisabled(store.get())).toBe(false);
  });

  it('happy path: video → kling start_end_prompt → both slots filled', () => {
    const { store, actions } = makeFixture();
    actions.setFamily('video', { videoNodes: VIDEO_NODES });
    actions.setScenario('start_end_prompt', { videoNodes: VIDEO_NODES });
    actions.setPrompt('camera pulls back');
    actions.setSlot('init_img', [{ path: '/a.jpg' }]);
    actions.setSlot('image_tail', { path: '/b.jpg' });
    expect(submitDisabled(store.get())).toBe(false);
  });

  it('happy path: upscale → drop video → no prompt → submit-ready', () => {
    const { store, actions } = makeFixture();
    actions.setFamily('upscale', { videoNodes: VIDEO_NODES });
    actions.setSlot('init_video', { path: '/clip.mp4', name: 'clip.mp4', source: 'disk' });
    expect(submitDisabled(store.get())).toBe(false);
  });

  it('full enhance journey: toggle on → enhance → edit → submit-ready', async () => {
    const { store, actions } = makeFixture();
    actions.setPrompt('a cat');
    actions.setSlot('init_img', [{ path: '/x.jpg' }]);
    actions.setEnhanceToggle(true);
    expect(submitDisabled(store.get())).toBe(true); // need preview first

    // Simulate /enhance success.
    actions.setEnhancedBusy(true);
    expect(submitDisabled(store.get())).toBe(true); // busy
    actions.setEnhancedResult({ prompt: 'a cat', model_id: 94, text: 'a regal tabby cat' });
    expect(submitDisabled(store.get())).toBe(false);

    // User edits enhanced text — still fresh.
    actions.editEnhancedPrompt('a regal tabby cat, golden hour');
    expect(submitDisabled(store.get())).toBe(false);

    // User then edits ORIGINAL prompt — preview drops, Submit disables.
    actions.setPrompt('a cat with stripes');
    expect(store.get().draft.enhanced_prompt).toBeNull();
    expect(submitDisabled(store.get())).toBe(true);
  });

  it('stale-state guard: family ping-pong does not leak slots/params/preview', () => {
    const { store, actions } = makeFixture();
    // Set up all kinds of state on image.
    actions.setPrompt('a cat');
    actions.setSlot('init_img', [{ path: '/x.jpg' }]);
    actions.setParam('ratio', 'r_1_1');
    actions.setEnhanceToggle(true);
    actions.setEnhancedResult({ prompt: 'a cat', model_id: 94, text: 'ENHANCED' });

    // Switch families: image → video → upscale → image
    actions.setFamily('video', { videoNodes: VIDEO_NODES });
    actions.setFamily('upscale', { videoNodes: VIDEO_NODES });
    actions.setFamily('image', { videoNodes: VIDEO_NODES });

    const d = store.get().draft;
    expect(d.family).toBe('image');
    expect(d.model_id).toBe(94); // first image node again
    expect(d.slots).toEqual({});
    expect(d.params).toEqual({});
    expect(d.enhanced_prompt).toBeNull(); // preview wiped
    // Note: enhance_prompt toggle survives across family swap (intentional).
    expect(d.enhance_prompt).toBe(true);
  });
});
