# Sidecar MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать локальный Python sidecar (FastAPI на 127.0.0.1:8765) для Phygital-Adobe-Studio sub-project A — image-only генерация через Phygital+ Nano Banana с persistence, recon-bootstrap и CLI-обёрткой.

**Architecture:** FastAPI + uvicorn (single worker). Vendor copy `Phygital-bot/client/` + `workflows/image_gen.py` через `scripts/sync_from_bot.py`. TaskRegistry в памяти + append-only `jobs.jsonl`. Concurrency через `asyncio.Semaphore(5)`. Auth bootstrap через Playwright headed.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, httpx (HTTP/2), truststore, pydantic-settings, playwright, loguru, pytest, pytest-asyncio.

**Project rule:** Никаких `git commit` шагов. В проекте Phygital-Adobe-Studio коммитим **только по явной просьбе пользователя** (см. `docs/HANDOFF.md`). Вместо commit — после каждой группы задач прогоняем `pytest -m "not live"` и убеждаемся что всё зелёное.

**Spec:** [`docs/superpowers/specs/2026-05-21-sidecar-mvp-design.md`](../specs/2026-05-21-sidecar-mvp-design.md)

---

## File Structure (что создаём/трогаем)

| Путь | Назначение |
|---|---|
| `sidecar/pyproject.toml` | **modify**: добавить deps |
| `sidecar/app/__init__.py` | exists, оставляем |
| `sidecar/app/main.py` | **modify**: FastAPI app + lifespan + uvicorn |
| `sidecar/app/config.py` | **create**: pydantic-settings |
| `sidecar/app/paths.py` | **create**: cross-platform AppData resolver |
| `sidecar/app/routers/__init__.py` | **create** |
| `sidecar/app/routers/health.py` | **create** |
| `sidecar/app/routers/auth.py` | **create** |
| `sidecar/app/routers/nodes.py` | **create** |
| `sidecar/app/routers/jobs.py` | **create** |
| `sidecar/app/services/__init__.py` | **create** |
| `sidecar/app/services/task_registry.py` | **create** |
| `sidecar/app/services/session_manager.py` | **create**: тонкая обёртка над vendored `refresh_session()` |
| `sidecar/app/services/session_bootstrap.py` | **create**: preflight + recon trigger |
| `sidecar/app/services/playwright_recon.py` | **create**: адаптация `Phygital-bot/recon/capture.py` для sidecar |
| `sidecar/app/services/downloader.py` | **create** |
| `sidecar/app/services/job_runner.py` | **create** |
| `sidecar/app/phygital_client/__init__.py` | **vendor** (содержит SOURCE_COMMIT) |
| `sidecar/app/phygital_client/api.py` | **vendor** from `Phygital-bot/client/api.py` |
| `sidecar/app/phygital_client/auth.py` | **vendor** from `Phygital-bot/client/auth.py` |
| `sidecar/app/phygital_client/session.py` | **vendor** from `Phygital-bot/client/session.py` |
| `sidecar/app/phygital_client/models.py` | **vendor** from `Phygital-bot/client/models.py` |
| `sidecar/app/workflows/__init__.py` | **create**: registry `NODES = {94: ImageGenWorkflow}` |
| `sidecar/app/workflows/base.py` | **vendor** from `Phygital-bot/workflows/base.py` |
| `sidecar/app/workflows/image_gen.py` | **vendor** from `Phygital-bot/workflows/image_gen.py` |
| `sidecar/scripts/__init__.py` | **create** |
| `sidecar/scripts/sync_from_bot.py` | **create**: ресинк vendor + rewriting imports |
| `sidecar/scripts/cli.py` | **create**: status/auth/nodes/generate/jobs |
| `sidecar/tests/__init__.py` | **create** |
| `sidecar/tests/conftest.py` | **create** |
| `sidecar/tests/test_paths.py` | **create** |
| `sidecar/tests/test_config.py` | **create** |
| `sidecar/tests/test_task_registry.py` | **create** |
| `sidecar/tests/test_downloader.py` | **create** |
| `sidecar/tests/test_job_runner.py` | **create** |
| `sidecar/tests/test_jobs_router.py` | **create** |
| `sidecar/tests/test_health_router.py` | **create** |
| `sidecar/tests/test_e2e_live.py` | **create** |
| `sidecar/.env.example` | **modify** |
| `sidecar/README.md` | **modify** |

---

## Group 1 — Foundation (Tasks 1–3)

### Task 1: pyproject.toml + package skeleton

**Files:**
- Modify: `sidecar/pyproject.toml`
- Create: `sidecar/app/routers/__init__.py`, `sidecar/app/services/__init__.py`, `sidecar/app/workflows/__init__.py`, `sidecar/scripts/__init__.py`, `sidecar/tests/__init__.py`

- [ ] **Step 1: Update pyproject.toml**

Replace `sidecar/pyproject.toml` with:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "phygital-studio-sidecar"
version = "0.0.1"
description = "Local FastAPI sidecar bridging Phygital+ API to Adobe CEP panels (Pr/AE)"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "httpx[http2]>=0.27",
  "truststore>=0.10",
  "loguru>=0.7",
  "Pillow>=11",
  "pillow-heif>=0.18",
  "playwright>=1.48",
  "python-multipart>=0.0.12",
  "pydantic>=2.9",
  "pydantic-settings>=2.5",
  "python-ulid>=3.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "pytest-cov>=5.0",
  "httpx>=0.27",
]

[project.scripts]
phygital-studio-sidecar = "app.main:run"

[tool.setuptools.packages.find]
where = ["."]
include = ["app*", "scripts*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
  "live: requires running sidecar and valid Phygital session (skipped in CI)",
]
testpaths = ["tests"]
```

- [ ] **Step 2: Create empty package __init__.py files**

Create five empty files:
- `sidecar/app/routers/__init__.py`
- `sidecar/app/services/__init__.py`
- `sidecar/app/workflows/__init__.py`
- `sidecar/scripts/__init__.py`
- `sidecar/tests/__init__.py`

Content of each: empty string (no docstring needed).

- [ ] **Step 3: Install dev environment**

Run from `sidecar/` directory:
```
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

Expected: успешная установка, `pip list` показывает fastapi, uvicorn, httpx, pytest.

- [ ] **Step 4: Smoke check imports**

Run:
```
.venv\Scripts\python -c "import fastapi, uvicorn, httpx, truststore, loguru, playwright, ulid; print('OK')"
```

Expected: `OK`. Если playwright не найден — это OK, мы установим browsers позже (Task 17).

---

### Task 2: `app/paths.py` (cross-platform AppData resolver)

**Files:**
- Create: `sidecar/app/paths.py`
- Create: `sidecar/tests/test_paths.py`

- [ ] **Step 1: Write failing test**

Create `sidecar/tests/test_paths.py`:

```python
"""Тесты cross-platform path resolver."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from app.paths import (
    APP_NAME,
    resolve_app_data,
    downloads_dir,
    uploads_dir,
    user_data_dir,
    logs_dir,
    session_file,
    jobs_jsonl,
    ensure_dirs,
)


def test_app_name_is_phygital_studio():
    assert APP_NAME == "PhygitalStudio"


@patch.dict(os.environ, {"LOCALAPPDATA": "C:/fake/LocalAppData"})
def test_resolve_app_data_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    p = resolve_app_data()
    assert p == Path("C:/fake/LocalAppData/PhygitalStudio")


def test_resolve_app_data_mac(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: Path("/Users/test"))
    p = resolve_app_data()
    assert p == Path("/Users/test/Library/Application Support/PhygitalStudio")


def test_resolve_app_data_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", lambda: Path("/home/test"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    p = resolve_app_data()
    assert p == Path("/home/test/.local/share/PhygitalStudio")


def test_subpaths_are_under_app_data(tmp_path, monkeypatch):
    monkeypatch.setattr("app.paths.resolve_app_data", lambda: tmp_path)
    assert downloads_dir() == tmp_path / "downloads"
    assert uploads_dir() == tmp_path / "uploads"
    assert user_data_dir() == tmp_path / "user_data"
    assert logs_dir() == tmp_path / "logs"
    assert session_file() == tmp_path / "session.json"
    assert jobs_jsonl() == tmp_path / "jobs.jsonl"


def test_ensure_dirs_creates_all(tmp_path, monkeypatch):
    monkeypatch.setattr("app.paths.resolve_app_data", lambda: tmp_path)
    ensure_dirs()
    assert (tmp_path / "downloads").is_dir()
    assert (tmp_path / "uploads").is_dir()
    assert (tmp_path / "user_data").is_dir()
    assert (tmp_path / "logs").is_dir()


def test_ensure_dirs_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr("app.paths.resolve_app_data", lambda: tmp_path)
    ensure_dirs()
    ensure_dirs()  # should not raise
    assert (tmp_path / "downloads").is_dir()
```

- [ ] **Step 2: Run test, expect failure**

Run from `sidecar/`:
```
.venv\Scripts\pytest tests/test_paths.py -v
```

Expected: ImportError на `from app.paths import ...` (модуля нет).

- [ ] **Step 3: Implement `app/paths.py`**

Create `sidecar/app/paths.py`:

```python
"""Cross-platform AppData resolver для Phygital Studio.

Win: %LOCALAPPDATA%\\PhygitalStudio\\
Mac: ~/Library/Application Support/PhygitalStudio/
Linux: $XDG_DATA_HOME/PhygitalStudio/ или ~/.local/share/PhygitalStudio/
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "PhygitalStudio"


def resolve_app_data() -> Path:
    """Корневая папка приложения для текущей OS."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    # linux / other
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def downloads_dir() -> Path:
    return resolve_app_data() / "downloads"


def uploads_dir() -> Path:
    return resolve_app_data() / "uploads"


def user_data_dir() -> Path:
    return resolve_app_data() / "user_data"


def logs_dir() -> Path:
    return resolve_app_data() / "logs"


def session_file() -> Path:
    return resolve_app_data() / "session.json"


def jobs_jsonl() -> Path:
    return resolve_app_data() / "jobs.jsonl"


def ensure_dirs() -> None:
    """Создать всю иерархию каталогов (идемпотентно)."""
    for d in (downloads_dir(), uploads_dir(), user_data_dir(), logs_dir()):
        d.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Run test, expect pass**

Run:
```
.venv\Scripts\pytest tests/test_paths.py -v
```

Expected: 7 passed.

---

### Task 3: `app/config.py` (Settings via pydantic-settings)

**Files:**
- Create: `sidecar/app/config.py`
- Create: `sidecar/tests/test_config.py`
- Modify: `sidecar/.env.example`

- [ ] **Step 1: Write failing test**

Create `sidecar/tests/test_config.py`:

```python
"""Тесты Settings."""
from __future__ import annotations

