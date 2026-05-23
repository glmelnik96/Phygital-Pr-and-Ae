// Spawn the sidecar via CEP's Node.js (`--enable-nodejs` in manifest)
// if it isn't already reachable on 127.0.0.1:8765.
//
// Strategy:
//   1. On every panel mount, look for a PID file we wrote on the previous
//      spawn. If the process is still around, kill it — that's what
//      "sidecar reloads when the panel reloads" means in practice (Ctrl+R
//      in the CEP debug DevTools wipes module state, so we can't rely on
//      `spawnedPid` alone). Wait briefly for the port to free up.
//   2. If a sidecar we didn't spawn is now answering /health (user is
//      running a dev sidecar in a terminal), respect it and no-op.
//   3. Otherwise, resolve the sidecar directory by walking up from the
//      extension's real path (realpathSync — the extension is loaded via
//      symlink from Adobe's per-user CEP extensions folder).
//   4. Spawn `<python> -m app.main` detached, headless, write the pid to
//      our marker file. Try a Python on PATH first, fall back to known
//      install locations.
//   5. Poll /health up to ~15s waiting for it to come up.
//
// Cross-platform notes:
//   - Windows: pythonw.exe (no console window). Stop = taskkill /T /F because
//     uvicorn forks workers and Node's process.kill leaves children running.
//   - macOS:   python3. Spawned with `detached: true` Node sets the child as
//     a new process group leader; stop = kill(-pgid, SIGTERM) to take the
//     workers down with it.

const SIDECAR_URL = 'http://127.0.0.1:8765';
const IS_WIN = typeof process !== 'undefined' && process.platform === 'win32';

const PYTHON_CANDIDATES = IS_WIN
  ? [
      'pythonw',
      'C:\\Python310\\pythonw.exe',
      'C:\\Python311\\pythonw.exe',
      'C:\\Python312\\pythonw.exe',
    ]
  : [
      // macOS — order matters: PATH first, then Homebrew (Apple-silicon, Intel),
      // then Python.org framework installs, then system.
      'python3',
      '/opt/homebrew/bin/python3',
      '/usr/local/bin/python3',
      '/Library/Frameworks/Python.framework/Versions/3.12/bin/python3',
      '/Library/Frameworks/Python.framework/Versions/3.11/bin/python3',
      '/Library/Frameworks/Python.framework/Versions/3.10/bin/python3',
      '/usr/bin/python3',
    ];

// PID of the sidecar process WE spawned (null if /health was already alive
// after the pidfile-cleanup pass — in that case the sidecar is user-managed
// and we leave it alone on Pr quit). Tracked in module scope so
// stopSpawnedSidecar() can find it from the beforeunload /
// ApplicationBeforeQuit handlers in panel.js.
let spawnedPid = null;

// Marker file path: os.tmpdir() works on Win + macOS and survives Pr crashes
// (so the next panel mount still cleans up an orphan from a hard exit).
const PIDFILE = (() => {
  if (typeof require !== 'function') return null;
  try {
    const path = require('path');
    const os = require('os');
    return path.join(os.tmpdir(), 'phygital-sidecar.pid');
  } catch (_) { return null; }
})();

function readPidFile() {
  if (!PIDFILE || typeof require !== 'function') return null;
  try {
    const fs = require('fs');
    if (!fs.existsSync(PIDFILE)) return null;
    const n = parseInt(fs.readFileSync(PIDFILE, 'utf8').trim(), 10);
    return Number.isFinite(n) ? n : null;
  } catch (_) { return null; }
}

function writePidFile(pid) {
  if (!PIDFILE || typeof require !== 'function') return;
  try {
    const fs = require('fs');
    fs.writeFileSync(PIDFILE, String(pid), 'utf8');
  } catch (_) {}
}

function clearPidFile() {
  if (!PIDFILE || typeof require !== 'function') return;
  try {
    const fs = require('fs');
    if (fs.existsSync(PIDFILE)) fs.unlinkSync(PIDFILE);
  } catch (_) {}
}

