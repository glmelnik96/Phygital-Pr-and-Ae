"""/jobs endpoints."""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel, Field

from app import paths
from app.services.idempotency import hash_request_body
from app.services.task_registry import JobState
from app.workflows import NODES

router = APIRouter()


class JobCreate(BaseModel):
    node_id: int
    params: dict[str, Any] = Field(default_factory=dict)
    # init_files: маппинг слот → путь(и) на диске. Для каждой ноды свой набор
    # слотов (init_img, image_tail, element_1..3, ref_img, start_img, ...).
    # Значение — либо список (для array-слотов), либо строка (для scalar).
    # Back-compat: если пришёл list[str] — трактуем как {"init_img": list}.
    init_files: dict[str, list[str] | str] | list[str] = Field(default_factory=dict)


def _state_to_dict(s: JobState) -> dict:
    return {
        "job_id": s.job_id,
        "node_id": s.node_id,
        "status": s.status,
        "task_id": s.task_id,
        "progress": s.progress,
        "result_paths": s.result_paths,
        "error": s.error,
        "created_at": s.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": s.updated_at.isoformat().replace("+00:00", "Z"),
    }


@router.post("/jobs/preview-cost")
async def preview_cost(body: JobCreate, request: Request) -> dict:
    """Подсчитать стоимость генерации без отправки задачи.

    Workflow.build_payload(...) → PhygitalClient.get_credits_price(payload).
    init_files игнорируются (для preview Phygital'у нужны только параметры).
    """
    if body.node_id not in NODES:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown_node", "node_id": body.node_id},
        )
    workflow_class = NODES[body.node_id]
    get_client = request.app.state.get_client

    # Все workflow принимают params в kwargs через __init__/build_payload.
    # Для preview-cost достаточно вызвать build_payload с params (без init_files).
    client = await get_client()
    try:
        wf = workflow_class(client)
        try:
            payload = wf.build_payload(**body.params)
        except TypeError as e:
            raise HTTPException(
                status_code=400,
                detail={"error": "bad_params", "message": str(e)},
            )
        price = await client.get_credits_price(payload)
    finally:
        await client.__aexit__(None, None, None)
    return price


@router.post("/jobs")
async def create_job(
    body: JobCreate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    if body.node_id not in NODES:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown_node", "node_id": body.node_id},
        )

    # M8: Idempotency-Key. Если клиент повторно шлёт запрос с тем же ключом и
    # тем же телом — возвращаем закэшированный job_id (без повторной отправки в
    # Phygital и без списания кредитов). Если тело другое — 422 conflict.
    idem_store = getattr(request.app.state, "idempotency_store", None)
    req_hash = None
    if idempotency_key and idem_store is not None:
        req_hash = hash_request_body(body.model_dump())
        found = await idem_store.lookup(idempotency_key, req_hash)
        if found is not None:
            kind, cached = found
            if kind == "hit":
                return cached
            # conflict
            raise HTTPException(
                status_code=422,
                detail={"error": "idempotency_conflict",
                        "message": "Idempotency-Key reused with different request body"},
            )

    # Опционально: проверка сессии. Можно вернуть 409 если нет сессии,
    # но многие panel могут submit'ить пока recon идёт — пусть try.
    reg = request.app.state.task_registry
    runner = request.app.state.job_runner

    # Нормализуем init_files: list → {"init_img": list}
    init_files = body.init_files
    if isinstance(init_files, list):
        init_files = {"init_img": list(init_files)} if init_files else {}

    params = dict(body.params)
    if init_files:
        params["_init_files"] = init_files

    job_id = await reg.create(node_id=body.node_id, params=params)
    runner.schedule(job_id)
    response = {"job_id": job_id}

    if idempotency_key and idem_store is not None and req_hash is not None:
        await idem_store.store(idempotency_key, req_hash, 200, response)

    return response


