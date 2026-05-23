"""Standalone bootstrap для Phygital-сессии (вне sidecar HTTP-сервера).

В отличие от `python -m scripts.cli auth login` — этот скрипт НЕ требует
запущенного sidecar'а. Импортирует `run_recon` напрямую и пишет session.json
по тому же пути, что и боевой sidecar (через app.paths.resolve_app_data).

Используется в:
  - `scripts/install_mac.sh` (финальный шаг установщика)
  - первичная инициализация Windows-разработчика (см. docs/INSTALL_WINDOWS.md)

Запуск:
  cd sidecar && python -m scripts.auth_recon [--timeout SEC]
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from app.paths import session_file, user_data_dir
from app.services.playwright_recon import ReconError, run_recon

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


async def _main(timeout_sec: int) -> int:
    sf = session_file()
    ud = user_data_dir()
    print(f"session  → {sf}")
    print(f"profile  → {ud}")
    print(f"timeout  → {timeout_sec}s")
    print("Открывается Chromium. Залогинься в Phygital+ обычным образом.")
    try:
        await run_recon(user_data_dir=ud, session_file=sf, timeout_sec=timeout_sec)
    except ReconError as e:
        print(f"recon failed: {e}", file=sys.stderr)
        return 1
    print(f"OK — session captured at {sf}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Phygital+ login bootstrap (standalone)")
    ap.add_argument("--timeout", type=int, default=600, help="seconds to wait for login (default 600)")
    args = ap.parse_args()
    return asyncio.run(_main(args.timeout))


if __name__ == "__main__":
    sys.exit(main())
