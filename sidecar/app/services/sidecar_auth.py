"""Sidecar HTTP authentication — shared-secret token + ASGI middleware.

**Зачем.** Sidecar слушает 127.0.0.1:8765 без какой-либо аутентификации. На
многопользовательской машине или при открытой в браузере вкладке злоумышленник
может POST'ить /jobs (списывая Phygital-кредиты), GET /jobs/X/download (читая
произвольные результаты пользователя), DELETE /assets, или POST /auth/recon
(всплывающий Chromium поверх рабочего стола). Это **C5** в audit-отчёте.

**Как.**

1. При первом старте sidecar генерирует cryptographically secure random token и
   сохраняет в `<app_data>/sidecar.token` (chmod 0o600 на POSIX). Win полагается
   на ACL родительской AppData-папки (per-user).
2. ASGI-middleware на каждый HTTP-запрос требует header
   `X-Phygital-Sidecar-Token: <token>`. Сравнение через `hmac.compare_digest`
   чтобы избежать timing-leak.
3. Allowlist: `/health` остаётся открытым, чтобы UI panel'а мог дёрнуть его до
   того как прочитает токен с диска (UX-bootstrap), и чтобы внешние health
   probe (Pr extension manager) работали без секрета.
4. CEP-панель читает токен через `require('fs')` из той же `<app_data>` (на
   обеих ОС путь воспроизводится в `cep-premiere/client/lib/sidecar_token.js`).

При ротации токена (удалили sidecar.token и рестарт sidecar'а) панель должна
быть перезагружена — она кеширует токен в памяти. На MVP-этапе это
приемлемо; для V2 — добавить /auth/token-rotated event и hot-reload.
"""
from __future__ import annotations

import hmac
import os
import secrets
import sys
from pathlib import Path

from loguru import logger
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

TOKEN_HEADER = "x-phygital-sidecar-token"
# Эндпоинты, доступные без токена. /health — UI bootstrap; ничего сенситивного
# не отдаёт (active_jobs count + jwt_ttl). Всё остальное — за стеной.
PUBLIC_PATHS: frozenset[str] = frozenset({"/health"})


def load_or_create_token(path: Path) -> str:
    """Прочитать токен из файла, иначе создать новый.

    На POSIX выставляет 0600 при создании. На Windows — relies on AppData ACL
    (per-user читает только владелец и SYSTEM/Administrators).

    Если файл существует, но пустой/мусор — пере-генерирует.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        existing = ""
    except OSError as e:
        logger.warning(f"sidecar_auth: failed to read token file {path}: {e}; regenerating")
        existing = ""

    if existing and len(existing) >= 16:
        return existing

    token = secrets.token_urlsafe(32)
    # Атомарная запись: tmp + rename — чтобы не оставить полу-записанный файл
    # при крэше уровня OS.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(token, encoding="utf-8")
    try:
        if sys.platform != "win32":
            os.chmod(tmp, 0o600)
    except OSError as e:
        logger.warning(f"sidecar_auth: chmod 0600 failed on {tmp}: {e}")
    os.replace(tmp, path)
    logger.info(f"sidecar_auth: new token generated → {path}")
    return token


class SidecarAuthMiddleware:
    """Pure ASGI middleware — проверяет shared-secret header.

    Реализован как pure ASGI (а не Starlette BaseHTTPMiddleware) ради
    производительности: BaseHTTPMiddleware врапит каждый запрос в дополнительный
    async iterator и плохо ведёт себя со streaming responses (FileResponse в
    /jobs/{id}/download).
    """

    def __init__(self, app: ASGIApp, token: str, public_paths: frozenset[str] = PUBLIC_PATHS) -> None:
        if not token:
            raise ValueError("SidecarAuthMiddleware requires a non-empty token")
        self._app = app
        self._token = token
        self._public = public_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            # WebSocket / lifespan — pass-through. Если в будущем добавим WS —
            # сюда же добавить auth.
            await self._app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if path in self._public:
            await self._app(scope, receive, send)
            return

        provided = ""
        for name, value in scope.get("headers", []) or []:
            if name == TOKEN_HEADER.encode("ascii"):
                try:
                    provided = value.decode("ascii", errors="replace")
                except UnicodeDecodeError:
                    provided = ""
                break

        if not provided or not hmac.compare_digest(provided, self._token):
            response = JSONResponse(
                {"error": "unauthorized", "hint": "missing or invalid X-Phygital-Sidecar-Token"},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        await self._app(scope, receive, send)
