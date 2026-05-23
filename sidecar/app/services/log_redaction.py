"""Скрытие чувствительных значений в логах sidecar'а (H4).

Раньше при DEBUG/INFO логировании на консоль и в sidecar.log могли утекать:
- значение `st-access-token` cookie (JWT) — bearer-credential для Phygital API;
- значение `st-refresh-token` cookie — позволяет восстановить access-token
  без логина;
- sidecar-token из %LOCALAPPDATA%\\PhygitalStudio\\sidecar.token (если бы
  кто-то по ошибке его залогировал).

Любая из этих утечек = полный доступ к платному аккаунту юзера. Лог-файл
лежит в %LOCALAPPDATA% и тоже не защищён DPAPI, поэтому если у атакующего
есть локальный доступ под нашим юзером — он прочтёт и .log тоже.

Защита здесь — best-effort обфускация: патчим loguru-record["message"]
через `logger.configure(patcher=...)` ДО форматирования. Так редакция
работает и для stderr-sink'а, и для file-sink'а.

Что редактируется:
1. JWT-токены (3 base64-сегмента через точки, начинаются с `eyJ`) →
   `<redacted-jwt>`. Покрывает st-access-token и любой Authorization-header.
2. Контент cookies-value для known credential-cookie-names →
   `<redacted-cookie>`. Покрывает st-refresh-token + случайный print(cookies).
3. Exact-match строки, добавленные через `register_secret(value)` →
   `<redacted>`. Используется для sidecar_token на старте.

Что НЕ покрывается:
- Если кто-то base64'нет JWT перед логированием — не поймаем (но и не должны).
- Сильно искажённые форматы (например, токен через перенос строки) — не поймаем.

Эта защита — defence-in-depth, основной защитой остаётся «не логировать
secret'ы в принципе» (см. предписания в коде).
"""
from __future__ import annotations

import re
from typing import Iterable

from loguru import logger

# JWT: 3 base64url-сегмента через точки. st-access-token начинается с eyJ
# (header `{"alg":...}`). Минимум 20 символов в каждом сегменте — чтобы
# не цеплять случайные слова с точками.
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")

# Bearer <token> в Authorization-header
_BEARER_RE = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._\-]+")

# Credential cookies (имя в формате list[dict] или подобном). Берём только
# те cookie-имена, которые мы знаем как credential'ы Phygital. Для них
# редактим значение `value`, попадающее в окно 200 символов после name'а
# (этого достаточно для типичных JSON-сериализаций cookie-дикта).
_COOKIE_NAMES = ("st-access-token", "st-refresh-token", "sFrontToken")
_COOKIE_VALUE_RES = [
    re.compile(rf'"{name}"[\s\S]{{0,200}}?"value"\s*:\s*"[^"]*"')
    for name in _COOKIE_NAMES
]
_VALUE_FIELD_RE = re.compile(r'"value"\s*:\s*"[^"]*"')


_extra_secrets: set[str] = set()


def register_secret(value: str) -> None:
    """Добавить exact-match строку, которую надо редактить в логах.

    Используется на старте для sidecar_token. Пустые/слишком короткие
    значения игнорируются — чтобы случайно не вырезать пол-лога.
    """
    if isinstance(value, str) and len(value) >= 8:
        _extra_secrets.add(value)


def register_secrets(values: Iterable[str]) -> None:
    for v in values:
        register_secret(v)


def _redact_text(text: str) -> str:
    if not text:
        return text
    out = _JWT_RE.sub("<redacted-jwt>", text)
    out = _BEARER_RE.sub(r"\1<redacted>", out)
    for rx in _COOKIE_VALUE_RES:
        out = rx.sub(
            lambda m: _VALUE_FIELD_RE.sub('"value": "<redacted-cookie>"', m.group(0)),
            out,
        )
    if _extra_secrets:
        for secret in _extra_secrets:
            if secret and secret in out:
                out = out.replace(secret, "<redacted>")
    return out


def _patcher(record: dict) -> None:
    """loguru patcher — мутирует record['message'] перед форматированием.

    record["message"] — это уже отформатированный {message}, не raw kwargs.
    Если кто-то логирует через logger.info(f"token={tok}") — здесь будет
    готовая строка с tok в открытую, мы её редактим.
    """
    msg = record.get("message")
    if not isinstance(msg, str):
        return
    redacted = _redact_text(msg)
    if redacted is not msg:
        record["message"] = redacted


def install_redaction() -> None:
    """Регистрирует patcher глобально. Идемпотентно (loguru пере-конфигурируется)."""
    logger.configure(patcher=_patcher)
