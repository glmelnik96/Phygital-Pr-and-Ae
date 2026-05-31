"""Manual live-capture для text-to-video нод Phygital+.

Открывает Chromium с persistent-профилем sidecar'а (тот же, что у
`auth_recon` — логин уже там, повторно логиниться не нужно), пишет HAR со
всеми XHR/Fetch + WS-фреймы в JSONL. Пользователь сам кликает нужные ноды
в Phygital-UI; по нажатию Enter в терминале — закрывает браузер и дампит
storage.

Цель: захватить РЕАЛЬНЫЕ submit-payloads / config_history / outputs для
text-to-video на нодах 74 / 100 / 121, чтобы потом сделать поддержку T2V
в `app/workflows/video_common.py` (новый VideoScenario.T2V + per-node slots).

Запуск:
    cd sidecar
    python -m scripts.recon_t2v

Что нужно сделать в открывшемся Chromium (в любом порядке):
    1. Kling 2.5 Turbo (node 74)
         - duration: 3 sec (минимум)
         - mode: std (дешевле pro)
         - prompt: любой нейтральный (например, "calm desert at sunrise")
         - init_img: ОСТАВИТЬ ПУСТЫМ
         - дождаться полного завершения генерации
    2. Seedance 1.0 Pro (node 100)
         - duration: 3s, resolution: 480p (минимум)
         - prompt: тот же
         - start_img / end_frame / ref_img: ВСЕ ПУСТЫЕ
    3. Kling Omni 2 (node 121)
         - duration: 3s, mode: std
         - prompt: тот же
         - first_frame / last_frame / elements / video: ВСЕ ПУСТЫЕ

Если какая-то нода блокирует submit без init-картинки (кнопка disabled или
ошибка) — это тоже важный сигнал, зафиксируем в HAR попытку. Просто отметь
в терминале какая нода отказалась.

После завершения всех генераций вернись в терминал и нажми Enter.
Дамп будет в `recon-captures/<ts>-t2v-manual/`:
    - phygital.har        — все XHR/Fetch + bodies
    - ws.jsonl            — WebSocket-фреймы
    - storage.json        — cookies + localStorage
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from playwright.async_api import WebSocket, async_playwright

from app.paths import user_data_dir

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


TARGET_URL = "https://app.phygital.plus/"
CAPTURES_ROOT = Path("recon-captures")

TASK_LIST = """
=======================================================================
 MANUAL T2V RECON — задачи в Phygital-UI:

 1) Kling 2.5 Turbo                        (node 74)
       duration=3sec, mode=std, БЕЗ init_img
 2) Seedance 1.0 Pro                       (node 100)
       duration=3s, resolution=480p, БЕЗ start_img/end_frame/ref_img
 3) Kling Omni 2                           (node 121)
       duration=3s, mode=std, БЕЗ first_frame/last_frame/elements/video

 prompt (любой): "a calm slow camera push-in over a still desert at sunrise"

 Если submit заблокирован в UI без init-картинки — попробуй всё равно
 кликнуть, чтобы поймать ошибку в HAR. Если совсем нельзя — пропусти
 и отметь в терминале.

 Когда все три ноды отработали (или отметил пропуски) — вернись сюда и
 нажми Enter.
=======================================================================
"""


async def dump_storage(context, page, path: Path) -> None:
    """Снимаем cookies + localStorage + sessionStorage активной страницы."""
    cookies = await context.cookies()
    try:
        local_storage = await page.evaluate(
            "() => Object.fromEntries(Object.entries(localStorage))"
        )
    except Exception:
        local_storage = {}
    try:
        session_storage = await page.evaluate(
            "() => Object.fromEntries(Object.entries(sessionStorage))"
        )
    except Exception:
        session_storage = {}
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "url": page.url,
        "cookies": cookies,
        "localStorage": local_storage,
        "sessionStorage": session_storage,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Storage dumped -> {path}")


def attach_ws_logger(ws: WebSocket, ws_log_path: Path) -> None:
    """Логируем все WebSocket-фреймы в JSONL (HAR не всегда сохраняет тела)."""
    logger.info(f"WS opened: {ws.url}")

    def write(direction: str, payload) -> None:
        try:
            data = payload if isinstance(payload, str) else f"<binary:{len(payload)}>"
        except Exception:
            data = "<unreadable>"
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "url": ws.url,
            "dir": direction,
            "payload": data,
        }
        with ws_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    ws.on("framesent", lambda p: write("send", p))
    ws.on("framereceived", lambda p: write("recv", p))
    ws.on("close", lambda: logger.info(f"WS closed: {ws.url}"))


async def stdin_wait() -> None:
    """Ждём Enter в stdin без блокировки event loop."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, sys.stdin.readline)


async def main() -> None:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    save_dir = CAPTURES_ROOT / f"{ts}-t2v-manual"
    save_dir.mkdir(parents=True, exist_ok=True)

    har_path = save_dir / "phygital.har"
    ws_log_path = save_dir / "ws.jsonl"
    storage_path = save_dir / "storage.json"

    profile_dir = user_data_dir()
    profile_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"profile -> {profile_dir}")
    logger.info(f"HAR     -> {har_path}")
    logger.info(f"WS      -> {ws_log_path}")
    logger.info(f"STOR    -> {storage_path}")

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            viewport={"width": 1440, "height": 900},
            record_har_path=str(har_path),
            record_har_content="embed",
            record_har_mode="full",
            args=["--disable-blink-features=AutomationControlled"],
        )

        # WS-перехватчик на все будущие страницы
        context.on(
            "page",
            lambda p: p.on("websocket", lambda ws: attach_ws_logger(ws, ws_log_path)),
        )

        page = context.pages[0] if context.pages else await context.new_page()
        page.on("websocket", lambda ws: attach_ws_logger(ws, ws_log_path))

        await page.goto(TARGET_URL, wait_until="domcontentloaded")

        print(TASK_LIST)

        await stdin_wait()

        # Берём актуальную активную страницу — юзер мог переключиться
        active = context.pages[-1] if context.pages else page
        try:
            await dump_storage(context, active, storage_path)
        except Exception as e:
            logger.error(f"Storage dump failed: {e}")

        await context.close()
        logger.success(f"Done. Captures saved to {save_dir.absolute()}")
        print(f"\nResult: {save_dir.absolute()}")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | {message}")
    asyncio.run(main())
