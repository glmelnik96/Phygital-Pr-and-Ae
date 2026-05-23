"""Cross-platform AppData resolver для Phygital Studio.

Win:   %LOCALAPPDATA%\\PhygitalStudio\\
Mac:   ~/Library/Application Support/PhygitalStudio/
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


def asset_cache_path() -> Path:
    """Файл-журнал asset cache (sha256 → file_obj_id mapping)."""
    return resolve_app_data() / "asset_cache.jsonl"


def asset_uploads_dir() -> Path:
    """Временные multipart-загрузки от CEP-панели (до отправки в Phygital+)."""
    return resolve_app_data() / "asset_uploads"


def sidecar_token_file() -> Path:
    """Per-install shared-secret для аутентификации CEP-панели → sidecar.

    Лежит в той же AppData, что и session.json (mode 0600 на POSIX). Любой
    локальный процесс, не имеющий прав на эту папку, не сможет прочитать токен
    и, соответственно, дёргать /jobs / /assets / /auth (cм. spec §11 — C5).
    """
    return resolve_app_data() / "sidecar.token"


def ensure_dirs() -> None:
    """Создать всю иерархию каталогов (идемпотентно)."""
    for d in (downloads_dir(), uploads_dir(), user_data_dir(), logs_dir(), asset_uploads_dir()):
        d.mkdir(parents=True, exist_ok=True)
