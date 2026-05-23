// Reads the per-install shared-secret token that the sidecar generates on its
// first boot (see sidecar/app/services/sidecar_auth.py). The CEP panel runs
// inside CEF with Node.js `require` enabled (via manifest's --enable-nodejs),
// so we can `fs.readFileSync` the token from the same AppData location that
// the sidecar uses. Path resolution mirrors `sidecar/app/paths.py`.
//
// Why mirror manually instead of asking the sidecar over HTTP? Because the
// whole point of the token is that the sidecar refuses unauthenticated
// requests — we can't ask it for the token over the very channel that
// requires the token. The filesystem is the trust boundary.
//
// Cache the token in module scope so repeated panel mounts don't keep
// touching disk. If the sidecar regenerates its token (manual deletion +
// restart), the panel must be reloaded to pick up the new value.

const TOKEN_HEADER_NAME = 'X-Phygital-Sidecar-Token';
let cachedToken = null;

function appDataDir() {
  // Mirrors sidecar/app/paths.py:resolve_app_data().
  if (typeof require !== 'function') return null;
  try {
    const os = require('os');
    const path = require('path');
    const platform = process.platform;
    if (platform === 'win32') {
      const base = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local');
      return path.join(base, 'PhygitalStudio');
    }
    if (platform === 'darwin') {
      return path.join(os.homedir(), 'Library', 'Application Support', 'PhygitalStudio');
    }
    // linux + other
    const xdg = process.env.XDG_DATA_HOME;
    if (xdg) return path.join(xdg, 'PhygitalStudio');
    return path.join(os.homedir(), '.local', 'share', 'PhygitalStudio');
  } catch (_) {
    return null;
  }
}

export function readSidecarToken({ force = false } = {}) {
  if (!force && cachedToken) return cachedToken;
  if (typeof require !== 'function') return null;
  try {
    const fs = require('fs');
    const path = require('path');
    const dir = appDataDir();
    if (!dir) return null;
    const tokenPath = path.join(dir, 'sidecar.token');
    if (!fs.existsSync(tokenPath)) return null;
    const raw = fs.readFileSync(tokenPath, 'utf8').trim();
    if (!raw || raw.length < 16) return null;
    cachedToken = raw;
    return raw;
  } catch (_) {
    return null;
  }
}

export function sidecarAuthHeader() {
  const t = readSidecarToken();
  if (!t) return {};
  return { [TOKEN_HEADER_NAME]: t };
}

export function clearTokenCache() {
  cachedToken = null;
}

export { TOKEN_HEADER_NAME };
