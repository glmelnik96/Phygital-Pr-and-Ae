# Premiere Pro Panel (sub-project B) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a Premiere Pro CEP panel (`cep-premiere/`) that lets a user pick a Phygital+ model+scenario, fill required slots from disk/bin/timeline/source-monitor, submit a job to the local FastAPI sidecar, watch progress, and auto-import the result into the active Pr project with one-click insert at playhead.

**Architecture:** Frontend = HTML+JS in Adobe CEF (CEP 11/12). UI built with Preact + htm (vendor copies, no bundler). Single state store (`lib/state.js`), single HTTP module (`lib/api.js`), single ExtendScript bridge (`lib/host.js` → `host/host.jsx`). Sidecar (`127.0.0.1:8765`) is the source of truth — UI is stateless across sessions except for a localStorage form draft.

**Tech Stack:** Preact 10.x, preact-hooks, htm 3.x, CSInterface (Adobe), ExtendScript ES3 for `host.jsx`, vitest + jsdom for unit tests, Pr 24+.

**Spec:** `docs/superpowers/specs/2026-05-21-pr-panel-design.md`. Read it first — this plan implements §3-§9 of that spec verbatim.

## Hard rules

1. **NO `git commit` без явной отмашки пользователя.** Steps that say "Commit" mean: `git add` the listed files, then **STOP and ask the user** before running `git commit`. Memory rule, project-wide.
2. **Existing scaffold files** (`cep-premiere/client/panel.js`, `cep-premiere/host/insert_media.jsx`, `cep-premiere/CSXS/manifest.xml`) get replaced/extended — read before overwriting.
3. **Sidecar must be running** for integration steps. User starts it (`python -m app.main` in their PowerShell — MSIX sandbox blocks Claude-spawned sidecars from seeing real AppData).
4. **No CDN.** All JS dependencies are vendor copies in `client/vendor/`.
5. **Cyrillic in tests/commits.** Project uses Russian comments in some places — match surrounding style; don't romanize existing files.

## File map

| Path | Created by task | Purpose |
|---|---|---|
| `cep-premiere/CSXS/manifest.xml` | T1 (edit existing) | CEP descriptor — points to `client/index.html` + `host/host.jsx` |
| `cep-premiere/.debug` | exists | CEF debug port — leave alone |
| `cep-premiere/package.json` | T1 | vitest + jsdom devDeps |
| `cep-premiere/vitest.config.js` | T1 | jsdom env + alias config |
| `cep-premiere/client/index.html` | T1 (rewrite) | Shell — loads `panel.js` as ES module |
| `cep-premiere/client/panel.css` | T1 | Styles |
| `cep-premiere/client/panel.js` | T1 (rewrite) | Entry: mounts `<App>`, init store + poller |
| `cep-premiere/client/vendor/preact.module.js` | T1 | Preact 10.x ESM bundle (offline copy) |
| `cep-premiere/client/vendor/preact-hooks.module.js` | T1 | Hooks ESM (offline copy) |
| `cep-premiere/client/vendor/htm.module.js` | T1 | htm 3.x ESM (offline copy) |
| `cep-premiere/client/vendor/CSInterface.js` | T1 | Adobe CEP bridge (from Adobe CEP-Resources) |
| `cep-premiere/client/lib/api.js` | T1, T3, T4, T5 | All `fetch` against sidecar |
| `cep-premiere/client/lib/host.js` | T6, T7 | All `CSInterface.evalScript` |
| `cep-premiere/client/lib/state.js` | T2, T3, T4 | Reactive store + actions + reducers |
| `cep-premiere/client/lib/validation.js` | T2 | Pure: slot completeness, scenario↔node compat |
| `cep-premiere/client/lib/slot_schema.js` | T2 | Static slots for node 94 + helper merge with `/nodes/video` |
| `cep-premiere/client/lib/toast.js` | T8 | Toast manager |
| `cep-premiere/client/lib/format.js` | T4 | Duration / size formatters |
| `cep-premiere/client/components/App.js` | T1, T2 | Root |
| `cep-premiere/client/components/Header.js` | T1, T8 | Status pill |
| `cep-premiere/client/components/Tabs.js` | T1 | 2-tab switcher |
| `cep-premiere/client/components/GenerateTab.js` | T2 | Form container |
| `cep-premiere/client/components/ModelPicker.js` | T2 | Dropdown 5 моделей |
| `cep-premiere/client/components/ScenarioPicker.js` | T2 | Dropdown сценариев для текущей модели |
| `cep-premiere/client/components/PromptInput.js` | T2 | textarea |
| `cep-premiere/client/components/SlotList.js` | T2 | Маппит slots → `<SlotPicker>` |
| `cep-premiere/client/components/SlotPicker.js` | T3, T6 | Source toggle + thumb + clear |
| `cep-premiere/client/components/ParamsAccordion.js` | T2 | optional params (collapsed) |
| `cep-premiere/client/components/CostBar.js` | T5 | Estimate button + result |
| `cep-premiere/client/components/SubmitButton.js` | T4 | Submit + disable rules |
| `cep-premiere/client/components/HistoryTab.js` | T4 | JobList container |
| `cep-premiere/client/components/JobFilter.js` | T4 | status filter |
| `cep-premiere/client/components/JobList.js` | T4 | render |
| `cep-premiere/client/components/JobCard.js` | T4, T7 | один job со всеми actions |
| `cep-premiere/client/components/Toast.js` | T8 | Stack renderer |
| `cep-premiere/host/host.jsx` | T6, T7 (rename from `insert_media.jsx`) | ExtendScript public API per spec §8 |
| `cep-premiere/tests/lib/api.test.js` | T1, T3, T4, T5 | unit |
| `cep-premiere/tests/lib/state.test.js` | T2, T3, T4 | unit |
| `cep-premiere/tests/lib/validation.test.js` | T2 | unit |
| `cep-premiere/tests/lib/slot_schema.test.js` | T2 | unit |
| `cep-premiere/tests/lib/toast.test.js` | T8 | unit |
| `cep-premiere/tests/integration/sidecar.test.js` | T9 | optional integration (требует поднятый sidecar) |
| `cep-premiere/README.md` | T9 | Install / manual E2E checklist |

---

The plan is split into 9 tasks (B.1 – B.9 from spec §9). Each task ships a self-contained, testable slice.


---

## Task 1 (B.1): Project shell + Header status pill

**Goal:** Panel loads in Pr, vendor modules import cleanly, Header polls `/health` and shows green/yellow/red pill. Tests for `api.getHealth` and basic state subscribe pass.

**Files:**
- Modify: `cep-premiere/CSXS/manifest.xml` (script path → `host.jsx`)
- Create: `cep-premiere/package.json`
- Create: `cep-premiere/vitest.config.js`
- Create: `cep-premiere/client/index.html` (rewrite scaffold)
- Create: `cep-premiere/client/panel.js` (rewrite scaffold)
- Create: `cep-premiere/client/panel.css`
- Create: `cep-premiere/client/vendor/preact.module.js` (download)
- Create: `cep-premiere/client/vendor/preact-hooks.module.js` (download)
- Create: `cep-premiere/client/vendor/htm.module.js` (download)
- Create: `cep-premiere/client/vendor/CSInterface.js` (download)
- Create: `cep-premiere/client/lib/html.js`
- Create: `cep-premiere/client/lib/api.js`
- Create: `cep-premiere/client/lib/state.js`
- Create: `cep-premiere/client/components/App.js`
- Create: `cep-premiere/client/components/Header.js`
- Create: `cep-premiere/client/components/Tabs.js`
- Create: `cep-premiere/tests/lib/api.test.js`
- Create: `cep-premiere/tests/setup.js`

- [ ] **Step 1.1: Add devDependencies via package.json**

Create `cep-premiere/package.json`:

```json
{
  "name": "phygital-studio-pr",
  "version": "0.0.1",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "devDependencies": {
    "vitest": "^1.6.0",
    "jsdom": "^24.0.0"
  }
}
```

Run: `cd cep-premiere && npm install`
Expected: node_modules created, no errors.

- [ ] **Step 1.2: Create vitest config + setup**

Create `cep-premiere/vitest.config.js`:

```js
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./tests/setup.js'],
    include: ['tests/**/*.test.js'],
  },
});
```

Create `cep-premiere/tests/setup.js`:

```js
// jsdom 24 provides fetch via undici. No setup needed beyond placeholder.
```

- [ ] **Step 1.3: Write failing test for `api.getHealth`**

Create `cep-premiere/tests/lib/api.test.js`:

```js
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
```

Run: `cd cep-premiere && npx vitest run tests/lib/api.test.js`
Expected: FAIL — `createApi` not defined.

- [ ] **Step 1.4: Implement `client/lib/api.js`**

Create `cep-premiere/client/lib/api.js`:

```js
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
    _request: request,
  };
}
```

Run: `cd cep-premiere && npx vitest run tests/lib/api.test.js`
Expected: 3/3 PASS.

- [ ] **Step 1.5: Download vendor modules**

```bash
cd cep-premiere/client/vendor
curl -L -o preact.module.js       https://unpkg.com/preact@10.22.0/dist/preact.module.js
curl -L -o preact-hooks.module.js https://unpkg.com/preact@10.22.0/hooks/dist/hooks.module.js
curl -L -o htm.module.js          https://unpkg.com/htm@3.1.1/dist/htm.module.js
curl -L -o CSInterface.js         https://raw.githubusercontent.com/Adobe-CEP/CEP-Resources/main/CEP_11.x/CSInterface.js
```

Fallback if unpkg blocked: replace `unpkg.com` with `cdn.jsdelivr.net/npm`.
Verify: `ls cep-premiere/client/vendor` shows 4 non-empty files.

- [ ] **Step 1.6: Patch hooks bare-import**

`hooks.module.js` contains `from"preact"`. CEF lacks bare-specifier resolution. Use Edit tool to replace `from"preact"` with `from"./preact.module.js"` (and `from "preact"` with `from "./preact.module.js"` if quoted with space) inside `cep-premiere/client/vendor/preact-hooks.module.js`.

Verify with Grep: pattern `preact.module.js` should match in that file.

- [ ] **Step 1.7: Create `client/lib/html.js`**

Create `cep-premiere/client/lib/html.js`:

```js
import htm from '../vendor/htm.module.js';
import { h } from '../vendor/preact.module.js';
export const html = htm.bind(h);
```

- [ ] **Step 1.8: Create `client/lib/state.js`**

Create `cep-premiere/client/lib/state.js`:

```js
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
};

export const store = createStore(DEFAULT_STATE);
```

- [ ] **Step 1.9: Create `client/index.html`**

Replace `cep-premiere/client/index.html`:

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="Content-Security-Policy"
        content="default-src 'self'; connect-src 'self' http://127.0.0.1:8765; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'">
  <title>Phygital Studio</title>
  <link rel="stylesheet" href="./panel.css">
</head>
<body>
  <div id="root"></div>
  <script src="./vendor/CSInterface.js"></script>
  <script type="module" src="./panel.js"></script>
