"""Шифрованное persisting'ение session.json (H3, H12).

Phygital-cookies (st-access-token / st-refresh-token) — это bearer-credentials
к платным API. До этого они лежали plain-text в %LOCALAPPDATA%\\PhygitalStudio
\\session.json и любой процесс под нашим юзером (включая malware, любую
extension в браузере, любой инструмент с локальным доступом) мог их прочитать
без какого-либо барьера.

Что делаем:
- На Windows: оборачиваем payload через Data Protection API (DPAPI,
  CryptProtectData с user-scope). Расшифровать может только текущий
  Windows-юзер на этой машине. Без зависимостей (ctypes из stdlib).
- На POSIX (Mac/Linux): plain JSON + chmod 0o600. Полноценный Keychain
  опускаем для V1 — на single-user-машине это уже даёт барьер от чужого
  процесса без root. Поверх можно прикрутить `keyring` в V2 при необходимости.

Все записи атомарные через tmp + os.replace (H12). Это значит что upgrade,
crash или kill -9 посреди save'а не оставит половинный JSON, который при
следующей загрузке прокинется как «corrupted session» и заставит юзера
заново логиниться.

Формат файла:
- Windows: префикс `DPAPI1\\n` + бинарный blob от CryptProtectData
- POSIX: обычный JSON (читается старым кодом — migration-friendly)

При чтении формат детектится по магическому префиксу. Старые plain-JSON
session.json читаются и на Windows (миграция произойдёт на ближайшем save'е).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

# Магия в первых байтах файла → отличает encrypted blob от plain JSON.
# Версионируется (DPAPI1 → DPAPI2…) — если поменяется формат внутри.
_DPAPI_MAGIC = b"DPAPI1\n"


def _is_windows() -> bool:
    return sys.platform == "win32"


def _dpapi_encrypt(data: bytes) -> bytes:
    """Win32 CryptProtectData (user-scope). Бросает OSError при сбое."""
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    ok = crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        None,   # description
        None,   # entropy
        None,   # reserved
        None,   # prompt struct
        0,      # flags
        ctypes.byref(blob_out),
    )
    if not ok:
        err = ctypes.get_last_error()
        raise OSError(f"CryptProtectData failed: WinError {err}")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _dpapi_decrypt(blob: bytes) -> bytes:
    """Win32 CryptUnprotectData. Бросает OSError при сбое."""
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    buf = ctypes.create_string_buffer(blob, len(blob))
    blob_in = DATA_BLOB(len(blob), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    )
    if not ok:
        err = ctypes.get_last_error()
        raise OSError(f"CryptUnprotectData failed: WinError {err}")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def write_secure_json(path: Path, payload: dict[str, Any]) -> None:
    """Атомарно сохранить payload в path.

    На Windows шифрует через DPAPI; на POSIX оставляет plain JSON + chmod
    0o600. Запись всегда через tmp + os.replace, чтобы убитый процесс
    не оставил пол-файла (H12).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")

    if _is_windows():
        try:
            encrypted = _dpapi_encrypt(data)
            out_bytes = _DPAPI_MAGIC + encrypted
        except OSError as e:
            # На Windows DPAPI должен работать всегда; если нет — деградируем
            # до plain JSON, но громко жалуемся в лог.
            logger.warning(f"DPAPI encrypt failed ({e}); falling back to plaintext for {path}")
            out_bytes = data
    else:
        out_bytes = data

    # mkstemp в той же директории = os.replace будет атомарным rename'ом.
    tmp_fd, tmp_str = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_str)
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(out_bytes)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # Некоторые ФС (tmpfs в тестах) не поддерживают fsync. Не валим
                # сохранение из-за этого.
                pass
        if not _is_windows():
            try:
                os.chmod(tmp_path, 0o600)
            except OSError as e:
                logger.warning(f"chmod 0o600 failed for {tmp_path}: {e}")
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def read_secure_json(path: Path) -> dict[str, Any] | None:
    """Прочитать payload (расшифровывая при необходимости).

    None если файла нет, файл битый или decrypt не удался. Возвращённый
    словарь идентичен тому, что было передано в write_secure_json.
    """
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
    except OSError as e:
        logger.error(f"Cannot read session file {path}: {e}")
        return None

    if raw.startswith(_DPAPI_MAGIC):
        if not _is_windows():
            logger.error(
                f"Encrypted (DPAPI) session file found on non-Windows platform: {path}. "
                "Скорее всего файл скопирован с Windows-машины; нужен новый логин."
            )
            return None
        try:
            data = _dpapi_decrypt(raw[len(_DPAPI_MAGIC):])
        except OSError as e:
            logger.error(f"DPAPI decrypt failed for {path}: {e}")
            return None
    else:
        data = raw

    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.error(f"Session file corrupted: {e}")
        return None
