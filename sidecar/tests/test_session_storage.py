"""Тесты secure session-store (H3, H12).

На Windows проверяем что DPAPI реально шифрует (на диске не plain JSON).
На POSIX — что mode 0o600. Везде — атомарность и migration с plain-JSON.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from app.services.session_storage import (
    _DPAPI_MAGIC,
    read_secure_json,
    write_secure_json,
)


# ── round-trip ───────────────────────────────────────────────────────────────


def test_write_then_read_roundtrip(tmp_path: Path):
    p = tmp_path / "session.json"
    payload = {"cookies": [{"name": "st-access-token", "value": "abc"}], "captured_at": "2026-05-23T00:00:00Z"}
    write_secure_json(p, payload)
    loaded = read_secure_json(p)
    assert loaded == payload


def test_read_returns_none_if_missing(tmp_path: Path):
    p = tmp_path / "missing.json"
    assert read_secure_json(p) is None


def test_read_returns_none_if_corrupt_plaintext(tmp_path: Path):
    p = tmp_path / "session.json"
    p.write_bytes(b"{not valid json")
    assert read_secure_json(p) is None


def test_read_can_migrate_old_plain_json(tmp_path: Path):
    """Старый код писал plain JSON. После S1.5 read должен прочитать старый
    файл (миграция случится на следующем save'е)."""
    p = tmp_path / "session.json"
    p.write_text(json.dumps({"cookies": [], "captured_at": "old"}), encoding="utf-8")
    loaded = read_secure_json(p)
    assert loaded == {"cookies": [], "captured_at": "old"}


def test_write_overwrites_existing(tmp_path: Path):
    p = tmp_path / "session.json"
    write_secure_json(p, {"a": 1})
    write_secure_json(p, {"a": 2})
    assert read_secure_json(p) == {"a": 2}


def test_write_creates_parent_dir(tmp_path: Path):
    p = tmp_path / "deep" / "nested" / "session.json"
    write_secure_json(p, {"k": "v"})
    assert p.exists()
    assert read_secure_json(p) == {"k": "v"}


def test_write_does_not_leave_tmp_files(tmp_path: Path):
    """tmp+os.replace должен убирать за собой tmp-файлы (H12)."""
    p = tmp_path / "session.json"
    write_secure_json(p, {"k": "v"})
    # Только сам session.json — никаких session.json.<random>.tmp.
    leftovers = [f for f in tmp_path.iterdir() if f.name != "session.json"]
    assert leftovers == [], f"unexpected tmp files: {leftovers}"


def test_write_handles_unicode(tmp_path: Path):
    p = tmp_path / "session.json"
    payload = {"name": "Глеб", "data": "日本語"}
    write_secure_json(p, payload)
    assert read_secure_json(p) == payload


def test_write_handles_empty_dict(tmp_path: Path):
    p = tmp_path / "session.json"
    write_secure_json(p, {})
    assert read_secure_json(p) == {}


# ── Windows DPAPI ────────────────────────────────────────────────────────────


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_windows_writes_encrypted_blob(tmp_path: Path):
    """На Windows файл должен начинаться с DPAPI-магии, не plain JSON."""
    p = tmp_path / "session.json"
    write_secure_json(p, {"cookies": [{"name": "secret", "value": "topsecret"}]})
    raw = p.read_bytes()
    assert raw.startswith(_DPAPI_MAGIC), "DPAPI magic header missing"
    # И на диске НЕ должно быть нашего секрета в открытую.
    assert b"topsecret" not in raw, "secret leaked to disk in plaintext!"


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_windows_encrypted_file_round_trips(tmp_path: Path):
    """Можем расшифровать собственный encrypted blob."""
    p = tmp_path / "session.json"
    payload = {"secret": "hunter2", "list": [1, 2, 3]}
    write_secure_json(p, payload)
    assert read_secure_json(p) == payload


# ── POSIX chmod 0o600 ────────────────────────────────────────────────────────


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only chmod check")
def test_posix_mode_is_0600(tmp_path: Path):
    p = tmp_path / "session.json"
    write_secure_json(p, {"k": "v"})
    mode = p.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"


# ── corrupted encrypted file ─────────────────────────────────────────────────


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_corrupted_dpapi_blob_returns_none(tmp_path: Path):
    """Битый DPAPI-блоб не должен крашить read'ер — возвращаем None."""
    p = tmp_path / "session.json"
    p.write_bytes(_DPAPI_MAGIC + b"garbage that wont decrypt")
    assert read_secure_json(p) is None


def test_dpapi_blob_on_non_windows_returns_none(tmp_path: Path, monkeypatch):
    """Если переслали DPAPI-файл с Win-машины на Mac — ошибка, не падение."""
    p = tmp_path / "session.json"
    p.write_bytes(_DPAPI_MAGIC + b"some-bytes")
    monkeypatch.setattr("app.services.session_storage._is_windows", lambda: False)
    assert read_secure_json(p) is None