</body>
</html>
```

- [ ] **Step 1.10: Create `client/panel.css`**

Create `cep-premiere/client/panel.css`:

```css
:root {
  --bg: #1e1e1e; --bg-2: #252525; --fg: #e0e0e0; --fg-dim: #999;
  --border: #3a3a3a; --accent: #4a9eff;
  --green: #5cbf6a; --yellow: #d9a23a; --red: #d05050;
  font-family: 'Segoe UI', Tahoma, sans-serif; font-size: 12px;
}
html, body { margin: 0; padding: 0; height: 100%; background: var(--bg); color: var(--fg); overflow: hidden; }
#root { height: 100%; display: flex; flex-direction: column; }
.header { display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; border-bottom: 1px solid var(--border); }
.header .title { font-weight: 600; }
.pill { display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border-radius: 10px; background: var(--bg-2); font-size: 11px; }
.pill .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--fg-dim); }
.pill.online .dot { background: var(--green); }
.pill.no_session .dot { background: var(--yellow); }
.pill.offline .dot { background: var(--red); }
.tabs { display: flex; border-bottom: 1px solid var(--border); }
.tab { flex: 1; padding: 8px; text-align: center; cursor: pointer; color: var(--fg-dim); }
.tab.active { color: var(--fg); border-bottom: 2px solid var(--accent); }
.tab-body { flex: 1; overflow-y: auto; padding: 10px; }
button { background: var(--bg-2); color: var(--fg); border: 1px solid var(--border); padding: 4px 10px; cursor: pointer; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
```

- [ ] **Step 1.11: Create `components/Header.js`**

Create `cep-premiere/client/components/Header.js`:

```js
import { html } from '../lib/html.js';

export function Header({ health }) {
  const cls = `pill ${health.status}`;
  const label =
    health.status === 'online' ? 'online' :
    health.status === 'no_session' ? 'no session' :
    health.status === 'offline' ? 'offline' :
    '...';
  return html`
    <div class="header">
      <div class="title">Phygital Studio</div>
      <div class=${cls}><span class="dot"></span>${label}</div>
    </div>
  `;
}
```

- [ ] **Step 1.12: Create `components/Tabs.js`**

Create `cep-premiere/client/components/Tabs.js`:

```js
import { html } from '../lib/html.js';

export function Tabs({ active, onChange, tabs }) {
  return html`
    <div class="tabs">
      ${tabs.map(t => html`
        <div class=${`tab ${active === t.id ? 'active' : ''}`}
             onClick=${() => onChange(t.id)}>${t.label}</div>
      `)}
    </div>
  `;
}
```

- [ ] **Step 1.13: Create `components/App.js`**

Create `cep-premiere/client/components/App.js`:

```js
import { html } from '../lib/html.js';
import { useState, useEffect } from '../vendor/preact-hooks.module.js';
import { Header } from './Header.js';
import { Tabs } from './Tabs.js';

export function App({ store, api }) {
  const [snap, setSnap] = useState(store.get());
  const [tab, setTab] = useState('generate');

  useEffect(() => store.subscribe(setSnap), []);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const h = await api.getHealth();
        if (cancelled) return;
        const status =
          h && h.jwt_ttl_sec && h.jwt_ttl_sec > 0 ? 'online' :
          h ? 'no_session' : 'offline';
        store.set({ health: { status, jwt_ttl_sec: h && h.jwt_ttl_sec } });
      } catch (e) {
        if (cancelled) return;
        store.set({ health: { status: 'offline', jwt_ttl_sec: null } });
      }
    }
    tick();
    const id = setInterval(tick, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return html`
    <${Header} health=${snap.health} />
    <${Tabs} active=${tab} onChange=${setTab} tabs=${[
      { id: 'generate', label: 'Generate' },
      { id: 'history', label: 'History' },
    ]} />
    <div class="tab-body">
      ${tab === 'generate'
        ? html`<div class="placeholder">Generate (T2)</div>`
        : html`<div class="placeholder">History (T4)</div>`}
    </div>
  `;
}
```

- [ ] **Step 1.14: Rewrite `client/panel.js`**

Replace `cep-premiere/client/panel.js`:

```js
import { render } from './vendor/preact.module.js';
import { html } from './lib/html.js';
import { createApi } from './lib/api.js';
import { store } from './lib/state.js';
import { App } from './components/App.js';

const api = createApi({ fetch: window.fetch.bind(window), baseUrl: 'http://127.0.0.1:8765' });
render(html`<${App} store=${store} api=${api} />`, document.getElementById('root'));
```

- [ ] **Step 1.15: Update manifest + rename host scaffold**

Edit `cep-premiere/CSXS/manifest.xml`: replace `<ScriptPath>./host/insert_media.jsx</ScriptPath>` with `<ScriptPath>./host/host.jsx</ScriptPath>`.

Rename: `mv cep-premiere/host/insert_media.jsx cep-premiere/host/host.jsx`. T6 rewrites the file contents.

- [ ] **Step 1.16: Run tests, stage, ask user before commit**

Run: `cd cep-premiere && npm test`
Expected: 3/3 PASS.

Stage:
```bash
git add cep-premiere/package.json cep-premiere/vitest.config.js \
        cep-premiere/CSXS/manifest.xml \
        cep-premiere/client/index.html cep-premiere/client/panel.js \
        cep-premiere/client/panel.css \
        cep-premiere/client/vendor/ \
        cep-premiere/client/lib/ cep-premiere/client/components/ \
        cep-premiere/tests/ \
        cep-premiere/host/host.jsx
```

**STOP — do NOT run `git commit`.** Ask user: "T1 staged. Proposed message: `feat(cep-premiere): panel shell + Header status pill + api.getHealth`. Commit?"

---

## Task 2 (B.2): Read-only Generate form + state + validation + slot schema

**Goal:** User can choose model + scenario, slot list renders correctly per scenario, prompt textarea works, draft autosaves to localStorage. NO upload, NO submit yet. Form is fully reactive.

**Files:**
- Create: `cep-premiere/client/lib/slot_schema.js`
- Create: `cep-premiere/client/lib/validation.js`
- Modify: `cep-premiere/client/lib/state.js` (actions for draft)
- Modify: `cep-premiere/client/lib/api.js` (add listVideoNodes)
- Create: `cep-premiere/client/components/GenerateTab.js`
- Create: `cep-premiere/client/components/ModelPicker.js`
- Create: `cep-premiere/client/components/ScenarioPicker.js`
- Create: `cep-premiere/client/components/PromptInput.js`
- Create: `cep-premiere/client/components/SlotList.js`
- Create: `cep-premiere/client/components/SlotPicker.js` (read-only placeholder)
- Create: `cep-premiere/client/components/ParamsAccordion.js`
- Modify: `cep-premiere/client/components/App.js` (mount `<GenerateTab>`)
- Create: `cep-premiere/tests/lib/slot_schema.test.js`
- Create: `cep-premiere/tests/lib/validation.test.js`
- Create: `cep-premiere/tests/lib/state.test.js`
- Modify: `cep-premiere/tests/lib/api.test.js` (add listVideoNodes coverage)

- [ ] **Step 2.1: Write failing tests for `slot_schema.js`**

Create `cep-premiere/tests/lib/slot_schema.test.js`:

```js
import { describe, it, expect } from 'vitest';
import { getNodeMeta, getSlotsForScenario, NANO_BANANA_META } from '../../client/lib/slot_schema.js';

const VIDEO_NODES_FIXTURE = [
  {
    node_id: 74, model: 'Kling v3 pro',
    slots: { init_img: 'array', image_tail: 'scalar', element_1: 'array', element_2: 'array', element_3: 'array' },
    scenarios: ['start_prompt', 'start_end_prompt', 'elements_prompt', 'elements_prompt_video'],
    scenario_slots: {
      start_prompt: ['init_img'],
      start_end_prompt: ['init_img', 'image_tail'],
      elements_prompt: ['element_1'],
      elements_prompt_video: ['element_1', 'image_tail'],
    },
    default_params: {},
  },
];

describe('slot_schema', () => {
  it('NANO_BANANA_META has node 94 + init_img array slot', () => {
    expect(NANO_BANANA_META.node_id).toBe(94);
    expect(NANO_BANANA_META.slots.init_img).toBe('array');
    expect(NANO_BANANA_META.scenario_slots.edit).toEqual(['init_img']);
  });

  it('getNodeMeta(94) returns Nano Banana even without /nodes/video', () => {
    const m = getNodeMeta({ videoNodes: [], nodeId: 94 });
    expect(m.node_id).toBe(94);
  });

  it('getNodeMeta(74) reads from videoNodes payload', () => {
    const m = getNodeMeta({ videoNodes: VIDEO_NODES_FIXTURE, nodeId: 74 });
    expect(m.model).toBe('Kling v3 pro');
  });

  it('getSlotsForScenario returns names with kind annotation', () => {
    const slots = getSlotsForScenario({ videoNodes: VIDEO_NODES_FIXTURE, nodeId: 74, scenario: 'start_end_prompt' });
    expect(slots).toEqual([
      { name: 'init_img', kind: 'array' },
      { name: 'image_tail', kind: 'scalar' },
    ]);
  });

  it('getSlotsForScenario for Nano Banana edit returns init_img array', () => {
    const slots = getSlotsForScenario({ videoNodes: [], nodeId: 94, scenario: 'edit' });
    expect(slots).toEqual([{ name: 'init_img', kind: 'array' }]);
  });

  it('getSlotsForScenario returns [] for unknown scenario', () => {
    const slots = getSlotsForScenario({ videoNodes: VIDEO_NODES_FIXTURE, nodeId: 74, scenario: 'nonsense' });
    expect(slots).toEqual([]);
  });
});
```

Run: `cd cep-premiere && npx vitest run tests/lib/slot_schema.test.js`
Expected: FAIL — module not defined.

- [ ] **Step 2.2: Implement `lib/slot_schema.js`**

Create `cep-premiere/client/lib/slot_schema.js`:

```js
// Node 94 (Nano Banana) is not in /nodes/video. Hard-code its slot map here.
// Video nodes (74/100/121/124) come from GET /nodes/video.

export const NANO_BANANA_META = {
  node_id: 94,
  model: 'Nano Banana',
  slots: { init_img: 'array' },
  scenarios: ['edit'],
  scenario_slots: { edit: ['init_img'] },
  default_params: {},
};

export function getNodeMeta({ videoNodes, nodeId }) {
  if (nodeId === 94) return NANO_BANANA_META;
  if (!videoNodes) return null;
  return videoNodes.find(n => n.node_id === nodeId) || null;
}

export function listAllNodes({ videoNodes }) {
  const out = [NANO_BANANA_META];
  if (videoNodes) out.push(...videoNodes);
  return out;
}

export function getSlotsForScenario({ videoNodes, nodeId, scenario }) {
  const meta = getNodeMeta({ videoNodes, nodeId });
  if (!meta) return [];
  const names = meta.scenario_slots[scenario];
  if (!names) return [];
  return names.map(name => ({ name, kind: meta.slots[name] || 'scalar' }));
}
```

Run: `cd cep-premiere && npx vitest run tests/lib/slot_schema.test.js`
Expected: 6/6 PASS.

- [ ] **Step 2.3: Write failing tests for `validation.js`**

Create `cep-premiere/tests/lib/validation.test.js`:

```js
import { describe, it, expect } from 'vitest';
import { validateDraft } from '../../client/lib/validation.js';

const VIDEO_FIXTURE = [{
  node_id: 74, model: 'Kling',
  slots: { init_img: 'array', image_tail: 'scalar' },
  scenarios: ['start_prompt', 'start_end_prompt'],
  scenario_slots: { start_prompt: ['init_img'], start_end_prompt: ['init_img', 'image_tail'] },
  default_params: {},
}];

function draft(overrides = {}) {
  return {
    model_id: 74,
    scenario: 'start_prompt',
    prompt: 'a beautiful scene',
    slots: { init_img: [{ path: '/x.jpg', name: 'x.jpg', source: 'disk' }] },
    params: {},
    ...overrides,
  };
}

describe('validateDraft', () => {
  it('passes a fully-formed draft', () => {
    const r = validateDraft({ videoNodes: VIDEO_FIXTURE, draft: draft() });
    expect(r.ok).toBe(true);
    expect(r.errors).toEqual([]);
  });

  it('fails when prompt is empty', () => {
    const r = validateDraft({ videoNodes: VIDEO_FIXTURE, draft: draft({ prompt: '   ' }) });
    expect(r.ok).toBe(false);
    expect(r.errors).toContainEqual({ field: 'prompt', message: 'Prompt required' });
  });

  it('fails when required slot empty', () => {
    const r = validateDraft({ videoNodes: VIDEO_FIXTURE, draft: draft({ slots: {} }) });
    expect(r.ok).toBe(false);
    expect(r.errors).toContainEqual({ field: 'slot:init_img', message: 'Slot init_img required' });
  });

  it('fails when scenario incompatible with model', () => {
    const r = validateDraft({ videoNodes: VIDEO_FIXTURE, draft: draft({ scenario: 'char_video_prompt' }) });
    expect(r.ok).toBe(false);
    expect(r.errors[0].field).toBe('scenario');
  });

  it('handles Nano Banana without videoNodes loaded', () => {
    const d = { model_id: 94, scenario: 'edit', prompt: 'p', slots: { init_img: [{ path: '/x.jpg', name: 'x', source: 'disk' }] }, params: {} };
    const r = validateDraft({ videoNodes: null, draft: d });
    expect(r.ok).toBe(true);
  });
});
```

Run: `cd cep-premiere && npx vitest run tests/lib/validation.test.js`
Expected: FAIL — not defined.

- [ ] **Step 2.4: Implement `lib/validation.js`**

Create `cep-premiere/client/lib/validation.js`:

```js
import { getNodeMeta, getSlotsForScenario } from './slot_schema.js';

