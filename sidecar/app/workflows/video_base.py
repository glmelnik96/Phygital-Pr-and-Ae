"""Базовый класс для видео-нод Phygital+.

Общая логика submit/wait/extract — одинаковая для всех видео-моделей:
  1. POST /api/v2/tasks/ → task_id
  2. POST /api/v2/tasks/config_history → 200
  3. polling /api/v2/tasks/queue-position/<id>
  4. /storage-object/.../download-links для готовых файлов

build_payload и _build_config — переопределяются в подклассах.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from loguru import logger

from app.phygital_client.models import GenerationJob
from app.workflows.base import Workflow


PENDING_STATUSES = {
    "new", "pending", "running", "queued", "in_progress", "waiting_for_launch",
}
DONE_STATUSES = {"done", "completed", "success"}
FAIL_STATUSES = {"failed", "error", "canceled", "cancelled", "error_params"}


class VideoWorkflow(Workflow):
    """Общий submit/wait/extract для всех видео-нод."""

    # Дочерние классы заполняют:
    WORKFLOW_SCHEMA_ID: int = 0
    NODE_GLOBAL_ID: str = ""
    NODE_NAME: str = ""
    SERVICE_VERSION: str = ""
    OUTPUT_NAME: str = "out_video"

    def __init__(self, client) -> None:
        super().__init__(client)
        self._last_price: dict[str, Any] | None = None
        self._last_args: dict[str, Any] = {}

    # build_payload и _build_config — у подклассов
    def build_payload(self, **inputs: Any) -> dict[str, Any]:
        raise NotImplementedError

    def _build_config(self, **inputs: Any) -> dict[str, Any]:
        raise NotImplementedError

    async def submit(self, payload: dict[str, Any]) -> str:
        # Опционально: запросить цену (для meta.taskPrice в config_history)
        try:
            self._last_price = await self.client.get_credits_price(payload)
        except Exception as e:
            logger.warning(f"price lookup failed (non-fatal): {e}")

        task_id = await self.client.submit_task(payload)
        logger.info(f"{self.NODE_NAME}: submitted task_id={task_id}")

        config = self._build_config(**self._last_args)
        await self.client.post_config_history(task_id, config)
        logger.info(f"{self.NODE_NAME}: posted config_history for task {task_id}")
        return str(task_id)

    async def wait(
        self,
        job_id: str,
        timeout: float = 1800.0,
        poll_interval: float = 1.5,
    ) -> GenerationJob:
        task_id = int(job_id)
        deadline = asyncio.get_event_loop().time() + timeout
        last_status: str | None = None
        last_progress: float | None = None

        while asyncio.get_event_loop().time() < deadline:
            data = await self.client.task_status(task_id)
            status = (data.get("status") or "").lower()
            if status != last_status:
                logger.info(
                    f"{self.NODE_NAME} task {task_id}: {status} "
                    f"(position={data.get('position')}, progress={data.get('progress')})"
                )
                last_status = status
            # Прокидываем progress наверх через registry: без этого UI висит на
            # 0% всю генерацию и резко прыгает в 100% при completion.
            last_progress = await self._emit_progress(data.get("progress"), last_progress)

            if status in DONE_STATUSES:
                link_ids = self._extract_link_ids(data.get("outputs") or [])
                if not link_ids:
                    return GenerationJob(
                        job_id=job_id, status="failed",
                        error="task done but no output link_ids", raw=data,
                    )
                links = await self.client.get_download_links(link_ids)
                urls = [lnk["download_link"] for lnk in links if lnk.get("download_link")]
                return GenerationJob(
                    job_id=job_id, status="completed",
                    result_urls=urls, raw={"task": data, "links": links},
                )

            if status in FAIL_STATUSES:
                return GenerationJob(
                    job_id=job_id, status="failed",
                    error=data.get("error_message") or f"status={status}", raw=data,
                )

            if status and status not in PENDING_STATUSES:
                logger.warning(f"Unknown status '{status}', treating as pending")

            await asyncio.sleep(poll_interval)

        return GenerationJob(job_id=job_id, status="failed", error="timeout")

    @staticmethod
    def _extract_link_ids(outputs: list[dict[str, Any]]) -> list[int]:
        ids: list[int] = []
        for out in outputs:
            raw = out.get("id")
            if isinstance(raw, list):
                ids.extend(int(x) for x in raw)
            elif isinstance(raw, int):
                ids.append(raw)
        return ids

    # ── helpers для подклассов ────────────────────────────────────────────
    @staticmethod
    def _array_slot(
        name: str,
        value: list[int] | None,
        data_type: str = "image",
        meta_dimensions: list[dict[str, int]] | None = None,
    ) -> dict[str, Any]:
        """Сформировать array-input: пустой → type='array'; populated → type=data_type."""
        if value:
            return {
                "name": name,
                "type": data_type,
                "optional": None,
                "isModified": False,
                "value": list(value),
                "meta": {"dimensions": meta_dimensions or [{} for _ in value]} if meta_dimensions is not None else {"dimensions": []},
            }
        return {
            "name": name,
            "type": "array",
            "optional": None,
            "isModified": False,
            "value": [],
            "meta": {"dimensions": []},
        }

    @staticmethod
    def _scalar_slot(
        name: str,
        value: int | str | None,
        data_type: str = "image",
        optional: bool = True,
        meta_dimensions: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """Сформировать scalar input (image/video). Empty value = ''."""
        v = value if value is not None and value != "" else ""
        meta: dict[str, Any] = {}
        if v != "" and meta_dimensions:
            meta["dimensions"] = meta_dimensions
        return {
            "name": name,
            "type": data_type,
            "optional": optional if optional else None,
            "isModified": False,
            "value": v,
            "meta": meta,
        }

    @staticmethod
    def _text_input(
        name: str, value: str = "", optional: bool = False, is_modified: bool = False
    ) -> dict[str, Any]:
        return {
            "name": name,
            "type": "text",
            "optional": True if optional else None,
            "isModified": is_modified,
            "value": value,
            "meta": {},
        }

    @staticmethod
    def _param(name: str, p_type: str, value: Any) -> dict[str, Any]:
        return {"name": name, "type": p_type, "value": value, "meta": {}}
