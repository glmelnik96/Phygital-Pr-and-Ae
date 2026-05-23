import { render } from './vendor/preact.module.js';
import { html } from './lib/html.js';
import { createApi } from './lib/api.js';
import { store } from './lib/state.js';
import { App } from './components/App.js';
import { ensureSidecar, stopSpawnedSidecar } from './lib/autostart.js';
import { sidecarAuthHeader } from './lib/sidecar_token.js';

// `getAuthHeaders` is called per-request (not once at boot) so that if the
// sidecar regenerates its token after a panel mount (e.g. fresh install
// finishing in parallel), the next request picks up the new value once
// `clearTokenCache()` is called or the panel reloads.
const api = createApi({
  fetch: window.fetch.bind(window),
  baseUrl: 'http://127.0.0.1:8765',
  getAuthHeaders: () => sidecarAuthHeader(),
});
render(html`<${App} store=${store} api=${api} />`, document.getElementById('root'));

// Fire-and-forget: the health useEffect in <App> will pick up the sidecar
// once /health responds. We don't await — panel UI stays responsive.
ensureSidecar().catch(() => {});

// Kill the sidecar we spawned when the user closes Pr (or unloads the panel).
// `beforeunload` covers DevTools reloads + panel close; CSXS
// `applicationBeforeQuit` covers the "X" on Pr's main window. stopSpawnedSidecar
// is a no-op if we didn't spawn the sidecar ourselves (someone else's process
// stays alive).
window.addEventListener('beforeunload', () => { stopSpawnedSidecar(); });
try {
  const cs = new (globalThis.CSInterface || window.CSInterface)();
  cs.addEventListener('applicationBeforeQuit', () => { stopSpawnedSidecar(); });
} catch (_) { /* not in CEP host — ignore */ }