import pytest

from app.config import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.host == "127.0.0.1"
    assert s.port == 8765
    assert s.phygital_max_concurrent == 5
    assert s.log_level == "INFO"
    assert s.poll_interval_sec == 1.5
    assert s.jwt_min_ttl_sec == 900  # 15 min


def test_env_override(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "PHYGITAL_MAX_CONCURRENT=10\nLOG_LEVEL=DEBUG\nPORT=9000\n",
        encoding="utf-8",
    )
    s = Settings(_env_file=str(env_file))
    assert s.phygital_max_concurrent == 10
    assert s.log_level == "DEBUG"
    assert s.port == 9000


def test_env_var_override(monkeypatch):
    monkeypatch.setenv("PHYGITAL_MAX_CONCURRENT", "7")
    s = Settings(_env_file=None)
    assert s.phygital_max_concurrent == 7
```

- [ ] **Step 2: Run test, expect failure**

```
.venv\Scripts\pytest tests/test_config.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `app/config.py`**

Create `sidecar/app/config.py`:

```python
"""Sidecar settings via pydantic-settings + .env."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    host: str = "127.0.0.1"
    port: int = 8765

    phygital_max_concurrent: int = Field(5, ge=1, le=20)
    poll_interval_sec: float = 1.5
    jwt_min_ttl_sec: int = 900  # preflight refresh порог

    download_timeout_sec: float = 300.0
    download_retries: int = 3

    log_level: str = "INFO"
    log_rotation_mb: int = 10
    log_retain: int = 5
```

- [ ] **Step 4: Update `.env.example`**

Replace `sidecar/.env.example` with:

```
# Sidecar HTTP
HOST=127.0.0.1
PORT=8765

# Concurrency
PHYGITAL_MAX_CONCURRENT=5
POLL_INTERVAL_SEC=1.5

# Auth
JWT_MIN_TTL_SEC=900

# Downloader
DOWNLOAD_TIMEOUT_SEC=300
DOWNLOAD_RETRIES=3

# Logging
LOG_LEVEL=INFO
LOG_ROTATION_MB=10
LOG_RETAIN=5
```

- [ ] **Step 5: Run test, expect pass**

```
.venv\Scripts\pytest tests/test_config.py -v
```

Expected: 3 passed.

---

## Group 2 — Vendoring (Tasks 4–5)

### Task 4: `scripts/sync_from_bot.py` (vendor copy + import rewriting)

**Files:**
- Create: `sidecar/scripts/sync_from_bot.py`

- [ ] **Step 1: Implement sync script**

Create `sidecar/scripts/sync_from_bot.py`:

```python
"""Vendor copy с Phygital-bot.

Источник по умолчанию: C:/Users/<user>/Documents/Phygital-bot/
Переопределяется флагом --source.

Что копируется:
  client/{api,auth,session,models}.py  → app/phygital_client/
  workflows/{base,image_gen}.py         → app/workflows/

Что НЕ копируется:
  client/config.py                      — bot-specific (Telegram), у нас свой app/config.py
  workflows/*.py кроме перечисленных    — добавляются в sub-project D (video)

При копировании переписываются импорты:
  from client.X         → from app.phygital_client.X
  from workflows.X      → from app.workflows.X
  import client.X       → import app.phygital_client.X
  import workflows.X    → import app.workflows.X

В app/phygital_client/__init__.py записывается SOURCE_COMMIT (git rev-parse HEAD источника).
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


# Файлы для копирования: (rel_src, rel_dst)
FILES = [
    ("client/api.py",         "app/phygital_client/api.py"),
    ("client/auth.py",        "app/phygital_client/auth.py"),
    ("client/session.py",     "app/phygital_client/session.py"),
    ("client/models.py",      "app/phygital_client/models.py"),
    ("workflows/base.py",     "app/workflows/base.py"),
    ("workflows/image_gen.py", "app/workflows/image_gen.py"),
]

IMPORT_REWRITES = [
    (re.compile(r"^from client\."), "from app.phygital_client."),
    (re.compile(r"^from workflows\."), "from app.workflows."),
    (re.compile(r"^import client\."), "import app.phygital_client."),
    (re.compile(r"^import workflows\."), "import app.workflows."),
    # late imports
    (re.compile(r"(\s+)from client\."), r"\1from app.phygital_client."),
    (re.compile(r"(\s+)from workflows\."), r"\1from app.workflows."),
]


def rewrite_imports(text: str) -> str:
    out_lines = []
    for line in text.splitlines(keepends=True):
        for pat, repl in IMPORT_REWRITES:
            line = pat.sub(repl, line)
        out_lines.append(line)
    return "".join(out_lines)


def get_source_commit(source: Path) -> str:
    """git rev-parse HEAD источника. Если git недоступен — возвращает 'unknown'."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(source),
            stderr=subprocess.DEVNULL,
        )
        return out.decode("ascii").strip()
    except Exception:
        return "unknown"


def write_init(dst_root: Path, source: Path, commit: str) -> None:
    """app/phygital_client/__init__.py с SOURCE_COMMIT."""
    init_path = dst_root / "app" / "phygital_client" / "__init__.py"
    init_path.write_text(
        f'"""Vendor copy from Phygital-bot.\n\n'
        f'Source: {source.as_posix()}\n'
        f'Commit: {commit}\n'
        f'Sync: run `python -m scripts.sync_from_bot --apply` to refresh.\n'
        f'\n'
        f'Не редактируй вручную — изменения будут затёрты при следующем sync.\n'
        f'"""\n'
        f'SOURCE = "{source.as_posix()}"\n'
        f'SOURCE_COMMIT = "{commit}"\n',
        encoding="utf-8",
    )


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent  # sidecar/

    ap = argparse.ArgumentParser(description="Vendor copy Phygital-bot → sidecar.")
    ap.add_argument(
        "--source",
        type=Path,
        default=Path.home() / "Documents" / "Phygital-bot",
        help="Путь к Phygital-bot репозиторию",
    )
    ap.add_argument("--apply", action="store_true", help="Действительно скопировать (без флага — dry-run).")
    args = ap.parse_args()

    source: Path = args.source
    if not source.exists():
        sys.exit(f"FATAL: source not found: {source}")

    commit = get_source_commit(source)
    print(f"Source: {source}")
    print(f"Commit: {commit}")
    print(f"Mode:   {'APPLY' if args.apply else 'DRY-RUN'}")
    print()

    for rel_src, rel_dst in FILES:
        src = source / rel_src
        dst = repo_root / rel_dst
        if not src.exists():
            print(f"  SKIP  {rel_src} → {rel_dst}  (source missing)")
            continue

        text = src.read_text(encoding="utf-8")
        rewritten = rewrite_imports(text)

        n_changed = sum(1 for a, b in zip(text.splitlines(), rewritten.splitlines()) if a != b)

        print(f"  COPY  {rel_src} → {rel_dst}  ({n_changed} import lines rewritten)")

        if args.apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(rewritten, encoding="utf-8")

    if args.apply:
        write_init(repo_root, source, commit)
        print()
        print(f"  WROTE app/phygital_client/__init__.py with SOURCE_COMMIT={commit}")
        print()
        print("Done. Не забудь пройтись по diff и убедиться что импорты валидны:")
        print("  .venv\\Scripts\\python -c \"from app.phygital_client.api import PhygitalClient; from app.workflows.image_gen import ImageGenWorkflow; print('OK')\"")
    else:
        print()
        print("DRY-RUN — повтори с --apply чтобы реально скопировать.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Dry-run sync**

Run from `sidecar/`:
```
.venv\Scripts\python -m scripts.sync_from_bot
```

Expected: список из 6 файлов с пометкой "(N import lines rewritten)", в конце "DRY-RUN — повтори с --apply".

---

### Task 5: Execute vendor sync + verify imports

**Files:**
- Apply: `sidecar/scripts/sync_from_bot.py --apply`

- [ ] **Step 1: Apply sync**

```
.venv\Scripts\python -m scripts.sync_from_bot --apply
```

Expected: 6 файлов скопированы, написан `app/phygital_client/__init__.py` с SOURCE_COMMIT.

- [ ] **Step 2: Create `app/workflows/__init__.py` with registry**

Replace `sidecar/app/workflows/__init__.py`:

```python
"""Реестр доступных воркфлоу для sidecar.

Каждый workflow_class реализует Workflow (см. base.py) и имеет:
  WORKFLOW_SCHEMA_ID (int) — node_id в Phygital
  NODE_NAME (str)          — человекочитаемое имя

NODES — единый источник для GET /nodes и для POST /jobs (валидация node_id).
"""
from __future__ import annotations

from app.workflows.base import Workflow
from app.workflows.image_gen import ImageGenWorkflow

NODES: dict[int, type[Workflow]] = {
    94: ImageGenWorkflow,  # Nano Banana (Gemini Image API)
}

