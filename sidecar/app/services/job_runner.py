"""JobRunner: семафоры + резолв init_files + запуск workflow + download.

run_job(job_id) — единая точка для запуска уже зарегистрированной job.
schedule(job_id) — fire-and-forget asyncio.create_task(run_job(...)).
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Awaitable, Callable

from loguru import logger

from app.phygital_client.models import GenerationJob
from app.services.asset_cache import AssetCache
from app.services.task_registry import TaskRegistry


GetClient = Callable[[], Awaitable[Any]]  # → PhygitalClient async-context
DownloadUrlsFn = Callable[..., Awaitable[list[Path]]]


@asynccontextmanager
async def _noop_ctx():
    yield


class JobRunner:
    # Тяжёлые видео-ноды — ограничиваем отдельным меньшим семафором.
    VIDEO_NODE_IDS = {74, 100, 121, 124}

    def __init__(
        self,
        *,
        registry: TaskRegistry,
        downloads_root: Path,
        max_concurrent: int,
        nodes: dict[int, type],
        get_client: GetClient,
        download_urls_fn: DownloadUrlsFn,
        asset_cache: AssetCache | None = None,
        max_concurrent_video: int = 2,
        poll_interval: float = 1.5,
    ) -> None:
        self.registry = registry
        self.downloads_root = downloads_root
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.video_semaphore = asyncio.Semaphore(max_concurrent_video)
        self.nodes = nodes
        self._get_client = get_client
        self._download_urls = download_urls_fn
        self.asset_cache = asset_cache
        self.poll_interval = poll_interval
        self._active: dict[str, asyncio.Task] = {}

    def schedule(self, job_id: str) -> None:
        task = asyncio.create_task(self.run_job(job_id))
        self._active[job_id] = task
        task.add_done_callback(lambda _t: self._active.pop(job_id, None))

    async def run_job(self, job_id: str) -> None:
        state = self.registry.get(job_id)
        if state is None:
            logger.warning(f"run_job: unknown job_id={job_id}")
            return

        node_id = state.node_id
        workflow_class = self.nodes.get(node_id)
        if workflow_class is None:
            await self.registry.update_status(
                job_id, status="failed", error=f"unknown_node:{node_id}",
            )
            return

        # Для видео-нод сначала видеосемафор, потом общий — чтобы видео не
        # блокировало все image-jobs целиком.
        is_video = node_id in self.VIDEO_NODE_IDS
        outer = self.video_semaphore if is_video else _noop_ctx()
        async with outer:
            if is_video:
                logger.debug(
                    f"video_sem acquired (free={self.video_semaphore._value}) for job {job_id}"
                )
            async with self.semaphore:
                await self._do_run(job_id, state, workflow_class)

    async def _do_run(self, job_id: str, state, workflow_class) -> None:
        # C1: httpx.AsyncClient внутри PhygitalClient — open file descriptor +
        # connection pool. Без явного __aexit__ ресурсы висят до GC, и при
        # параллельной нагрузке (n jobs in flight) уходят в ulimit / выжирают
        # порты. _get_client() возвращает уже __aenter__'нутый клиент, поэтому
        # caller (мы) обязан закрыть его в try/finally. Тестовые AsyncMock-и
        # отдают MagicMock-клиента — у него aexit либо не awaitable либо
        # mock-объект, поэтому swallow'им исключение.
        client = None
        try:
            await self.registry.update_status(job_id, status="submitted")
            client = await self._get_client()

            # Резолвим _init_files → file_obj_ids через AssetCache.
            # Для изображений собираем не только id, но и dimensions (нужно для
            # img2img payload — Phygital валидирует .value.len == .meta.dimensions.len).
            params = dict(state.params)
            init_files = params.pop("_init_files", None)
            slot_entries: dict[str, list] = {}  # slot → [AssetEntry, ...]
            if init_files:
                if self.asset_cache is None:
                    raise RuntimeError("asset_cache not configured but init_files provided")
                await self.registry.update_status(job_id, status="uploading")
                for slot, val in init_files.items():
                    if isinstance(val, list):
                        ids: list[int] = []
                        entries = []
                        for p in val:
                            entry = await self.asset_cache.add(Path(p), client)
                            ids.append(entry.file_obj_id)
                            entries.append(entry)
                        params[slot] = ids
                        slot_entries[slot] = entries
                    elif isinstance(val, str) and val:
                        entry = await self.asset_cache.add(Path(val), client)
                        params[slot] = entry.file_obj_id
                        slot_entries[slot] = [entry]

            # Dispatch: node 94 (Nano Banana) с непустым init_img → img2img-форма.
            # У неё другой шейп payload (type="image", meta.dimensions=[{h,w}]).
            # Без этого Phygital кэнселит таск через ~30s валидации.
            if state.node_id == 94 and slot_entries.get("init_img"):
                from app.workflows.image_to_image import ImageToImageWorkflow

                entries = slot_entries["init_img"]
                dims = [
                    {"height": e.height, "width": e.width}
                    for e in entries
                    if e.height is not None and e.width is not None
                ]
                if len(dims) != len(entries):
                    raise RuntimeError(
                        f"init_img: AssetCache entries missing height/width "
                        f"({len(dims)}/{len(entries)}); cache stale, re-add files"
                    )
                workflow = ImageToImageWorkflow(client)
                workflow._init_img_ids = params.pop("init_img")
                workflow._init_img_dims = dims
            else:
                workflow = workflow_class(client)
            await self.registry.update_status(job_id, status="running")
            # Прокидываем progress 0..1 из poll-цикла воркфлоу в registry,
            # чтобы CEP-клиент видел реальный прогресс, а не 0%→100%.
            # Status оставляем "running" — обновляем только progress поле.
            async def _on_progress(p: float, _job_id: str = job_id) -> None:
                await self.registry.update_status(_job_id, status="running", progress=p)
            workflow.on_progress = _on_progress
            gen_job: GenerationJob = await workflow.run(**params)

            if gen_job.status == "completed":
                await self.registry.update_status(
                    job_id, status="downloading",
                    task_id=gen_job.job_id,
                )
                out_dir = self.downloads_root / job_id
                paths = await self._download_urls(
                    urls=gen_job.result_urls,
                    out_dir=out_dir,
                )
                await self.registry.update_status(
                    job_id, status="completed",
                    task_id=gen_job.job_id,
                    result_paths=[str(p) for p in paths],
                )
            else:
                await self.registry.update_status(
                    job_id, status="failed",
                    task_id=gen_job.job_id,
                    error=gen_job.error or f"status={gen_job.status}",
                )

        except Exception as e:
            logger.exception(f"run_job({job_id}) failed")
            await self.registry.update_status(
                job_id, status="failed", error=f"{type(e).__name__}: {e}",
            )
        finally:
            if client is not None:
                aexit = getattr(client, "__aexit__", None)
                if aexit is not None:
                    try:
                        result = aexit(None, None, None)
                        if hasattr(result, "__await__"):
                            await result
                    except Exception:
                        # Best-effort close — не маскируем основную ошибку.
                        logger.debug(f"client.__aexit__ failed for job {job_id}", exc_info=True)

    async def cancel_all(self) -> None:
        for job_id, task in list(self._active.items()):
            task.cancel()
            await self.registry.update_status(job_id, status="canceled", error="shutdown")
        self._active.clear()
