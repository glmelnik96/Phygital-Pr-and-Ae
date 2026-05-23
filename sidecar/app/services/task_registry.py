"""TaskRegistry: in-memory state + append-only jsonl журнал.

Статусы (см. ARCHITECTURE.md):
  queued | uploading | submitted | pending | running | downloading | completed | failed | canceled

Формат jsonl — одна строка на событие:
  {"ts":"...","job_id":"...","event":"created","node_id":N,"params":{...}}
  {"ts":"...","job_id":"...","event":"status","status":"...","task_id":"...","result_paths":[...],"error":"..."}
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from loguru import logger
from ulid import ULID


JobStatus = Literal[
    "queued", "uploading", "submitted", "pending",
    "running", "downloading", "completed", "failed", "canceled",
]

TERMINAL: set[str] = {"completed", "failed", "canceled"}


@dataclass
class JobState:
    job_id: str
    node_id: int
    params: dict[str, Any]
    status: JobStatus = "queued"
    task_id: str | None = None
    progress: float | None = None
    result_paths: list[str] = field(default_factory=list)
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TaskRegistry:
    """In-memory dict + append-only jsonl. Pre-thread-safety: один процесс, asyncio."""

    def __init__(self, jsonl_path: Path) -> None:
        self.jsonl_path = jsonl_path
        self._jobs: dict[str, JobState] = {}
        self._write_lock = asyncio.Lock()

    async def create(self, *, node_id: int, params: dict[str, Any]) -> str:
        job_id = str(ULID())
        state = JobState(job_id=job_id, node_id=node_id, params=params)
        self._jobs[job_id] = state
        await self._append(
            {"ts": _now_iso(), "job_id": job_id, "event": "created",
             "node_id": node_id, "params": params}
        )
        return job_id

    def get(self, job_id: str) -> JobState | None:
        return self._jobs.get(job_id)

    def list(self, *, status: str | None = None, limit: int | None = None) -> list[JobState]:
        items = list(self._jobs.values())
        if status:
            items = [s for s in items if s.status == status]
        items.sort(key=lambda s: s.created_at, reverse=True)
        if limit:
            items = items[:limit]
        return items

    async def remove(self, job_id: str) -> bool:
        """Полное удаление job из реестра. Запись 'deleted' в jsonl, чтобы restore не вернул его."""
        if job_id not in self._jobs:
            return False
        del self._jobs[job_id]
        await self._append({"ts": _now_iso(), "job_id": job_id, "event": "deleted"})
        return True

    async def update_status(
        self,
        job_id: str,
        *,
        status: JobStatus,
        task_id: str | None = None,
        progress: float | None = None,
        result_paths: list[str] | None = None,
        error: str | None = None,
    ) -> None:
        state = self._jobs.get(job_id)
        if state is None:
            logger.warning(f"update_status: unknown job_id={job_id}")
            return
        state.status = status
        if task_id is not None:
            state.task_id = task_id
        if progress is not None:
            state.progress = progress
        if result_paths is not None:
            state.result_paths = result_paths
        if error is not None:
            state.error = error
        state.updated_at = datetime.now(timezone.utc)

        rec: dict[str, Any] = {"ts": _now_iso(), "job_id": job_id, "event": "status", "status": status}
        if task_id is not None:
            rec["task_id"] = task_id
        if progress is not None:
            rec["progress"] = progress
        if result_paths is not None:
            rec["result_paths"] = result_paths
        if error is not None:
            rec["error"] = error
        await self._append(rec)

    async def restore(self) -> None:
        """Прочитать jsonl и схлопнуть события до текущего state.

        C2: чтение jsonl на event loop'е блокировало startup при больших
        журналах (>10k jobs ≈ сотни ms блокировки uvicorn'а). Выносим в
        threadpool через asyncio.to_thread.
        """
        if not self.jsonl_path.exists():
            return

        def _read_records() -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            with self.jsonl_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        logger.warning(f"restore: skip malformed line: {e}")
            return out

        records = await asyncio.to_thread(_read_records)
        for rec in records:
            self._apply_event(rec)

        # Пометить orphans: jobs со status="queued"/"submitted"/"pending" без task_id
        # значит sidecar упал между create и получением task_id. Резюмировать нельзя.
        for state in self._jobs.values():
            if state.status in ("queued", "submitted", "pending") and not state.task_id:
                state.status = "failed"
                state.error = "orphaned_on_restart"
                # Записываем это как событие, чтобы при следующем restore был консистентный state
                await self._append(
                    {"ts": _now_iso(), "job_id": state.job_id, "event": "status",
                     "status": "failed", "error": "orphaned_on_restart"}
                )

        logger.info(f"TaskRegistry restored: {len(self._jobs)} jobs from {self.jsonl_path}")

    def _apply_event(self, rec: dict[str, Any]) -> None:
        job_id = rec.get("job_id")
        if not job_id:
            return
        event = rec.get("event")
        if event == "created":
            self._jobs[job_id] = JobState(
                job_id=job_id,
                node_id=rec.get("node_id", 0),
                params=rec.get("params", {}),
            )
        elif event == "deleted":
            self._jobs.pop(job_id, None)
        elif event == "status":
            state = self._jobs.get(job_id)
            if state is None:
                # status без created — игнорируем
                return
            state.status = rec.get("status", state.status)
            if "task_id" in rec:
                state.task_id = rec["task_id"]
            if "progress" in rec:
                state.progress = rec["progress"]
            if "result_paths" in rec:
                state.result_paths = rec["result_paths"]
            if "error" in rec:
                state.error = rec["error"]

    async def _append(self, rec: dict[str, Any]) -> None:
        # C2: append-only fsync на каждое событие → блокирует event loop на
        # медленных дисках. Сериализация JSON и fs-write оба выносятся в
        # threadpool. Лок здесь сериализует _writes_, чтобы две корутины не
        # перепутали порядок строк в файле.
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        async with self._write_lock:
            await asyncio.to_thread(self._write_line, line)

    def _write_line(self, line: str) -> None:
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(line)
