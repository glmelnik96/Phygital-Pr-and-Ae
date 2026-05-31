"""Кэш system-prompt'ов prompt-энхансера в Phygital storage.

Каждый из шести энхансеров — это .md в docs/enhancer_prompts/ (см. Q3-b).
Файл аплоадится в Phygital один раз и используется Gemini Text (node 72)
как `documents[0]`. file_obj_id кэшируется на диск с sha256 содержимого:
если файл редактировали — sha256 не совпадёт и мы переаплоадим.

Адаптация шаблона из Phygital-bot/workflows/brand_docs.py:
  * DOCS_DIR  → docs/enhancer_prompts/ (через project root)
  * cache    → AppData/enhancer_docs.json (вместо in-repo storage/)
  * mapping  → node_id → filename (см. ENHANCER_DOCS)

Phygital storage TTL для file_obj_id — наблюдаемо ~14h. Превентивно
переаплоадим записи старше 12h, чтобы покрыть TTL с запасом.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path

from loguru import logger

from app.paths import resolve_app_data
from app.phygital_client.api import PhygitalClient

# project_root/docs/enhancer_prompts/
# __file__ = sidecar/app/services/enhancer_docs.py  →  parents[3] = project root
DOCS_DIR = Path(__file__).resolve().parents[3] / "docs" / "enhancer_prompts"

CACHE_FILE = resolve_app_data() / "enhancer_docs.json"

MAX_DOC_AGE_SECONDS = 12 * 3600

# По одному файлу на модель (Q4: «отдельными файлами»).
ENH_NANO_BANANA = "enh_nano_banana.md"   # node 94 (Nano Banana, t2i+i2i)
ENH_GPT_IMAGE = "enh_gpt_image.md"       # node 98 (GPT Image, t2i+i2i)
ENH_KLING = "enh_kling.md"               # node 74 (Kling v3 pro, t2v+i2v)
ENH_SEEDANCE = "enh_seedance.md"         # node 100 (Seedance, t2v+i2v+v2v)
ENH_KLING_OMNI = "enh_kling_omni.md"     # node 121 (Kling Omni, t2v+i2v+v2v)
ENH_KLING_MOTION = "enh_kling_motion.md" # node 124 (Kling Motion, character motion)

# node_id → имя файла system-prompt'а
ENHANCER_DOCS: dict[int, str] = {
    94: ENH_NANO_BANANA,
    98: ENH_GPT_IMAGE,
    74: ENH_KLING,
    100: ENH_SEEDANCE,
    121: ENH_KLING_OMNI,
    124: ENH_KLING_MOTION,
}

_lock = asyncio.Lock()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _load_cache() -> dict[str, dict]:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"enhancer_docs cache unreadable ({e}), starting fresh")
        return {}


def _save_cache(cache: dict[str, dict]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def get_enhancer_doc_id(client: PhygitalClient, filename: str) -> int:
    """Вернуть file_obj_id для system-prompt .md из docs/enhancer_prompts/.

    Аплоадит при первом обращении, при изменении sha256 или если запись старше
    MAX_DOC_AGE_SECONDS (12h — превентивное обновление перед протуханием TTL).
    """
    path = DOCS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"enhancer system_prompt not found: {path}")

    digest = _sha256(path)
    async with _lock:
        cache = _load_cache()
        entry = cache.get(filename)
        if (
            entry
            and entry.get("sha256") == digest
            and isinstance(entry.get("file_obj_id"), int)
            and isinstance(entry.get("uploaded_at"), (int, float))
            and (time.time() - float(entry["uploaded_at"])) < MAX_DOC_AGE_SECONDS
        ):
            logger.debug(
                f"enhancer_doc cache hit: {filename} → {entry['file_obj_id']}"
            )
            return int(entry["file_obj_id"])

        if entry:
            age_h = (
                (time.time() - float(entry["uploaded_at"])) / 3600
                if isinstance(entry.get("uploaded_at"), (int, float))
                else None
            )
            logger.info(
                f"enhancer_doc cache stale: {filename} "
                f"(age_h={age_h!r}, had_id={entry.get('file_obj_id')}); re-uploading"
            )
        logger.info(f"enhancer_doc upload: {filename} (sha256={digest[:12]})")
        fid = await client.upload_file(path)
        cache[filename] = {
            "file_obj_id": fid,
            "sha256": digest,
            "name": filename,
            "uploaded_at": int(time.time()),
        }
        _save_cache(cache)
        logger.info(f"enhancer_doc cached: {filename} → file_obj_id={fid}")
        return fid


async def invalidate_enhancer_doc(filename: str) -> None:
    """Сбросить запись из кэша. Зовётся, когда Phygital вернул 'Cannot upload
    files' — file_obj_id протух раньше TTL, надо переаплоадить на след. вызове."""
    async with _lock:
        cache = _load_cache()
        removed = cache.pop(filename, None)
        if removed is not None:
            _save_cache(cache)
            logger.warning(
                f"enhancer_doc cache invalidated: {filename} "
                f"(was file_obj_id={removed.get('file_obj_id')})"
            )


async def get_enhancer_doc_for_node(client: PhygitalClient, node_id: int) -> int:
    """Вернуть file_obj_id system-prompt'а для конкретной целевой ноды.

    EnhancerService использует это, чтобы выбрать правильный promp-энхансер
    (Kling vs Seedance vs Nano Banana — у каждого свой «диалект»).
    """
    filename = ENHANCER_DOCS.get(node_id)
    if filename is None:
        raise ValueError(
            f"enhancer prompt not configured for node_id={node_id} "
            f"(supported: {sorted(ENHANCER_DOCS)})"
        )
    return await get_enhancer_doc_id(client, filename)


def enhancer_filename_for_node(node_id: int) -> str | None:
    """Чистый lookup без аплоада — нужен для invalidate'а из job_runner'а."""
    return ENHANCER_DOCS.get(node_id)
