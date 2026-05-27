"""Базовый класс воркфлоу. Конкретный transport (REST / WS / SSE) — после recon."""
from __future__ import annotations

import abc
import logging
from typing import Any, Awaitable, Callable

from app.phygital_client.api import PhygitalClient
from app.phygital_client.models import GenerationJob

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float], Awaitable[None]]


def _normalize_progress(raw: Any) -> float | None:
    """Приводим progress из Phygital к диапазону 0..1.

    HAR-recon показал что разные ноды возвращают по-разному: одни 0..100 (int),
    другие 0..1 (float). Эвристика: если value > 1.0 — это проценты, делим на 100.
    None / нечисловое / отрицательное — отбрасываем (callback не вызываем).
    """
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if v < 0:
        return None
    if v > 1.0:
        v = v / 100.0
    # clamp на случай дрейфа Phygital (видели 101 в логах при completion)
    return max(0.0, min(1.0, v))


class Workflow(abc.ABC):
    """Базовый интерфейс: подготовить payload → submit → дождаться результата."""

    workflow_id: str = ""

    def __init__(self, client: PhygitalClient) -> None:
        self.client = client
        # job_runner устанавливает callback перед .run() — wait() пушит сюда
        # нормализованный progress 0..1 при каждом изменении.
        self.on_progress: ProgressCallback | None = None

    @abc.abstractmethod
    def build_payload(self, **inputs: Any) -> dict[str, Any]: ...

    @abc.abstractmethod
    async def submit(self, payload: dict[str, Any]) -> str: ...  # → job_id

    @abc.abstractmethod
    async def wait(self, job_id: str, timeout: float = 300.0) -> GenerationJob: ...

    async def run(self, **inputs: Any) -> GenerationJob:
        payload = self.build_payload(**inputs)
        job_id = await self.submit(payload)
        return await self.wait(job_id)

    async def _emit_progress(self, raw: Any, last: float | None) -> float | None:
        """Вызывает on_progress если value валиден и отличается от last.
        Возвращает новое last (либо прежнее, если без изменений / без callback).
        Ошибка в callback не валит wait-loop — логируем и продолжаем.
        """
        value = _normalize_progress(raw)
        if value is None or value == last:
            return last
        if self.on_progress is not None:
            try:
                await self.on_progress(value)
            except Exception:
                logger.exception("on_progress callback failed (suppressed)")
        return value