// Проверяет, что pid принадлежит python-процессу (нашему sidecar'у).
// Нужно потому, что PID'ы переиспользуются: после краша Pr на диске остался
// pidfile со 124, через неделю 124 — это чей-то Chrome. Если просто
// taskkill'нуть его, юзер получит молчаливый закрытый браузер.
//
// Возвращает true только если процесс существует И его image — python*.
// Если что-то неясно (tasklist/ps упал, кодировка непонятна) — возвращаем
// false и НЕ убиваем; лучше оставить тёмный зомби-pidfile чем зашибить
// чужое приложение.
function _isOurSidecar(pid) {
  if (!pid || typeof require !== 'function') return false;
  try {
    const { execFileSync } = require('child_process');
    if (IS_WIN) {
      // tasklist печатает в CP866 на ru-RU локали — но image-имя ascii, так что
      // безопасно искать "python" подстрокой в utf-8/binary.
      const out = execFileSync(
        'tasklist',
        ['/FI', `PID eq ${pid}`, '/NH', '/FO', 'CSV'],
        { windowsHide: true, stdio: ['ignore', 'pipe', 'ignore'], timeout: 3000 },
      );
      // CSV format: "pythonw.exe","12345","Console","1","12,345 K"
      // Если PID отсутствует — tasklist печатает "INFO: No tasks are running..."
      const text = out.toString('binary').toLowerCase();
      if (text.includes('no tasks are running')) return false;
      return text.includes('python');
    } else {
      const out = execFileSync('ps', ['-p', String(pid), '-o', 'comm='], {
        stdio: ['ignore', 'pipe', 'ignore'], timeout: 3000,
      });
      const name = out.toString('utf8').trim().toLowerCase();
      // comm может быть "python3", "python3.11", "Python" (framework build), и т.п.
      return name.includes('python');
    }
  } catch (_) {
    // ps/tasklist not found, или process не существует, или timeout — считаем
    // что это не наш sidecar и кила не делаем.
    return false;
  }
}

function killPid(pid) {
  if (!pid || typeof require !== 'function') return;
  // Guard против PID-reuse: не убиваем процесс, который точно не наш.
  if (!_isOurSidecar(pid)) return;
  try {
    if (IS_WIN) {
      // /T = tree, /F = force. Required because uvicorn forks workers.
      const { execFileSync } = require('child_process');
      execFileSync('taskkill', ['/PID', String(pid), '/T', '/F'], {
        stdio: 'ignore',
        windowsHide: true,
      });
    } else {
      // detached:true made the child a process-group leader, so its pgid == pid.
      try { process.kill(-pid, 'SIGTERM'); }
      catch (_) { try { process.kill(pid, 'SIGTERM'); } catch (_) {} }
    }
  } catch (_) {
    // Already dead, or signal denied — nothing we can do from here.
  }
}

async function isAlive(timeoutMs = 1500) {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    const r = await fetch(SIDECAR_URL + '/health', { signal: ctrl.signal });
    clearTimeout(t);
    return r.ok;
  } catch (_) {
    return false;
  }
}

function resolveSidecarDir() {
  // CEP exposes Node.js as the standard `require`.
  if (typeof require !== 'function') return null;
  try {
    const path = require('path');
    const fs = require('fs');
    // CSInterface is loaded via <script> in index.html → global.
    const cs = new (globalThis.CSInterface || window.CSInterface)();
    const extDirRaw = cs.getSystemPath((globalThis.SystemPath || window.SystemPath).EXTENSION);
    // Walk through the symlink so we land on the real cep-premiere directory.
    const extDir = fs.realpathSync(extDirRaw);
    // sidecar/ is a sibling of cep-premiere/.
    return path.resolve(extDir, '..', 'sidecar');
  } catch (_) {
    return null;
  }
}

