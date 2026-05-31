"""Тесты POST /enhance — контракт + edge-cases.

Реальный Phygital-вызов мокаем через EnhancerService: ставим заглушку на
`app.routers.enhance.EnhancerService`, чтобы не дергать сеть/Playwright.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import build_app
from app.services.enhancer import EnhancerError


class _FakeEnhanceResult:
    def __init__(self, text: str, node_id: int, filename: str):
        self.enhanced_prompt = text
        self.target_node_id = node_id
        self.system_prompt_file = filename


def _fake_client_factory():
    """get_client возвращает open'нутый клиент с __aexit__ заглушкой."""
    fake_client = AsyncMock()
    fake_client.__aexit__ = AsyncMock(return_value=None)

    async def _gc():
        return fake_client

    return _gc, fake_client


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.paths.resolve_app_data", lambda: tmp_path)
    app = build_app()
    with TestClient(app) as c:
        # job_runner.schedule стабим (если /enhance случайно его дёрнет —
        # тест упадёт явно, без сетевых сайд-эффектов).
        c.app.state.job_runner.schedule = MagicMock()
        # Подменяем get_client на fake — Phygital не вызываем.
        gc, _ = _fake_client_factory()
        c.app.state.get_client = gc
        yield c


# ─── 1. Валидация запроса ──────────────────────────────────────────────────

def test_enhance_requires_prompt(client):
    r = client.post("/enhance", json={"node_id": 94, "prompt": ""})
    # pydantic: prompt min_length=1 → 422
    assert r.status_code == 422


def test_enhance_requires_node_id(client):
    r = client.post("/enhance", json={"prompt": "hello"})
    assert r.status_code == 422


def test_enhance_rejects_mismatched_init_img_lengths(client):
    r = client.post(
        "/enhance",
        json={
            "node_id": 94,
            "prompt": "hello",
            "init_img_ids": [1, 2],
            "init_img_dims": [{"width": 1024, "height": 1024}],  # length 1 != 2
        },
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error"] == "init_img_dims_length_mismatch"
    assert detail["ids"] == 2 and detail["dims"] == 1


# ─── 2. Бизнес-логика ───────────────────────────────────────────────────────

def test_enhance_unsupported_node_returns_400(client, monkeypatch):
    """Topaz (87) — нет system-prompt'а, EnhancerService.supports=False."""
    # Никакой подмены EnhancerService — пусть реальный supports() отработает.
    r = client.post("/enhance", json={"node_id": 87, "prompt": "x"})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["error"] == "enhancer_not_supported"
    assert detail["node_id"] == 87


def test_enhance_supported_nodes_succeed(client, monkeypatch):
    """Happy path: для каждой supported-ноды возвращает enhanced_prompt."""
    # Мокаем EnhancerService так, чтобы возвращал детерминированный текст.
    fake_svc = MagicMock()
    fake_svc.supports.return_value = True
    fake_svc.enhance = AsyncMock(
        return_value=_FakeEnhanceResult(
            text="ENHANCED test prompt",
            node_id=94,
            filename="enh_nano_banana.md",
        )
    )
    monkeypatch.setattr(
        "app.routers.enhance.EnhancerService", lambda *a, **kw: fake_svc
    )

    r = client.post("/enhance", json={"node_id": 94, "prompt": "test prompt"})
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "enhanced_prompt": "ENHANCED test prompt",
        "target_node_id": 94,
        "system_prompt_file": "enh_nano_banana.md",
    }
    # Должны были вызвать enhance() с правильными аргументами
    fake_svc.enhance.assert_awaited_once()
    kwargs = fake_svc.enhance.call_args.kwargs
    assert kwargs["node_id"] == 94
    assert kwargs["user_prompt"] == "test prompt"
    # init_img_ids/dims пустые → передаются как None
    assert kwargs["init_img_ids"] is None
    assert kwargs["init_img_dims"] is None