NODE_NAMES: dict[int, str] = {
    94: "Nano Banana",
}
```

- [ ] **Step 3: Verify imports**

```
.venv\Scripts\python -c "from app.phygital_client.api import PhygitalClient; from app.phygital_client.session import Session, SessionManager; from app.phygital_client.auth import refresh_session, RefreshError; from app.phygital_client.models import GenerationJob; from app.workflows.image_gen import ImageGenWorkflow, WORKFLOW_SCHEMA_ID; from app.workflows import NODES; print('OK', SOURCE_COMMIT := __import__('app.phygital_client', fromlist=['SOURCE_COMMIT']).SOURCE_COMMIT, NODES)"
```

Expected: `OK <commit-hash> {94: <class 'app.workflows.image_gen.ImageGenWorkflow'>}`.

Если падает на ImportError — посмотри какой импорт битый и поправь `IMPORT_REWRITES` в sync script, потом повтори с `--apply`.

- [ ] **Step 4: Run full test suite**

```
.venv\Scripts\pytest -m "not live" -v
```

Expected: всё что было (paths + config) зелёное; vendor код тестов сам не имеет, но и не должен падать на коллекции.

---

## Group 3 — Core Services (Tasks 6–11)

### Task 6: `app/services/task_registry.py` (in-memory + jsonl + ULID)

**Files:**
- Create: `sidecar/app/services/task_registry.py`
- Create: `sidecar/tests/test_task_registry.py`

- [ ] **Step 1: Write failing tests**

Create `sidecar/tests/test_task_registry.py`:

```python
"""Тесты TaskRegistry."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.services.task_registry import (
    JobState,
    TaskRegistry,
    JobStatus,
)


@pytest.fixture
def reg(tmp_path: Path) -> TaskRegistry:
    return TaskRegistry(jsonl_path=tmp_path / "jobs.jsonl")


async def test_create_assigns_ulid(reg: TaskRegistry):
    job_id = await reg.create(node_id=94, params={"prompt": "hi"})
    assert isinstance(job_id, str)
    assert len(job_id) == 26  # ULID

    state = reg.get(job_id)
    assert state.status == "queued"
    assert state.node_id == 94
    assert state.params == {"prompt": "hi"}
    assert state.error is None


async def test_create_persists_to_jsonl(reg: TaskRegistry, tmp_path: Path):
    job_id = await reg.create(node_id=94, params={"prompt": "hi"})
    jsonl = (tmp_path / "jobs.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(jsonl) == 1
    rec = json.loads(jsonl[0])
    assert rec["event"] == "created"
    assert rec["job_id"] == job_id
    assert rec["node_id"] == 94


async def test_update_status_appends_event(reg: TaskRegistry, tmp_path: Path):
    job_id = await reg.create(node_id=94, params={})
    await reg.update_status(job_id, status="submitted", task_id="phygital-abc")
    await reg.update_status(job_id, status="completed", result_paths=["/tmp/x.png"])

    state = reg.get(job_id)
    assert state.status == "completed"
    assert state.task_id == "phygital-abc"
    assert state.result_paths == ["/tmp/x.png"]

    jsonl = (tmp_path / "jobs.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(jsonl) == 3  # created + 2 updates


async def test_restore_replays_events(tmp_path: Path):
    jsonl = tmp_path / "jobs.jsonl"
    jsonl.write_text(
        json.dumps({"ts": "2026-05-21T10:00:00Z", "job_id": "01HX", "event": "created", "node_id": 94, "params": {}}) + "\n"
        + json.dumps({"ts": "2026-05-21T10:00:01Z", "job_id": "01HX", "event": "status", "status": "submitted", "task_id": "abc"}) + "\n"
        + json.dumps({"ts": "2026-05-21T10:00:02Z", "job_id": "01HX", "event": "status", "status": "completed", "result_paths": ["/tmp/x.png"]}) + "\n",
        encoding="utf-8",
    )
    reg = TaskRegistry(jsonl_path=jsonl)
    await reg.restore()

    state = reg.get("01HX")
    assert state.status == "completed"
    assert state.task_id == "abc"
    assert state.result_paths == ["/tmp/x.png"]


async def test_restore_marks_orphans_without_task_id(tmp_path: Path):
    jsonl = tmp_path / "jobs.jsonl"
    jsonl.write_text(
        json.dumps({"ts": "2026-05-21T10:00:00Z", "job_id": "01ORPH", "event": "created", "node_id": 94, "params": {}}) + "\n"
        # никакого status submit/task_id — sidecar упал между create и submit
        ,
        encoding="utf-8",
    )
    reg = TaskRegistry(jsonl_path=jsonl)
    await reg.restore()

    state = reg.get("01ORPH")
    assert state.status == "failed"
    assert state.error == "orphaned_on_restart"


async def test_restore_keeps_running_with_task_id(tmp_path: Path):
    jsonl = tmp_path / "jobs.jsonl"
    jsonl.write_text(
        json.dumps({"ts": "2026-05-21T10:00:00Z", "job_id": "01R", "event": "created", "node_id": 94, "params": {}}) + "\n"
        + json.dumps({"ts": "2026-05-21T10:00:01Z", "job_id": "01R", "event": "status", "status": "running", "task_id": "abc"}) + "\n",
        encoding="utf-8",
    )
    reg = TaskRegistry(jsonl_path=jsonl)
    await reg.restore()

    state = reg.get("01R")
    assert state.status == "running"  # будет resync через Phygital в job_runner
    assert state.task_id == "abc"


async def test_concurrent_create_unique_ids(reg: TaskRegistry):
    job_ids = await asyncio.gather(*[reg.create(node_id=94, params={}) for _ in range(50)])
    assert len(set(job_ids)) == 50


async def test_list_filter_by_status(reg: TaskRegistry):
    j1 = await reg.create(node_id=94, params={})
    j2 = await reg.create(node_id=94, params={})
    j3 = await reg.create(node_id=94, params={})
    await reg.update_status(j1, status="completed")
    await reg.update_status(j2, status="running")
    # j3 остаётся queued

    running = reg.list(status="running")
    assert {s.job_id for s in running} == {j2}
    completed = reg.list(status="completed")
    assert {s.job_id for s in completed} == {j1}
    all_jobs = reg.list()
    assert {s.job_id for s in all_jobs} == {j1, j2, j3}
```

- [ ] **Step 2: Run tests, expect failure**

```
.venv\Scripts\pytest tests/test_task_registry.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement TaskRegistry**

Create `sidecar/app/services/task_registry.py`:

```python
"""TaskRegistry: in-memory state + append-only jsonl журнал.

Статусы (см. ARCHITECTURE.md):
  queued | uploading | submitted | pending | running | downloading | completed | failed | canceled

Формат jsonl — одна строка на событие:
  {"ts":"...","job_id":"...","event":"created","node_id":N,"params":{...}}
  {"ts":"...","job_id":"...","event":"status","status":"...","task_id":"...","result_paths":[...],"error":"..."}
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from loguru import logger
from ulid import ULID


JobStatus = Literal[
    "queued", "uploading", "submitted", "pending",
    "running", "downloading", "completed", "failed", "canceled",
]

TERMINAL: set[str] = {"completed", "failed", "canceled"}


@dataclass
class JobState:
    job_id: str
    node_id: int
    params: dict[str, Any]
    status: JobStatus = "queued"
    task_id: str | None = None
    progress: float | None = None
    result_paths: list[str] = field(default_factory=list)
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TaskRegistry:
    """In-memory dict + append-only jsonl. Pre-thread-safety: один процесс, asyncio."""

    def __init__(self, jsonl_path: Path) -> None:
        self.jsonl_path = jsonl_path
        self._jobs: dict[str, JobState] = {}
        self._write_lock = asyncio.Lock()

    async def create(self, *, node_id: int, params: dict[str, Any]) -> str:
        job_id = str(ULID())
        state = JobState(job_id=job_id, node_id=node_id, params=params)
        self._jobs[job_id] = state
        await self._append(
            {"ts": _now_iso(), "job_id": job_id, "event": "created",
             "node_id": node_id, "params": params}
        )
        return job_id

    def get(self, job_id: str) -> JobState | None:
        return self._jobs.get(job_id)

    def list(self, *, status: str | None = None, limit: int | None = None) -> list[JobState]:
        items = list(self._jobs.values())
        if status:
            items = [s for s in items if s.status == status]
        items.sort(key=lambda s: s.created_at, reverse=True)
        if limit:
            items = items[:limit]
        return items

    async def update_status(
        self,
        job_id: str,
        *,
        status: JobStatus,
        task_id: str | None = None,
        progress: float | None = None,
        result_paths: list[str] | None = None,
        error: str | None = None,
    ) -> None:
        state = self._jobs.get(job_id)
        if state is None:
            logger.warning(f"update_status: unknown job_id={job_id}")
            return
        state.status = status
        if task_id is not None:
            state.task_id = task_id
        if progress is not None:
            state.progress = progress
        if result_paths is not None:
            state.result_paths = result_paths
        if error is not None:
            state.error = error
        state.updated_at = datetime.now(timezone.utc)

        rec: dict[str, Any] = {"ts": _now_iso(), "job_id": job_id, "event": "status", "status": status}
        if task_id is not None:
            rec["task_id"] = task_id
        if progress is not None:
            rec["progress"] = progress
        if result_paths is not None:
            rec["result_paths"] = result_paths
        if error is not None:
            rec["error"] = error
        await self._append(rec)

    async def restore(self) -> None:
        """Прочитать jsonl и схлопнуть события до текущего state."""
        if not self.jsonl_path.exists():
            return

        with self.jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.warning(f"restore: skip malformed line: {e}")
                    continue
                self._apply_event(rec)

        # Пометить orphans: jobs со status="queued"/"submitted"/"pending" без task_id
        # значит sidecar упал между create и получением task_id. Резюмировать нельзя.
        for state in self._jobs.values():
            if state.status in ("queued", "submitted", "pending") and not state.task_id:
                state.status = "failed"
                state.error = "orphaned_on_restart"
                # Записываем это как событие, чтобы при следующем restore был консистентный state
                await self._append(
                    {"ts": _now_iso(), "job_id": state.job_id, "event": "status",
                     "status": "failed", "error": "orphaned_on_restart"}
                )

        logger.info(f"TaskRegistry restored: {len(self._jobs)} jobs from {self.jsonl_path}")

    def _apply_event(self, rec: dict[str, Any]) -> None:
        job_id = rec.get("job_id")
        if not job_id:
            return
        event = rec.get("event")
        if event == "created":
            self._jobs[job_id] = JobState(
                job_id=job_id,
                node_id=rec.get("node_id", 0),
                params=rec.get("params", {}),
            )
        elif event == "status":
            state = self._jobs.get(job_id)
            if state is None:
                # status без created — игнорируем
                return
            state.status = rec.get("status", state.status)
            if "task_id" in rec:
                state.task_id = rec["task_id"]
            if "progress" in rec:
                state.progress = rec["progress"]
            if "result_paths" in rec:
                state.result_paths = rec["result_paths"]
            if "error" in rec:
                state.error = rec["error"]

    async def _append(self, rec: dict[str, Any]) -> None:
        async with self._write_lock:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with self.jsonl_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run tests, expect pass**

```
.venv\Scripts\pytest tests/test_task_registry.py -v
```

Expected: 8 passed.

---

### Task 7: `app/services/session_manager.py` (тонкая обёртка над vendored refresh)

**Files:**
- Create: `sidecar/app/services/session_manager.py`

