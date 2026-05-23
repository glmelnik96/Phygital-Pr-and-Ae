"""Pytest config — общие фикстуры для всех тестов."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


# ── автоматическая инъекция sidecar-token в TestClient ──────────────────────
# Все router-тесты пользуются паттерном:
#     with TestClient(build_app()) as c: ...
# После старта lifespan'а app.state.sidecar_token заполнен (см. main.py +
# services/sidecar_auth.py). Чтобы каждый тест не дублировал ручную установку
# заголовка, патчим TestClient.__enter__ в autouse-фикстуре: token читается
# из app.state и кладётся в client.headers как дефолт.
_real_enter = TestClient.__enter__


def _patched_enter(self):  # type: ignore[no-untyped-def]
    result = _real_enter(self)
    token = getattr(getattr(self, "app", None), "state", None)
    token = getattr(token, "sidecar_token", None) if token is not None else None
    if token:
        self.headers["X-Phygital-Sidecar-Token"] = token
    return result


@pytest.fixture(autouse=True)
def _auto_inject_sidecar_token(monkeypatch):
    monkeypatch.setattr(TestClient, "__enter__", _patched_enter)
