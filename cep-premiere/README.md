# Phygital Studio — Premiere Pro panel

Sub-project B of Phygital Adobe Studio. CEP panel that drives generation via
the local FastAPI sidecar.

The panel **auto-spawns the sidecar** the first time it boots (CEP Node.js is
enabled in `manifest.xml`). It also **kills the sidecar when Pr quits** so you
never have an orphan `python` listening on 8765 between sessions. No terminal
window is involved.

---

## Prerequisites — Windows

> Lessons baked in below: do **both** CSXS keys (11 + 12 — Pr 2024 uses 11, Pr
> 2025+ uses 12), Russian characters in the user-profile path work fine as long
> as the symlink target is absolute, and the panel **must be fully closed and
> reopened** after the symlink — CEP only scans extensions at process start.

### 1. Enable CEP debug mode

```powershell
reg add "HKCU\Software\Adobe\CSXS.11" /v PlayerDebugMode /t REG_SZ /d 1 /f
reg add "HKCU\Software\Adobe\CSXS.12" /v PlayerDebugMode /t REG_SZ /d 1 /f
```

HKCU only — no admin needed. Both keys because the CSXS host version differs
across Pr 2024 (CSXS.11) and Pr 2025+ (CSXS.12). If you skip one and Pr loads
the matching host, the panel just silently doesn't show up.

### 2. Symlink the panel into the per-user CEP extensions folder

```powershell
# admin PowerShell — needed for New-Item -ItemType SymbolicLink
mkdir "$env:APPDATA\Adobe\CEP\extensions" -Force
New-Item -ItemType SymbolicLink `
  -Path "$env:APPDATA\Adobe\CEP\extensions\com.phygital.studio.pr" `
  -Target "C:\Users\<user>\Documents\Phygital-Adobe-Studio\cep-premiere"
```

`autostart.js` resolves the sidecar directory via `fs.realpathSync()` so the
symlink works transparently — the sidecar `cwd` lands on the real repo folder,
not the symlink path.

### 3. Python 3.10+ on PATH

Sidecar dependencies live in `sidecar/pyproject.toml`. On a fresh Python 3.10
the manual install was:

```powershell
pip install loguru truststore pillow-heif playwright pydantic-settings python-ulid h2 fastapi uvicorn httpx
```

The autostarter tries `pythonw` on PATH first, then `C:\Python3{10,11,12}\pythonw.exe`
as fallbacks. `pythonw.exe` (no `w`-less `python.exe`) is intentional — it does
not pop a console window.

### 4. First-time sidecar setup

Run the Playwright recon flow once to capture a Phygital+ session:

```powershell
cd sidecar
python -m scripts.auth_recon
```

After this the session lives in `%LOCALAPPDATA%\PhygitalStudio\session.json`
and the panel will see `health.status === 'online'` immediately.

> **MSIX sandbox gotcha (Claude Code on Windows):** if you launch the sidecar
> from a Claude-managed terminal, Windows virtualizes `%LOCALAPPDATA%` into
> `…\Packages\Claude_<id>\LocalCache\…`. Your CEP panel (running in real Pr)
> can't see it. **Start the sidecar by hand or let the panel autostart do it.**

### 5. Restart Premiere

`Alt+F4` to fully exit, then reopen. **Window → Extensions → Phygital Studio**.

Sidecar will spawn automatically; the header pill turns green when /health
comes up (≤ 15 s).

---

## Prerequisites — macOS

> The panel + sidecar are cross-platform. Only the install ceremony changes.

### 1. Enable CEP debug mode

```bash
defaults write com.adobe.CSXS.11 PlayerDebugMode 1
defaults write com.adobe.CSXS.12 PlayerDebugMode 1
```

Same dual-key rationale as on Windows (Pr 2024 → CSXS.11; Pr 2025+ → CSXS.12).
Log out of Pr or restart the Mac for the defaults to take effect cleanly.

### 2. Symlink the panel

```bash
mkdir -p "$HOME/Library/Application Support/Adobe/CEP/extensions"
ln -s "$HOME/path/to/Phygital-Adobe-Studio/cep-premiere" \
      "$HOME/Library/Application Support/Adobe/CEP/extensions/com.phygital.studio.pr"
```

