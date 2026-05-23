"""Тесты /account/balance — балансовый эндпоинт-обёртка над Phygital+.

Лайфспан в build_app() сам ставит app.state.get_client = closure, поэтому
патчим уже после старта TestClient (внутри `with`).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import build_app


def _stub_client_with_credits(payload: dict):
    client = MagicMock()
    client.get_credits_info = AsyncMock(return_value=payload)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


def _make_app_and_client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.paths.resolve_app_data", lambda: tmp_path)
    return build_app()


def test_balance_returns_total_across_members(tmp_path: Path, monkeypatch):
    app = _make_app_and_client(tmp_path, monkeypatch)
    payload = {
        "members": [
            {"credits_balance": 100.5, "is_infinity": False,
             "expiration_date": "2026-06-19T07:59:24.819586+00:00",
             "user_name": "alice@example.com"},
            {"credits_balance": 50.0, "is_infinity": False,
             "expiration_date": None, "user_name": "bob@example.com"},
        ]
    }
    stub = _stub_client_with_credits(payload)

    with TestClient(app) as c:
        async def _get_client():
            return stub
        app.state.get_client = _get_client  # override the lifespan-installed factory
        r = c.get("/account/balance")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["balance"] == pytest.approx(150.5)
    assert body["is_infinity"] is False
    assert body["currency"] == "credits"
    assert body["user_name"] == "alice@example.com"
    assert body["expires_at"] == "2026-06-19T07:59:24.819586+00:00"


def test_balance_handles_empty_members(tmp_path: Path, monkeypatch):
    app = _make_app_and_client(tmp_path, monkeypatch)
    stub = _stub_client_with_credits({"members": []})

    with TestClient(app) as c:
        async def _get_client():
            return stub
        app.state.get_client = _get_client
        r = c.get("/account/balance")
    assert r.status_code == 200
    body = r.json()
    assert body["balance"] == 0.0
    assert body["user_name"] is None


def test_balance_propagates_infinity_flag(tmp_path: Path, monkeypatch):
    app = _make_app_and_client(tmp_path, monkeypatch)
    stub = _stub_client_with_credits({
        "members": [{"credits_balance": 0.0, "is_infinity": True, "user_name": "x"}]
    })

    with TestClient(app) as c:
        async def _get_client():
            return stub
        app.state.get_client = _get_client
        r = c.get("/account/balance")
    assert r.status_code == 200
    assert r.json()["is_infinity"] is True


def test_balance_503_when_no_session(tmp_path: Path, monkeypatch):
    """Без сессии get_client kicks RuntimeError('no_session') — должен прилетать 503."""
    app = _make_app_and_client(tmp_path, monkeypatch)

    with TestClient(app) as c:
        async def _get_client():
            raise RuntimeError("no_session")
        app.state.get_client = _get_client
        r = c.get("/account/balance")
    assert r.status_code == 503


def test_balance_502_on_phygital_error(tmp_path: Path, monkeypatch):
    app = _make_app_and_client(tmp_path, monkeypatch)
    client = MagicMock()
    client.get_credits_info = AsyncMock(side_effect=RuntimeError("upstream 500"))
    client.__aexit__ = AsyncMock(return_value=None)

    with TestClient(app) as c:
        async def _get_client():
            return client
        app.state.get_client = _get_client
        r = c.get("/account/balance")
    assert r.status_code == 502
    assert "phygital_error" in r.json()["detail"]


def test_balance_tolerates_non_numeric_credits(tmp_path: Path, monkeypatch):
    """Defensive: if Phygital ever returns null/None in credits_balance, ignore it."""
    app = _make_app_and_client(tmp_path, monkeypatch)
    stub = _stub_client_with_credits({
        "members": [
            {"credits_balance": None, "user_name": "alice"},
            {"credits_balance": "not a number", "user_name": "bob"},
            {"credits_balance": 42.0, "user_name": "carol"},
        ]
    })

    with TestClient(app) as c:
        async def _get_client():
            return stub
        app.state.get_client = _get_client
        r = c.get("/account/balance")
    assert r.status_code == 200
    assert r.json()["balance"] == pytest.approx(42.0)
