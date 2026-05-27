"""Тесты прокидывания progress из poll-цикла воркфлоу в callback.

Без этой механики UI зависает на 0% всю генерацию и резко прыгает в 100%
при completion. Проверяем:
1. _normalize_progress: 0..100 vs 0..1, отрицательные/None/нечисловые
2. _emit_progress: вызывает callback только при изменении, не при equal
3. video_base.wait и image_gen.wait действительно зовут callback
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.workflows.base import Workflow, _normalize_progress


# ── _normalize_progress ──────────────────────────────────────────────────


def test_normalize_none_returns_none():
    assert _normalize_progress(None) is None


def test_normalize_non_numeric_returns_none():
    assert _normalize_progress("abc") is None
    assert _normalize_progress({}) is None


def test_normalize_negative_returns_none():
    assert _normalize_progress(-0.5) is None
    assert _normalize_progress(-10) is None


def test_normalize_fraction_passthrough():
    assert _normalize_progress(0.0) == 0.0
    assert _normalize_progress(0.42) == 0.42
    assert _normalize_progress(1.0) == 1.0


def test_normalize_percent_divided_by_100():
    assert _normalize_progress(50) == 0.5
    assert _normalize_progress(99.5) == pytest.approx(0.995)
    assert _normalize_progress(100) == 1.0


def test_normalize_overflow_clamped_to_1():
    # Phygital иногда отдаёт 101/102 при completion.
    assert _normalize_progress(101) == 1.0
    assert _normalize_progress(200) == 1.0


# ── _emit_progress ───────────────────────────────────────────────────────


class _DummyWorkflow(Workflow):
    """Минимальный конкретный воркфлоу — нужны только метод _emit_progress
    и инстанс с client=None (валидное значение в данном контексте — атрибут
    не используется в _emit_progress)."""
    def build_payload(self, **inputs: Any) -> dict[str, Any]:  # pragma: no cover
        return {}
    async def submit(self, payload: dict[str, Any]) -> str:  # pragma: no cover
        return ""
    async def wait(self, job_id: str, timeout: float = 300.0):  # pragma: no cover
        return None  # type: ignore[return-value]


def _make_wf() -> _DummyWorkflow:
    # PhygitalClient в base.__init__ только присваивается атрибуту, не дергается
    # — передаём заглушку через SimpleNamespace вместо настоящего клиента.
    return _DummyWorkflow(client=SimpleNamespace())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_emit_skips_when_no_callback():
    wf = _make_wf()
    # callback не установлен — emit не должен падать, last обновляется
    new_last = await wf._emit_progress(0.5, None)
    assert new_last == 0.5


@pytest.mark.asyncio
async def test_emit_calls_callback_on_change():
    wf = _make_wf()
    received: list[float] = []
    async def cb(p: float) -> None:
        received.append(p)
    wf.on_progress = cb

    last = None
    last = await wf._emit_progress(0, last)
    last = await wf._emit_progress(50, last)
    last = await wf._emit_progress(50, last)  # дубль — callback не зовётся
    last = await wf._emit_progress(100, last)

    assert received == [0.0, 0.5, 1.0]
    assert last == 1.0


@pytest.mark.asyncio
async def test_emit_swallows_callback_exception():
    """Ошибка в callback не должна валить poll-loop генерации."""
    wf = _make_wf()
    calls = []
    async def cb(p: float) -> None:
        calls.append(p)
        raise RuntimeError("boom")
    wf.on_progress = cb

    last = None
    last = await wf._emit_progress(0.3, last)
    assert last == 0.3
    assert calls == [0.3]
    # после ошибки можно продолжать
    last = await wf._emit_progress(0.7, last)
    assert last == 0.7
    assert calls == [0.3, 0.7]


@pytest.mark.asyncio
async def test_emit_ignores_invalid_values():
    wf = _make_wf()
    received: list[float] = []
    async def cb(p: float) -> None:
        received.append(p)
    wf.on_progress = cb

    last = None
    last = await wf._emit_progress(None, last)
    assert last is None
    last = await wf._emit_progress(-5, last)
    assert last is None
    last = await wf._emit_progress("bad", last)
    assert last is None
    last = await wf._emit_progress(0.5, last)
    assert last == 0.5
    assert received == [0.5]


# ── Integration: video_base.wait вызывает callback ───────────────────────


class _FakeClient:
    """Подменяет PhygitalClient.task_status на сценарий из списка статусов."""

    def __init__(self, sequence: list[dict[str, Any]]):
        self._seq = list(sequence)
        self._i = 0

    async def task_status(self, task_id: int) -> dict[str, Any]:
        i = min(self._i, len(self._seq) - 1)
        self._i += 1
        return self._seq[i]

    async def get_download_links(self, ids):
        return [{"download_link": f"http://example.com/{i}"} for i in ids]


@pytest.mark.asyncio
async def test_video_wait_propagates_progress(monkeypatch):
    """video_base.wait() должен звать on_progress на каждом изменении."""
    from app.workflows.video_base import VideoWorkflow

    # Создаём конкретный подкласс — VideoWorkflow абстрактный.
    class _StubVideo(VideoWorkflow):
        NODE_ID = 999
        NODE_NAME = "stub"
        def _build_config(self, **kwargs):  # pragma: no cover
            return {}

    seq = [
        {"status": "queued", "progress": 0},
        {"status": "running", "progress": 25},
        {"status": "running", "progress": 75},
        {"status": "done", "progress": 100, "outputs": [{"id": [1]}]},
    ]
    client = _FakeClient(seq)
    wf = _StubVideo(client=client)  # type: ignore[arg-type]

    received: list[float] = []
    async def cb(p: float) -> None:
        received.append(p)
    wf.on_progress = cb

    # Сократим poll_interval до 0 чтобы тест не висел.
    result = await wf.wait("0", timeout=5.0, poll_interval=0.0)
    assert result.status == "completed"
    # 0 → 0.25 → 0.75 → 1.0 (без дублей)
    assert received == [0.0, 0.25, 0.75, 1.0]


@pytest.mark.asyncio
async def test_wait_falls_back_to_synth_when_api_omits_progress():
    """Если Phygital не отдаёт `progress` (только status/position) — должен
    включиться synth по elapsed-time, чтобы UI не висел на 0%."""
    from app.workflows.image_gen import ImageGenWorkflow

    # Клиент с искусственной задержкой 10ms между poll'ами — иначе на быстрой
    # машине loop.time() даёт суб-микросекундные дельты и synth не вырастает.
    class _SlowClient:
        def __init__(self, sequence):
            self._seq = list(sequence)
            self._i = 0
        async def task_status(self, task_id):
            await asyncio.sleep(0.01)
            i = min(self._i, len(self._seq) - 1)
            self._i += 1
            return self._seq[i]
        async def get_download_links(self, ids):
            return [{"download_link": f"http://example.com/{i}"} for i in ids]

    import asyncio
    seq = [
        {"status": "queued", "position": 3},
        {"status": "running", "position": 0},
        {"status": "running"},
        {"status": "running"},
        {"status": "running"},
        {"status": "running"},
        {"status": "done", "outputs": [{"id": [1]}]},
    ]
    client = _SlowClient(seq)
    wf = ImageGenWorkflow(client=client)  # type: ignore[arg-type]
    # 30ms expected — после ~6 polls в running (60ms) synth дойдёт до cap.
    wf.EXPECTED_DURATION_S = 0.03

    received: list[float] = []
    async def cb(p: float) -> None:
        received.append(p)
    wf.on_progress = cb

    result = await wf.wait("0", timeout=5.0, poll_interval=0.0)
    assert result.status == "completed"
    assert len(received) >= 1, f"synth-progress не сработал: received={received}"
    assert all(0.0 <= p <= 0.95 for p in received), received
    assert any(p > 0.5 for p in received), f"synth не вырос: {received}"


@pytest.mark.asyncio
async def test_image_wait_propagates_progress():
    """image_gen.wait() должен звать on_progress на каждом изменении."""
    from app.workflows.image_gen import ImageGenWorkflow

    seq = [
        {"status": "queued", "progress": 0.0},
        {"status": "running", "progress": 0.4},
        {"status": "done", "progress": 1.0, "outputs": [{"id": [42]}]},
    ]
    client = _FakeClient(seq)
    wf = ImageGenWorkflow(client=client)  # type: ignore[arg-type]

    received: list[float] = []
    async def cb(p: float) -> None:
        received.append(p)
    wf.on_progress = cb

    result = await wf.wait("0", timeout=5.0, poll_interval=0.0)
    assert result.status == "completed"
    assert received == [0.0, 0.4, 1.0]
