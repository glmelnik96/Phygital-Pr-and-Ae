// Tiny reactive store. Single exported `store`; createStore() for tests.

export function createStore(initial = {}) {
  let state = { ...initial };
  const listeners = new Set();
  function get() { return state; }
  function set(patch) {
    state = { ...state, ...(typeof patch === 'function' ? patch(state) : patch) };
    for (const l of listeners) l(state);
  }
  function subscribe(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  }
  return { get, set, subscribe };
}

export const DEFAULT_STATE = {
  health: { status: 'unknown', jwt_ttl_sec: null },
  videoNodes: null,
  draft: null,
  jobs: [],
  toasts: [],
  cost: { key: null, price: null, loading: false, error: null },
  // Balance в store (а не в локальном state Header'а) — нужно CostBar'у/
  // SubmitButton'у для сравнения price vs balance до Generate.
  balance: { value: null, infinity: false, error: null, loading: false },
};

// Cost cache: key = JSON.stringify({model_id, scenario, params, prompt})
// Invalidated on any draft change that affects price.
export function makeCostKey(draft) {
  if (!draft) return '';
  return JSON.stringify({
    m: draft.model_id,
    s: draft.scenario,
    p: draft.params || {},
    pr: draft.prompt || '',
  });
}

export const store = createStore(DEFAULT_STATE);

import { getNodeMeta, getSlotsForScenario, NANO_BANANA_META } from './slot_schema.js';

export function makeInitialDraft() {
  return {
    model_id: NANO_BANANA_META.node_id,
    scenario: NANO_BANANA_META.scenarios[0],
    prompt: '',
    slots: {},
    params: {},
  };
}

export const DRAFT_LS_KEY = 'phygital-studio.draft.v1';

export function loadDraftFromStorage() {
  try {
    const raw = localStorage.getItem(DRAFT_LS_KEY);
    if (!raw) return null;
    const obj = JSON.parse(raw);
    if (typeof obj !== 'object' || !obj.model_id) return null;
    return obj;
  } catch { return null; }
}

export function saveDraftToStorage(draft) {
  try { localStorage.setItem(DRAFT_LS_KEY, JSON.stringify(draft)); } catch {}
}

export function createDraftActions(store) {
  function setDraft(patch) {
    store.set(s => ({ draft: { ...s.draft, ...patch } }));
  }
  return {
    setModel(model_id, { videoNodes }) {
      const meta = getNodeMeta({ videoNodes, nodeId: model_id });
      const scenario = meta ? meta.scenarios[0] : null;
      setDraft({ model_id, scenario, slots: {} });
    },
    setScenario(scenario, { videoNodes }) {
      const draft = store.get().draft;
      const allowed = new Set(
        getSlotsForScenario({ videoNodes, nodeId: draft.model_id, scenario }).map(s => s.name)
      );
      const slots = {};
      for (const [k, v] of Object.entries(draft.slots)) {
        if (allowed.has(k)) slots[k] = v;
      }
      setDraft({ scenario, slots });
    },
    setPrompt(prompt) { setDraft({ prompt }); },
    setSlot(name, value) {
      const draft = store.get().draft;
      setDraft({ slots: { ...draft.slots, [name]: value } });
    },
    clearSlot(name) {
      const draft = store.get().draft;
      const slots = { ...draft.slots };
      delete slots[name];
      setDraft({ slots });
    },
    setParam(name, value) {
      const draft = store.get().draft;
      setDraft({ params: { ...draft.params, [name]: value } });
    },
  };
}

const ASSET_HISTORY_KEY = 'phygital-studio.assetHistory.v1';

export function loadAssetHistory() {
  try { return JSON.parse(localStorage.getItem(ASSET_HISTORY_KEY) || '{}') || {}; }
  catch { return {}; }
}
export function saveAssetHistory(history) {
  try { localStorage.setItem(ASSET_HISTORY_KEY, JSON.stringify(history)); } catch {}
}

export function isAssetCacheHit({ history, entry, now }) {
  // Hit if we've seen this sha256 before in this client (history[sha256] exists),
  // OR if the asset's uploaded_at is older than 5s (predates this upload attempt).
  if (history[entry.sha256]) return true;
  const ts = Date.parse(entry.uploaded_at);
  // uploaded_at >5s ago means the sidecar's AssetCache already had this file before our POST — it's a cross-session cache hit.
  if (!isNaN(ts) && (now - ts) > 5000) return true;
  return false;
}

export function createUploadActions(store) {
  let history = loadAssetHistory();
  return {
    async upload({ api, blob, filename }) {
      const entry = await api.uploadAsset({ blob, filename });
      const now = Date.now();
      const cached = isAssetCacheHit({ history, entry, now });
      if (!history[entry.sha256]) {
        history[entry.sha256] = { firstSeenAt: now, filename };
        saveAssetHistory(history);
      }
      return { entry, cached };
    },
  };
}

// Persistent cache of per-job artefacts (localPath, projectItemId). Sidecar
// /jobs API не знает про disk-path/Pr-binding — после перезагрузки панели
// миниатюра пропадала и "Show in bin" заново качал/импортировал.
// Храним только лёгкие метаданные, blob не дублируем (он уже на диске).
const JOB_META_KEY = 'phygital-studio.jobMeta.v1';

export function loadJobMetaCache() {
  try { return JSON.parse(localStorage.getItem(JOB_META_KEY) || '{}') || {}; }
  catch { return {}; }
}
export function saveJobMetaCache(cache) {
  try { localStorage.setItem(JOB_META_KEY, JSON.stringify(cache)); } catch {}
}
export function patchJobMetaCache(jobId, patch) {
  const c = loadJobMetaCache();
  c[jobId] = { ...(c[jobId] || {}), ...patch };
  saveJobMetaCache(c);
}
export function dropJobMetaCache(jobId) {
  const c = loadJobMetaCache();
  if (jobId in c) { delete c[jobId]; saveJobMetaCache(c); }
}
// Sweep entries for jobs no longer present in the live list — keeps localStorage bounded.
export function reconcileJobMetaCache(remoteJobIds) {
  const c = loadJobMetaCache();
  const keep = new Set(remoteJobIds);
  let dirty = false;
  for (const k of Object.keys(c)) if (!keep.has(k)) { delete c[k]; dirty = true; }
  if (dirty) saveJobMetaCache(c);
}

export function mergeJobs(prev, remote) {
  const prevById = new Map((prev || []).map(j => [j.job_id, j]));
  const meta = loadJobMetaCache();
  const out = remote.map(rj => {
    const local = prevById.get(rj.job_id);
    const persisted = meta[rj.job_id] || {};
    // priority: server fields > in-memory local enrichments > persisted cache.
    // persisted re-hydrates after panel reload (когда prevById пуст).
    return { ...persisted, ...(local || {}), ...rj };
  });
  return out;
}

export function diffJobs(prev, remote) {
  const prevById = new Map((prev || []).map(j => [j.job_id, j]));
  const completedNow = [];
  const newJobs = [];
  for (const rj of remote) {
    const local = prevById.get(rj.job_id);
    if (!local) {
      newJobs.push(rj);
      if (rj.status === 'completed') completedNow.push(rj);
      continue;
    }
    if (local.status !== 'completed' && rj.status === 'completed') {
      completedNow.push(rj);
    }
  }
  return { completedNow, newJobs };
}
