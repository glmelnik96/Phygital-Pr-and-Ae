"""/jobs endpoints."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel, Field

from app import paths
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
async def create_job(body: JobCreate, request: Request) -> dict:
    if body.node_id not in NODES:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown_node", "node_id": body.node_id},
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
    return {"job_id": job_id}


@router.get("/jobs")
async def list_jobs(request: Request, status: str | None = None, limit: int = 50) -> dict:
    reg = request.app.state.task_registry
    items = reg.list(status=status, limit=limit)
    return {"jobs": [_state_to_dict(s) for s in items]}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict:
    state = request.app.state.task_registry.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail={"error": "unknown_job", "job_id": job_id})
    return _state_to_dict(state)


@router.get("/jobs/{job_id}/download")
async def download_job(job_id: str, request: Request, index: int = 0):
    state = request.app.state.task_registry.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail={"error": "unknown_job"})
    if state.status != "completed" or not state.result_paths:
        raise HTTPException(status_code=409, detail={"error": "not_completed", "status": state.status})
    if index < 0 or index >= len(state.result_paths):
        raise HTTPException(status_code=400, detail={"error": "bad_index"})

    # C4: result_paths приходит из downloader, но в jsonl записано и при
    # restore() мы доверяем содержимому файла. Если jsonl как-либо испорчен
    # (атакующий с локальным доступом отредактировал, или будущая sync с
    # облака) — путь "../../etc/shadow" будет принят без проверки. Поэтому
    # canonicalize и проверяем что физически лежит внутри downloads_dir.
    fpath = Path(state.result_paths[index])
    try:
        resolved = fpath.resolve(strict=False)
        root = paths.downloads_dir().resolve(strict=False)
    except OSError as e:
        logger.warning(f"download_job {job_id}: path resolve failed: {e}")
        raise HTTPException(status_code=410, detail={"error": "file_gone"})

    try:
        # Path.is_relative_to добавлен в 3.9, sidecar требует 3.10+ (см. paths.ensure_dirs).
        if not resolved.is_relative_to(root):
            logger.error(
                f"download_job {job_id}: path traversal blocked — "
                f"resolved={resolved} not under {root}"
            )
            raise HTTPException(status_code=403, detail={"error": "path_outside_downloads"})
    except (AttributeError, ValueError):
        # Защитная ветка — на старых питонах или при сравнении путей на разных дисках
        # is_relative_to кидает. Считаем такое подозрительным.
        raise HTTPException(status_code=403, detail={"error": "path_outside_downloads"})

    if not resolved.exists():
        raise HTTPException(status_code=410, detail={"error": "file_gone"})
    return FileResponse(resolved, filename=resolved.name)


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str, request: Request):
    reg = request.app.state.task_registry
    if not await reg.remove(job_id):
        raise HTTPException(status_code=404, detail={"error": "unknown_job"})
    # TODO sub-project F: реально дёрнуть Phygital cancel если task_id есть
    return Response(status_code=204)
