"""POST /clip-video — рендер фрагмента видео по in/out секундам через ffmpeg.

Используется CEP-панелью, когда пользователь выбрал клип в Source Monitor и
выставил In/Out — вместо загрузки всего исходника на Phygital+ мы локально
вырезаем нужный фрагмент и панель уже загружает короткий клип.

ffmpeg должен быть в PATH (см. cep-premiere/README.md → Prerequisites). Если
он не найден — возвращаем `ffmpeg_missing` с подсказкой.

**Безопасность (H1).** `source_path` приходит от клиента и идёт в ffmpeg как
`-i <src>`. Без проверок это позволяет:

- читать произвольные файлы (`-i C:/Users/.ssh/id_rsa`) — не классический
  command injection (args передаются массивом), но ffmpeg сам по себе откроет
  что укажешь;
- protocol-injection через префиксы вроде `concat:`, `subfile:`, `crypto:`,
  `hls:`, `udp:`, `tcp:`, `pipe:` — открывает кучу векторов (sub-files,
  network fetches, pipe to stdin).

Защита тут — двухслойная:

1. `_validate_media_source()` проверяет, что путь существует, это файл,
   суффикс из media-whitelist'а и нет протокол-префикса.
2. `-protocol_whitelist file,crypto,data` в самом ffmpeg — даже если что-то
   проскочит mimo валидации (например через symlink на named pipe), ffmpeg
   откажет на network/concat/pipe протоколах.
"""
from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from app import paths

router = APIRouter()


# Whitelist суффиксов, которые имеет смысл скармливать ffmpeg как input
# в нашем сценарии (Pr Source Monitor / explorer drop). Audio-форматы тоже
# в списке, потому что Pr иногда отдаёт audio-only clips в Source Monitor.
_ALLOWED_MEDIA_SUFFIXES: frozenset[str] = frozenset({
    ".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mxf", ".mts", ".m2ts",
    ".mpg", ".mpeg", ".ts", ".flv", ".wmv", ".3gp", ".3g2", ".ogv", ".vob",
    ".prproj",  # вообще-то Pr-project, но frame extract на нём не должен падать с 400
    ".wav", ".mp3", ".aac", ".m4a", ".flac", ".ogg", ".aif", ".aiff",
})


def _validate_media_source(source_path: str) -> Path:
    """Жёсткая валидация input-пути перед скармливанием его ffmpeg.

    Бросает HTTPException 400 при любых подозрениях. Возвращает canonical
    Path, который безопасно передавать в -i.
    """
    if not source_path or not isinstance(source_path, str):
        raise HTTPException(400, detail={"error": "bad_source_path", "reason": "empty"})

    # ffmpeg protocol-prefix: "concat:", "subfile:", "crypto:", "tcp:" и т.п.
    # Признак — двоеточие до любого слеша/бекслеша. На Windows нормальные пути
    # выглядят как "C:\..." — двоеточие на ПОЗИЦИИ 1, после буквы диска. Поэтому
    # запрещаем двоеточие в первом сегменте ТОЛЬКО если оно не выглядит как
    # drive-letter (single ascii letter + ':' в начале).
    head_before_sep = source_path.split("/", 1)[0].split("\\", 1)[0]
    is_win_drive = (
        len(head_before_sep) == 2
        and head_before_sep[1] == ":"
        and head_before_sep[0].isascii()
        and head_before_sep[0].isalpha()
    )
    if ":" in head_before_sep and not is_win_drive:
        raise HTTPException(400, detail={
            "error": "bad_source_path",
            "reason": "protocol_prefix_not_allowed",
        })

    p = Path(source_path)
    try:
        resolved = p.resolve(strict=False)
    except OSError as e:
        logger.warning(f"_validate_media_source: resolve failed: {e}")
        raise HTTPException(400, detail={"error": "bad_source_path", "reason": "resolve_failed"})

    # Не должен указывать на named pipe / device file / etc. На POSIX
    # is_file() возвращает False для named pipes (FIFOs) — это нам и нужно.
    if not resolved.exists():
        raise HTTPException(400, detail={"error": "source_not_found", "path": str(resolved)})
    if not resolved.is_file():
        raise HTTPException(400, detail={
            "error": "bad_source_path",
            "reason": "not_a_regular_file",
        })

    if resolved.suffix.lower() not in _ALLOWED_MEDIA_SUFFIXES:
        raise HTTPException(400, detail={
            "error": "bad_source_path",
            "reason": "suffix_not_allowed",
            "suffix": resolved.suffix,
        })

    return resolved


