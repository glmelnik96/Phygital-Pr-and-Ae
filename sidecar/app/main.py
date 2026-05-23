"""Phygital Studio sidecar — FastAPI app + uvicorn entrypoint.

Состояние живёт в app.state:
  - settings: Settings
  - session_bootstrap: SessionBootstrap
  - task_registry: TaskRegistry
  - job_runner: JobRunner
"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from loguru import logger

from app import paths
from app.config import Settings


def build_app() -> FastAPI:
    """Build FastAPI app. Используется и в тестах, и в run()."""
    settings = Settings()
    paths.ensure_dirs()

    # Импорты ленивые, чтобы тесты paths могли мокать
    from app.routers.health import router as health_router
    from app.routers.auth import router as auth_router
    from app.routers.nodes import router as nodes_router
    from app.routers.jobs import router as jobs_router
    from app.routers.assets import router as assets_router
    from app.routers.clips import router as clips_router
    from app.routers.account import router as account_router
    from app.services.session_bootstrap import SessionBootstrap
    from app.services.task_registry import TaskRegistry
    from app.services.job_runner import JobRunner
    from app.services.asset_cache import AssetCache
    from app.services.downloader import download_urls
    from app.phygital_client.api import PhygitalClient
    from app.workflows import NODES

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Startup
        bs = SessionBootstrap(
            session_file=paths.session_file(),
            jwt_min_ttl_sec=settings.jwt_min_ttl_sec,
        )
        await bs.preflight()
        _app.state.session_bootstrap = bs

        reg = TaskRegistry(jsonl_path=paths.jobs_jsonl())
        await reg.restore()
        _app.state.task_registry = reg

        asset_cache = AssetCache(jsonl_path=paths.asset_cache_path())
        await asset_cache.restore()
        _app.state.asset_cache = asset_cache

        async def _get_client():
            """Фабрика PhygitalClient с актуальной сессией.

            ВАЖНО: возвращает уже open'нутый async-context. Caller обязан
            закрыть через `async with`. JobRunner ожидает что workflow примет
            client и сам управляет lifecycle через `async with`.

            Для простоты MVP — возвращаем уже __aenter__'нутый клиент, а runner
            забудет про close (PhygitalClient внутри держит httpx.AsyncClient,
            который GC закроет; не идеально, но для MVP норм).
            TODO sub-project D: переписать на правильный async-context handoff.
            """
            if bs.session is None or not bs.session.access_token:
                raise RuntimeError("no_session")
            c = PhygitalClient(session=bs.session, session_manager=bs.manager)
            await c.__aenter__()
            return c

        runner = JobRunner(
            registry=reg,
            downloads_root=paths.downloads_dir(),
            max_concurrent=settings.phygital_max_concurrent,
            nodes=NODES,
            get_client=_get_client,
            download_urls_fn=download_urls,
            asset_cache=asset_cache,
            max_concurrent_video=settings.phygital_max_concurrent_video,
            poll_interval=settings.poll_interval_sec,
        )
        _app.state.job_runner = runner
        _app.state.get_client = _get_client

        _app.state.settings = settings

        logger.info(f"Sidecar started: http://{settings.host}:{settings.port}")
        yield
        logger.info("Sidecar shutting down")

    app = FastAPI(title="Phygital Studio Sidecar", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(nodes_router)
    app.include_router(jobs_router)
    app.include_router(assets_router)
    app.include_router(clips_router)
    app.include_router(account_router)
    return app


def run() -> None:
    settings = Settings()
    _configure_logging(settings)
    uvicorn.run(
        "app.main:build_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_config=None,  # используем loguru
    )


def _configure_logging(settings: Settings) -> None:
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level, format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}")
    log_path = paths.logs_dir() / "sidecar.log"
    paths.logs_dir().mkdir(parents=True, exist_ok=True)
    logger.add(
        log_path,
        level=settings.log_level,
        rotation=f"{settings.log_rotation_mb} MB",
        retention=settings.log_retain,
        encoding="utf-8",
    )


if __name__ == "__main__":
    run()