@router.get("/jobs")
async def list_jobs(
    request: Request,
    status: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> dict:
    """List jobs sorted by created_at desc. Pagination via cursor (M9).

    Cursor — это job_id последнего элемента предыдущей страницы. Клиент шлёт
    cursor=null для первой страницы, затем передаёт `next_cursor` из ответа.
    Если next_cursor отсутствует — страница последняя.
    """
    reg = request.app.state.task_registry
    # registry.list возвращает уже отсортированные по created_at desc, без cursor —
    # отдаём «окно» вручную чтобы next_cursor было точным.
    all_items = reg.list(status=status, limit=None)
    if cursor:
        # Найти позицию cursor и взять элементы после неё. Если cursor не найден —
        # клиент мог получить устаревший id (job удалён); возвращаем пустую страницу.
        idx = next((i for i, s in enumerate(all_items) if s.job_id == cursor), None)
        all_items = all_items[idx + 1:] if idx is not None else []
    # +1 чтобы понять есть ли следующая страница без второго запроса.
    window = all_items[: limit + 1] if limit else all_items
    has_more = bool(limit) and len(window) > limit
    page = window[:limit] if limit else window
    next_cursor = page[-1].job_id if has_more and page else None
    return {
        "jobs": [_state_to_dict(s) for s in page],
        "next_cursor": next_cursor,
    }


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict:
    state = request.app.state.task_registry.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail={"error": "unknown_job", "job_id": job_id})
    return _state_to_dict(state)


def _resolve_download(state: JobState, index: int) -> Path:
    """Shared resolver: проверяет статус, индекс, traversal, существование файла.
    Кидает HTTPException на любую ошибку. Возвращает canonical resolved path.
    """
    if state.status != "completed" or not state.result_paths:
        raise HTTPException(status_code=409, detail={"error": "not_completed", "status": state.status})
    if index < 0 or index >= len(state.result_paths):
        raise HTTPException(status_code=400, detail={"error": "bad_index"})

    fpath = Path(state.result_paths[index])
    try:
        resolved = fpath.resolve(strict=False)
        root = paths.downloads_dir().resolve(strict=False)
    except OSError as e:
        logger.warning(f"download resolve failed for job={state.job_id}: {e}")
        raise HTTPException(status_code=410, detail={"error": "file_gone"})

    try:
        if not resolved.is_relative_to(root):
            logger.error(
                f"download {state.job_id}: path traversal blocked — "
                f"resolved={resolved} not under {root}"
            )
            raise HTTPException(status_code=403, detail={"error": "path_outside_downloads"})
    except (AttributeError, ValueError):
        raise HTTPException(status_code=403, detail={"error": "path_outside_downloads"})

    if not resolved.exists():
        raise HTTPException(status_code=410, detail={"error": "file_gone"})
    return resolved


@router.head("/jobs/{job_id}/download")
async def head_download_job(job_id: str, request: Request, index: int = 0):
    """M14: HEAD-вариант download — отдаёт только заголовки (Content-Type,
    Content-Length, Last-Modified). Панель использует это для preflight'а
    миниатюры без скачивания тела (например, чтобы проверить, что артефакт
    существует и узнать MIME, прежде чем рендерить превью)."""
    state = request.app.state.task_registry.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail={"error": "unknown_job"})
    resolved = _resolve_download(state, index)
    stat = resolved.stat()
    mime, _ = mimetypes.guess_type(resolved.name)
    headers = {
        "Content-Type": mime or "application/octet-stream",
        "Content-Length": str(stat.st_size),
        # ISO 8601 не подходит для HTTP-Date — но frontend парсит просто как timestamp,
        # FileResponse в GET тоже не шлёт строгий HTTP-Date. Достаточно epoch секунд.
        "X-Last-Modified-Epoch": str(int(stat.st_mtime)),
    }
    return Response(status_code=200, headers=headers)


@router.get("/jobs/{job_id}/download")
async def download_job(job_id: str, request: Request, index: int = 0):
    # C4: result_paths приходит из downloader, но в jsonl записано и при
    # restore() мы доверяем содержимому файла. _resolve_download canonicalize'ит
    # путь и проверяет что он внутри downloads_dir (см. _resolve_download).
    state = request.app.state.task_registry.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail={"error": "unknown_job"})
    resolved = _resolve_download(state, index)
    return FileResponse(resolved, filename=resolved.name)


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str, request: Request):
    reg = request.app.state.task_registry
    if not await reg.remove(job_id):
        raise HTTPException(status_code=404, detail={"error": "unknown_job"})
    # TODO sub-project F: реально дёрнуть Phygital cancel если task_id есть
    return Response(status_code=204)