def _sanitize_ffmpeg_stderr(raw: bytes, src_path: Path | None = None) -> str:
    """Trim + redact paths in ffmpeg stderr перед отдачей клиенту.

    Без этого 2KB stderr могут содержать дополнительные пути из ffmpeg-логов
    (например соседние файлы при probe), что — утечка локального файлового
    тейк-листа в HTTP-ответ.
    """
    text = raw.decode(errors="replace")[-2000:]
    if src_path is not None:
        # Маскируем только сам источник — это значение клиент уже знал. Не
        # маскируем downloads/ asset_uploads/ — клиент тоже знает их структуру.
        text = text.replace(str(src_path), "<source>")
    return text


class ClipVideoRequest(BaseModel):
    source_path: str
    in_sec: float
    out_sec: float


class ExtractFrameRequest(BaseModel):
    source_path: str
    at_sec: float


@router.post("/clip-video")
async def clip_video(req: ClipVideoRequest) -> dict:
    src = _validate_media_source(req.source_path)
    if req.out_sec <= req.in_sec:
        raise HTTPException(400, detail={"error": "invalid_range",
                                         "in_sec": req.in_sec, "out_sec": req.out_sec})

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise HTTPException(500, detail={
            "error": "ffmpeg_missing",
            "hint": "Install ffmpeg and ensure it is on PATH (see cep-premiere/README.md).",
        })

    paths.asset_uploads_dir().mkdir(parents=True, exist_ok=True)
    suffix = src.suffix or ".mp4"
    out_path = paths.asset_uploads_dir() / f"clip_{uuid.uuid4().hex}{suffix}"

    duration = max(0.04, float(req.out_sec) - float(req.in_sec))
    # Re-encode (не -c copy): stream copy ломается на не-keyframe границах и
    # часто даёт пустой первый GOP. libx264+aac короткий клип кодирует быстро.
    # -protocol_whitelist file,crypto,data — даже если что-то проскочит mimo
    # _validate_media_source (например symlink на network mount), ffmpeg
    # откажется работать с tcp/udp/concat/pipe протоколами.
    cmd = [
        ffmpeg, "-y",
        "-protocol_whitelist", "file,crypto,data",
        "-ss", f"{float(req.in_sec):.3f}",
        "-i", str(src),
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate()
    if proc.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(500, detail={
            "error": "ffmpeg_failed",
            "code": proc.returncode,
            "stderr": _sanitize_ffmpeg_stderr(stderr, src),
        })

    return {
        "path": str(out_path),
        "in_sec": req.in_sec,
        "out_sec": req.out_sec,
        "duration_sec": duration,
        "size_bytes": out_path.stat().st_size,
    }


@router.post("/extract-frame")
async def extract_frame(req: ExtractFrameRequest) -> dict:
    """Извлечь один кадр из source-файла в указанный source-relative момент.

    Используется CEP-панелью для Timeline frame: QE DOM frame export сломан на
    части билдов Pr (на user-машине qe.exportFrameJPEG/PNG/TIFF/Targa/DPX молча
    возвращают rv=false без exception и без файла). Поэтому host.jsx находит
    топовый видео-клип под playhead'ом, пересчитывает source-relative секунду
    и зовёт этот endpoint — ffmpeg извлекает кадр напрямую из исходника, минуя
    Pr-рендер.
    """
    src = _validate_media_source(req.source_path)
    if req.at_sec < 0:
        raise HTTPException(400, detail={"error": "invalid_time", "at_sec": req.at_sec})

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise HTTPException(500, detail={
            "error": "ffmpeg_missing",
            "hint": "Install ffmpeg and ensure it is on PATH (see cep-premiere/README.md).",
        })

    paths.asset_uploads_dir().mkdir(parents=True, exist_ok=True)
    out_path = paths.asset_uploads_dir() / f"frame_{uuid.uuid4().hex}.jpg"

    # -ss ПЕРЕД -i = fast seek по keyframes, потом точная декодировка одного
    # кадра. -frames:v 1 = ровно один кадр. -q:v 2 = JPEG visually-lossless.
    # -protocol_whitelist — см. clip_video.
    cmd = [
        ffmpeg, "-y",
        "-protocol_whitelist", "file,crypto,data",
        "-ss", f"{float(req.at_sec):.3f}",
        "-i", str(src),
        "-frames:v", "1",
        "-q:v", "2",
        str(out_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate()
    if proc.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(500, detail={
            "error": "ffmpeg_failed",
            "code": proc.returncode,
            "stderr": _sanitize_ffmpeg_stderr(stderr, src),
        })

    return {
        "path": str(out_path),
        "at_sec": req.at_sec,
        "size_bytes": out_path.stat().st_size,
    }
