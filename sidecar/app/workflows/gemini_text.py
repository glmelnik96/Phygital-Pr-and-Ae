"""Gemini Text workflow (Phygital+ node id=72, "Gemini text").

NODE_GLOBAL_ID = "Phygital Creator/phygc-rnd-gemini-text-api"
SERVICE_VERSION = "0.0.23"

Inputs:
  - text_prompt (text)
  - init_img (array of image, max 900) — опционально (img-context для enhancer'а)
  - videos (array)                       — пока не используем
  - audio                                — пока не используем
  - documents (array of pdf/txt/md/csv/doc/docx/xlsx/xls) — system_prompt-документы
Outputs:
  - description (text) → GenerationJob.result_text

Используется как text-сервис для prompt enhancer'а (EnhancerService).

Порт из Phygital-bot/workflows/gemini_text.py.
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from app.phygital_client.api import PhygitalClient
from app.phygital_client.models import GenerationJob
from app.workflows.base import Workflow, _normalize_progress
from app.workflows.image_gen import DONE_STATUSES, FAIL_STATUSES, PENDING_STATUSES
from app.workflows.image_to_image import _prepare_for_upload

NODE_GLOBAL_ID = "Phygital Creator/phygc-rnd-gemini-text-api"
NODE_NAME = "Gemini text"
SERVICE_VERSION = "0.0.23"
WORKFLOW_SCHEMA_ID = 72


class GeminiTextWorkflow(Workflow):
    """Single-node Gemini Text. Возвращает description как result_text."""

    workflow_id = str(WORKFLOW_SCHEMA_ID)
    EXPECTED_DURATION_S: float = 25.0  # Gemini Text 26-60s по логам Phygital-bot

    def __init__(
        self,
        client: PhygitalClient,
        *,
        model: str = "pro_3_1",
        thinking_level: str = "high",
    ) -> None:
        super().__init__(client)
        self.model = model
        self.thinking_level = thinking_level
        self._last_prompt: str = ""
        self._last_price: dict[str, Any] | None = None
        self._init_img_ids: list[int] = []
        self._init_img_dims: list[dict[str, int]] = []
        self._document_ids: list[int] = []

    # ── payload ───────────────────────────────────────────────────────────
    def build_payload(
        self,
        *,
        prompt: str,
        model: str | None = None,
        thinking_level: str | None = None,
        **_extra: Any,
    ) -> dict[str, Any]:
        self._last_prompt = prompt
        if model is not None:
            self.model = model
        if thinking_level is not None:
            self.thinking_level = thinking_level
        return {
            "id": WORKFLOW_SCHEMA_ID,
            "inputs": self._inputs_list(prompt),
            "params": self._params_list(),
            "outputs": [{"name": "description", "type": "text", "value": ""}],
        }

    def _params_list(self) -> list[dict[str, Any]]:
        return [
            {"name": "model", "type": "enum", "value": self.model, "meta": {}},
            {"name": "thinking_level", "type": "enum", "value": self.thinking_level, "meta": {}},
        ]

    def _inputs_list(self, prompt: str) -> list[dict[str, Any]]:
        """Шейп взят 1:1 из recon Phygital-bot:
          - documents.type = "document" (НЕ "array" — backend иначе вешает в pending)
          - init_img.type = "image" при заполнении, "array" иначе
          - audio.value = "" (не None)
          - isModified везде False
        """
        if self._init_img_ids:
            init_img = {"name": "init_img", "type": "image", "optional": None,
                        "isModified": False,
                        "value": list(self._init_img_ids),
                        "meta": {"dimensions": list(self._init_img_dims)}}
        else:
            init_img = {"name": "init_img", "type": "array", "optional": None,
                        "isModified": False, "value": [],
                        "meta": {"dimensions": []}}

        return [
            {"name": "text_prompt", "type": "text", "optional": None,
             "isModified": False, "value": prompt, "meta": {}},
            init_img,
            {"name": "videos", "type": "array", "optional": None,
             "isModified": False, "value": [], "meta": {}},
            {"name": "audio", "type": "audio", "optional": True,
             "isModified": False, "value": "", "meta": {}},
            {"name": "documents", "type": "document", "optional": None,
             "isModified": False, "value": list(self._document_ids), "meta": {}},
        ]

    # ── config_history ────────────────────────────────────────────────────
    def _build_config(self, prompt: str) -> dict[str, Any]:
        node_uuid = str(uuid.uuid4())
        node = {
            "globalId": NODE_GLOBAL_ID,
            "name": NODE_NAME,
            "uuid": node_uuid,
            "taskID": 0,
            "serviceVersion": SERVICE_VERSION,
            "inputSocketGroup": {
                "text_prompt": {
                    "name": "text_prompt", "type": "text", "value": prompt,
                    "optionalInfo": {"isEnabled": True, "mapOfEnabylity": {},
                                     "originalWorkspaceIds": prompt},
                },
                "init_img": {
                    "name": "init_img", "type": "array", "value": None,
                    "optionalInfo": {"isEnabled": True, "mapOfEnabylity": {},
                                     "originalWorkspaceIds": None},
                },
                "videos": {
                    "name": "videos", "type": "array", "value": None,
                    "optionalInfo": {"isEnabled": True, "mapOfEnabylity": {},
                                     "originalWorkspaceIds": None},
                },
                "audio": {
                    "name": "audio", "type": "audio", "value": None,
                    "optionalInfo": {"isEnabled": True, "mapOfEnabylity": {},
                                     "originalWorkspaceIds": None},
                },
                "documents": {
                    "name": "documents", "type": "array", "value": None,
                    "optionalInfo": {"isEnabled": True, "mapOfEnabylity": {},
                                     "originalWorkspaceIds": None},
                },
            },
            "outputSocketGroup": [
                {"name": "description", "dataType": "text",
                 "optionalInfo": {}, "optional": None, "displayName": None, "value": ""}
            ],
            "meta": {
                "text_prompttextSelector": {"highlights": []},
                **({"taskPrice": self._last_price} if self._last_price else {}),
                "taskSchema": {
                    "id": WORKFLOW_SCHEMA_ID,
                    "inputs": self._inputs_list(prompt),
                    "params": self._params_list(),
                    "outputs": [{"name": "description", "type": "text", "value": ""}],
                },
            },
            "params": {
                p["name"]: {
                    "name": p["name"], "type": p["type"],
                    "optionalInfo": {"isEnabled": True, "mapOfEnabylity": {}},
                    "value": p["value"],
                }
                for p in self._params_list()
            },
            "width": 350,
            "position": {"x": 600, "y": 200},
            "connections": [],
            "height": 617,
        }
        return {"nodes": [node], "executedNodeUuid": node_uuid}

    # ── uploads ───────────────────────────────────────────────────────────
    async def upload_images(
        self, paths: list[str | Path]
    ) -> tuple[list[int], list[dict[str, int]]]:
        ids: list[int] = []
        dims: list[dict[str, int]] = []
        for p in paths:
            pp = Path(p).expanduser().resolve()
            if not pp.exists():
                raise FileNotFoundError(pp)
            effective, dim, normalized = _prepare_for_upload(pp)
            try:
                fid = await self.client.upload_file(effective)
            finally:
                if normalized and effective != pp:
                    try:
                        effective.unlink()
                    except OSError:
                        pass
            ids.append(fid)
            dims.append(dim)
        return ids, dims

    async def upload_documents(self, paths: list[str | Path]) -> list[int]:
        """Документы (pdf/txt/md/csv/doc/docx/xlsx/xls) — без нормализации,
        грузим как есть."""
        ids: list[int] = []
        for p in paths:
            pp = Path(p).expanduser().resolve()
            if not pp.exists():
                raise FileNotFoundError(pp)
            fid = await self.client.upload_file(pp)
            logger.info(f"[gemini-text] uploaded document {pp.name} → file_obj_id={fid}")
            ids.append(fid)
        return ids

    # ── API calls ─────────────────────────────────────────────────────────
    async def submit(self, payload: dict[str, Any]) -> str:
        try:
            price_payload = {
                "id": WORKFLOW_SCHEMA_ID,
                "inputs": [{"name": "init_img", "value": None, "type": "image", "meta": {}}],
                "params": self._params_list(),
                "outputs": [],
            }
            self._last_price = await self.client.get_credits_price(price_payload)
            logger.debug(f"gemini-text price: {self._last_price.get('price')}")
        except Exception as e:
            logger.warning(f"gemini-text price lookup failed (non-fatal): {e}")

        task_id = await self.client.submit_task(payload)
        logger.info(f"[gemini-text] Submitted task_id={task_id}")

        config = self._build_config(self._last_prompt)
        await self.client.post_config_history(task_id, config)
        logger.info(f"[gemini-text] Posted config_history for task {task_id}")
        return str(task_id)

    async def wait(
        self,
        job_id: str,
        timeout: float = 180.0,
        poll_interval: float = 1.5,
    ) -> GenerationJob:
        # 180s ≈ 3× медианы Gemini Text. Залипший таск не должен держать
        # global_sem 5+ минут — лучше быстро failed и юзер ретраит.
        task_id = int(job_id)
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        last_status: str | None = None
        last_progress: float | None = None
        running_started_at: float | None = None
        logged_first = False

        while loop.time() < deadline:
            data = await self.client.task_status(task_id)
            status = (data.get("status") or "").lower()
            if not logged_first:
                logger.info(
                    f"[gemini-text] task {task_id} first poll: keys={list(data.keys())} "
                    f"progress={data.get('progress')!r}"
                )
                logged_first = True
            if status != last_status:
                logger.info(
                    f"[gemini-text] task {task_id}: {status} "
                    f"(position={data.get('position')}, progress={data.get('progress')})"
                )
                last_status = status
                if status in {"running", "in_progress"} and running_started_at is None:
                    running_started_at = loop.time()
            real_norm = _normalize_progress(data.get("progress"))
            if real_norm is not None:
                value: float | None = real_norm
            elif status in {"running", "in_progress"}:
                value = self._synth_progress(running_started_at, loop.time())
            else:
                value = None
            last_progress = await self._push_progress(value, last_progress)

            if status in DONE_STATUSES:
                text = self._extract_description(data.get("outputs") or [], raw=data)
                if not text:
                    return GenerationJob(
                        job_id=job_id, status="failed",
                        error="gemini-text done but description is empty", raw=data,
                    )
                return GenerationJob(
                    job_id=job_id, status="completed",
                    result_text=text, raw={"task": data},
                )

            if status in FAIL_STATUSES:
                return GenerationJob(
                    job_id=job_id, status="failed",
                    error=data.get("error_message") or f"status={status}", raw=data,
                )

            if status and status not in PENDING_STATUSES:
                logger.warning(f"[gemini-text] Unknown status '{status}', treating as pending")

            await asyncio.sleep(poll_interval)

        return GenerationJob(job_id=job_id, status="failed", error="timeout")

    @staticmethod
    def _extract_description(outputs: list[dict[str, Any]], *, raw: dict[str, Any]) -> str:
        """Достаём description-текст из outputs. Несколько форм — логируем raw
        если не нашли (для recon-fallback)."""
        for out in outputs:
            if out.get("name") != "description":
                continue
            v = out.get("value")
            if isinstance(v, str) and v.strip():
                return v
            if isinstance(v, dict):
                for k in ("text", "description", "result", "content"):
                    if isinstance(v.get(k), str) and v[k].strip():
                        return v[k]
            for k in ("text", "result", "content"):
                if isinstance(out.get(k), str) and out[k].strip():
                    return out[k]
        logger.error(f"[gemini-text] couldn't extract description from outputs={outputs!r}")
        return ""

    # ── high-level entrypoint ─────────────────────────────────────────────
    async def run_text(
        self,
        *,
        prompt: str,
        init_img_ids: list[int] | None = None,
        init_img_dims: list[dict[str, int]] | None = None,
        document_ids: list[int] | None = None,
        **params: Any,
    ) -> GenerationJob:
        """Удобный entrypoint: задаём init_img_ids/document_ids явно, без аплоада.
        Аплоад делается на уровне EnhancerService, чтобы переиспользовать
        file_obj_id между нодами (Gemini → Nano Banana → итог)."""
        self._init_img_ids = list(init_img_ids or [])
        self._init_img_dims = list(init_img_dims or [{} for _ in self._init_img_ids])
        self._document_ids = list(document_ids or [])
        return await self.run(prompt=prompt, **params)
