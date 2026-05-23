"""Тесты SidecarAuthMiddleware + load_or_create_token."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.sidecar_auth import (
    PUBLIC_PATHS,
    SidecarAuthMiddleware,
    TOKEN_HEADER,
    load_or_create_token,
)


# ── load_or_create_token ────────────────────────────────────────────────────


def test_creates_new_token_if_missing(tmp_path: Path):
    p = tmp_path / "sidecar.token"
    assert not p.exists()
    tok = load_or_create_token(p)
    assert tok
    assert len(tok) >= 16
    assert p.read_text(encoding="utf-8").strip() == tok


def test_reuses_existing_token(tmp_path: Path):
    p = tmp_path / "sidecar.token"
    p.write_text("AAAAAAAAAAAAAAAAAAAAAAAA", encoding="utf-8")  # 24 chars
    tok = load_or_create_token(p)
    assert tok == "AAAAAAAAAAAAAAAAAAAAAAAA"


def test_regenerates_if_too_short(tmp_path: Path):
    """Если файл существует, но контент слишком короткий (битый) — re-create."""
    p = tmp_path / "sidecar.token"
    p.write_text("short", encoding="utf-8")
    tok = load_or_create_token(p)
    assert len(tok) >= 16
    assert tok != "short"


def test_strips_whitespace(tmp_path: Path):
    p = tmp_path / "sidecar.token"
    p.write_text("  AAAAAAAAAAAAAAAAAAAAAAAAAAAA  \n", encoding="utf-8")
    tok = load_or_create_token(p)
    assert tok == "AAAAAAAAAAAAAAAAAAAAAAAAAAAA"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only chmod check")
def test_posix_mode_is_0600(tmp_path: Path):
    p = tmp_path / "sidecar.token"
    load_or_create_token(p)
    mode = p.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"


def test_creates_parent_directory(tmp_path: Path):
    p = tmp_path / "nested" / "deeper" / "sidecar.token"
    load_or_create_token(p)
    assert p.exists()


# ── SidecarAuthMiddleware ───────────────────────────────────────────────────


def _make_app(token: str) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SidecarAuthMiddleware, token=token)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/secret")
    def secret():
        return {"secret": "data"}

    @app.post("/echo")
    async def echo(payload: dict):
        return payload

    return app


def test_health_is_public_no_token_needed():
    app = _make_app("topsecret-token-of-no-importance")
    with TestClient(app) as c:
        r = c.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_protected_endpoint_rejects_missing_token():
    app = _make_app("topsecret-token-of-no-importance")
    with TestClient(app) as c:
        r = c.get("/secret")
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"


def test_protected_endpoint_rejects_wrong_token():
    app = _make_app("real-token")
    with TestClient(app) as c:
        r = c.get("/secret", headers={TOKEN_HEADER: "wrong-token"})
    assert r.status_code == 401


def test_protected_endpoint_accepts_correct_token():
    app = _make_app("real-token-xxxxxxxxxxxxxxx")
    with TestClient(app) as c:
        r = c.get("/secret", headers={TOKEN_HEADER: "real-token-xxxxxxxxxxxxxxx"})
    assert r.status_code == 200
    assert r.json() == {"secret": "data"}


def test_post_with_correct_token_passes_body():
    app = _make_app("real-token-xxxxxxxxxxxxxxx")
    with TestClient(app) as c:
        r = c.post(
            "/echo",
            json={"hello": "world"},
            headers={TOKEN_HEADER: "real-token-xxxxxxxxxxxxxxx"},
        )
    assert r.status_code == 200
    assert r.json() == {"hello": "world"}


def test_token_comparison_is_constant_time():
    """Sanity: middleware uses hmac.compare_digest, not == (timing attack
    mitigation). Smoke test: ровно-длинные строки разной семантики оба
    отбиваются с 401."""
    app = _make_app("0" * 32)
    with TestClient(app) as c:
        r1 = c.get("/secret", headers={TOKEN_HEADER: "0" * 31 + "1"})
        r2 = c.get("/secret", headers={TOKEN_HEADER: "1" * 32})
    assert r1.status_code == 401
    assert r2.status_code == 401


def test_empty_token_constructor_fails():
    app = FastAPI()
    with pytest.raises(ValueError):
        SidecarAuthMiddleware(app, token="")


def test_public_paths_default_contains_health():
    assert "/health" in PUBLIC_PATHS


# ── integration: full build_app ──────────────────────────────────────────────


def test_build_app_protected_endpoint_returns_401_without_token(tmp_path: Path, monkeypatch):
    """Sanity: реальный build_app() ставит middleware, /jobs закрыто без токена."""
    monkeypatch.setattr("app.paths.resolve_app_data", lambda: tmp_path)
    from app.main import build_app

    app = build_app()
    # Используем TestClient напрямую (без autouse-fixture, который выставляет
    # токен в заголовке). Конструктор без `with` не запускает lifespan, но
    # middleware всё равно регистрируется в build_app, так что 401 срабатывает.
    with TestClient(app) as c:
        # Снимаем дефолтный токен который autouse-fixture впихнул.
        c.headers.pop(TOKEN_HEADER, None)
        c.headers.pop("X-Phygital-Sidecar-Token", None)
        r = c.get("/jobs")
    assert r.status_code == 401


def test_build_app_health_endpoint_accessible_without_token(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.paths.resolve_app_data", lambda: tmp_path)
    from app.main import build_app

    app = build_app()
    with TestClient(app) as c:
        c.headers.pop(TOKEN_HEADER, None)
        c.headers.pop("X-Phygital-Sidecar-Token", None)
        r = c.get("/health")
    assert r.status_code == 200


# ── _assert_loopback_host ────────────────────────────────────────────────────


def test_refuses_non_loopback_host(tmp_path: Path, monkeypatch):
    """H2: HOST=0.0.0.0 → RuntimeError на старте.

    Settings берёт env-переменные по имени поля (case-insensitive,
    без префикса) — см. app/config.py. То есть PHYGITAL_HOST не работает,
    но это и хорошо: меньше шанса случайно выставить.
    """
    monkeypatch.setattr("app.paths.resolve_app_data", lambda: tmp_path)
    monkeypatch.setenv("HOST", "0.0.0.0")
    from app.main import build_app

    with pytest.raises(RuntimeError, match="loopback"):
        build_app()


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_allows_loopback_hosts(tmp_path: Path, monkeypatch, host: str):
    monkeypatch.setattr("app.paths.resolve_app_data", lambda: tmp_path)
    monkeypatch.setenv("HOST", host)
    from app.main import build_app

    app = build_app()  # не должно бросить
    assert app is not None