def test_enhance_passes_image_context(client, monkeypatch):
    """init_img_ids/init_img_dims должны прокидываться в EnhancerService."""
    fake_svc = MagicMock()
    fake_svc.supports.return_value = True
    fake_svc.enhance = AsyncMock(
        return_value=_FakeEnhanceResult("E", 100, "enh_seedance.md")
    )
    monkeypatch.setattr(
        "app.routers.enhance.EnhancerService", lambda *a, **kw: fake_svc
    )

    r = client.post(
        "/enhance",
        json={
            "node_id": 100,
            "prompt": "девушка идёт",
            "init_img_ids": [12345],
            "init_img_dims": [{"width": 1024, "height": 768}],
        },
    )
    assert r.status_code == 200
    kwargs = fake_svc.enhance.call_args.kwargs
    assert kwargs["init_img_ids"] == [12345]
    assert kwargs["init_img_dims"] == [{"width": 1024, "height": 768}]


def test_enhance_enhancer_error_returns_502(client, monkeypatch):
    fake_svc = MagicMock()
    fake_svc.supports.return_value = True
    fake_svc.enhance = AsyncMock(side_effect=EnhancerError("gemini timeout"))
    monkeypatch.setattr(
        "app.routers.enhance.EnhancerService", lambda *a, **kw: fake_svc
    )

    r = client.post("/enhance", json={"node_id": 94, "prompt": "x"})
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert detail["error"] == "enhancer_failed"
    assert "gemini timeout" in detail["message"]


# ─── 3. Зеркальный /v1/enhance — main.py регистрирует и его ─────────────────

def test_enhance_v1_alias_works(client, monkeypatch):
    fake_svc = MagicMock()
    fake_svc.supports.return_value = True
    fake_svc.enhance = AsyncMock(
        return_value=_FakeEnhanceResult("E", 94, "enh_nano_banana.md")
    )
    monkeypatch.setattr(
        "app.routers.enhance.EnhancerService", lambda *a, **kw: fake_svc
    )
    r = client.post("/v1/enhance", json={"node_id": 94, "prompt": "x"})
    assert r.status_code == 200
    assert r.json()["enhanced_prompt"] == "E"


# ─── 4. Закрытие клиента (finally) — проверяем что __aexit__ зовётся ────────

def test_enhance_closes_phygital_client_on_success(client, monkeypatch):
    """В роутере есть `finally: await client.__aexit__(...)` — иначе утечка
    httpx.AsyncClient. Проверяем, что __aexit__ был вызван даже когда всё ок."""
    fake_client = AsyncMock()
    fake_client.__aexit__ = AsyncMock(return_value=None)

    async def _gc():
        return fake_client

    client.app.state.get_client = _gc

    fake_svc = MagicMock()
    fake_svc.supports.return_value = True
    fake_svc.enhance = AsyncMock(
        return_value=_FakeEnhanceResult("E", 94, "enh_nano_banana.md")
    )
    monkeypatch.setattr(
        "app.routers.enhance.EnhancerService", lambda *a, **kw: fake_svc
    )

    r = client.post("/enhance", json={"node_id": 94, "prompt": "x"})
    assert r.status_code == 200
    fake_client.__aexit__.assert_awaited_once()


def test_enhance_closes_phygital_client_on_error(client, monkeypatch):
    fake_client = AsyncMock()
    fake_client.__aexit__ = AsyncMock(return_value=None)

    async def _gc():
        return fake_client

    client.app.state.get_client = _gc

    fake_svc = MagicMock()
    fake_svc.supports.return_value = True
    fake_svc.enhance = AsyncMock(side_effect=EnhancerError("boom"))
    monkeypatch.setattr(
        "app.routers.enhance.EnhancerService", lambda *a, **kw: fake_svc
    )

    r = client.post("/enhance", json={"node_id": 94, "prompt": "x"})
    assert r.status_code == 502
    fake_client.__aexit__.assert_awaited_once()
