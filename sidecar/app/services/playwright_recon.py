"""Playwright headed bootstrap для Phygital-сессии.

Триггерится из POST /auth/recon. Поведение:
  1. Запускает Chromium с persistent context в %LOCALAPPDATA%\\PhygitalStudio\\user_data\\
  2. Открывает https://app.phygital.plus/
  3. Ждёт пока юзер залогинится (детектится по наличию st-access-token cookie).
  4. Polling раз в 1с — как только cookie появилась, дампит session.json и закрывает браузер.
  5. Если за timeout_sec не залогинились — закрывает без save.

В отличие от Phygital-bot/recon/capture.py — никакого HAR/WS-логирования, никакого stdin.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from playwright.async_api import async_playwright

from app.services.session_storage import write_secure_json

TARGET_URL = "https://app.phygital.plus/"
ACCESS_COOKIE = "st-access-token"
DEFAULT_TIMEOUT_SEC = 600  # 10 минут на логин
MIN_FRESH_TTL_SEC = 60  # сколько минимум должно остаться у JWT, чтобы считать его «свежим»


def _jwt_ttl_seconds(token: str) -> int | None:
    """Парсим exp из JWT payload. None если токен битый/без exp."""
    if not token or token.count(".") < 2:
        return None
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = int(json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0))
    except Exception:
        return None
    if not exp:
        return None
    return exp - int(time.time())


class ReconError(Exception):
    pass


async def run_recon(
    *,
    user_data_dir: Path,
    session_file: Path,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> None:
    """Запускает Chromium, ждёт логина, сохраняет session.json.

    Raises ReconError если за timeout пользователь не залогинился.
    """
    user_data_dir.mkdir(parents=True, exist_ok=True)
    session_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Recon: opening {TARGET_URL} (timeout {timeout_sec}s)")

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            viewport={"width": 1440, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )

        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(TARGET_URL, wait_until="domcontentloaded")

        # Persistent context может хранить протухший st-access-token от прошлой
        # сессии. Если такой найден — логируем один раз и ждём СВЕЖИЙ.
        stale_warned = False
        deadline = asyncio.get_event_loop().time() + timeout_sec
        while asyncio.get_event_loop().time() < deadline:
            cookies = await context.cookies()
            access = next((c for c in cookies if c.get("name") == ACCESS_COOKIE), None)
            if access and access.get("value"):
                ttl = _jwt_ttl_seconds(access["value"])
                if ttl is not None and ttl > MIN_FRESH_TTL_SEC:
                    logger.info(f"Recon: detected fresh st-access-token (ttl={ttl}s), dumping session")
                    _write_session_dump(session_file, cookies, page.url)
                    await context.close()
                    return
                if not stale_warned:
                    logger.warning(
                        f"Recon: stale st-access-token in persistent profile (ttl={ttl}); waiting for fresh login"
                    )
                    stale_warned = True
            await asyncio.sleep(1.0)

        await context.close()
        raise ReconError(f"Recon timeout after {timeout_sec}s -- user did not log in")


def _write_session_dump(path: Path, cookies: list[dict], url: str) -> None:
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "cookies": cookies,
    }
    # Шифрованная (DPAPI на Win) + атомарная запись — см. session_storage.py
    # для деталей формата и mitigations (H3, H12).
    write_secure_json(path, payload)
    logger.info(f"Session dumped -> {path}")
