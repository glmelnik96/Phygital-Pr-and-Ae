"""Passive recon: открываем Chromium, ты юзаешь Phygital+ в UI как обычно,
скрипт пишет ВСЁ — HTTP, WebSocket, storage. Никаких автоматических действий
со стороны скрипта, никакой логики «один сценарий».

Адаптация capture.py из Phygital-bot (проверен, гонялся 2026-05-13 и 2026-05-17),
с поправкой на наш проект: вывод в cwd (а не в sandbox Claude), отдельный
recon-user-data чтобы не конфликтовать с user_data сайдкара.

ЗАПУСК (из своего PowerShell, НЕ из агентского терминала):

    cd <repo>\\sidecar
    .venv\\Scripts\\activate
    python -m scripts.recon_capture

ФЛОУ:
  1. Откроется Chromium. В первый запуск — залогинься в Phygital+ (сохранится в
     ./recon-user-data/, в следующие сессии логин подхватится).
  2. Делай ЛЮБОЕ количество генераций ЛЮБЫХ нод — UI-кликами, как обычно.
     Скрипт молча пишет всё что происходит.
  3. Когда закончил — вернись в терминал, нажми Enter. Скрипт дампнет storage
     и аккуратно закроет браузер.

ВЫВОД (в ./recon-captures/<timestamp>/):
  phygital.har         — все XHR/Fetch с request/response (тела embed)
  ws.jsonl             — все WebSocket-фреймы (send + recv), по строке на фрейм
  storage.json         — cookies + localStorage + sessionStorage финальные
  meta.json            — стартовое время, URL, версия Chromium

ОПЦИИ:
  --out DIR            корневая папка для дампов (default: ./recon-captures)
  --user-data DIR      где хранить persistent Chromium-профиль (default: ./recon-user-data)
  --url URL            стартовая страница (default: https://app.phygital.plus/)
  --headless           без окна (бесполезно для ручного рекона, но удобно для smoke)
  --no-har             отключить HAR (если очень-очень тяжёлые сессии)

АНАЛИЗ ПОСЛЕ:
  - HAR открывается в Chrome DevTools (правый клик → Save as HAR → Drag & drop в Network tab)
  - ws.jsonl грепается обычным jq / grep'ом по task_id, status, etc
  - storage.json содержит свежий session (можно скопировать как session.json)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from playwright.async_api import async_playwright, WebSocket

TARGET_URL_DEFAULT = "https://app.phygital.plus/"


async def dump_storage(context, page, path: Path) -> None:
    cookies = await context.cookies()
    try:
        local_storage = await page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")
    except Exception:
        local_storage = {}
    try:
        session_storage = await page.evaluate("() => Object.fromEntries(Object.entries(sessionStorage))")
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
    logger.info(f"storage  → {path}")


def attach_ws_logger(ws: WebSocket, ws_log_path: Path) -> None:
    logger.info(f"WS opened: {ws.url}")

    def write(direction: str, payload) -> None:
        try:
            data = payload if isinstance(payload, str) else f"<binary:{len(payload)}>"
        except Exception:
            data = "<unreadable>"
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "url": ws.url,
            "dir": direction,
            "payload": data,
        }
        with ws_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    ws.on("framesent", lambda p: write("send", p))
    ws.on("framereceived", lambda p: write("recv", p))
    ws.on("close", lambda: logger.info(f"WS closed: {ws.url}"))


async def stdin_wait() -> None:
    """Ждём Enter в stdin без блока event loop."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, sys.stdin.readline)


async def main() -> None:
    ap = argparse.ArgumentParser(description="Passive Phygital+ recon — open Chromium, capture all")
    ap.add_argument("--out", default="./recon-captures", help="root dir for dumps (default: ./recon-captures)")
    ap.add_argument("--user-data", default="./recon-user-data", help="persistent Chromium profile dir")
    ap.add_argument("--url", default=TARGET_URL_DEFAULT, help=f"start URL (default: {TARGET_URL_DEFAULT})")
    ap.add_argument("--headless", action="store_true", help="run headless (not useful for manual recon)")
    ap.add_argument("--no-har", action="store_true", help="disable HAR recording")
    args = ap.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_root = Path(args.out).expanduser().resolve() / ts
    out_root.mkdir(parents=True, exist_ok=True)
    user_data = Path(args.user_data).expanduser().resolve()
    user_data.mkdir(parents=True, exist_ok=True)

    har_path = out_root / "phygital.har"
    ws_log_path = out_root / "ws.jsonl"
    storage_path = out_root / "storage.json"
    meta_path = out_root / "meta.json"

    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | {message}")

    logger.info(f"output dir: {out_root}")
    logger.info(f"user data : {user_data}")
    if not args.no_har:
        logger.info(f"HAR       → {har_path}")
    logger.info(f"WS        → {ws_log_path}")
    logger.info(f"storage   → {storage_path}")

    async with async_playwright() as pw:
        launch_kwargs: dict = {
            "user_data_dir": str(user_data),
            "headless": args.headless,
            "viewport": {"width": 1440, "height": 900},
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if not args.no_har:
            launch_kwargs["record_har_path"] = str(har_path)
            launch_kwargs["record_har_content"] = "embed"
            launch_kwargs["record_har_mode"] = "full"

        context = await pw.chromium.launch_persistent_context(**launch_kwargs)

        # WS-логгер навешиваем на любые новые pages в контексте
        context.on("page", lambda p: p.on("websocket", lambda ws: attach_ws_logger(ws, ws_log_path)))

        page = context.pages[0] if context.pages else await context.new_page()
        page.on("websocket", lambda ws: attach_ws_logger(ws, ws_log_path))

        # meta
        meta_path.write_text(json.dumps({
            "started_at": datetime.now(timezone.utc).isoformat(),
            "url": args.url,
            "headless": args.headless,
            "har_enabled": not args.no_har,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

        await page.goto(args.url, wait_until="domcontentloaded")

        print("\n" + "=" * 70)
        print(" Phygital+ открыт. Делай ЛЮБОЕ количество генераций любых нод.")
        print(" Скрипт молча пишет HAR + WS + storage.")
        print(" Когда закончишь — вернись сюда и нажми Enter.")
        print("=" * 70 + "\n")

        await stdin_wait()

        active = context.pages[-1] if context.pages else page
        try:
            await dump_storage(context, active, storage_path)
        except Exception as e:
            logger.error(f"storage dump failed: {e}")

        # финальный meta-update
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["finished_at"] = datetime.now(timezone.utc).isoformat()
        meta["final_url"] = active.url
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        await context.close()
        logger.success(f"done. all captures in {out_root}")


if __name__ == "__main__":
    asyncio.run(main())