- [ ] **Step 1: Implement (без тестов — wrapper'у с side-effect к диску тесты пишутся в Task 8 через session_bootstrap)**

Create `sidecar/app/services/session_manager.py`:

```python
"""Тонкая обёртка над vendored refresh_session(): убирает bot-specific
fallback `_find_fresher_recon_dump`, который смотрит в `Phygital-bot/recon/captures/`.

Sidecar не использует recon-fallback — если refresh не прошёл, мы поднимаем
auth_expired и панель показывает кнопку "войти ещё раз" (POST /auth/recon).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from app.phygital_client.auth import RefreshError, refresh_session
from app.phygital_client.session import Session


class SidecarSessionManager:
    """Совместим с интерфейсом PhygitalClient (нужен .refresh(session))."""

    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        self._refresh_lock = asyncio.Lock()

    def load(self) -> Session | None:
        if not self.storage_path.exists():
            logger.warning(f"Session file not found: {self.storage_path}")
            return None
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.error(f"Session file corrupted: {e}")
            return None
        s = Session(cookies=data.get("cookies", []))
        captured = data.get("captured_at")
        if captured:
            try:
                s.captured_at = datetime.fromisoformat(captured.replace("Z", "+00:00"))
            except Exception:
                pass
        if not s.access_token:
            logger.warning("Session loaded but st-access-token missing")
        return s

    def save(self, session: Session) -> None:
        session.captured_at = datetime.now(timezone.utc)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "cookies": session.cookies,
            "captured_at": session.captured_at.isoformat(),
        }
        self.storage_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"Session saved → {self.storage_path}")

    async def refresh(self, session: Session) -> Session:
        """Один refresh, под локом, без recon-fallback'а."""
        async with self._refresh_lock:
            try:
                await refresh_session(session)
            except RefreshError as e:
                logger.warning(f"refresh failed: {e}")
                raise
            self.save(session)
            return session
```

- [ ] **Step 2: Smoke-import**

```
.venv\Scripts\python -c "from app.services.session_manager import SidecarSessionManager; print('OK')"
```

Expected: `OK`.

---

### Task 8: `app/services/session_bootstrap.py` (preflight + lifecycle)

**Files:**
- Create: `sidecar/app/services/session_bootstrap.py`
- Create: `sidecar/tests/test_session_bootstrap.py`

- [ ] **Step 1: Write failing tests**

Create `sidecar/tests/test_session_bootstrap.py`:

```python
"""Тесты SessionBootstrap (без сети — мокаем refresh)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.services.session_bootstrap import SessionBootstrap
from app.phygital_client.session import Session


def _write_session_file(path: Path, *, access_token: str = "test.jwt.token") -> None:
    cookies = [
        {"name": "st-access-token", "value": access_token},
        {"name": "st-refresh-token", "value": "refresh"},
    ]
    path.write_text(
        json.dumps({"cookies": cookies, "captured_at": "2026-05-21T10:00:00+00:00"}),
        encoding="utf-8",
    )


async def test_no_session_file_returns_null(tmp_path: Path):
    bs = SessionBootstrap(session_file=tmp_path / "session.json", jwt_min_ttl_sec=900)
    info = await bs.preflight()
    assert info.session_age_sec is None
    assert info.jwt_ttl_sec is None
    assert info.ok is False


async def test_existing_session_with_valid_jwt(tmp_path: Path, monkeypatch):
    sf = tmp_path / "session.json"
    # JWT с exp в будущем — собираем фейковый
    import base64, json as _json, time
    payload = _json.dumps({"exp": int(time.time()) + 3600}).encode()
    payload_b64 = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
    fake_jwt = f"header.{payload_b64}.sig"
    _write_session_file(sf, access_token=fake_jwt)

    bs = SessionBootstrap(session_file=sf, jwt_min_ttl_sec=900)
    info = await bs.preflight()
    assert info.ok is True
    assert info.jwt_ttl_sec is not None and info.jwt_ttl_sec > 3000


async def test_short_ttl_triggers_refresh(tmp_path: Path):
    sf = tmp_path / "session.json"
    import base64, json as _json, time
    # JWT с exp через 5 минут — меньше jwt_min_ttl_sec=900s
    payload = _json.dumps({"exp": int(time.time()) + 300}).encode()
    payload_b64 = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
    fake_jwt = f"header.{payload_b64}.sig"
    _write_session_file(sf, access_token=fake_jwt)

    bs = SessionBootstrap(session_file=sf, jwt_min_ttl_sec=900)
    # Мокаем refresh, чтобы не ходить в сеть
    bs.manager.refresh = AsyncMock(side_effect=lambda s: s)
    info = await bs.preflight()
    bs.manager.refresh.assert_called_once()
```

- [ ] **Step 2: Run tests, expect failure**

```
.venv\Scripts\pytest tests/test_session_bootstrap.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement SessionBootstrap**

Create `sidecar/app/services/session_bootstrap.py`:

```python
"""SessionBootstrap: проверяет состояние сессии при старте sidecar.

На startup:
  - если session.json есть и JWT доживёт >= jwt_min_ttl_sec → ok
  - если есть но мало TTL → попробовать refresh
  - если нет файла → ok=False, ждём POST /auth/recon
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from app.phygital_client.auth import RefreshError
from app.services.session_manager import SidecarSessionManager


@dataclass
class SessionInfo:
    ok: bool
    session_age_sec: int | None
    jwt_ttl_sec: int | None


class SessionBootstrap:
    def __init__(self, session_file: Path, jwt_min_ttl_sec: int = 900) -> None:
        self.session_file = session_file
        self.jwt_min_ttl_sec = jwt_min_ttl_sec
        self.manager = SidecarSessionManager(storage_path=session_file)
        self.session = None  # type: ignore[assignment]

    async def preflight(self) -> SessionInfo:
        s = self.manager.load()
        if s is None:
            return SessionInfo(ok=False, session_age_sec=None, jwt_ttl_sec=None)

        self.session = s

        ttl = s.jwt_ttl_seconds()
        age = None
        if s.captured_at:
            age = int((datetime.now(timezone.utc) - s.captured_at).total_seconds())

        if ttl is None:
            logger.warning("Session loaded but JWT TTL not readable")
            return SessionInfo(ok=False, session_age_sec=age, jwt_ttl_sec=None)

        if ttl < self.jwt_min_ttl_sec:
            logger.info(f"JWT TTL={ttl}s < min={self.jwt_min_ttl_sec}s, refreshing...")
            try:
                await self.manager.refresh(s)
                ttl = s.jwt_ttl_seconds()
                logger.info(f"Refresh OK, new TTL={ttl}s")
            except RefreshError as e:
                logger.error(f"Preflight refresh failed: {e}")
                return SessionInfo(ok=False, session_age_sec=age, jwt_ttl_sec=ttl)

        return SessionInfo(ok=True, session_age_sec=age, jwt_ttl_sec=ttl)

    def info(self) -> SessionInfo:
        """Текущее состояние БЕЗ refresh (для GET /health)."""
        if self.session is None:
            s = self.manager.load()
            if s is None:
                return SessionInfo(ok=False, session_age_sec=None, jwt_ttl_sec=None)
            self.session = s
        s = self.session
        ttl = s.jwt_ttl_seconds()
        age = None
        if s.captured_at:
            age = int((datetime.now(timezone.utc) - s.captured_at).total_seconds())
        ok = ttl is not None and ttl > 0
        return SessionInfo(ok=ok, session_age_sec=age, jwt_ttl_sec=ttl)
```

- [ ] **Step 4: Run tests, expect pass**

```
.venv\Scripts\pytest tests/test_session_bootstrap.py -v
```

Expected: 3 passed.

---

### Task 9: `app/services/playwright_recon.py` (sidecar-friendly recon)

**Files:**
- Create: `sidecar/app/services/playwright_recon.py`

(Адаптация `Phygital-bot/recon/capture.py` для sidecar: вместо HAR/WS-логов и stdin Enter — просто открывает Chromium, ждёт пока пользователь залогинится, и сохраняет session.json при закрытии вкладки или таймауте.)

- [ ] **Step 1: Implement Playwright recon**

Create `sidecar/app/services/playwright_recon.py`:

```python
"""Playwright headed bootstrap для Phygital-сессии.

Триггерится из POST /auth/recon. Поведение:
  1. Запускает Chromium с persistent context в %LOCALAPPDATA%\\PhygitalStudio\\user_data\\
  2. Открывает https://app.phygital.plus/
  3. Ждёт пока юзер залогинится (детектится по наличию st-access-token cookie).
  4. Polling раз в 1с — как только cookie появилась, дампит session.json и закрывает браузер.
  5. Если за timeout_sec не залогинились — закрывает без save.

В отличие от Phygital-bot/recon/capture.py — никакого HAR/WS-логирования, никакого stdin.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from playwright.async_api import async_playwright

TARGET_URL = "https://app.phygital.plus/"
ACCESS_COOKIE = "st-access-token"
DEFAULT_TIMEOUT_SEC = 600  # 10 минут на логин


class ReconError(Exception):
    pass


async def run_recon(
    *,
    user_data_dir: Path,
    session_file: Path,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> None:
    """Запускает Chromium, ждёт логина, сохраняет session.json.

    Raises ReconError если за timeout пользователь не залогинился.
    """
    user_data_dir.mkdir(parents=True, exist_ok=True)
    session_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Recon: opening {TARGET_URL} (timeout {timeout_sec}s)")

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            viewport={"width": 1440, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )

        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(TARGET_URL, wait_until="domcontentloaded")

        deadline = asyncio.get_event_loop().time() + timeout_sec
        while asyncio.get_event_loop().time() < deadline:
            cookies = await context.cookies()
            access = next((c for c in cookies if c.get("name") == ACCESS_COOKIE), None)
            if access and access.get("value"):
                logger.info("Recon: detected st-access-token cookie, dumping session")
                _write_session_dump(session_file, cookies, page.url)
                await context.close()
                return
            await asyncio.sleep(1.0)

        await context.close()
        raise ReconError(f"Recon timeout after {timeout_sec}s — user did not log in")


def _write_session_dump(path: Path, cookies: list[dict], url: str) -> None:
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "cookies": cookies,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Session dumped → {path}")
```

- [ ] **Step 2: Install Playwright browser (одноразово)**

```
.venv\Scripts\playwright install chromium
```

Expected: Chromium скачан в `%LOCALAPPDATA%\ms-playwright\`.

Тестов нет — это headed Playwright, тестируется руками через `POST /auth/recon` (Task 13) / CLI (Task 19).

---

### Task 10: `app/services/downloader.py` (S3 → диск)

**Files:**
- Create: `sidecar/app/services/downloader.py`
- Create: `sidecar/tests/test_downloader.py`

- [ ] **Step 1: Write failing tests**

Create `sidecar/tests/test_downloader.py`:

```python
"""Тесты downloader (с моком httpx)."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.services.downloader import download_urls, DownloadError


async def test_download_single_url(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"hello-png-bytes", headers={"Content-Type": "image/png"})

    transport = httpx.MockTransport(handler)
    out_dir = tmp_path / "01HX"
    paths = await download_urls(
        urls=["https://example.com/img.png"],
        out_dir=out_dir,
        transport=transport,
    )
    assert len(paths) == 1
    assert paths[0].exists()
    assert paths[0].read_bytes() == b"hello-png-bytes"
    assert paths[0].parent == out_dir


async def test_download_multiple_urls(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        if "img1" in str(request.url):
            return httpx.Response(200, content=b"A", headers={"Content-Type": "image/png"})
        return httpx.Response(200, content=b"B", headers={"Content-Type": "image/png"})

    transport = httpx.MockTransport(handler)
    paths = await download_urls(
        urls=["https://x/img1.png", "https://x/img2.png"],
        out_dir=tmp_path / "01HX",
        transport=transport,
    )
    assert len(paths) == 2
    assert {p.read_bytes() for p in paths} == {b"A", b"B"}


async def test_download_retries_on_5xx(tmp_path: Path):
    attempts = {"n": 0}
    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, content=b"ok", headers={"Content-Type": "image/png"})

    transport = httpx.MockTransport(handler)
    paths = await download_urls(
        urls=["https://x/img.png"],
        out_dir=tmp_path / "01HX",
        transport=transport,
        retries=3,
        retry_delay=0.01,
    )
    assert len(paths) == 1
    assert attempts["n"] == 3


async def test_download_fails_after_max_retries(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    with pytest.raises(DownloadError):
        await download_urls(
            urls=["https://x/img.png"],
            out_dir=tmp_path / "01HX",
            transport=transport,
            retries=2,
            retry_delay=0.01,
        )


async def test_extension_from_url(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x", headers={"Content-Type": "video/mp4"})

    transport = httpx.MockTransport(handler)
    paths = await download_urls(
        urls=["https://x/clip.mp4?sig=abc"],
        out_dir=tmp_path / "01HX",
        transport=transport,
    )
    assert paths[0].suffix == ".mp4"
```

- [ ] **Step 2: Run tests, expect failure**

```
.venv\Scripts\pytest tests/test_downloader.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement downloader**

Create `sidecar/app/services/downloader.py`:

```python
"""Скачиватель URL'ов в локальный каталог.

S3 от Phygital периодически даёт 5xx — поэтому ретраим с backoff.
"""
from __future__ import annotations

import asyncio
import ssl
from pathlib import Path
from urllib.parse import urlparse

import httpx
import truststore
from loguru import logger


_SSL_CTX = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


class DownloadError(Exception):
    pass


# Расширения по content-type, как fallback если URL без явного suffix.
_EXT_BY_TYPE = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "application/octet-stream": ".bin",
}


def _ext_from_url(url: str) -> str | None:
    path = urlparse(url).path
    if "." in path.rsplit("/", 1)[-1]:
        return Path(path).suffix
    return None


def _ext_from_content_type(ct: str | None) -> str:
    if not ct:
        return ".bin"
    base = ct.split(";", 1)[0].strip().lower()
    return _EXT_BY_TYPE.get(base, ".bin")


async def download_urls(
    *,
    urls: list[str],
    out_dir: Path,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout: float = 300.0,
    retries: int = 3,
    retry_delay: float = 1.0,
) -> list[Path]:
    """Качает все URL в out_dir. Имена файлов — 0001.<ext>, 0002.<ext>, ...

    Returns: список путей сохранённых файлов.
    Raises: DownloadError если хотя бы один URL не скачался после retries.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    kwargs: dict = {"timeout": timeout, "verify": _SSL_CTX, "follow_redirects": True}
    if transport is not None:
        kwargs["transport"] = transport
        kwargs.pop("verify")  # MockTransport не использует verify

    results: list[Path] = []
    async with httpx.AsyncClient(**kwargs) as client:
        for idx, url in enumerate(urls, start=1):
            for attempt in range(1, retries + 1):
                try:
                    resp = await client.get(url)
                    if 500 <= resp.status_code < 600:
                        raise httpx.HTTPStatusError(
                            f"{resp.status_code} from {url}", request=resp.request, response=resp,
                        )
                    resp.raise_for_status()
                    ext = _ext_from_url(url) or _ext_from_content_type(resp.headers.get("Content-Type"))
                    name = f"{idx:04d}{ext}"
                    fpath = out_dir / name
                    fpath.write_bytes(resp.content)
                    results.append(fpath)
                    break  # success → next url
                except (httpx.HTTPStatusError, httpx.RequestError) as e:
                    if attempt >= retries:
                        raise DownloadError(f"Failed to download {url} after {retries} attempts: {e}") from e
                    delay = retry_delay * (2 ** (attempt - 1))
                    logger.warning(f"download {url}: attempt {attempt}/{retries} failed ({e}); sleep {delay:.1f}s")
                    await asyncio.sleep(delay)
    return results
```

- [ ] **Step 4: Run tests, expect pass**

```
.venv\Scripts\pytest tests/test_downloader.py -v
```

Expected: 5 passed.

---

### Task 11: `app/services/job_runner.py` (semaphore + workflow runner)

**Files:**
- Create: `sidecar/app/services/job_runner.py`
- Create: `sidecar/tests/test_job_runner.py`

- [ ] **Step 1: Write failing tests**

Create `sidecar/tests/test_job_runner.py`:

```python
"""Тесты JobRunner (с моком воркфлоу)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.phygital_client.models import GenerationJob
from app.services.job_runner import JobRunner
from app.services.task_registry import TaskRegistry


@pytest.fixture
def reg(tmp_path: Path) -> TaskRegistry:
    return TaskRegistry(jsonl_path=tmp_path / "jobs.jsonl")


async def test_run_completes_successfully(reg: TaskRegistry, tmp_path: Path, monkeypatch):
    job_id = await reg.create(node_id=94, params={"prompt": "hi"})

    fake_workflow = MagicMock()
    fake_workflow.run = AsyncMock(return_value=GenerationJob(
        job_id="phygital-task-123",
        status="completed",
        result_urls=["https://x/img.png"],
    ))
    fake_workflow_class = MagicMock(return_value=fake_workflow)

    fake_download = AsyncMock(return_value=[tmp_path / "01HX" / "0001.png"])

    runner = JobRunner(
        registry=reg,
        downloads_root=tmp_path,
        max_concurrent=2,
        nodes={94: fake_workflow_class},
        get_client=AsyncMock(return_value=MagicMock()),
        download_urls_fn=fake_download,
    )

    await runner.run_job(job_id)

    state = reg.get(job_id)
    assert state.status == "completed"
    assert state.task_id == "phygital-task-123"
    assert state.result_paths == [str(tmp_path / "01HX" / "0001.png")]


async def test_run_records_failure(reg: TaskRegistry, tmp_path: Path):
    job_id = await reg.create(node_id=94, params={"prompt": "hi"})

    fake_workflow = MagicMock()
    fake_workflow.run = AsyncMock(return_value=GenerationJob(
        job_id="t-1", status="failed", error="bad prompt",
    ))
    fake_workflow_class = MagicMock(return_value=fake_workflow)

    runner = JobRunner(
        registry=reg,
        downloads_root=tmp_path,
        max_concurrent=2,
        nodes={94: fake_workflow_class},
        get_client=AsyncMock(return_value=MagicMock()),
        download_urls_fn=AsyncMock(),
    )
    await runner.run_job(job_id)

    state = reg.get(job_id)
    assert state.status == "failed"
    assert state.error == "bad prompt"


async def test_run_records_unexpected_exception(reg: TaskRegistry, tmp_path: Path):
    job_id = await reg.create(node_id=94, params={"prompt": "hi"})

    fake_workflow = MagicMock()
    fake_workflow.run = AsyncMock(side_effect=RuntimeError("boom"))
    fake_workflow_class = MagicMock(return_value=fake_workflow)

    runner = JobRunner(
        registry=reg,
        downloads_root=tmp_path,
        max_concurrent=2,
        nodes={94: fake_workflow_class},
        get_client=AsyncMock(return_value=MagicMock()),
        download_urls_fn=AsyncMock(),
    )
    await runner.run_job(job_id)

    state = reg.get(job_id)
    assert state.status == "failed"
    assert "boom" in (state.error or "")


async def test_semaphore_limits_concurrency(reg: TaskRegistry, tmp_path: Path):
    started = []
    release_event = asyncio.Event()

    async def slow_run(**kwargs):
        started.append(1)
        await release_event.wait()
        return GenerationJob(job_id="t", status="completed", result_urls=[])

    fake_workflow = MagicMock()
    fake_workflow.run = slow_run
    fake_workflow_class = MagicMock(return_value=fake_workflow)

    runner = JobRunner(
        registry=reg,
        downloads_root=tmp_path,
        max_concurrent=2,
        nodes={94: fake_workflow_class},
        get_client=AsyncMock(return_value=MagicMock()),
        download_urls_fn=AsyncMock(return_value=[]),
    )

    j1 = await reg.create(node_id=94, params={})
    j2 = await reg.create(node_id=94, params={})
    j3 = await reg.create(node_id=94, params={})

    tasks = [
        asyncio.create_task(runner.run_job(j1)),
        asyncio.create_task(runner.run_job(j2)),
        asyncio.create_task(runner.run_job(j3)),
    ]
    await asyncio.sleep(0.05)
    assert len(started) == 2  # третья ждёт семафор

    release_event.set()
    await asyncio.gather(*tasks)
    assert len(started) == 3
```

- [ ] **Step 2: Run tests, expect failure**

```
.venv\Scripts\pytest tests/test_job_runner.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement JobRunner**

Create `sidecar/app/services/job_runner.py`:

```python
"""JobRunner: семафор + запуск workflow + download.

run_job(job_id) — единая точка для запуска уже зарегистрированной job.
schedule(job_id) — fire-and-forget asyncio.create_task(run_job(...)).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable

from loguru import logger

from app.phygital_client.models import GenerationJob
from app.services.task_registry import TaskRegistry


GetClient = Callable[[], Awaitable[Any]]  # → PhygitalClient async-context
DownloadUrlsFn = Callable[..., Awaitable[list[Path]]]


class JobRunner:
    def __init__(
        self,
        *,
        registry: TaskRegistry,
        downloads_root: Path,
        max_concurrent: int,
        nodes: dict[int, type],
        get_client: GetClient,
        download_urls_fn: DownloadUrlsFn,
        poll_interval: float = 1.5,
    ) -> None:
        self.registry = registry
        self.downloads_root = downloads_root
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.nodes = nodes
        self._get_client = get_client
        self._download_urls = download_urls_fn
        self.poll_interval = poll_interval
        self._active: dict[str, asyncio.Task] = {}

    def schedule(self, job_id: str) -> None:
        task = asyncio.create_task(self.run_job(job_id))
        self._active[job_id] = task
        task.add_done_callback(lambda _t: self._active.pop(job_id, None))

    async def run_job(self, job_id: str) -> None:
        state = self.registry.get(job_id)
        if state is None:
            logger.warning(f"run_job: unknown job_id={job_id}")
            return

        node_id = state.node_id
        workflow_class = self.nodes.get(node_id)
        if workflow_class is None:
            await self.registry.update_status(
                job_id, status="failed", error=f"unknown_node:{node_id}",
            )
            return

        async with self.semaphore:
            try:
                await self.registry.update_status(job_id, status="submitted")
                client = await self._get_client()
                workflow = workflow_class(client)
                await self.registry.update_status(job_id, status="running")
                gen_job: GenerationJob = await workflow.run(**state.params)

                if gen_job.status == "completed":
                    await self.registry.update_status(
                        job_id, status="downloading",
                        task_id=gen_job.job_id,
                    )
                    out_dir = self.downloads_root / job_id
                    paths = await self._download_urls(
                        urls=gen_job.result_urls,
                        out_dir=out_dir,
                    )
                    await self.registry.update_status(
                        job_id, status="completed",
                        task_id=gen_job.job_id,
                        result_paths=[str(p) for p in paths],
                    )
                else:
                    await self.registry.update_status(
                        job_id, status="failed",
                        task_id=gen_job.job_id,
                        error=gen_job.error or f"status={gen_job.status}",
                    )

            except Exception as e:
                logger.exception(f"run_job({job_id}) failed")
                await self.registry.update_status(
                    job_id, status="failed", error=f"{type(e).__name__}: {e}",
                )

    async def cancel_all(self) -> None:
        for job_id, task in list(self._active.items()):
            task.cancel()
            await self.registry.update_status(job_id, status="canceled", error="shutdown")
        self._active.clear()
```

- [ ] **Step 4: Run tests, expect pass**

```
.venv\Scripts\pytest tests/test_job_runner.py -v
```

Expected: 4 passed.

---

## Group 4 — HTTP Routers (Tasks 12–15)

### Task 12: `app/routers/health.py` + `app/main.py` (минимум для smoke)

**Files:**
- Create: `sidecar/app/routers/health.py`
- Modify: `sidecar/app/main.py`
- Create: `sidecar/tests/test_health_router.py`

- [ ] **Step 1: Write failing test**

Create `sidecar/tests/test_health_router.py`:

```python
"""Тест /health."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import build_app


def test_health_no_session(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.paths.resolve_app_data", lambda: tmp_path)
    app = build_app()
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True  # sidecar поднят
    assert body["session_age_sec"] is None
    assert body["jwt_ttl_sec"] is None
    assert body["active_jobs"] == 0
```

- [ ] **Step 2: Run test, expect failure**

```
.venv\Scripts\pytest tests/test_health_router.py -v
```

Expected: ImportError на `from app.main import build_app`.

- [ ] **Step 3: Implement health router**

Create `sidecar/app/routers/health.py`:

```python
"""GET /health."""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict:
    bs = request.app.state.session_bootstrap
    reg = request.app.state.task_registry

    info = bs.info()
    active = len([s for s in reg.list() if s.status in ("queued", "submitted", "running", "downloading", "uploading", "pending")])

    return {
        "ok": True,
        "session_age_sec": info.session_age_sec,
        "jwt_ttl_sec": info.jwt_ttl_sec,
        "active_jobs": active,
    }
```

- [ ] **Step 4: Implement minimal `app/main.py`**

Replace `sidecar/app/main.py`:

```python
"""Phygital Studio sidecar — FastAPI app + uvicorn entrypoint.

Состояние живёт в app.state:
  - settings: Settings
  - session_bootstrap: SessionBootstrap
  - task_registry: TaskRegistry
  - job_runner: JobRunner
  - get_client: фабрика PhygitalClient
"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from loguru import logger

from app import paths
from app.config import Settings


def build_app() -> FastAPI:
    """Build FastAPI app. Используется и в тестах, и в run()."""
    settings = Settings()
    paths.ensure_dirs()

    # Импорты ленивые, чтобы тесты paths могли мокать
    from app.routers.health import router as health_router
    from app.services.session_bootstrap import SessionBootstrap
    from app.services.task_registry import TaskRegistry

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Startup
        bs = SessionBootstrap(
            session_file=paths.session_file(),
            jwt_min_ttl_sec=settings.jwt_min_ttl_sec,
        )
        await bs.preflight()
        _app.state.session_bootstrap = bs

        reg = TaskRegistry(jsonl_path=paths.jobs_jsonl())
        await reg.restore()
        _app.state.task_registry = reg

        _app.state.settings = settings

        logger.info(f"Sidecar started: http://{settings.host}:{settings.port}")
        yield
        logger.info("Sidecar shutting down")

    app = FastAPI(title="Phygital Studio Sidecar", lifespan=lifespan)
    app.include_router(health_router)
    return app


def run() -> None:
    settings = Settings()
    _configure_logging(settings)
    uvicorn.run(
        "app.main:build_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_config=None,  # используем loguru
    )


def _configure_logging(settings: Settings) -> None:
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level, format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}")
    log_path = paths.logs_dir() / "sidecar.log"
    paths.logs_dir().mkdir(parents=True, exist_ok=True)
    logger.add(
        log_path,
        level=settings.log_level,
        rotation=f"{settings.log_rotation_mb} MB",
        retention=settings.log_retain,
        encoding="utf-8",
    )


if __name__ == "__main__":
    run()
```

- [ ] **Step 5: Run health test**

```
.venv\Scripts\pytest tests/test_health_router.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Manual smoke — поднять sidecar и curl /health**

В одном терминале:
```
.venv\Scripts\python -m app.main
```

В другом терминале:
```
curl http://127.0.0.1:8765/health
```

Expected JSON: `{"ok":true,"session_age_sec":null,"jwt_ttl_sec":null,"active_jobs":0}` (если ещё не было recon — session_age null).

Останови sidecar (Ctrl+C).

---

### Task 13: `app/routers/auth.py` (POST /auth/recon)

**Files:**
- Create: `sidecar/app/routers/auth.py`
- Modify: `sidecar/app/main.py` (include_router)

- [ ] **Step 1: Implement auth router**

Create `sidecar/app/routers/auth.py`:

```python
"""POST /auth/recon — запускает Playwright headed логин в фоне.

Защита от двойного вызова — флаг app.state.recon_in_progress.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from app import paths
from app.services.playwright_recon import run_recon, ReconError

router = APIRouter()


@router.post("/auth/recon")
async def start_recon(request: Request) -> dict:
    state = request.app.state
    if getattr(state, "recon_task", None) and not state.recon_task.done():
        raise HTTPException(status_code=409, detail={"error": "recon_in_progress"})

    async def _do() -> None:
        try:
            await run_recon(
                user_data_dir=paths.user_data_dir(),
                session_file=paths.session_file(),
                timeout_sec=600,
            )
            # После успешного recon — обновить state.session_bootstrap.session
            bs = state.session_bootstrap
            bs.session = None  # форсим перечитать
            bs.info()
            logger.info("Recon finished, session updated")
        except ReconError as e:
            logger.error(f"Recon failed: {e}")
        except Exception:
            logger.exception("Recon crashed")

    state.recon_task = asyncio.create_task(_do())
    return {"started": True, "hint": "poll GET /health until session_age_sec is set"}
```

- [ ] **Step 2: Wire into main.py**

В `sidecar/app/main.py` после `from app.routers.health import router as health_router` добавь:

```python
    from app.routers.auth import router as auth_router
```

После `app.include_router(health_router)` добавь:

```python
    app.include_router(auth_router)
```

- [ ] **Step 3: Smoke (только без выполнения recon)**

```
.venv\Scripts\python -c "from app.main import build_app; app = build_app(); print([r.path for r in app.routes])"
```

Expected: список включает `/health` и `/auth/recon`.

Реальный тест POST /auth/recon — в Task 19 (через CLI), там же откроется браузер.

---

### Task 14: `app/routers/nodes.py` (GET /nodes)

**Files:**
- Create: `sidecar/app/routers/nodes.py`
- Modify: `sidecar/app/main.py`

- [ ] **Step 1: Implement nodes router**

Create `sidecar/app/routers/nodes.py`:

```python
"""GET /nodes — список доступных нод."""
from __future__ import annotations

from fastapi import APIRouter

from app.workflows import NODES, NODE_NAMES

router = APIRouter()


@router.get("/nodes")
async def list_nodes() -> dict:
    nodes = []
    for node_id, workflow_class in NODES.items():
        nodes.append({
            "id": node_id,
            "name": NODE_NAMES.get(node_id, str(node_id)),
            "workflow_class": workflow_class.__name__,
            # TODO sub-project D: добавить inputs/params/averageTime/default_price
            # путём расширения Workflow ABC методом describe()
        })
    return {"nodes": nodes}
```

- [ ] **Step 2: Wire into main.py**

В `build_app()` добавь:
```python
    from app.routers.nodes import router as nodes_router
    # ...
    app.include_router(nodes_router)
```

- [ ] **Step 3: Smoke**

```
.venv\Scripts\python -m app.main
```

В другом терминале:
```
curl http://127.0.0.1:8765/nodes
```

Expected: `{"nodes":[{"id":94,"name":"Nano Banana","workflow_class":"ImageGenWorkflow"}]}`.

---

### Task 15: `app/routers/jobs.py` (POST /jobs + GET/DELETE/download)

**Files:**
- Create: `sidecar/app/routers/jobs.py`
- Create: `sidecar/tests/test_jobs_router.py`
- Modify: `sidecar/app/main.py` (wire job_runner + get_client factory)

- [ ] **Step 1: Write failing tests**

Create `sidecar/tests/test_jobs_router.py`:

```python
"""Тесты /jobs router."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import build_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.paths.resolve_app_data", lambda: tmp_path)
    app = build_app()
    # Замокаем job_runner.schedule, чтобы тесты не лазили в Playwright/Phygital
    with TestClient(app) as c:
        c.app.state.job_runner.schedule = MagicMock()
        yield c


def test_post_jobs_creates_with_known_node(client):
    r = client.post("/jobs", json={"node_id": 94, "params": {"prompt": "hi"}})
    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body and len(body["job_id"]) == 26
    client.app.state.job_runner.schedule.assert_called_once_with(body["job_id"])


def test_post_jobs_rejects_unknown_node(client):
    r = client.post("/jobs", json={"node_id": 999, "params": {}})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "unknown_node"


def test_get_jobs_returns_empty(client):
    r = client.get("/jobs")
    assert r.status_code == 200
    assert r.json() == {"jobs": []}


def test_get_jobs_after_create(client):
    client.post("/jobs", json={"node_id": 94, "params": {}})
    r = client.get("/jobs")
    assert r.status_code == 200
    jobs = r.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["node_id"] == 94
    assert jobs[0]["status"] == "queued"


def test_get_job_by_id(client):
    r = client.post("/jobs", json={"node_id": 94, "params": {}})
    job_id = r.json()["job_id"]
    r2 = client.get(f"/jobs/{job_id}")
    assert r2.status_code == 200
    assert r2.json()["job_id"] == job_id
    assert r2.json()["status"] == "queued"


def test_get_unknown_job_404(client):
    r = client.get("/jobs/01HXNOTEXIST")
    assert r.status_code == 404


def test_delete_job(client):
    r = client.post("/jobs", json={"node_id": 94, "params": {}})
    job_id = r.json()["job_id"]
    r2 = client.delete(f"/jobs/{job_id}")
    assert r2.status_code == 204
    state = client.app.state.task_registry.get(job_id)
    assert state.status == "canceled"


def test_download_404_if_not_completed(client):
    r = client.post("/jobs", json={"node_id": 94, "params": {}})
    job_id = r.json()["job_id"]
    r2 = client.get(f"/jobs/{job_id}/download")
    assert r2.status_code == 409
```

- [ ] **Step 2: Run tests, expect failure**

```
.venv\Scripts\pytest tests/test_jobs_router.py -v
```

Expected: либо ImportError, либо большинство FAIL (job_runner ещё не wired).

- [ ] **Step 3: Implement jobs router**

Create `sidecar/app/routers/jobs.py`:

```python
"""/jobs endpoints."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.task_registry import JobState
from app.workflows import NODES

router = APIRouter()


class JobCreate(BaseModel):
    node_id: int
    params: dict[str, Any] = Field(default_factory=dict)
    init_files: list[str] = Field(default_factory=list)  # для sub-project D


def _state_to_dict(s: JobState) -> dict:
    return {
        "job_id": s.job_id,
        "node_id": s.node_id,
        "status": s.status,
        "task_id": s.task_id,
        "progress": s.progress,
        "result_paths": s.result_paths,
        "error": s.error,
        "created_at": s.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": s.updated_at.isoformat().replace("+00:00", "Z"),
    }


@router.post("/jobs")
async def create_job(body: JobCreate, request: Request) -> dict:
    if body.node_id not in NODES:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown_node", "node_id": body.node_id},
        )
    # Опционально: проверка сессии. Можно вернуть 409 если нет сессии,
    # но многие panel могут submit'ить пока recon идёт — пусть try.
    reg = request.app.state.task_registry
    runner = request.app.state.job_runner
    job_id = await reg.create(node_id=body.node_id, params=body.params)
    runner.schedule(job_id)
    return {"job_id": job_id}


@router.get("/jobs")
async def list_jobs(request: Request, status: str | None = None, limit: int = 50) -> dict:
    reg = request.app.state.task_registry
    items = reg.list(status=status, limit=limit)
    return {"jobs": [_state_to_dict(s) for s in items]}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict:
    state = request.app.state.task_registry.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail={"error": "unknown_job", "job_id": job_id})
    return _state_to_dict(state)


@router.get("/jobs/{job_id}/download")
async def download_job(job_id: str, request: Request, index: int = 0):
    state = request.app.state.task_registry.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail={"error": "unknown_job"})
    if state.status != "completed" or not state.result_paths:
        raise HTTPException(status_code=409, detail={"error": "not_completed", "status": state.status})
    if index < 0 or index >= len(state.result_paths):
        raise HTTPException(status_code=400, detail={"error": "bad_index"})
    fpath = Path(state.result_paths[index])
    if not fpath.exists():
        raise HTTPException(status_code=410, detail={"error": "file_gone"})
    return FileResponse(fpath, filename=fpath.name)


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str, request: Request):
    reg = request.app.state.task_registry
    state = reg.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail={"error": "unknown_job"})
    await reg.update_status(job_id, status="canceled", error="user_canceled")
    # TODO sub-project D: реально дёрнуть Phygital cancel если task_id есть
    return Response(status_code=204)
```

- [ ] **Step 4: Wire job_runner + get_client в main.py**

В `sidecar/app/main.py` в `build_app()` после импорта роутеров добавь:

```python
    from app.routers.jobs import router as jobs_router
    from app.services.job_runner import JobRunner
    from app.services.downloader import download_urls
    from app.phygital_client.api import PhygitalClient
    from app.workflows import NODES
```

В `lifespan` после `_app.state.task_registry = reg` добавь:

```python
        async def _get_client():
            """Фабрика PhygitalClient с актуальной сессией.

            ВАЖНО: возвращает уже open'нутый async-context. Caller обязан
            закрыть через `async with`. JobRunner ожидает что workflow примет
            client и сам управляет lifecycle через `async with`.

            Для простоты MVP — возвращаем уже __aenter__'нутый клиент, а runner
            забудет про close (PhygitalClient внутри держит httpx.AsyncClient,
            который GC закроет; не идеально, но для MVP норм).
            TODO sub-project D: переписать на правильный async-context handoff.
            """
            if bs.session is None or not bs.session.access_token:
                raise RuntimeError("no_session")
            c = PhygitalClient(session=bs.session, session_manager=bs.manager)
            await c.__aenter__()
            return c

        runner = JobRunner(
            registry=reg,
            downloads_root=paths.downloads_dir(),
            max_concurrent=settings.phygital_max_concurrent,
            nodes=NODES,
            get_client=_get_client,
            download_urls_fn=download_urls,
            poll_interval=settings.poll_interval_sec,
        )
        _app.state.job_runner = runner
```

И добавь `app.include_router(jobs_router)` после других include_router.

- [ ] **Step 5: Run jobs router tests**

```
.venv\Scripts\pytest tests/test_jobs_router.py -v
```

Expected: 8 passed.

- [ ] **Step 6: Run full non-live suite**

```
.venv\Scripts\pytest -m "not live" -v
```

Expected: всё зелёное.

---

## Group 5 — CLI (Task 16)

### Task 16: `scripts/cli.py` (status/auth/nodes/generate/jobs)

**Files:**
- Create: `sidecar/scripts/cli.py`

- [ ] **Step 1: Implement CLI**

Create `sidecar/scripts/cli.py`:

```python
"""CLI обёртка над HTTP API sidecar.

Использование:
  python -m scripts.cli status
  python -m scripts.cli auth login
  python -m scripts.cli nodes
  python -m scripts.cli generate --node 94 --prompt "cat in a hat" --out ./out.png
  python -m scripts.cli jobs list
  python -m scripts.cli jobs cancel <job_id>

Все запросы идут на http://127.0.0.1:8765 (sidecar должен быть поднят
отдельно через `python -m app.main`).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import httpx

# Windows: stdout в utf-8, чтобы кириллица не падала в cp866 консоли
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8765"


async def cmd_status(_args) -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        r = await c.get("/health")
    if r.status_code != 200:
        print(f"sidecar not reachable: {r.status_code}")
        return 2
    h = r.json()
    print(f"sidecar OK    session_age={h['session_age_sec']}    jwt_ttl={h['jwt_ttl_sec']}    active_jobs={h['active_jobs']}")
    return 0


async def cmd_auth_login(_args) -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        r = await c.post("/auth/recon")
        if r.status_code == 409:
            print("recon already in progress — wait or restart sidecar")
            return 2
        if r.status_code != 200:
            print(f"recon trigger failed: {r.status_code} {r.text}")
            return 2
        print("Browser opened. Залогинься в Phygital+ — sidecar дождётся cookies автоматически.")
        print("Жду пока появится сессия...")
        for _ in range(600):  # 10 минут
            await asyncio.sleep(1.0)
            h = (await c.get("/health")).json()
            if h["session_age_sec"] is not None and h["jwt_ttl_sec"] and h["jwt_ttl_sec"] > 0:
                print(f"OK    session_age={h['session_age_sec']}    jwt_ttl={h['jwt_ttl_sec']}")
                return 0
        print("Timeout waiting for login")
        return 2


async def cmd_nodes(_args) -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        r = await c.get("/nodes")
    if r.status_code != 200:
        print(f"failed: {r.status_code}")
        return 2
    for n in r.json()["nodes"]:
        print(f"  {n['id']:>4}  {n['name']:<24} ({n['workflow_class']})")
    return 0


async def cmd_generate(args) -> int:
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        r = await c.post("/jobs", json={
            "node_id": args.node,
            "params": {"prompt": args.prompt},
        })
        if r.status_code != 200:
            print(f"submit failed: {r.status_code} {r.text}")
            return 2
        job_id = r.json()["job_id"]
        print(f"job_id={job_id}")

        last = None
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            await asyncio.sleep(1.5)
            j = (await c.get(f"/jobs/{job_id}")).json()
            if j["status"] != last:
                print(f"  [{j['status']}]")
                last = j["status"]
            if j["status"] in ("completed", "failed", "canceled"):
                break
        else:
            print(f"timeout after {args.timeout}s")
            return 2

        if j["status"] != "completed":
            print(f"failed: {j.get('error')}")
            return 2

        # Download first result
        d = await c.get(f"/jobs/{job_id}/download")
        if d.status_code != 200:
            print(f"download failed: {d.status_code}")
            return 2
        out_path.write_bytes(d.content)
        print(f"saved → {out_path}    ({len(d.content)} bytes)")
        return 0


async def cmd_jobs_list(args) -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        r = await c.get("/jobs", params={"limit": args.limit})
    if r.status_code != 200:
        print(f"failed: {r.status_code}")
        return 2
    for j in r.json()["jobs"]:
        print(f"  {j['job_id']}  node={j['node_id']}  status={j['status']:<11}  task={j['task_id'] or '-':<12}  {j['updated_at']}")
    return 0


async def cmd_jobs_cancel(args) -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        r = await c.delete(f"/jobs/{args.job_id}")
    if r.status_code == 204:
        print(f"canceled {args.job_id}")
        return 0
    print(f"failed: {r.status_code} {r.text}")
    return 2


def main() -> None:
    ap = argparse.ArgumentParser(prog="phygital-studio-cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status").set_defaults(fn=cmd_status)

    auth = sub.add_parser("auth").add_subparsers(dest="auth_cmd", required=True)
    auth.add_parser("login").set_defaults(fn=cmd_auth_login)

    sub.add_parser("nodes").set_defaults(fn=cmd_nodes)

    g = sub.add_parser("generate")
    g.add_argument("--node", type=int, required=True, help="node_id (например, 94 для Nano Banana)")
    g.add_argument("--prompt", type=str, required=True)
    g.add_argument("--out", type=str, default="./out.png")
    g.add_argument("--timeout", type=int, default=300, help="seconds")
    g.set_defaults(fn=cmd_generate)

    j = sub.add_parser("jobs").add_subparsers(dest="jobs_cmd", required=True)
    j_list = j.add_parser("list")
    j_list.add_argument("--limit", type=int, default=50)
    j_list.set_defaults(fn=cmd_jobs_list)
    j_cancel = j.add_parser("cancel")
    j_cancel.add_argument("job_id")
    j_cancel.set_defaults(fn=cmd_jobs_cancel)

    args = ap.parse_args()
    exit_code = asyncio.run(args.fn(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke — `status` без поднятого sidecar**

```
.venv\Scripts\python -m scripts.cli status
```

Expected: `sidecar not reachable: ...` или connection refused.

- [ ] **Step 3: Smoke — `status` с поднятым sidecar**

В одном терминале:
```
.venv\Scripts\python -m app.main
```

В другом:
```
.venv\Scripts\python -m scripts.cli status
.venv\Scripts\python -m scripts.cli nodes
```

Expected: status печатает `session_age=None jwt_ttl=None active_jobs=0`, nodes показывает `94  Nano Banana`.

Останови sidecar.

---

## Group 6 — E2E live test (Task 17)

### Task 17: `tests/test_e2e_live.py` + ручной прогон

**Files:**
- Create: `sidecar/tests/test_e2e_live.py`
- Create: `sidecar/tests/conftest.py`

- [ ] **Step 1: Implement conftest + live test**

Create `sidecar/tests/conftest.py`:

```python
"""Pytest config — общие фикстуры для всех тестов."""
import pytest

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
```

Create `sidecar/tests/test_e2e_live.py`:

```python
"""End-to-end live test.

ТРЕБОВАНИЯ ДЛЯ ЗАПУСКА:
  1. Sidecar поднят: `python -m app.main` в отдельном терминале.
  2. Валидная Phygital-сессия в %LOCALAPPDATA%\\PhygitalStudio\\session.json.
     (Получить через `python -m scripts.cli auth login` — откроет браузер.)

ЗАПУСК:
  pytest -m live tests/test_e2e_live.py -v -s

В CI пропускается — нужен живой Phygital backend.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

BASE = "http://127.0.0.1:8765"


@pytest.mark.live
async def test_image_gen_end_to_end():
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        # 1. health — есть сессия?
        h = (await c.get("/health")).json()
        assert h["ok"], "sidecar /health failed"
        assert h["session_age_sec"] is not None, "no Phygital session — run `cli auth login` first"
        assert h["jwt_ttl_sec"] and h["jwt_ttl_sec"] > 0, f"JWT expired (ttl={h['jwt_ttl_sec']})"

        # 2. nodes — Nano Banana доступна?
        nodes = (await c.get("/nodes")).json()["nodes"]
        assert any(n["id"] == 94 for n in nodes), "Nano Banana (94) not in /nodes"

        # 3. submit
        r = await c.post("/jobs", json={
            "node_id": 94,
            "params": {"prompt": "minimalist test image, single white circle on black background"},
        })
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]
        print(f"\n  job_id={job_id}")

        # 4. poll
        last = None
        for _ in range(80):  # ~120s
            await asyncio.sleep(1.5)
            j = (await c.get(f"/jobs/{job_id}")).json()
            if j["status"] != last:
                print(f"  [{j['status']}]")
                last = j["status"]
            if j["status"] in ("completed", "failed", "canceled"):
                break

        assert j["status"] == "completed", f"job ended with status={j['status']} error={j.get('error')}"
        assert j["result_paths"], "no result_paths"

        # 5. download
        d = await c.get(f"/jobs/{job_id}/download")
        assert d.status_code == 200, d.text
        assert d.headers["content-type"].startswith("image/"), d.headers["content-type"]
        assert len(d.content) > 10_000, f"image too small: {len(d.content)} bytes"
        print(f"  downloaded {len(d.content)} bytes, content-type={d.headers['content-type']}")
```

- [ ] **Step 2: USER GATE — нужен живой Phygital recon**

⚠️ **СТОП. Это первая точка, где нужно прямое вмешательство пользователя.**

Чтобы прогнать live-тест:
1. Запусти `python -m app.main` в одном терминале.
2. В другом — `python -m scripts.cli auth login`. Откроется Chromium, залогинься в Phygital+.
3. CLI напишет `OK session_age=... jwt_ttl=...`.
4. `python -m scripts.cli generate --node 94 --prompt "cat in a hat" --out ./out.png` — должно сгенерить картинку.
5. Если шаг 4 успешен — `pytest -m live tests/test_e2e_live.py -v -s`.

Если хоть один шаг падает — собрать логи sidecar (`%LOCALAPPDATA%\PhygitalStudio\logs\sidecar.log`) и обсудить.

- [ ] **Step 3: Run live test (после успешного manual smoke)**

```
.venv\Scripts\pytest -m live tests/test_e2e_live.py -v -s
```

Expected: 1 passed за ~30-60с (Nano Banana обычно отвечает за 20-40с).

---

## Group 7 — Docs (Task 18)

### Task 18: `sidecar/README.md`

**Files:**
- Modify: `sidecar/README.md`

- [ ] **Step 1: Write README**

Replace `sidecar/README.md`:

````markdown
# Phygital Studio — Sidecar

Локальный Python sidecar (FastAPI на `127.0.0.1:8765`), который мостит Phygital+ API в Adobe CEP-панели.

## Установка (Windows)

```cmd
cd sidecar
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
playwright install chromium
```

## Vendor sync

`app/phygital_client/` и `app/workflows/{base,image_gen}.py` — vendor copy от `Phygital-bot`. Никогда не редактируй вручную.

Ресинк:
```cmd
python -m scripts.sync_from_bot --apply
```

Текущий vendored commit — в `app/phygital_client/__init__.py` (`SOURCE_COMMIT`).

## Запуск

```cmd
python -m app.main
```

Sidecar поднимается на `http://127.0.0.1:8765`. Логи — stdout + `%LOCALAPPDATA%\PhygitalStudio\logs\sidecar.log`.

## CLI

```cmd
python -m scripts.cli status                              # GET /health
python -m scripts.cli auth login                          # POST /auth/recon → откроет браузер
python -m scripts.cli nodes                               # GET /nodes
python -m scripts.cli generate --node 94 --prompt "..." --out out.png
python -m scripts.cli jobs list
python -m scripts.cli jobs cancel <job_id>
```

## HTTP API

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/health` | — | `{ok, session_age_sec, jwt_ttl_sec, active_jobs}` |
| POST | `/auth/recon` | — | `{started: true}` или 409 `recon_in_progress` |
| GET | `/nodes` | — | `{nodes: [{id, name, workflow_class}]}` |
| POST | `/jobs` | `{node_id, params, init_files?}` | `{job_id}` |
| GET | `/jobs` | `?status=&limit=` | `{jobs: [...]}` |
| GET | `/jobs/{id}` | — | `{job_id, status, progress, result_paths, error, ...}` |
| GET | `/jobs/{id}/download` | `?index=0` | bytes |
| DELETE | `/jobs/{id}` | — | 204 |

## Тесты

```cmd
pytest -m "not live" -v          # юнит, в CI
pytest -m live -v -s             # требует sidecar + сессии
```

## Состояние на диске

Всё лежит в `%LOCALAPPDATA%\PhygitalStudio\` (Windows) или `~/Library/Application Support/PhygitalStudio/` (Mac).

| Файл | Что |
|---|---|
| `session.json` | Phygital cookies + JWT |
| `user_data/` | Playwright persistent profile |
| `downloads/<job_id>/` | Скачанные результаты |
| `uploads/<session_id>/` | (для sub-project D) загруженные init-картинки |
| `jobs.jsonl` | Append-only журнал статусов задач |
| `logs/sidecar.log` | Логи (ротируются 10MB × 5) |

## Архитектура и спек

- [`../docs/superpowers/specs/2026-05-21-sidecar-mvp-design.md`](../docs/superpowers/specs/2026-05-21-sidecar-mvp-design.md)
- [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)
- [`../docs/AUTH.md`](../docs/AUTH.md)
````

---

## Self-Review (после написания всего плана)

**Spec coverage:**
- Vendoring strategy → T4, T5 ✓
- jsonl persistence → T6 ✓
- Semaphore N=5 → T11 (через Settings → main wires) ✓
- 3 слоя приёмки → T6-15 (unit), T16 (CLI), T17 (live) ✓
- Все DoD из спека покрыты в Tasks 1-18 ✓

**Placeholder scan:**
- `# TODO sub-project D` в jobs router и main.py wire — это явно отложенный scope (init_files, real cancel), описание полное. OK.
- Никаких TBD / "implement later" без указания где это будет.

**Type consistency:**
- `JobStatus`, `JobState` определены в T6 и используются в T11, T15.
- `GenerationJob` импортируется из `app.phygital_client.models` в T11.
- `SidecarSessionManager`, `SessionBootstrap`, `SessionInfo` — корректно проброшены.
- `NODES` dict из `app/workflows/__init__.py` (T5) используется в T14, T15.

Всё консистентно.

---

## Что НЕ покрыто этим планом (явно out-of-scope, в следующих спеках)

- Init-files upload (`POST /jobs/{id}/upload`) — sub-project D
- Реальный cancel задачи в Phygital — sub-project D
- Video workflows (sora/veo/runway/kling) — sub-project D
- CEP-панели (Pr/AE) — sub-projects B/C
- Mac portability — sub-project F (sidecar уже использует pathlib + paths.py, должно "просто работать")