Apple-silicon Macs: nothing extra — Pr is universal, CEP runs in whatever
arch Pr is launched as.

### 3. Python 3.10+ on PATH

Homebrew is the common path:

```bash
brew install python@3.11
pip3 install loguru truststore pillow-heif playwright pydantic-settings python-ulid h2 fastapi uvicorn httpx
```

The autostarter tries `python3` on PATH first, then:
- `/opt/homebrew/bin/python3` (Apple silicon)
- `/usr/local/bin/python3` (Intel Homebrew)
- `/Library/Frameworks/Python.framework/Versions/3.{12,11,10}/bin/python3` (python.org)
- `/usr/bin/python3` (system; macOS ships 3.9 — avoid)

### 4. First-time sidecar setup

```bash
cd sidecar
python3 scripts/auth_recon.py
```

Session goes to `~/Library/Application Support/PhygitalStudio/session.json`.

> **Code-signing / TCC:** the first time `python3` is launched by Pr (as CEP's
> child process) macOS may prompt for *Files and Folders* access. Approve it —
> the sidecar needs to read frames extracted by Pr and write to
> `~/Library/Application Support/PhygitalStudio/`.

### 5. Restart Premiere

`Cmd+Q` to fully quit (not just close the window), then reopen.
**Window → Extensions → Phygital Studio**.

---

## How the autostart / shutdown works

1. `panel.js` calls `ensureSidecar()` (`client/lib/autostart.js`).
2. If `127.0.0.1:8765/health` already answers — no-op (someone started the
   sidecar manually; we leave it alone, including on shutdown).
3. Otherwise spawn `<python> -m app.main` from `<repo>/sidecar/` with
   `detached: true, stdio: 'ignore'` (`windowsHide: true` on Windows). The
   panel resolves the sidecar dir by `realpathSync`ing the symlinked
   extension dir and stepping up one level to the sibling `sidecar/` folder.
4. Poll `/health` for up to ~15 s. The header pill turns green when the
   sidecar comes up.

On Pr quit (`applicationBeforeQuit` CSXS event) **and** on panel reload
(`beforeunload`), `stopSpawnedSidecar()` fires:
- Windows: `taskkill /PID <pid> /T /F` (the `/T` is required — uvicorn forks
  workers and Node's `process.kill` leaves children running).
- macOS: `process.kill(-pgid, SIGTERM)` against the negative pgid (we spawned
  with `detached: true`, so the child is a process-group leader).

`stopSpawnedSidecar()` is a no-op if `/health` was already alive at boot — we
only ever kill what we started.

### Manual stop (if you ever need it)

Windows:
```powershell
Get-Process pythonw -ErrorAction SilentlyContinue | Stop-Process
```

macOS:
```bash
pkill -f "app.main"
```

---

## Unit tests

```bash
cd cep-premiere
npm install
npm test
```

Integration tests against a live sidecar are skipped by default. Enable with:
```bash
PHYGITAL_INTEGRATION=1 npm test
```

## Manual E2E checklist (spec §7.3)

1. Sidecar offline → header pill red → Generate disabled.
2. Sidecar online → pill green → form usable.
3. Nano Banana → Browse → pick image → wait upload → submit → completed →
   auto-import → Insert.
4. Kling start_prompt → pick from Pr timeline (video) → frame auto-extracted →
   submit → completed → Insert.
5. Re-pick same file → `cached` indicator visible.
6. Seedance with person face → expect content moderation fail → error in JobCard.
7. Reload panel → draft restored → running jobs continue polling.
8. Kill sidecar mid-run → red pill + toast → restart sidecar → green pill + resume.
9. Cost preview → click Estimate → see `~N credits`.
10. Quit Pr → verify no `pythonw` (Windows) / `python3 -m app.main` (macOS)
    is left running.

## Debug

`http://localhost:8099` → CEF DevTools. Console errors from `ensureSidecar()`
show up here; `child.once('error')` is silent by design so we can fall through
to the next Python candidate.

## File layout

See `docs/superpowers/specs/2026-05-21-pr-panel-design.md` §3.1.
