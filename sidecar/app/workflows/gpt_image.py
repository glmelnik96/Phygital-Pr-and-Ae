"""GPT Image API workflow (Phygital node id=98).

NODE_GLOBAL_ID = "Phygital Creator/phygc-rnd-gptimage-api"
SERVICE_VERSION = "0.0.29"

Отличия от Nano Banana (id=94):
  - `inputs.images` (а не `init_img`); тип переключается с "array" (пусто)
    на "image" (когда есть file_obj_id) — тот же фокус, что и у Gemini.
  - Всегда присутствует третий input `mask` (optional, value="").
  - Params: `version`, `aspect_ratio`, `quality`, `background`, `number_of_images`.
  - `outputs.name == "images"` (множественное число!).

Порт из Phygital-bot/workflows/gpt_image.py с sidecar-адаптациями:
  - импорты `app.phygital_client.*` / `app.workflows.*`
  - synth-progress fallback + first-poll diagnostic
  - kwargs из UI в `build_payload` обновляют self.X (как `ImageGenWorkflow`).
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

WORKFLOW_SCHEMA_ID = 98
NODE_GLOBAL_ID = "Phygital Creator/phygc-rnd-gptimage-api"
NODE_NAME = "GPT Image"
SERVICE_VERSION = "0.0.29"

# OpenAI gpt-image-1 принимает до 16 reference images в одном edit-вызове.
# Phygital фронт лимит явно не валидирует — проверял HAR'ом: 17+ просто
# протухает на стороне OpenAI ~30s без человекочитаемой ошибки. Лучше
# фейлить локально с понятным сообщением.
MAX_INPUT_IMAGES = 16


class GPTImageWorkflow(Workflow):
    """GPT Image API — text→image и image→image в одном классе."""

    workflow_id = str(WORKFLOW_SCHEMA_ID)
    EXPECTED_DURATION_S: float = 40.0  # GPT Image обычно ~30-60s

    def __init__(
        self,
        client: PhygitalClient,
        *,
        version: str = "v2",
        aspect_ratio: str = "auto",
        quality: str = "Medium",
        background: str = "auto",
        number_of_images: int = 1,
    ) -> None:
        super().__init__(client)
        self.version = version
        self.aspect_ratio = aspect_ratio
        self.quality = quality
        self.background = background
        self.number_of_images = number_of_images
        self._init_img_ids: list[int] = []
        self._init_img_dims: list[dict[str, int]] = []
        self._last_prompt: str = ""
        self._last_price: dict[str, Any] | None = None

    # ── params ────────────────────────────────────────────────────────────
    def _params_list(self) -> list[dict[str, Any]]:
        return [
            {"name": "version", "type": "enum", "value": self.version, "meta": {}},
            {"name": "aspect_ratio", "type": "enum", "value": self.aspect_ratio, "meta": {}},
            {"name": "number_of_images", "type": "number", "value": self.number_of_images, "meta": {}},
            {"name": "quality", "type": "enum", "value": self.quality, "meta": {}},
            {"name": "background", "type": "enum", "value": self.background, "meta": {}},
        ]

    def _images_input(self) -> dict[str, Any]:
        has_imgs = bool(self._init_img_ids)
        return {
            "name": "images",
            "type": "image" if has_imgs else "array",
            "optional": None,
            "isModified": False,
            "value": list(self._init_img_ids),
            "meta": {"dimensions": list(self._init_img_dims)},
        }

    # ── submit payload ────────────────────────────────────────────────────
    def build_payload(
        self,
        *,
        prompt: str,
        version: str | None = None,
        aspect_ratio: str | None = None,
        quality: str | None = None,
        background: str | None = None,
        number_of_images: int | None = None,
        **_extra: Any,
    ) -> dict[str, Any]:
        # UI-параметры из run(**params) → сюда. См. ImageGenWorkflow.build_payload
        # про silent param drop без перезаписи self.X.
        self._last_prompt = prompt
        if version is not None:
            self.version = version
        if aspect_ratio is not None:
            self.aspect_ratio = aspect_ratio
        if quality is not None:
            self.quality = quality
        if background is not None:
            self.background = background
        if number_of_images is not None:
            self.number_of_images = number_of_images
        return {
            "id": WORKFLOW_SCHEMA_ID,
            "inputs": [
                {"name": "prompt", "type": "text", "optional": None,
                 "isModified": False, "value": prompt, "meta": {}},
                self._images_input(),
                {"name": "mask", "type": "image", "optional": True,
                 "isModified": False, "value": "", "meta": {}},
            ],
            "params": self._params_list(),
            "outputs": [{"name": "images", "type": "array", "value": ""}],
        }

    # ── config_history (один node) ────────────────────────────────────────
    def _build_config(self, prompt: str, task_id: int) -> dict[str, Any]:
        node_uuid = str(uuid.uuid4())
        node = {
            "globalId": NODE_GLOBAL_ID,
            "name": NODE_NAME,
            "uuid": node_uuid,
            "taskID": task_id,
            "serviceVersion": SERVICE_VERSION,
            "inputSocketGroup": {
                "prompt": {
                    "name": "prompt", "type": "text", "value": prompt,
                    "optionalInfo": {"isEnabled": True, "mapOfEnabylity": {},
                                     "originalWorkspaceIds": prompt},
                },
                "images": {
                    "name": "images", "type": "array", "value": None,
                    "optionalInfo": {"isEnabled": True, "mapOfEnabylity": {},
                                     "originalWorkspaceIds": None},
                },
                "mask": {
                    "name": "mask", "type": "image", "value": None,
                    "optionalInfo": {"isEnabled": True, "mapOfEnabylity": {},
                                     "originalWorkspaceIds": None},
                },
            },
            "outputSocketGroup": [
                {
                    "name": "images", "dataType": "array",
                    "optionalInfo": {"valueOptions": {"itemType": {"dataType": "image"}}},
                    "optional": None, "displayName": None, "value": [],
                }
            ],
            "meta": {
                "prompttextSelector": {"highlights": []},
                **({"taskPrice": self._last_price} if self._last_price else {}),
                "taskSchema": {
                    "id": WORKFLOW_SCHEMA_ID,
                    "inputs": [
                        {"name": "prompt", "type": "text", "optional": None,
                         "isModified": False, "value": prompt, "meta": {}},
                        self._images_input(),
                        {"name": "mask", "type": "image", "optional": True,
                         "isModified": False, "value": "", "meta": {}},
                    ],
                    "params": self._params_list(),
                    "outputs": [{"name": "images", "type": "array", "value": ""}],
                },
                "taskID": task_id,
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
            "position": {"x": 1011, "y": 136},
            "connections": [],
            "height": 671,
        }
        return {"nodes": [node], "executedNodeUuid": node_uuid}

    # ── upload init images ────────────────────────────────────────────────
    async def upload_images(
        self, paths: list[str | Path]
    ) -> tuple[list[int], list[dict[str, int]]]:
        if len(paths) > MAX_INPUT_IMAGES:
            raise ValueError(
                f"GPT Image accepts at most {MAX_INPUT_IMAGES} reference images "
                f"per request, got {len(paths)}"
            )
        ids: list[int] = []
        dims: list[dict[str, int]] = []
        for p in paths:
            pp = Path(p).expanduser().resolve()
            if not pp.exists():
                raise FileNotFoundError(pp)
            effective, dim, normalized = _prepare_for_upload(pp)
            if normalized:
                logger.info(
                    f"normalized {pp.name} → {dim['width']}x{dim['height']} "
                    f"({effective.stat().st_size / 1024:.0f}KB png)"
                )
            try:
                fid = await self.client.upload_file(effective)
            finally:
                if normalized and effective != pp:
                    try:
                        effective.unlink()
                    except OSError:
                        pass
            logger.info(
                f"uploaded {pp.name} → file_obj_id={fid} ({dim['width']}x{dim['height']})"
            )
            ids.append(fid)
            dims.append(dim)
        return ids, dims

    # ── API calls ─────────────────────────────────────────────────────────
    async def submit(self, payload: dict[str, Any]) -> str:
        try:
            price_payload = {
                "id": WORKFLOW_SCHEMA_ID,
                "inputs": [{"name": "images", "value": None, "type": "image", "meta": {}}],
                "params": self._params_list(),
                "outputs": [],
            }
            self._last_price = await self.client.get_credits_price(price_payload)
            logger.debug(f"gpt-image price: {self._last_price.get('price')}")
        except Exception as e:
            logger.warning(f"gpt-image price lookup failed (non-fatal): {e}")

        task_id = await self.client.submit_task(payload)
        logger.info(f"[gpt-image] Submitted task_id={task_id}")

        config = self._build_config(self._last_prompt, int(task_id))
        await self.client.post_config_history(int(task_id), config)
        logger.info(f"[gpt-image] Posted config_history for task {task_id}")
        return str(task_id)

    async def wait(
        self,
        job_id: str,
        timeout: float = 900.0,
        poll_interval: float = 1.5,
    ) -> GenerationJob:
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
                    f"[gpt-image] task {task_id} first poll: keys={list(data.keys())} "
                    f"progress={data.get('progress')!r} percent={data.get('percent')!r}"
                )
                logged_first = True
            if status != last_status:
                logger.info(
                    f"[gpt-image] task {task_id}: {status} "
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
                logger.warning(f"[gpt-image] Unknown status '{status}', treating as pending")

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

    # ── high-level entrypoint ─────────────────────────────────────────────
    async def run_with_files(
        self,
        *,
        prompt: str,
        init_paths: list[str | Path] | None = None,
        **params: Any,
    ) -> GenerationJob:
        if init_paths:
            self._init_img_ids, self._init_img_dims = await self.upload_images(init_paths)
        else:
            self._init_img_ids, self._init_img_dims = [], []
        return await self.run(prompt=prompt, **params)