// Внутренний helper: пробует один candidate-интерпретатор и резолвится в
// child object при успехе (либо null при ENOENT / ошибке spawn'а).
//
// Раньше тут была баг (H6): child.once('error', () => failed = true) +
// сразу же `if (!failed)` — error-событие async, поэтому failed всегда
// false на момент проверки. ENOENT приходил уже после того как мы
// записали "успешный" pid в pidfile и вернули true. В итоге если py-
// интерпретатор отсутствовал, ensureSidecar 15с polling'a возвращал
// spawn-timeout, а на диске оставался pidfile с pid'ом несуществующего
// процесса (или, что хуже, с pid'ом случайного чужого процесса после
// pid-reuse).
//
// Теперь явно ждём 'spawn' либо 'error' (или таймаут 600мс) перед
// возвращением. 'spawn' event есть в Node.js 14.17+ — CEP NodeJS на
// поддерживаемых версиях Pr/AE подходит.
function _trySpawn(spawn, py, sidecarDir) {
  return new Promise((resolve) => {
    let child = null;
    let settled = false;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      resolve(result);
    };
    try {
      child = spawn(py, ['-m', 'app.main'], {
        cwd: sidecarDir,
        detached: true,    // new process group → we can kill the group on quit
        stdio: 'ignore',
        windowsHide: true, // no-op on macOS, hides console on Windows
      });
    } catch (_) {
      finish(null);
      return;
    }
    child.once('error', () => finish(null));
    child.once('spawn', () => {
      try { child.unref(); } catch (_) {}
      finish(child);
    });
    // Fallback таймаут — на случай если 'spawn' event не реализован.
    setTimeout(() => {
      if (settled) return;
      if (child && child.pid) {
        try { child.unref(); } catch (_) {}
        finish(child);
      } else {
        finish(null);
      }
    }, 600);
  });
}

async function spawnSidecarOnce(sidecarDir) {
  if (typeof require !== 'function') return false;
  const { spawn } = require('child_process');
  const path = require('path');
  const fs = require('fs');
  // Prefer the project-local venv if it exists (created by scripts/install_mac.sh
  // or `py -m venv .venv` on Windows). Falling back to system Python is only OK
  // for dev setups where deps were installed globally.
  const venvPy = IS_WIN
    ? path.join(sidecarDir, '.venv', 'Scripts', 'pythonw.exe')
    : path.join(sidecarDir, '.venv', 'bin', 'python3');
  const candidates = [venvPy, ...PYTHON_CANDIDATES];
  for (const py of candidates) {
    // Для абсолютных путей дешевле сначала проверить наличие, чем спавнить и
    // ловить ENOENT. Для `pythonw` / `python3` (PATH lookup) — спавним сразу.
    if (path.isAbsolute(py)) {
      let exists = false;
      try { exists = fs.existsSync(py); } catch (_) { exists = false; }
      if (!exists) continue;
    }
    const child = await _trySpawn(spawn, py, sidecarDir);
    if (child && child.pid) {
      spawnedPid = child.pid;
      writePidFile(child.pid);
      return true;
    }
  }
  return false;
}

// Kill the sidecar process tree if (and only if) we spawned it. Called from
// panel.js on beforeunload + CSXS ApplicationBeforeQuit.
export function stopSpawnedSidecar() {
  if (spawnedPid == null) return false;
  killPid(spawnedPid);
  clearPidFile();
  spawnedPid = null;
  return true;
}

export async function ensureSidecar({ pollTimeoutMs = 15000, pollIntervalMs = 500 } = {}) {
  // Step 1 — auto-reload semantics: kill any sidecar a previous panel mount
  // spawned, so the new code (incl. new routes / NODE_PARAM changes) actually
  // takes effect on Ctrl+R / panel close-reopen. Read pid from disk because
  // module-scope `spawnedPid` is lost across panel reloads.
  const prevPid = readPidFile();
  if (prevPid != null) {
    killPid(prevPid);
    clearPidFile();
    // Brief grace so the OS releases :8765 and uvicorn workers actually exit.
    await new Promise(r => setTimeout(r, 500));
  }

  // Step 2 — if /health is *still* answering after the cleanup pass, someone
  // else (user-run dev terminal) owns the sidecar. Respect it and don't spawn.
  if (await isAlive()) return { ok: true, spawned: false };

  // Step 3 — spawn fresh.
  const sidecarDir = resolveSidecarDir();
  if (!sidecarDir) return { ok: false, reason: 'cep-node-unavailable' };
  if (!(await spawnSidecarOnce(sidecarDir))) return { ok: false, reason: 'spawn-failed' };

  const deadline = Date.now() + pollTimeoutMs;
  while (Date.now() < deadline) {
    await new Promise(r => setTimeout(r, pollIntervalMs));
    if (await isAlive()) return { ok: true, spawned: true };
  }
  return { ok: false, reason: 'spawn-timeout' };
}