export function validateDraft({ videoNodes, draft }) {
  const errors = [];
  if (!draft) return { ok: false, errors: [{ field: 'draft', message: 'No draft' }] };

  const meta = getNodeMeta({ videoNodes, nodeId: draft.model_id });
  if (!meta) return { ok: false, errors: [{ field: 'model_id', message: 'Unknown model' }] };

  if (!meta.scenarios.includes(draft.scenario)) {
    errors.push({ field: 'scenario', message: `Scenario ${draft.scenario} not valid for ${meta.model}` });
  }

  if (!draft.prompt || !draft.prompt.trim()) {
    errors.push({ field: 'prompt', message: 'Prompt required' });
  }

  const required = getSlotsForScenario({ videoNodes, nodeId: draft.model_id, scenario: draft.scenario });
  for (const { name, kind } of required) {
    const val = draft.slots && draft.slots[name];
    const empty =
      val == null ||
      (Array.isArray(val) && val.length === 0) ||
      (kind === 'scalar' && !val);
    if (empty) errors.push({ field: `slot:${name}`, message: `Slot ${name} required` });
  }

  return { ok: errors.length === 0, errors };
}
```

Run: `cd cep-premiere && npx vitest run tests/lib/validation.test.js`
Expected: 5/5 PASS.

- [ ] **Step 2.5: Write failing tests for state draft actions**

Create `cep-premiere/tests/lib/state.test.js`:

```js
import { describe, it, expect, beforeEach } from 'vitest';
import { createStore, DEFAULT_STATE, createDraftActions, makeInitialDraft } from '../../client/lib/state.js';

