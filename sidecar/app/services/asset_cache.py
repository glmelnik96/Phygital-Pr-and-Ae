"""Asset cache: sha256-keyed dedup файлов, загруженных в Phygital+.

Каждая запись хранит маппинг (sha256 → file_obj_id), плюс mime/size/uploaded_at.
Журнал — append-only jsonl. На старте `restore()` восстанавливает in-memory dict.

`add(path, client)` — если sha256 уже в кэше, вернёт существующую запись без
повторного upload'а. Иначе посчитает sha256, загрузит файл через
`PhygitalClient.upload_file`, добавит запись в jsonl и in-memory.

`delete`/`clear` обновляют только in-memory state и пишут событие в журнал
(append-only); компакция jsonl — отложенный TODO.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger
from pydantic import BaseModel

if TYPE_CHECKING:
    from app.phygital_client.api import PhygitalClient


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class AssetEntry(BaseModel):
    sha256: str
    file_obj_id: int
    local_path: str | None = None
    mime: str
    size: int
    uploaded_at: str  # ISO Z
    # height/width пишутся только для изображений (mime image/*); для видео и
    # прочего None. Старые записи jsonl без этих полей загружаются с None.
    height: int | None = None
    width: int | None = None


class AssetCache:
    """sha256-keyed dedup; in-memory dict поверх append-only jsonl."""

    def __init__(self, jsonl_path: Path) -> None:
        self.jsonl_path = jsonl_path
        self._entries: dict[str, AssetEntry] = {}
        self._lock = asyncio.Lock()

    async def restore(self) -> None:
        if not self.jsonl_path.exists():
            return

        def _read_lines() -> list[str]:
            with self.jsonl_path.open("r", encoding="utf-8") as f:
                return f.readlines()

        # Чтение jsonl выносим в threadpool — большие кэши могут блокировать
        # event loop при startup'е (C2-class issue).
        lines = await asyncio.to_thread(_read_lines)
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(f"asset_cache restore: malformed line: {e}")
                continue
            event = rec.get("event")
            if event == "added":
                raw = rec.get("entry") or {}
                try:
                    entry = AssetEntry(**raw)
                except Exception as err:
                    logger.warning(f"asset_cache restore: bad entry: {err}")
                    continue
                self._entries[entry.sha256] = entry
            elif event == "deleted":
                sha = rec.get("sha256")
                if sha:
                    self._entries.pop(sha, None)
            elif event == "cleared":
                self._entries.clear()
        logger.info(
            f"AssetCache restored: {len(self._entries)} entries from {self.jsonl_path}"
        )

    def list(self) -> list[AssetEntry]:
        return list(self._entries.values())

    def get(self, sha256: str) -> AssetEntry | None:
        return self._entries.get(sha256)

    async def add(self, path: Path | str, client: "PhygitalClient") -> AssetEntry:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(str(path))

        # sha256 считаем по ОРИГИНАЛЬНОМу файлу — это пользовательский ключ дедупа.
        # Хеширование может занять секунды для 100MB файла, плюс пересохранение
        # в Pillow для большой картинки — всё это блокирует event loop. Выносим
        # CPU-bound работу в threadpool.
        digest = await asyncio.to_thread(_sha256_file, path)

        # H7: lock держим ТОЛЬКО для cache-check, не на network upload.
        # Раньше: 5 jobs concurrently → все ждут одной upload-операции (serial),
        # max_concurrent=5 деградировал до 1. Теперь параллельные add()
        # разных файлов реально параллельны; одинаковые файлы ловятся на
        # cache hit'е либо после первого upload'а — повторный addseq всё равно
        # увидит запись (в худшем случае залить дважды; Phygital сам дедуп
        # по sha256 не делает, но дубль file_obj_id безвреден — entry просто
        # перезапишется на тот, что вернулся позже).
        async with self._lock:
            cached = self._entries.get(digest)
        if cached is not None:
            logger.debug(f"asset_cache hit sha256={digest[:12]}…")
            return cached

        size = path.stat().st_size
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        # Для изображений: ресайз/HEIC→JPEG/RGBA→white + измерение height/width.
        # Для всего остального — оригинальный файл, dimensions None.
        effective_path = path
        normalized_tmp: Path | None = None
        height: int | None = None
        width: int | None = None
        if mime.startswith("image/"):
            from app.workflows.image_to_image import _prepare_for_upload  # late import (Pillow heavy)

            def _prep():
                return _prepare_for_upload(path)
            try:
                effective_path, dim, was_normalized = await asyncio.to_thread(_prep)
            except Exception as e:
                # Файл с image/* mime но не парсится Pillow (corrupt, unsupported).
                # Не блокируем — заливаем как есть, dimensions None. Если Phygital
                # требует dims (img2img), JobRunner упадёт явно дальше.
                logger.warning(
                    f"asset_cache: _prepare_for_upload({path.name}) failed: {e}; "
                    f"uploading as-is without dimensions"
                )
            else:
                height, width = dim["height"], dim["width"]
                if was_normalized:
                    normalized_tmp = effective_path
                    logger.info(
                        f"asset_cache normalized {path.name} → {width}x{height} "
                        f"({effective_path.stat().st_size/1024:.0f}KB jpeg)"
                    )

        try:
            file_obj_id = await client.upload_file(effective_path)
        finally:
            if normalized_tmp is not None and normalized_tmp != path:
                try:
                    normalized_tmp.unlink()
                except OSError:
                    pass

        entry = AssetEntry(
            sha256=digest,
            file_obj_id=int(file_obj_id),
            local_path=str(path),
            mime=mime,
            size=size,
            uploaded_at=_now_iso(),
            height=height,
            width=width,
        )
        # Под локом — только финальная атомарная запись в dict + jsonl.
        async with self._lock:
            # Если за время upload'а другой джоб уже залил тот же файл —
            # уважаем его entry; иначе пишем свой.
            existing = self._entries.get(digest)
            if existing is not None:
                logger.debug(
                    f"asset_cache: race resolved — keeping existing entry for {digest[:12]}…"
                )
                return existing
            self._entries[digest] = entry
            await self._append(
                {"event": "added", "ts": _now_iso(), "entry": entry.model_dump()}
            )
        logger.info(
            f"asset_cache added sha256={digest[:12]}… file_obj_id={file_obj_id} "
            f"mime={mime} size={size}"
            + (f" {width}x{height}" if height else "")
        )
        return entry

    async def delete(self, sha256: str) -> bool:
        async with self._lock:
            if sha256 not in self._entries:
                return False
            self._entries.pop(sha256)
            await self._append({"event": "deleted", "ts": _now_iso(), "sha256": sha256})
            logger.info(f"asset_cache deleted sha256={sha256[:12]}…")
            return True

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()
            await self._append({"event": "cleared", "ts": _now_iso()})
            logger.info("asset_cache cleared")

    async def _append(self, rec: dict[str, Any]) -> None:
        # Вызывается ВНУТРИ self._lock (см. add/delete/clear), так что
        # доп. синхронизация writes не нужна; асинхронность через
        # asyncio.to_thread снимает блокировку event loop'а.
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        await asyncio.to_thread(self._write_line, line)

    def _write_line(self, line: str) -> None:
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(line)
