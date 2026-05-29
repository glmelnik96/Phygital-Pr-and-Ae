"""Тесты /clip-video и /extract-frame — фокус на security (H1).

ffmpeg на CI обычно отсутствует, поэтому полный e2e (рендер реальный) живёт
в test_e2e_live.py. Здесь — только валидация input'а и формы ошибок.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import build_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.paths.resolve_app_data", lambda: tmp_path)
    app = build_app()
    with TestClient(app) as c:
        c.app.state.job_runner.schedule = MagicMock()
        yield c


# ── базовая валидация ───────────────────────────────────────────────────────


def test_clip_video_empty_source_path(client):
    r = client.post("/clip-video", json={"source_path": "", "in_sec": 0, "out_sec": 1})
    assert r.status_code == 400
    assert r.json()["detail"]["reason"] == "empty"


def test_clip_video_source_not_found(client, tmp_path):
    missing = tmp_path / "nope.mp4"
    r = client.post("/clip-video", json={
        "source_path": str(missing),
        "in_sec": 0, "out_sec": 1,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "source_not_found"


def test_extract_frame_empty_source_path(client):
    r = client.post("/extract-frame", json={"source_path": "", "at_sec": 0})
    assert r.status_code == 400


def test_extract_frame_negative_time(client, tmp_path):
    f = tmp_path / "video.mp4"
    f.write_bytes(b"fake")
    r = client.post("/extract-frame", json={"source_path": str(f), "at_sec": -1.0})
    assert r.status_code == 400


# ── H1: protocol injection ───────────────────────────────────────────────────


@pytest.mark.parametrize("evil_path", [
    "concat:/etc/passwd|/etc/shadow",
    "subfile:,start,123,end,456,:///etc/passwd",
    "crypto:/etc/passwd",
    "tcp://attacker.example.com:1234",
    "udp://239.0.0.1:5000",
    "hls://example.com/playlist.m3u8",
    "pipe:0",
    "data:image/png;base64,iVBOR",
])
def test_clip_video_rejects_protocol_prefix(client, evil_path):
    r = client.post("/clip-video", json={
        "source_path": evil_path,
        "in_sec": 0, "out_sec": 1,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["reason"] == "protocol_prefix_not_allowed"


@pytest.mark.parametrize("evil_path", [
    "concat:/etc/passwd|/etc/shadow",
    "tcp://attacker.example.com:1234",
    "pipe:0",
])
def test_extract_frame_rejects_protocol_prefix(client, evil_path):
    r = client.post("/extract-frame", json={
        "source_path": evil_path,
        "at_sec": 0,
    })
    assert r.status_code == 400


def test_mac_hfs_path_not_treated_as_protocol(client, tmp_path):
    """Mac HFS-form "Macintosh HD:Users:user:video.mov" — НЕ должно
    быть protocol_prefix_not_allowed. Раньше любой ':' в первом сегменте
    отбрасывался, ломая bin/timeline пик на части Mac-билдов Pr."""
    # На Win этот путь не существует, упадёт на source_not_found —
    # но не на protocol-check'е.
    r = client.post("/clip-video", json={
        "source_path": "Macintosh HD:Users:user:video.mov",
        "in_sec": 0, "out_sec": 1,
    })
    assert r.status_code == 400
    detail = r.json().get("detail", {})
    assert detail.get("reason") != "protocol_prefix_not_allowed", detail


def test_volume_with_space_not_treated_as_protocol(client):
    """External-volume HFS форма "External Drive:movies:clip.mp4"."""
    r = client.post("/clip-video", json={
        "source_path": "External Drive:movies:clip.mp4",
        "in_sec": 0, "out_sec": 1,
    })
    detail = r.json().get("detail", {})
    assert detail.get("reason") != "protocol_prefix_not_allowed", detail


def test_windows_drive_letter_not_treated_as_protocol(client, tmp_path):
    """C:\\Users\\... — НЕ должно быть protocol_prefix_not_allowed."""
    f = tmp_path / "video.mp4"
    f.write_bytes(b"fake")
    # Файл вполне может быть передан как "C:/...mp4" даже на Linux в тестах,
    # но _validate_media_source видит "C:" как drive-letter heuristic'ом и
    # отдаёт его дальше — упадёт уже на "не существует / not a regular file
    # / suffix not allowed" в реальном пути. Здесь проверяем что не на этапе
    # protocol-check'а.
    r = client.post("/clip-video", json={
        "source_path": str(f),
        "in_sec": 0, "out_sec": 1,
    })
    detail = r.json().get("detail", {})
    # допустимо: ffmpeg_missing (если нет ffmpeg) ИЛИ ffmpeg_failed —
    # главное, что НЕ "protocol_prefix_not_allowed".
    assert detail.get("reason") != "protocol_prefix_not_allowed"


# ── suffix whitelist ─────────────────────────────────────────────────────────


def test_clip_video_rejects_bad_suffix(client, tmp_path):
    bad = tmp_path / "secret.txt"
    bad.write_text("password", encoding="utf-8")
    r = client.post("/clip-video", json={
        "source_path": str(bad),
        "in_sec": 0, "out_sec": 1,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["reason"] == "suffix_not_allowed"


def test_extract_frame_rejects_executable_suffix(client, tmp_path):
    bad = tmp_path / "evil.sh"
    bad.write_text("#!/bin/sh\nrm -rf /", encoding="utf-8")
    r = client.post("/extract-frame", json={
        "source_path": str(bad),
        "at_sec": 0,
    })
    assert r.status_code == 400


def test_clip_video_accepts_mp4_extension(client, tmp_path, monkeypatch):
    """mp4 проходит валидацию (даже если ffmpeg падает на пустых байтах)."""
    f = tmp_path / "video.mp4"
    f.write_bytes(b"not really mp4")
    r = client.post("/clip-video", json={
        "source_path": str(f),
        "in_sec": 0, "out_sec": 1,
    })
    # 400 не должно возвращаться (на этапе валидации). Может быть 500
    # (ffmpeg_failed / ffmpeg_missing) — это уже про runtime, не про auth.
    assert r.status_code != 400, r.json()


# ── invalid range / not-a-file ────────────────────────────────────────────────


def test_clip_video_invalid_range(client, tmp_path):
    f = tmp_path / "video.mp4"
    f.write_bytes(b"fake")
    r = client.post("/clip-video", json={
        "source_path": str(f), "in_sec": 5.0, "out_sec": 1.0,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_range"


def test_clip_video_rejects_directory_as_source(client, tmp_path):
    d = tmp_path / "subdir"
    d.mkdir()
    r = client.post("/clip-video", json={
        "source_path": str(d), "in_sec": 0, "out_sec": 1,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["reason"] == "not_a_regular_file"