describe('state draft actions', () => {
  let store, actions;
  beforeEach(() => {
    store = createStore({ ...DEFAULT_STATE, draft: makeInitialDraft() });
    actions = createDraftActions(store);
  });

  it('makeInitialDraft picks Nano Banana edit by default', () => {
    const d = makeInitialDraft();
    expect(d.model_id).toBe(94);
    expect(d.scenario).toBe('edit');
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
```

Run: `cd cep-premiere && npx vitest run tests/lib/state.test.js`
Expected: FAIL.

- [ ] **Step 2.6: Extend `lib/state.js` with draft actions**

Edit `cep-premiere/client/lib/state.js` — append after existing exports:

```js
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

const DRAFT_LS_KEY = 'phygital-studio.draft.v1';

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
```

Run: `cd cep-premiere && npx vitest run tests/lib/state.test.js`
Expected: 4/4 PASS.

- [ ] **Step 2.7: Add `listVideoNodes` to api.js + test**

In `cep-premiere/tests/lib/api.test.js`, append:

```js
import { createApi as _createApiAgain } from '../../client/lib/api.js';

describe('api.listVideoNodes', () => {
  it('GETs /nodes/video and returns body', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(
      JSON.stringify({ nodes: [{ node_id: 74 }] }),
      { status: 200, headers: { 'content-type': 'application/json' } }
    ));
    const api = _createApiAgain({ fetch: fetchMock, baseUrl: 'http://h' });
    const out = await api.listVideoNodes();
    expect(out.nodes[0].node_id).toBe(74);
    expect(fetchMock).toHaveBeenCalledWith('http://h/nodes/video', expect.objectContaining({ method: 'GET' }));
  });
});
```

In `cep-premiere/client/lib/api.js`, inside the returned object, add:

```js
    listVideoNodes: () => request('/nodes/video'),
    listNodes: () => request('/nodes'),
```

Run: `cd cep-premiere && npx vitest run tests/lib/api.test.js`
Expected: 4/4 PASS.

- [ ] **Step 2.8: Create form components**

Create `cep-premiere/client/components/PromptInput.js`:

```js
import { html } from '../lib/html.js';

export function PromptInput({ value, onChange }) {
  return html`
    <div class="field">
      <label>Prompt</label>
      <textarea rows="3" value=${value} onInput=${e => onChange(e.target.value)}></textarea>
    </div>
  `;
}
```

Create `cep-premiere/client/components/ModelPicker.js`:

```js
import { html } from '../lib/html.js';

export function ModelPicker({ nodes, value, onChange }) {
  return html`
    <div class="field">
      <label>Model</label>
      <select value=${value} onChange=${e => onChange(parseInt(e.target.value, 10))}>
        ${nodes.map(n => html`<option value=${n.node_id}>${n.model}</option>`)}
      </select>
    </div>
  `;
}
```

Create `cep-premiere/client/components/ScenarioPicker.js`:

```js
import { html } from '../lib/html.js';

export function ScenarioPicker({ scenarios, value, onChange }) {
  return html`
    <div class="field">
      <label>Scenario</label>
      <select value=${value} onChange=${e => onChange(e.target.value)}>
        ${scenarios.map(s => html`<option value=${s}>${s}</option>`)}
      </select>
    </div>
  `;
}
```

Create `cep-premiere/client/components/SlotPicker.js` (read-only placeholder; T3 fills upload):

```js
import { html } from '../lib/html.js';

export function SlotPicker({ name, kind, value, onPick, onClear }) {
  const items = kind === 'array' ? (value || []) : (value ? [value] : []);
  return html`
    <div class="slot">
      <div class="slot-head">
        <span class="slot-name">${name}</span>
        <span class="slot-kind">(${kind}${kind === 'array' ? ', required' : ', required'})</span>
      </div>
      <div class="slot-sources">
        <button onClick=${() => onPick && onPick('bin')} disabled>Bin</button>
        <button onClick=${() => onPick && onPick('timeline')} disabled>Timeline</button>
        <button onClick=${() => onPick && onPick('source_monitor')} disabled>Src mon</button>
        <button onClick=${() => onPick && onPick('disk')} disabled>Browse...</button>
      </div>
      ${items.length === 0
        ? html`<div class="slot-empty">No file</div>`
        : items.map(it => html`
          <div class="slot-item">
            <span>${it.name}</span>
            <button onClick=${() => onClear && onClear(it)}>×</button>
          </div>
        `)}
    </div>
  `;
}
```

Create `cep-premiere/client/components/SlotList.js`:

```js
import { html } from '../lib/html.js';
import { SlotPicker } from './SlotPicker.js';

export function SlotList({ slots, values, onPick, onClear }) {
  if (!slots.length) return html`<div class="slot-list-empty">No slots required for this scenario</div>`;
  return html`
    <div class="slot-list">
      ${slots.map(s => html`
        <${SlotPicker}
          name=${s.name} kind=${s.kind}
          value=${values[s.name]}
          onPick=${src => onPick(s, src)}
          onClear=${item => onClear(s, item)}
        />
      `)}
    </div>
  `;
}
```

Create `cep-premiere/client/components/ParamsAccordion.js` (collapsed by default; render nothing if no params):

```js
import { html } from '../lib/html.js';
import { useState } from '../vendor/preact-hooks.module.js';

export function ParamsAccordion({ defaults, values, onChange }) {
  const [open, setOpen] = useState(false);
  const keys = Object.keys(defaults || {});
  if (keys.length === 0) return null;
  return html`
    <div class="params">
      <div class="params-head" onClick=${() => setOpen(o => !o)}>
        ${open ? '▼' : '▶'} Advanced params (${keys.length})
      </div>
      ${open && html`
        <div class="params-body">
          ${keys.map(k => html`
            <div class="field">
              <label>${k}</label>
              <input value=${values[k] ?? defaults[k]}
                     onInput=${e => onChange(k, e.target.value)} />
            </div>
          `)}
        </div>
      `}
    </div>
  `;
}
```

Create `cep-premiere/client/components/GenerateTab.js`:

```js
import { html } from '../lib/html.js';
import { useEffect } from '../vendor/preact-hooks.module.js';
import { ModelPicker } from './ModelPicker.js';
import { ScenarioPicker } from './ScenarioPicker.js';
import { PromptInput } from './PromptInput.js';
import { SlotList } from './SlotList.js';
import { ParamsAccordion } from './ParamsAccordion.js';
import { listAllNodes, getNodeMeta, getSlotsForScenario } from '../lib/slot_schema.js';
import { saveDraftToStorage } from '../lib/state.js';

export function GenerateTab({ snap, actions }) {
  const { draft, videoNodes, health } = snap;
  const allNodes = listAllNodes({ videoNodes });
  const meta = getNodeMeta({ videoNodes, nodeId: draft.model_id });
  const scenarios = meta ? meta.scenarios : [];
  const slots = getSlotsForScenario({ videoNodes, nodeId: draft.model_id, scenario: draft.scenario });

  useEffect(() => { saveDraftToStorage(draft); }, [JSON.stringify(draft)]);

  const disabled = health.status !== 'online';

  return html`
    <div class=${`generate ${disabled ? 'disabled' : ''}`}>
      <${ModelPicker} nodes=${allNodes} value=${draft.model_id}
        onChange=${id => actions.setModel(id, { videoNodes })} />
      <${ScenarioPicker} scenarios=${scenarios} value=${draft.scenario}
        onChange=${s => actions.setScenario(s, { videoNodes })} />
      <${PromptInput} value=${draft.prompt} onChange=${actions.setPrompt} />
      <${SlotList} slots=${slots} values=${draft.slots}
        onPick=${(slot, src) => console.log('pick', slot, src)}
        onClear=${(slot) => actions.clearSlot(slot.name)} />
      <${ParamsAccordion} defaults=${meta ? meta.default_params : {}}
        values=${draft.params} onChange=${actions.setParam} />
    </div>
  `;
}
```

- [ ] **Step 2.9: Wire `<GenerateTab>` into `App.js` + load videoNodes**

Edit `cep-premiere/client/components/App.js` — add at top:

```js
import { GenerateTab } from './GenerateTab.js';
import { createDraftActions, makeInitialDraft, loadDraftFromStorage } from '../lib/state.js';
```

Inside `App({ store, api })`, after the existing `useEffect`s, add:

```js
  // Bootstrap draft + videoNodes
  useEffect(() => {
    const cur = store.get();
    if (!cur.draft) {
      const restored = loadDraftFromStorage() || makeInitialDraft();
      store.set({ draft: restored });
    }
    if (!cur.videoNodes) {
      api.listVideoNodes()
        .then(r => store.set({ videoNodes: r.nodes }))
        .catch(() => {});
    }
  }, []);

  const actions = createDraftActions(store);
```

Replace the placeholder `tab === 'generate' ? ... : ...` with:

```js
  ${tab === 'generate'
    ? (snap.draft
        ? html`<${GenerateTab} snap=${snap} actions=${actions} />`
        : html`<div class="placeholder">Loading...</div>`)
    : html`<div class="placeholder">History (T4)</div>`}
```

- [ ] **Step 2.10: Append form CSS**

Append to `cep-premiere/client/panel.css`:

```css
.field { margin-bottom: 8px; }
.field label { display: block; font-size: 11px; color: var(--fg-dim); margin-bottom: 2px; }
.field input, .field textarea, .field select {
  width: 100%; box-sizing: border-box; background: var(--bg-2); color: var(--fg);
  border: 1px solid var(--border); padding: 4px 6px; font: inherit;
}
.field textarea { resize: vertical; }
.slot { border: 1px solid var(--border); padding: 6px; margin-bottom: 6px; background: var(--bg-2); }
.slot-head { display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 4px; }
.slot-kind { color: var(--fg-dim); }
.slot-sources { display: flex; gap: 4px; margin-bottom: 4px; }
.slot-sources button { font-size: 11px; padding: 2px 6px; }
.slot-empty { font-size: 11px; color: var(--fg-dim); padding: 4px; }
.slot-item { display: flex; justify-content: space-between; align-items: center; padding: 2px 4px; }
.params-head { padding: 4px 0; cursor: pointer; color: var(--fg-dim); }
.params-body { padding-left: 10px; }
.generate.disabled { opacity: 0.5; pointer-events: none; }
```

- [ ] **Step 2.11: Run all tests, stage, ask before commit**

Run: `cd cep-premiere && npm test`
Expected: all suites green (api 4, slot_schema 6, validation 5, state 4 = 19/19).

Stage `cep-premiere/client/lib/`, `cep-premiere/client/components/`, `cep-premiere/tests/lib/`, `cep-premiere/client/panel.css`.

**STOP — ask user before `git commit`.** Proposed message: `feat(cep-premiere): read-only Generate form + state + validation`.

---

## Task 3 (B.3): Disk source + uploadAsset + thumbnails + dedup indicator

**Goal:** User clicks Browse, picks a file from disk, panel uploads via `POST /assets`, sees thumbnail + filename + `cached` indicator on repeat upload. No Pr integration yet.

**Files:**
- Modify: `cep-premiere/client/lib/api.js` (uploadAsset)
- Modify: `cep-premiere/client/lib/state.js` (uploadHistory tracking)
- Modify: `cep-premiere/client/components/SlotPicker.js` (enable disk Browse + thumb)
- Modify: `cep-premiere/client/components/GenerateTab.js` (wire onPick)
- Modify: `cep-premiere/tests/lib/api.test.js` (uploadAsset coverage)
- Modify: `cep-premiere/tests/lib/state.test.js` (slot+asset actions)

CEP runs in Node-enabled CEF (`--enable-nodejs` in manifest). Disk file pick: use Node's `require('original-fs')` + a hidden `<input type="file">` element. Disk dialog: use `cep.fs.showOpenDialogEx`. Both available via CSInterface.

- [ ] **Step 3.1: Write failing test for `api.uploadAsset`**

Append to `cep-premiere/tests/lib/api.test.js`:

```js
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
```

Run: vitest — expect FAIL.

- [ ] **Step 3.2: Implement `api.uploadAsset`**

Inside `createApi(...)` return object in `client/lib/api.js`:

```js
    uploadAsset: async ({ blob, filename }) => {
      const fd = new FormData();
      fd.append('file', blob, filename);
      return request('/assets', { method: 'POST', body: fd });
    },
```

Note: don't set `content-type` header — browser sets it with boundary.

Run vitest — expect 5/5 PASS in api.test.js.

- [ ] **Step 3.3: Write failing test for upload history dedup detection**

Append to `cep-premiere/tests/lib/state.test.js`:

```js
import { createUploadActions, isAssetCacheHit } from '../../client/lib/state.js';

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
```

Run — expect FAIL.

- [ ] **Step 3.4: Implement upload history + dedup heuristic in state.js**

Append to `cep-premiere/client/lib/state.js`:

```js
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
  if (!isNaN(ts) && (now - ts) > 5000) return true;
  return false;
}

export function createUploadActions(store) {
  let history = loadAssetHistory();
  return {
    async upload({ api, blob, filename, slotName, kind }) {
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
```

Run state.test.js — expect 7/7 PASS.

- [ ] **Step 3.5: Add disk picker + thumbnail to `SlotPicker.js`**

Replace `cep-premiere/client/components/SlotPicker.js`:

```js
import { html } from '../lib/html.js';

function thumbFor(item) {
  if (item.thumb) return html`<img class="slot-thumb" src=${item.thumb} alt="" />`;
  return html`<div class="slot-thumb placeholder"></div>`;
}

export function SlotPicker({ name, kind, value, onPick, onClear }) {
  const items = kind === 'array' ? (value || []) : (value ? [value] : []);
  const canAddMore = kind === 'array' || items.length === 0;
  return html`
    <div class="slot">
      <div class="slot-head">
        <span class="slot-name">${name}</span>
        <span class="slot-kind">(${kind}, required)</span>
      </div>
      <div class="slot-sources">
        <button onClick=${() => onPick && onPick('bin')} disabled title="T6">Bin</button>
        <button onClick=${() => onPick && onPick('timeline')} disabled title="T6">Timeline</button>
        <button onClick=${() => onPick && onPick('source_monitor')} disabled title="T6">Src mon</button>
        <button onClick=${() => onPick && onPick('disk')} disabled=${!canAddMore}>Browse...</button>
      </div>
      ${items.length === 0
        ? html`<div class="slot-empty">No file</div>`
        : items.map(it => html`
          <div class="slot-item">
            ${thumbFor(it)}
            <div class="slot-item-meta">
              <div class="slot-item-name">${it.name}</div>
              <div class="slot-item-sub">
                ${it.asset && it.asset.width ? `${it.asset.width}×${it.asset.height}` : ''}
                ${it.cached ? html`<span class="slot-cached">cached</span>` : ''}
              </div>
            </div>
            <button onClick=${() => onClear && onClear(it)}>×</button>
          </div>
        `)}
    </div>
  `;
}
```

Append CSS to `panel.css`:

```css
.slot-thumb { width: 40px; height: 40px; object-fit: cover; background: #444; border-radius: 2px; }
.slot-thumb.placeholder { display: inline-block; }
.slot-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.slot-item-meta { flex: 1; min-width: 0; }
.slot-item-name { font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.slot-item-sub { font-size: 10px; color: var(--fg-dim); }
.slot-cached { display: inline-block; padding: 1px 4px; border-radius: 2px; background: var(--green); color: #000; margin-left: 6px; }
```

- [ ] **Step 3.6: Implement disk pick + upload flow in GenerateTab**

Add helper `client/lib/disk.js`:

Create `cep-premiere/client/lib/disk.js`:

```js
// CEP exposes window.cep.fs.showOpenDialogEx. In jsdom tests this won't exist;
// callers should feature-detect.

export function pickFilesFromDisk({ multi, accept }) {
  const cep = window.cep;
  if (!cep || !cep.fs || !cep.fs.showOpenDialogEx) {
    return Promise.reject(new Error('cep.fs.showOpenDialogEx unavailable'));
  }
  // Per Adobe CEP docs: showOpenDialogEx(allowMultipleSelection, chooseDirectory, title, initialPath, fileTypes)
  const res = cep.fs.showOpenDialogEx(!!multi, false, 'Pick file', '', accept || []);
  if (res.err !== 0) return Promise.reject(new Error(`dialog err ${res.err}`));
  return Promise.resolve(res.data || []);
}

export async function readFileAsBlob(path) {
  // Use Node fs via the CEP node-enabled context.
  const fs = require('fs');
  const buf = fs.readFileSync(path);
  const ext = path.split('.').pop().toLowerCase();
  const mime =
    ext === 'jpg' || ext === 'jpeg' ? 'image/jpeg' :
    ext === 'png' ? 'image/png' :
    ext === 'mp4' ? 'video/mp4' :
    ext === 'mov' ? 'video/quicktime' :
    ext === 'wav' || ext === 'mp3' ? `audio/${ext === 'mp3' ? 'mpeg' : 'wav'}` :
    'application/octet-stream';
  return new Blob([buf], { type: mime });
}

export async function makeThumbDataURL(blob, max = 64) {
  if (!blob.type.startsWith('image/')) return null;
  const url = URL.createObjectURL(blob);
  try {
    const img = await new Promise((res, rej) => {
      const i = new Image();
      i.onload = () => res(i);
      i.onerror = rej;
      i.src = url;
    });
    const ratio = Math.min(max / img.width, max / img.height, 1);
    const w = Math.max(1, Math.round(img.width * ratio));
    const h = Math.max(1, Math.round(img.height * ratio));
    const c = document.createElement('canvas');
    c.width = w; c.height = h;
    c.getContext('2d').drawImage(img, 0, 0, w, h);
    return c.toDataURL('image/jpeg', 0.6);
  } finally { URL.revokeObjectURL(url); }
}
```

- [ ] **Step 3.7: Wire `onPick='disk'` in GenerateTab**

Edit `cep-premiere/client/components/GenerateTab.js` — replace `onPick=${(slot, src) => console.log('pick', slot, src)}` with `onPick=${onPick}` and add helper:

```js
import { pickFilesFromDisk, readFileAsBlob, makeThumbDataURL } from '../lib/disk.js';
import { createUploadActions } from '../lib/state.js';

// inside GenerateTab(...)
const uploadActions = createUploadActions(snap.store /* note: pass store via props */);
```

Actually `createUploadActions` doesn't need store here — it returns a closure over `history`. Simpler: keep the upload module-level. Adjust:

Change `GenerateTab` signature to take `api` prop. In `App.js`, pass `api` down.

Revised `GenerateTab.js`:

```js
import { html } from '../lib/html.js';
import { useEffect, useState } from '../vendor/preact-hooks.module.js';
import { ModelPicker } from './ModelPicker.js';
import { ScenarioPicker } from './ScenarioPicker.js';
import { PromptInput } from './PromptInput.js';
import { SlotList } from './SlotList.js';
import { ParamsAccordion } from './ParamsAccordion.js';
import { listAllNodes, getNodeMeta, getSlotsForScenario } from '../lib/slot_schema.js';
import { saveDraftToStorage, createUploadActions } from '../lib/state.js';
import { pickFilesFromDisk, readFileAsBlob, makeThumbDataURL } from '../lib/disk.js';

const uploadActions = createUploadActions(null);

export function GenerateTab({ snap, actions, api }) {
  const { draft, videoNodes, health } = snap;
  const allNodes = listAllNodes({ videoNodes });
  const meta = getNodeMeta({ videoNodes, nodeId: draft.model_id });
  const scenarios = meta ? meta.scenarios : [];
  const slots = getSlotsForScenario({ videoNodes, nodeId: draft.model_id, scenario: draft.scenario });

  useEffect(() => { saveDraftToStorage(draft); }, [JSON.stringify(draft)]);

  async function onPick(slot, source) {
    if (source !== 'disk') return; // T6 wires bin/timeline/source_monitor
    let paths;
    try {
      paths = await pickFilesFromDisk({ multi: slot.kind === 'array' });
    } catch (e) { return; }
    if (!paths || paths.length === 0) return;
    for (const p of paths) {
      const name = p.split(/[\\/]/).pop();
      const blob = await readFileAsBlob(p);
      const thumb = await makeThumbDataURL(blob).catch(() => null);
      // optimistic insert
      const item = { source: 'disk', path: p, name, thumb };
      if (slot.kind === 'array') {
        const cur = draft.slots[slot.name] || [];
        actions.setSlot(slot.name, [...cur, item]);
      } else {
        actions.setSlot(slot.name, item);
      }
      try {
        const { entry, cached } = await uploadActions.upload({ api, blob, filename: name });
        const enriched = { ...item, asset: entry, cached };
        if (slot.kind === 'array') {
          const cur = draft.slots[slot.name] || [];
          const arr = cur.map(x => x.path === p ? enriched : x);
          actions.setSlot(slot.name, arr);
        } else {
          actions.setSlot(slot.name, enriched);
        }
      } catch (e) {
        // T8 will toast; for now mark item.error
        const err = { ...item, error: e.message || 'upload failed' };
        if (slot.kind === 'array') {
          const cur = draft.slots[slot.name] || [];
          const arr = cur.map(x => x.path === p ? err : x);
          actions.setSlot(slot.name, arr);
        } else actions.setSlot(slot.name, err);
      }
    }
  }

  function onClear(slot, item) {
    if (slot.kind === 'array') {
      const cur = draft.slots[slot.name] || [];
      const next = cur.filter(x => x !== item);
      if (next.length === 0) actions.clearSlot(slot.name);
      else actions.setSlot(slot.name, next);
    } else {
      actions.clearSlot(slot.name);
    }
  }

  const disabled = health.status !== 'online';

  return html`
    <div class=${`generate ${disabled ? 'disabled' : ''}`}>
      <${ModelPicker} nodes=${allNodes} value=${draft.model_id}
        onChange=${id => actions.setModel(id, { videoNodes })} />
      <${ScenarioPicker} scenarios=${scenarios} value=${draft.scenario}
        onChange=${s => actions.setScenario(s, { videoNodes })} />
      <${PromptInput} value=${draft.prompt} onChange=${actions.setPrompt} />
      <${SlotList} slots=${slots} values=${draft.slots}
        onPick=${onPick} onClear=${onClear} />
      <${ParamsAccordion} defaults=${meta ? meta.default_params : {}}
        values=${draft.params} onChange=${actions.setParam} />
    </div>
  `;
}
```

- [ ] **Step 3.8: Enable disk button in `SlotPicker.js`**

In `SlotPicker.js` already updated: the Browse button is enabled when `canAddMore`. No further change.

- [ ] **Step 3.9: Pass `api` from App.js**

Edit `cep-premiere/client/components/App.js`: change the `<GenerateTab>` line to `<${GenerateTab} snap=${snap} actions=${actions} api=${api} />`.

- [ ] **Step 3.10: Run all tests, stage, ask before commit**

Run: `cd cep-premiere && npm test`. Expect green (api 5, slot_schema 6, validation 5, state 7).

Stage modified/created files. Ask user. Proposed message: `feat(cep-premiere): disk source + uploadAsset + thumbnails + cache indicator`.


---

## Task 4 (B.4): Submit + polling + History tab + auto-download

**Goal:** User can submit a job (Nano Banana img2img end-to-end works). Polling updates every 2s. History tab shows job cards. Completed jobs auto-download to a local cache directory; UI shows result thumbnail. Pr import deferred to T7.

**Files:**
- Modify: `cep-premiere/client/lib/api.js` (createJob, listJobs, getJob, downloadJob, deleteJob)
- Modify: `cep-premiere/client/lib/state.js` (jobs reducer + polling)
- Create: `cep-premiere/client/lib/format.js` (duration, status label)
- Modify: `cep-premiere/client/components/App.js` (mount polling + History)
- Create: `cep-premiere/client/components/HistoryTab.js`
- Create: `cep-premiere/client/components/JobList.js`
- Create: `cep-premiere/client/components/JobCard.js`
- Create: `cep-premiere/client/components/JobFilter.js`
- Create: `cep-premiere/client/components/SubmitButton.js`
- Modify: `cep-premiere/client/components/GenerateTab.js` (mount SubmitButton)
- Modify: `cep-premiere/tests/lib/api.test.js`
- Modify: `cep-premiere/tests/lib/state.test.js`

- [ ] **Step 4.1: Write failing tests for `api.createJob`, `listJobs`, `downloadJob`**

Append to `cep-premiere/tests/lib/api.test.js`:

```js
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
```

Run vitest. Expect FAIL.

- [ ] **Step 4.2: Implement job endpoints in `api.js`**

In `client/lib/api.js` add a second internal request flavor that returns blob (current `request()` parses JSON only). Replace returned object additions:

```js
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
```

Run vitest. Expect 8/8 in api.test.js PASS.

- [ ] **Step 4.3: Write failing tests for job snapshot reducer**

Append to `cep-premiere/tests/lib/state.test.js`:

```js
import { diffJobs, mergeJobs } from '../../client/lib/state.js';

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
```

Run vitest. Expect FAIL.

- [ ] **Step 4.4: Implement `mergeJobs` + `diffJobs`**

Append to `cep-premiere/client/lib/state.js`:

```js
export function mergeJobs(prev, remote) {
  const prevById = new Map((prev || []).map(j => [j.job_id, j]));
  const out = remote.map(rj => {
    const local = prevById.get(rj.job_id);
    return local ? { ...local, ...rj } : { ...rj };
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
```

Run vitest. Expect state tests 10/10.

- [ ] **Step 4.5: Create `lib/format.js`**

Create `cep-premiere/client/lib/format.js`:

```js
export function fmtDuration(ms) {
  if (!ms || ms < 0) return '0s';
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const ss = s % 60;
  if (m === 0) return `${ss}s`;
  return `${m}m ${ss.toString().padStart(2, '0')}s`;
}

export function jobAgeMs(job, now = Date.now()) {
  const t = Date.parse(job.created_at);
  if (isNaN(t)) return 0;
  return now - t;
}
```

- [ ] **Step 4.6: Create `<SubmitButton>`**

Create `cep-premiere/client/components/SubmitButton.js`:

```js
import { html } from '../lib/html.js';
import { useState } from '../vendor/preact-hooks.module.js';
import { validateDraft } from '../lib/validation.js';

export function SubmitButton({ snap, api, onSubmitted }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const { draft, videoNodes, health } = snap;
  const v = validateDraft({ videoNodes, draft });
  const disabled = busy || health.status !== 'online' || !v.ok;

  async function onClick() {
    setBusy(true); setErr(null);
    try {
      const init_files = {};
      for (const [name, val] of Object.entries(draft.slots)) {
        if (Array.isArray(val)) init_files[name] = val.map(x => x.path);
        else if (val) init_files[name] = val.path;
      }
      const params = { ...draft.params, prompt: draft.prompt };
      const out = await api.createJob({ node_id: draft.model_id, params, init_files });
      if (onSubmitted) onSubmitted(out.job_id);
    } catch (e) {
      setErr(e.message || 'submit failed');
    } finally {
      setBusy(false);
    }
  }

  return html`
    <div class="submit">
      <button class="primary" onClick=${onClick} disabled=${disabled}>
        ${busy ? 'Submitting...' : 'Generate'}
      </button>
      ${!v.ok && v.errors.length > 0
        ? html`<div class="submit-errs">${v.errors.map(e => html`<div>${e.message}</div>`)}</div>`
        : null}
      ${err ? html`<div class="submit-err">${err}</div>` : null}
    </div>
  `;
}
```

Append CSS:

```css
.submit { margin-top: 10px; }
.submit-errs { margin-top: 4px; font-size: 11px; color: var(--yellow); }
.submit-err { margin-top: 4px; font-size: 11px; color: var(--red); }
```

- [ ] **Step 4.7: Wire `<SubmitButton>` into GenerateTab**

In `GenerateTab.js`, add `import { SubmitButton } from './SubmitButton.js';` and render `<${SubmitButton} snap=${snap} api=${api} onSubmitted=${(id) => console.log('submitted', id)} />` at the bottom of `.generate` div.

- [ ] **Step 4.8: Create JobCard / JobList / JobFilter / HistoryTab**

Create `cep-premiere/client/components/JobCard.js`:

```js
import { html } from '../lib/html.js';
import { fmtDuration, jobAgeMs } from '../lib/format.js';

const STATUS_CLS = {
  queued: 'q', running: 'r', completed: 'ok', failed: 'fail', canceled: 'fail',
};

export function JobCard({ job, api, onAction }) {
  const cls = STATUS_CLS[job.status] || 'q';
  const age = fmtDuration(jobAgeMs(job));
  const prog = Math.round((job.progress || 0) * 100);
  return html`
    <div class=${`job-card ${cls}`}>
      <div class="job-head">
        <span class="job-title">${job.node_id}</span>
        <span class="job-age">${age}</span>
      </div>
      <div class="job-status">${job.status} ${job.status === 'running' ? `· ${prog}%` : ''}</div>
      ${job.error ? html`<div class="job-error">${job.error}</div>` : null}
      ${job.resultBlobUrl
        ? html`<img class="job-thumb" src=${job.resultBlobUrl} alt="" />`
        : null}
      <div class="job-actions">
        ${job.status === 'completed' ? html`
          <button onClick=${() => onAction('insert', job)} disabled title="T7">Insert</button>
          <button onClick=${() => onAction('show', job)} disabled title="T7">Show in bin</button>
          <button onClick=${() => onAction('download', job)}>Download</button>
        ` : null}
        ${job.status === 'failed' || job.status === 'canceled'
          ? html`<button onClick=${() => onAction('retry', job)}>Retry</button>`
          : null}
        <button onClick=${() => onAction('delete', job)}>Delete</button>
      </div>
    </div>
  `;
}
```

Create `cep-premiere/client/components/JobList.js`:

```js
import { html } from '../lib/html.js';
import { JobCard } from './JobCard.js';

export function JobList({ jobs, api, onAction }) {
  if (!jobs.length) return html`<div class="empty">No jobs yet</div>`;
  const sorted = [...jobs].sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
  return html`
    <div class="job-list">
      ${sorted.map(j => html`<${JobCard} job=${j} api=${api} onAction=${onAction} />`)}
    </div>
  `;
}
```

Create `cep-premiere/client/components/JobFilter.js`:

```js
import { html } from '../lib/html.js';

export function JobFilter({ value, onChange }) {
  const opts = ['all', 'queued', 'running', 'completed', 'failed', 'canceled'];
  return html`
    <div class="job-filter">
      ${opts.map(o => html`
        <span class=${`fc ${value === o ? 'active' : ''}`} onClick=${() => onChange(o)}>${o}</span>
      `)}
    </div>
  `;
}
```

Create `cep-premiere/client/components/HistoryTab.js`:

```js
import { html } from '../lib/html.js';
import { useState } from '../vendor/preact-hooks.module.js';
import { JobFilter } from './JobFilter.js';
import { JobList } from './JobList.js';

export function HistoryTab({ snap, api, onAction }) {
  const [filter, setFilter] = useState('all');
  const jobs = filter === 'all' ? snap.jobs : snap.jobs.filter(j => j.status === filter);
  return html`
    <div class="history">
      <${JobFilter} value=${filter} onChange=${setFilter} />
      <${JobList} jobs=${jobs} api=${api} onAction=${onAction} />
    </div>
  `;
}
```

Append CSS:

```css
.job-card { border: 1px solid var(--border); padding: 8px; margin-bottom: 8px; background: var(--bg-2); }
.job-card.ok { border-left: 3px solid var(--green); }
.job-card.r { border-left: 3px solid var(--accent); }
.job-card.fail { border-left: 3px solid var(--red); }
.job-card.q { border-left: 3px solid var(--fg-dim); }
.job-head { display: flex; justify-content: space-between; }
.job-title { font-weight: 600; }
.job-age { color: var(--fg-dim); font-size: 11px; }
.job-status { font-size: 11px; margin-top: 2px; }
.job-error { font-size: 11px; color: var(--red); margin-top: 4px; }
.job-thumb { display: block; max-width: 100%; margin-top: 6px; }
.job-actions { display: flex; gap: 4px; margin-top: 6px; flex-wrap: wrap; }
.job-actions button { font-size: 11px; padding: 2px 6px; }
.job-filter { display: flex; gap: 6px; margin-bottom: 8px; font-size: 11px; }
.fc { padding: 2px 6px; cursor: pointer; color: var(--fg-dim); }
.fc.active { color: var(--fg); border-bottom: 1px solid var(--accent); }
.empty { text-align: center; color: var(--fg-dim); padding: 20px; }
```

- [ ] **Step 4.9: Add polling + auto-download in App.js**

Edit `cep-premiere/client/components/App.js`. Add imports:

```js
import { HistoryTab } from './HistoryTab.js';
import { mergeJobs, diffJobs } from '../lib/state.js';
```

Inside `App({ store, api })`, add another `useEffect` after the bootstrap one:

```js
  // Job polling — 2s tick when sidecar online
  useEffect(() => {
    let cancelled = false;
    async function tick() {
      if (store.get().health.status !== 'online') return;
      try {
        const r = await api.listJobs({ limit: 50 });
        if (cancelled) return;
        const cur = store.get().jobs || [];
        const remote = r.jobs || [];
        const { completedNow } = diffJobs(cur, remote);
        store.set({ jobs: mergeJobs(cur, remote) });
        // Auto-download for completed ones we haven't downloaded yet
        for (const j of completedNow) {
          if (!j.result_paths || !j.result_paths.length) continue;
          try {
            const blob = await api.downloadJob(j.job_id, 0);
            const url = URL.createObjectURL(blob);
            const jobs = store.get().jobs.map(x =>
              x.job_id === j.job_id ? { ...x, resultBlobUrl: url } : x
            );
            store.set({ jobs });
          } catch (_) { /* swallow; T8 toasts */ }
        }
      } catch (_) { /* sidecar might be flaky; T8 handles */ }
    }
    tick();
    const id = setInterval(tick, 2000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);
```

Replace history placeholder with:

```js
  : html`<${HistoryTab} snap=${snap} api=${api}
      onAction=${async (action, job) => {
        if (action === 'delete') { await api.deleteJob(job.job_id); }
        if (action === 'download') {
          const blob = await api.downloadJob(job.job_id, 0);
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = `${job.job_id}.${blob.type.endsWith('mp4') ? 'mp4' : 'jpg'}`;
          a.click();
        }
        if (action === 'retry') {
          // restore form from job.params — T7 polishes
          console.log('retry', job);
        }
      }} />`
```

Auto-jump to History when a new job is submitted: change SubmitButton's `onSubmitted` in `GenerateTab.js` to use a callback prop from App. Simplest: lift `setTab` into context.

Quick approach — `GenerateTab` accepts `onSubmitted` prop, and `App` passes `() => setTab('history')`:

In `App.js` JSX:
```js
${tab === 'generate'
  ? html`<${GenerateTab} snap=${snap} actions=${actions} api=${api}
      onSubmitted=${() => setTab('history')} />`
  : html`... HistoryTab ...`}
```

In `GenerateTab.js`, pass `onSubmitted={props.onSubmitted}` to `<SubmitButton>`.

- [ ] **Step 4.10: Run tests + manual smoke + ask before commit**

`cd cep-premiere && npm test` — all green.

Manual smoke (requires sidecar running by user):
- Open panel in Pr → Generate tab.
- Pick Nano Banana → Browse → pick test.jpg → wait for upload → cached indicator on 2nd pick.
- Submit → switches to History → JobCard polls → completed → thumb appears.

Stage. Ask user. Proposed message: `feat(cep-premiere): submit + polling + History tab + auto-download`.

---

## Task 5 (B.5): Cost preview

**Goal:** Estimate button calls `/jobs/preview-cost`, displays credits + current balance. Result cached in state until params/scenario/model change.

**Files:**
- Modify: `cep-premiere/client/lib/api.js` (getBalance)
- Modify: `cep-premiere/client/lib/state.js` (costEstimate slice)
- Create: `cep-premiere/client/components/CostBar.js`
- Modify: `cep-premiere/client/components/GenerateTab.js` (mount CostBar)
- Modify: `cep-premiere/tests/lib/api.test.js`

Sidecar exposes `/health` (jwt_ttl_sec) but not `/balance` directly — credits are queried by the sidecar via Phygital API on demand. Decision: only show estimate (no balance) for MVP. If we later expose `/account/balance` endpoint, expand UI. Mark TODO.

- [ ] **Step 5.1: Write failing test for `api.previewCost`**

Already declared in T4. Add a more thorough test:

```js
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
```

Run vitest. Should already PASS if T4.2 was implemented correctly. If not, fix `previewCost` in `api.js`.

- [ ] **Step 5.2: Extend state with cost slice**

Append to `cep-premiere/client/lib/state.js`:

```js
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
```

Also extend DEFAULT_STATE to include `cost: { key: null, price: null, loading: false, error: null }`. Edit DEFAULT_STATE.

- [ ] **Step 5.3: Write `<CostBar>` component**

Create `cep-premiere/client/components/CostBar.js`:

```js
import { html } from '../lib/html.js';
import { useState, useEffect } from '../vendor/preact-hooks.module.js';
import { makeCostKey } from '../lib/state.js';

export function CostBar({ snap, api, store }) {
  const { draft } = snap;
  const key = makeCostKey(draft);
  const cost = snap.cost || { key: null };
  const stale = cost.key !== key;

  async function estimate() {
    store.set({ cost: { key, price: null, loading: true, error: null } });
    try {
      const out = await api.previewCost({ node_id: draft.model_id, params: { ...draft.params, prompt: draft.prompt } });
      store.set({ cost: { key, price: out.price ?? out.credits ?? null, loading: false, error: null } });
    } catch (e) {
      store.set({ cost: { key, price: null, loading: false, error: e.message || 'cost failed' } });
    }
  }

  return html`
    <div class="cost">
      <button onClick=${estimate} disabled=${cost.loading}>${cost.loading ? '...' : 'Estimate'}</button>
      ${!stale && cost.price != null
        ? html`<span class="cost-price">~${cost.price} credits</span>`
        : stale && cost.price != null
          ? html`<span class="cost-stale">stale, re-estimate</span>`
          : null}
      ${cost.error ? html`<span class="cost-err">${cost.error}</span>` : null}
      ${!stale && typeof cost.price === 'number' && cost.price > 100
        ? html`<div class="cost-warn">This generation will cost > 100 credits</div>`
        : null}
    </div>
  `;
}
```

Append CSS:

```css
.cost { display: flex; align-items: center; gap: 8px; margin-top: 8px; padding: 6px; border: 1px solid var(--border); }
.cost-price { font-weight: 600; }
.cost-stale { color: var(--fg-dim); font-size: 11px; }
.cost-err { color: var(--red); font-size: 11px; }
.cost-warn { color: var(--yellow); font-size: 11px; margin-top: 4px; width: 100%; }
```

- [ ] **Step 5.4: Mount `<CostBar>` in GenerateTab**

Edit `GenerateTab.js`:
- `import { CostBar } from './CostBar.js';`
- Render `<${CostBar} snap=${snap} api=${api} store=${store} />` between `<${ParamsAccordion}>` and `<${SubmitButton}>`.
- Add `store` prop. In App.js, pass `store={store}` to `<GenerateTab>`.

- [ ] **Step 5.5: Run tests + manual smoke + commit (gated)**

Manual: open panel, fill form, click Estimate, see `~N credits` (e.g. `~120`).

`cd cep-premiere && npm test` — green.

Stage, ask user. Proposed message: `feat(cep-premiere): cost preview via /jobs/preview-cost`.

---

## Task 6 (B.6): host.jsx + Pr sources (bin / timeline / source monitor) + frame extract

**Goal:** Enable Bin / Timeline / Src mon buttons in SlotPicker. Pick a clip from Pr → if image-slot + video clip, auto-extract playhead frame → upload → fill slot.

**Files:**
- Modify: `cep-premiere/host/host.jsx` (rewrite — spec §8 API)
- Create: `cep-premiere/client/lib/host.js`
- Modify: `cep-premiere/client/components/GenerateTab.js` (handle non-disk sources)
- Modify: `cep-premiere/client/components/SlotPicker.js` (enable buttons)

ExtendScript runs in ES3 VM — no `const`, no arrow funcs, no `Promise`, no template literals. Only `var`, `function`, and Pr's `app.project`, `app.project.activeSequence`, `qe`, `ProjectItem`, `Track`, etc.

- [ ] **Step 6.1: Write `host/host.jsx` with full §8 API**

Replace `cep-premiere/host/host.jsx`:

```jsx
// Phygital Studio — Pr ExtendScript host.
// Public API (all return JSON.stringify({ok, ...})):
//   getBinSelection()
//   getTimelineSelection(playheadOnly)
//   getSourceMonitorItem()
//   extractFrame(projectItemId, timecodeSec)
//   importToBin(path)
//   insertClipAtPlayhead(projectItemId)
//
// All paths are absolute. Functions never throw — wrap in try/catch and
// return {ok:false, error}.

#target premierepro

function _ok(extra) {
  var o = { ok: true };
  for (var k in extra) if (extra.hasOwnProperty(k)) o[k] = extra[k];
  return JSON.stringify(o);
}
function _err(code, reason) {
  return JSON.stringify({ ok: false, error: code, reason: reason || null });
}

function _itemKind(pi) {
  // ProjectItem.type: 1=clip, 2=bin, 3=root, 4=file
  // Better: inspect getMediaPath + nodeId. Fall back to extension sniffing.
  try {
    if (pi.getMediaPath) {
      var p = String(pi.getMediaPath() || '');
      var ext = p.split('.').pop().toLowerCase();
      if (['mp4','mov','avi','mkv','m4v','mxf'].indexOf(ext) >= 0) return 'video';
      if (['jpg','jpeg','png','tif','tiff','psd','heic'].indexOf(ext) >= 0) return 'image';
      if (['wav','mp3','aac','aiff'].indexOf(ext) >= 0) return 'audio';
    }
  } catch (e) {}
  return 'unknown';
}

function _walkItems(root, out) {
  for (var i = 0; i < root.children.numItems; i++) {
    var c = root.children[i];
    if (c.type === ProjectItemType.BIN || c.type === 2) _walkItems(c, out);
    else out.push(c);
  }
}

function _findProjectItemById(id) {
  // ProjectItem doesn't expose stable id. Use nodeId.
  var stack = [app.project.rootItem];
  while (stack.length) {
    var n = stack.pop();
    for (var i = 0; i < n.children.numItems; i++) {
      var c = n.children[i];
      if (String(c.nodeId) === String(id)) return c;
      if (c.type === 2 /* bin */) stack.push(c);
    }
  }
  return null;
}

function getBinSelection() {
  try {
    var sel = app.project.getSelection ? app.project.getSelection() : null;
    if (!sel || sel.length === 0) return _err('no_selection');
    var items = [];
    for (var i = 0; i < sel.length; i++) {
      var pi = sel[i];
      var kind = _itemKind(pi);
      if (['video','image','audio'].indexOf(kind) < 0) continue;
      items.push({
        projectItemId: String(pi.nodeId),
        path: String(pi.getMediaPath()),
        name: String(pi.name),
        kind: kind,
      });
    }
    if (items.length === 0) return _err('unsupported_kind');
    return _ok({ items: items });
  } catch (e) { return _err('exception', String(e)); }
}

function getTimelineSelection(playheadOnly) {
  try {
    var seq = app.project.activeSequence;
    if (!seq) return _err('no_active_sequence');
    var items = [];
    var phTicks = seq.getPlayerPosition ? seq.getPlayerPosition() : null;
    function clipAt(track, clip) {
      var inSec = clip.start.seconds;
      var outSec = clip.end.seconds;
      if (playheadOnly && phTicks) {
        var phSec = phTicks.seconds;
        if (phSec < inSec || phSec > outSec) return false;
      }
      var pi = clip.projectItem;
      if (!pi) return false;
      var kind = _itemKind(pi);
      items.push({
        projectItemId: String(pi.nodeId),
        path: String(pi.getMediaPath ? pi.getMediaPath() : ''),
        name: String(clip.name),
        kind: kind,
        in_sec: inSec,
        out_sec: outSec,
      });
      return true;
    }
    for (var t = 0; t < seq.videoTracks.numTracks; t++) {
      var trk = seq.videoTracks[t];
      for (var c = 0; c < trk.clips.numItems; c++) {
        var clip = trk.clips[c];
        if (playheadOnly || clip.isSelected()) clipAt(trk, clip);
      }
    }
    if (items.length === 0) {
      return _err(playheadOnly ? 'no_clip_at_playhead' : 'no_selection');
    }
    return _ok({ items: items });
  } catch (e) { return _err('exception', String(e)); }
}

function getSourceMonitorItem() {
  try {
    var sm = app.sourceMonitor;
    if (!sm) return _err('no_source_monitor_clip');
    var proj = sm.getProjectItem ? sm.getProjectItem() : null;
    if (!proj) return _err('no_source_monitor_clip');
    var pi = proj;
    return _ok({ item: {
      projectItemId: String(pi.nodeId),
      path: String(pi.getMediaPath()),
      name: String(pi.name),
      kind: _itemKind(pi),
    }});
  } catch (e) { return _err('exception', String(e)); }
}

function _tmpDir() {
  // %TEMP% or system temp. CEP exposes via Folder.temp.
  var d = Folder.temp.fsName + '/PhygitalStudio_frames';
  var f = new Folder(d);
  if (!f.exists) f.create();
  return d;
}

function extractFrame(projectItemId, timecodeSec) {
  try {
    var pi = _findProjectItemById(projectItemId);
    if (!pi) return _err('not_found');
    var t = timecodeSec;
    if (t === null || typeof t === 'undefined') {
      var seq = app.project.activeSequence;
      if (!seq) return _err('no_active_sequence');
      var p = seq.getPlayerPosition();
      t = p ? p.seconds : 0;
    }
    var outPath = _tmpDir() + '/frame_' + (new Date().getTime()) + '_' + Math.floor(Math.random() * 1e6) + '.jpg';
    var time = new Time();
    time.seconds = t;
    // Pr 22+: ProjectItem.exportFrameJPEG (single arg = path, time defaults to in-point).
    // Use sequence's exportFrameJPEG via qe if available.
    if (pi.exportFrameJPEG) {
      pi.exportFrameJPEG(outPath, time);
    } else if (typeof qe !== 'undefined') {
      var qes = qe.project.getActiveSequence();
      qes.exportFrameJPEG(outPath);
    } else {
      return _err('extract_failed', 'no_method');
    }
    return _ok({ framePath: outPath, timecode: String(t) });
  } catch (e) { return _err('extract_failed', String(e)); }
}

function _binByName(name) {
  for (var i = 0; i < app.project.rootItem.children.numItems; i++) {
    var c = app.project.rootItem.children[i];
    if (c.type === 2 /* bin */ && c.name === name) return c;
  }
  return app.project.rootItem.createBin(name);
}

function importToBin(path) {
  try {
    var bin = _binByName('PhygitalStudio');
    var before = bin.children.numItems;
    app.project.importFiles([path], true, bin, false);
    if (bin.children.numItems > before) {
      var pi = bin.children[bin.children.numItems - 1];
      return _ok({ projectItemId: String(pi.nodeId), binName: 'PhygitalStudio' });
    }
    return _err('import_failed', 'no new item');
  } catch (e) { return _err('import_failed', String(e)); }
}

function insertClipAtPlayhead(projectItemId) {
  try {
    var seq = app.project.activeSequence;
    if (!seq) return _err('no_active_sequence');
    var pi = _findProjectItemById(projectItemId);
    if (!pi) return _err('not_found');
    var ph = seq.getPlayerPosition();
    seq.insertClip(pi, ph);
    return _ok({ sequenceId: String(seq.sequenceID), insertedAt: String(ph.seconds) });
  } catch (e) { return _err('insert_failed', String(e)); }
}
```

This file is ExtendScript ES3 — DO NOT use ES6+ syntax. No tests (ExtendScript has no Node CI). Verified manually via T9.

- [ ] **Step 6.2: Create `client/lib/host.js`**

Create `cep-premiere/client/lib/host.js`:

```js
// Single point of CSInterface.evalScript. Returns Promise<object>.
// CSInterface is loaded globally via <script> tag in index.html.

let cs = null;
function getCS() {
  if (cs) return cs;
  if (typeof window !== 'undefined' && window.CSInterface) {
    cs = new window.CSInterface();
  }
  return cs;
}

function call(fnName, ...args) {
  return new Promise((resolve, reject) => {
    const csi = getCS();
    if (!csi) return reject(new Error('CSInterface unavailable'));
    const argsJs = args.map(a => JSON.stringify(a)).join(', ');
    csi.evalScript(`${fnName}(${argsJs})`, (out) => {
      try {
        const parsed = JSON.parse(out);
        if (parsed && parsed.ok) resolve(parsed);
        else reject(Object.assign(new Error(parsed && parsed.error || 'unknown'), { result: parsed }));
      } catch (e) {
        reject(new Error('host parse fail: ' + out));
      }
    });
  });
}

export const host = {
  getBinSelection:        () => call('getBinSelection'),
  getTimelineSelection:   (playheadOnly = false) => call('getTimelineSelection', playheadOnly),
  getSourceMonitorItem:   () => call('getSourceMonitorItem'),
  extractFrame:           (projectItemId, timecodeSec) => call('extractFrame', projectItemId, timecodeSec),
  importToBin:            (path) => call('importToBin', path),
  insertClipAtPlayhead:   (projectItemId) => call('insertClipAtPlayhead', projectItemId),
};

// Promise queue: ExtendScript is single-threaded; serialize evalScript calls.
let chain = Promise.resolve();
export function hostQueued(name, ...args) {
  const next = chain.then(() => host[name](...args));
  chain = next.catch(() => {});
  return next;
}
```

- [ ] **Step 6.3: Wire non-disk sources in `GenerateTab.onPick`**

Edit `cep-premiere/client/components/GenerateTab.js`:

```js
import { host, hostQueued } from '../lib/host.js';
```

Replace `async function onPick(slot, source) {...}` with:

```js
async function onPick(slot, source) {
  try {
    let pickResult = null;
    if (source === 'disk') {
      const paths = await pickFilesFromDisk({ multi: slot.kind === 'array' });
      if (!paths || paths.length === 0) return;
      for (const p of paths) await ingestPath(slot, p, 'disk');
      return;
    }
    if (source === 'bin')             pickResult = await host.getBinSelection();
    else if (source === 'timeline')   pickResult = await host.getTimelineSelection(true);
    else if (source === 'source_monitor') pickResult = await host.getSourceMonitorItem();
    if (!pickResult) return;

    const items = pickResult.items || (pickResult.item ? [pickResult.item] : []);
    const isImageSlot = isImageSlotName(slot.name);

    for (const it of items) {
      let usePath = it.path;
      // For image-slots + video clips → auto extract frame
      if (isImageSlot && it.kind === 'video') {
        try {
          const fr = await host.extractFrame(it.projectItemId, null);
          usePath = fr.framePath;
        } catch (e) {
          console.warn('extract failed', e); continue;
        }
      }
      await ingestPath(slot, usePath, source, it.name);
    }
  } catch (e) {
    console.warn('pick fail', e);
  }
}

function isImageSlotName(name) {
  // Heuristic by spec §3.3 slot map. Image slots are: init_img, image_tail,
  // element_*, start_img, end_frame, ref_img, first_frame, last_frame, char_ref.
  // Non-image: ref_vid, ref_audio, video.
  return !/^(ref_vid|ref_audio|video)$/.test(name);
}

async function ingestPath(slot, path, source, displayName) {
  const name = displayName || path.split(/[\\/]/).pop();
  const blob = await readFileAsBlob(path);
  const thumb = await makeThumbDataURL(blob).catch(() => null);
  const item = { source, path, name, thumb };
  if (slot.kind === 'array') {
    const cur = draft.slots[slot.name] || [];
    actions.setSlot(slot.name, [...cur, item]);
  } else {
    actions.setSlot(slot.name, item);
  }
  try {
    const { entry, cached } = await uploadActions.upload({ api, blob, filename: name });
    const enriched = { ...item, asset: entry, cached };
    if (slot.kind === 'array') {
      const cur2 = (draft.slots[slot.name] || []).map(x => x.path === path ? enriched : x);
      actions.setSlot(slot.name, cur2);
    } else actions.setSlot(slot.name, enriched);
  } catch (e) {
    const err = { ...item, error: e.message };
    if (slot.kind === 'array') {
      const cur2 = (draft.slots[slot.name] || []).map(x => x.path === path ? err : x);
      actions.setSlot(slot.name, cur2);
    } else actions.setSlot(slot.name, err);
  }
}
```

- [ ] **Step 6.4: Enable buttons in `SlotPicker.js`**

Edit `cep-premiere/client/components/SlotPicker.js`. Remove the `disabled` + `title="T6"` attributes on Bin / Timeline / Src mon buttons:

```js
        <button onClick=${() => onPick && onPick('bin')}>Bin</button>
        <button onClick=${() => onPick && onPick('timeline')}>Timeline</button>
        <button onClick=${() => onPick && onPick('source_monitor')}>Src mon</button>
        <button onClick=${() => onPick && onPick('disk')} disabled=${!canAddMore}>Browse...</button>
```

- [ ] **Step 6.5: Manual smoke + commit (gated)**

Open Pr → import a video clip into a bin → select it → click Bin in SlotPicker (for image slot) → frame should extract → upload → cached on repeat.

Try Timeline: place a clip on the timeline, position playhead inside it, click Timeline → same flow.

Stage. Ask user. Proposed message: `feat(cep-premiere): host.jsx + Pr sources + frame extract`.

---

## Task 7 (B.7): Auto-import + Insert to timeline + JobCard actions

**Goal:** When a job completes, the downloaded blob is written to disk, imported into Pr `PhygitalStudio` bin, JobCard shows Insert/Show-in-bin enabled. Click Insert → clip lands at playhead.

**Files:**
- Modify: `cep-premiere/client/lib/host.js` (already covers importToBin/insertClipAtPlayhead via T6)
- Modify: `cep-premiere/client/components/App.js` (auto-import after download)
- Modify: `cep-premiere/client/components/JobCard.js` (enable Insert / Show)
- Modify: `cep-premiere/client/lib/state.js` (track projectItemId per job)
- Create: `cep-premiere/client/lib/disk_save.js` (write blob to disk)

- [ ] **Step 7.1: Implement disk save helper**

Create `cep-premiere/client/lib/disk_save.js`:

```js
// Save a Blob to a stable disk path inside %LOCALAPPDATA%/PhygitalStudio/downloads/.
// Requires Node-enabled CEF (manifest --enable-nodejs).

export async function saveBlobToDisk(blob, filename) {
  const fs = require('fs');
  const path = require('path');
  const os = require('os');
  const dir = path.join(process.env.LOCALAPPDATA || os.tmpdir(), 'PhygitalStudio', 'downloads-panel');
  fs.mkdirSync(dir, { recursive: true });
  const out = path.join(dir, filename);
  const buf = Buffer.from(await blob.arrayBuffer());
  fs.writeFileSync(out, buf);
  return out;
}
```

- [ ] **Step 7.2: Auto-import in polling loop**

Edit `cep-premiere/client/components/App.js` — inside the polling `useEffect`, after the download block, add import step:

```js
        for (const j of completedNow) {
          if (!j.result_paths || !j.result_paths.length) continue;
          try {
            const blob = await api.downloadJob(j.job_id, 0);
            const ext = blob.type.startsWith('image/') ? 'jpg' : (blob.type.includes('mp4') ? 'mp4' : 'bin');
            const localPath = await (await import('../lib/disk_save.js')).saveBlobToDisk(blob, `${j.job_id}.${ext}`);
            const url = URL.createObjectURL(blob);
            const enriched = { resultBlobUrl: url, localPath };
            // Try Pr import
            try {
              const { hostQueued } = await import('../lib/host.js');
              const r = await hostQueued('importToBin', localPath);
              enriched.projectItemId = r.projectItemId;
            } catch (_) { /* keep download even if Pr offline */ }
            store.set(s => ({
              jobs: s.jobs.map(x => x.job_id === j.job_id ? { ...x, ...enriched } : x),
            }));
          } catch (_) {}
        }
```

- [ ] **Step 7.3: Enable Insert / Show-in-bin in JobCard**

Edit `cep-premiere/client/components/JobCard.js`. Replace the completed-actions block:

```js
${job.status === 'completed' ? html`
  <button onClick=${() => onAction('insert', job)} disabled=${!job.projectItemId}>Insert</button>
  <button onClick=${() => onAction('show', job)} disabled=${!job.projectItemId}>Show in bin</button>
  <button onClick=${() => onAction('download', job)}>Download</button>
` : null}
```

- [ ] **Step 7.4: Wire actions in App.js**

In `App.js` `<HistoryTab onAction>` callback, add:

```js
        if (action === 'insert') {
          if (!job.projectItemId) return;
          const { hostQueued } = await import('../lib/host.js');
          await hostQueued('insertClipAtPlayhead', job.projectItemId);
        }
        if (action === 'show') {
          // Pr has no direct "reveal in bin" API; bring panel focus + log.
          console.log('show', job.projectItemId);
        }
```

- [ ] **Step 7.5: Manual smoke + commit (gated)**

Manual:
- Submit Nano Banana img2img with disk source.
- Wait for completed.
- See thumb in JobCard + Insert enabled.
- Click Insert → clip appears at playhead in Pr active sequence.

Stage. Ask user. Proposed message: `feat(cep-premiere): auto-import to bin + Insert at playhead`.

---

## Task 8 (B.8): Error UX polish — toasts, inline warnings, disconnect resilience

**Goal:** Every error path surfaces in UI: upload fail, submit 4xx/5xx, Pr fail, sidecar disconnect with reconnect.

**Files:**
- Create: `cep-premiere/client/lib/toast.js`
- Create: `cep-premiere/client/components/Toast.js`
- Modify: `cep-premiere/client/components/App.js`
- Modify: `cep-premiere/client/components/GenerateTab.js`
- Modify: `cep-premiere/client/components/SubmitButton.js`
- Create: `cep-premiere/tests/lib/toast.test.js`

- [ ] **Step 8.1: Write failing test for toast manager**

Create `cep-premiere/tests/lib/toast.test.js`:

```js
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createToastManager } from '../../client/lib/toast.js';

describe('toast manager', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('addToast appends and dispatches updates', () => {
    const tm = createToastManager();
    const updates = [];
    tm.subscribe(t => updates.push(t));
    tm.success('hi');
    expect(updates[0].length).toBe(1);
    expect(updates[0][0].message).toBe('hi');
    expect(updates[0][0].level).toBe('success');
  });

  it('auto-dismisses after duration', () => {
    const tm = createToastManager();
    let last = [];
    tm.subscribe(t => { last = t; });
    tm.success('hi', 1000);
    expect(last.length).toBe(1);
    vi.advanceTimersByTime(1100);
    expect(last.length).toBe(0);
  });

  it('error toasts default to longer ttl', () => {
    const tm = createToastManager();
    let last = [];
    tm.subscribe(t => { last = t; });
    tm.error('bad');
    expect(last[0].duration).toBeGreaterThanOrEqual(5000);
  });

  it('max 3 stacked toasts', () => {
    const tm = createToastManager({ max: 3 });
    let last = [];
    tm.subscribe(t => { last = t; });
    tm.success('a'); tm.success('b'); tm.success('c'); tm.success('d');
    expect(last.length).toBe(3);
  });
});
```

Run vitest. Expect FAIL.

- [ ] **Step 8.2: Implement `lib/toast.js`**

Create `cep-premiere/client/lib/toast.js`:

```js
export function createToastManager({ max = 3 } = {}) {
  const toasts = [];
  const listeners = new Set();
  let nextId = 1;

  function notify() {
    const snap = toasts.slice();
    for (const l of listeners) l(snap);
  }

  function add(level, message, duration) {
    const t = { id: nextId++, level, message, duration };
    toasts.push(t);
    while (toasts.length > max) toasts.shift();
    notify();
    if (duration > 0) {
      setTimeout(() => {
        const i = toasts.findIndex(x => x.id === t.id);
        if (i >= 0) { toasts.splice(i, 1); notify(); }
      }, duration);
    }
    return t.id;
  }

  return {
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    success(msg, duration = 3000) { return add('success', msg, duration); },
    warning(msg, duration = 5000) { return add('warning', msg, duration); },
    error(msg, duration = 8000) { return add('error', msg, duration); },
    dismiss(id) {
      const i = toasts.findIndex(x => x.id === id);
      if (i >= 0) { toasts.splice(i, 1); notify(); }
    },
  };
}

export const toast = createToastManager();
```

Run vitest. Expect 4/4 PASS.

- [ ] **Step 8.3: Create `<Toast>` component**

Create `cep-premiere/client/components/Toast.js`:

```js
import { html } from '../lib/html.js';
import { useState, useEffect } from '../vendor/preact-hooks.module.js';
import { toast } from '../lib/toast.js';

export function ToastStack() {
  const [list, setList] = useState([]);
  useEffect(() => toast.subscribe(setList), []);
  return html`
    <div class="toast-stack">
      ${list.map(t => html`
        <div class=${`toast ${t.level}`} onClick=${() => toast.dismiss(t.id)}>${t.message}</div>
      `)}
    </div>
  `;
}
```

Append CSS:

```css
.toast-stack { position: fixed; top: 50px; right: 10px; display: flex; flex-direction: column; gap: 6px; z-index: 9999; }
.toast { padding: 6px 10px; border-radius: 4px; cursor: pointer; max-width: 260px; font-size: 11px; }
.toast.success { background: var(--green); color: #000; }
.toast.warning { background: var(--yellow); color: #000; }
.toast.error { background: var(--red); color: #fff; }
```

- [ ] **Step 8.4: Wire ToastStack + sidecar disconnect handling**

Edit `cep-premiere/client/components/App.js`:
- `import { ToastStack } from './Toast.js';` and `import { toast } from '../lib/toast.js';`
- Render `<${ToastStack} />` at the top of the returned tree (next to `<Header>`).
- In health useEffect: when transitioning offline → online, fire `toast.success('Sidecar connected')`; when transitioning online → offline, fire `toast.warning('Sidecar offline — retrying')`. Track previous status in `useRef`.
- In polling loop catch: skip silently (already handled by health toast).
- In completedNow loop catch on download: `toast.error(\`Download failed for ${j.job_id}\`)`.
- In completedNow loop on import success: `toast.success('Imported ' + j.job_id)`.
- In completedNow on import fail: `toast.warning('Imported but Pr offline')`.

- [ ] **Step 8.5: Wire toasts into GenerateTab / SubmitButton**

In `GenerateTab.js`, replace `console.warn(...)` calls with `toast.warning(...)` / `toast.error(...)`. Specifically:
- upload fail catch: `toast.error('Upload failed: ' + e.message)`
- extract fail catch: `toast.warning('Frame extract failed: ' + (e.reason || e.message))`
- pick fail outer catch: `toast.error('Source pick failed: ' + e.message)`

In `SubmitButton.js`, replace `setErr(...)` lines with `setErr` AND `toast.error('Submit failed: ' + e.message)`.

- [ ] **Step 8.6: Run tests + commit (gated)**

`cd cep-premiere && npm test` — green (api 8, slot_schema 6, validation 5, state 10, toast 4 = 33/33).

Manual smoke:
- Kill sidecar → see red pill + warning toast.
- Restart sidecar → green pill + success toast → polling resumes.
- Submit with invalid prompt → see validation errors under button.
- Force upload fail (e.g. submit huge file) → see error toast.

Stage. Ask user. Proposed message: `feat(cep-premiere): toast system + sidecar disconnect resilience`.

---

## Task 9 (B.9): Manual E2E + README + closure note

**Goal:** Document install, manual checklist; run all 9 spec §7.3 scenarios; write closure artifact in the Obsidian vault.

**Files:**
- Modify: `cep-premiere/README.md`
- Create: `cep-premiere/tests/integration/sidecar.test.js` (optional, requires running sidecar)
- Create: vault note at `01 Projects/Phygital Adobe Studio/Sub-project B — закрытие Pr-панель YYYY-MM-DD.md`

- [ ] **Step 9.1: Rewrite README**

Replace `cep-premiere/README.md` content:

```markdown
# Phygital Studio — Premiere Pro panel

Sub-project B of Phygital Adobe Studio. CEP panel that drives generation via
the local FastAPI sidecar.

## Install (dev mode)

1. Enable PlayerDebugMode (Pr 24+, CEP 11):
   - Windows: `HKEY_CURRENT_USER\Software\Adobe\CSXS.11` (and `.12`) → DWORD `PlayerDebugMode = 1`.
   - macOS: `defaults write com.adobe.CSXS.11 PlayerDebugMode 1`.
2. Symlink (or copy) this folder to `<COMMON CEP EXTENSIONS DIR>/com.phygital.studio.pr/`:
   - Win user-level: `%APPDATA%\Adobe\CEP\extensions\`.
   - Mac user-level: `~/Library/Application Support/Adobe/CEP/extensions/`.
3. Start the sidecar in a user shell (NOT from Claude — MSIX sandbox virtualizes paths):
   - `cd sidecar && python -m app.main`
4. Open Pr → Window → Extensions → Phygital Studio.

Debug: `http://localhost:8088` (port from `.debug`) → CEF DevTools.

## Unit tests

```
cd cep-premiere
npm install
npm test
```

## Manual E2E checklist (spec §7.3)

1. Sidecar offline → header pill red → Generate disabled.
2. Sidecar online → pill green → form usable.
3. Nano Banana → Browse → pick image → wait upload → submit → completed → auto-import → Insert.
4. Kling start_prompt → pick from Pr timeline (video) → frame auto-extracted → submit → completed → Insert.
5. Re-pick same file → `cached` indicator visible.
6. Seedance with person face → expect content moderation fail → error in JobCard.
7. Reload panel → draft restored → running jobs continue polling.
8. Kill sidecar mid-run → red pill + toast → restart sidecar → green pill + resume.
9. Cost preview → click Estimate → see `~N credits`.

## File layout

See `docs/superpowers/specs/2026-05-21-pr-panel-design.md` §3.1.
```

- [ ] **Step 9.2: (Optional) Integration test against sidecar**

Skip auto-running this. Create skeleton only:

Create `cep-premiere/tests/integration/sidecar.test.js`:

```js
import { describe, it, expect, beforeAll } from 'vitest';
import { createApi } from '../../client/lib/api.js';

describe.skipIf(!process.env.PHYGITAL_INTEGRATION)('sidecar integration', () => {
  const api = createApi({ fetch, baseUrl: 'http://127.0.0.1:8765' });
  it('GET /health', async () => {
    const h = await api.getHealth();
    expect(h).toBeTruthy();
  });
  it('GET /nodes/video', async () => {
    const r = await api.listVideoNodes();
    expect(r.nodes.length).toBeGreaterThan(0);
  });
});
```

Enable with `PHYGITAL_INTEGRATION=1 npm test`.

- [ ] **Step 9.3: Run all 9 manual scenarios + record results**

Walk through README §"Manual E2E checklist". Record pass/fail per item in vault closure note.

- [ ] **Step 9.4: Write vault closure note**

Write a sub-project closure note in the personal knowledge vault (path varies per setup) with frontmatter (tags, status: закрыт), summary of what was built, list of completed/skipped manual items, and links to the related project notes.

Update the project folder note: status, 🎯 Next action (→ sub-project C, AE-панель), artifact table.
Update the master ecosystem index with a chronology entry.

- [ ] **Step 9.5: Update project memory**

Update agent project memory (path-private) to add a "Sub-project B (Pr panel) — DONE <date>" bullet with key implementation details (Preact + htm stack, files structure, manual E2E pass count, anything unexpected encountered).

- [ ] **Step 9.6: Commit (gated)**

Stage README + vault notes + memory update. Ask user. Proposed message: `docs(cep-premiere): close sub-project B with manual E2E and README`.

---

## Self-review checklist (verifies the plan before execution starts)

**Spec coverage** — every section of `2026-05-21-pr-panel-design.md` mapped to tasks:
- §1 Context — covered by overall plan goal.
- §2 Brainstorm decisions — embedded in tasks (T2 stack, T3 disk-first, T6 frame extract, T7 auto-import, T1 layout, T2 localStorage draft, all Win-first).
- §3.1 Module boundaries — file map at top of plan matches spec tree.
- §3.2 Invariants (single fetch / evalScript / mutation) — enforced by T1 api.js, T6 host.js, T2 state.js boundaries.
- §3.3 Dependencies — downloaded in T1.5.
- §4.1 Dynamic form — T2.
- §4.2 Slot picker — T2 (read-only), T3 (disk + thumb), T6 (Pr sources).
- §4.3 Cost preview — T5.
- §4.4 Job card — T4 + T7.
- §4.5 Header / status pill — T1 + T8 (transitions).
- §5 Data flow — T1 (health), T3 (upload), T4 (submit/poll), T7 (auto-import).
- §6 Error handling — T8 (toasts), T6 (inline warnings via toast), T8 (disconnect).
- §7 Testing — T1–T8 unit tests, T9 manual + skeleton integration.
- §8 host.jsx API — T6.
- §9 B.1–B.9 — directly = Tasks 1–9.
- §10 Open items — listed but not blockers; frame extract method tested in T6, CSP in T1 (CSP meta), Pr ref stability surface in T7 errors.

**Placeholder scan** — no "TBD" / "TODO: implement later" / "add appropriate error handling" — all code blocks complete.

**Type consistency** —
- `SlotValue` shape `{source, path, name, thumb?, asset?, cached?, error?}` consistent T2 → T3 → T6.
- `JobState` fields from sidecar `{job_id, node_id, status, task_id, progress, result_paths, error, created_at, updated_at}` — T4 uses these directly.
- `host.jsx` return shape `JSON.stringify({ok, ...})` consistent T6 → T7.
- `api.previewCost` returns `{price, currency}` — T5 displays `price`. If sidecar actually returns different keys, update CostBar (Step 5.3 already falls back to `out.credits`).

**Scope check** — 9 tasks, each with self-contained test/manual acceptance. No single task touches more than ~6 files. Polish tasks (T8, T9) intentionally last so prior tasks stay focused.

