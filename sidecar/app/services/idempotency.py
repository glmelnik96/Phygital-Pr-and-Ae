"""Idempotency-Key store (M8).

Минимальная реализация для POST /jobs: in-memory TTL-кэш {key → (request_hash,
status, response_body)}. Повторный POST с тем же Idempotency-Key и тем же телом
возвращает закэшированный ответ. Несовпадение тела → 422 (классический контракт
из draft-ietf-httpapi-idempotency-key-header).

Только POST /jobs — для GET/DELETE идемпотентность по семантике HTTP уже есть.
TTL — 24h: дольше нет смысла, короче рискуем повторными списаниями кредитов при
ретраях с реконнектом сети.

В памяти, не персистится. Перезагрузка sidecar обнуляет кэш — клиент не должен
ретраить через рестарт sidecar'а с тем же ключом (нечестно, но MVP).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any


_TTL_SEC = 24 * 60 * 60


@dataclass
class _Entry:
    request_hash: str
    status_code: int
    response_body: dict[str, Any]
    expires_at: float


def hash_request_body(body: Any) -> str:
    """SHA256 канонизированного JSON тела. Используется для conflict detection."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class IdempotencyStore:
    """Thread-safe (через asyncio.Lock) TTL-кэш для idempotency keys."""

    def __init__(self, ttl_sec: int = _TTL_SEC) -> None:
        self._ttl = ttl_sec
        self._entries: dict[str, _Entry] = {}
        self._lock = asyncio.Lock()

    async def lookup(self, key: str, request_hash: str) -> tuple[str, dict] | None:
        """Returns ('hit', response_body), ('conflict', {}), or None for miss."""
        async with self._lock:
            self._sweep_expired_locked()
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.request_hash != request_hash:
                return ("conflict", {})
            return ("hit", entry.response_body)

    async def store(self, key: str, request_hash: str, status_code: int, body: dict) -> None:
        async with self._lock:
            self._entries[key] = _Entry(
                request_hash=request_hash,
                status_code=status_code,
                response_body=body,
                expires_at=time.monotonic() + self._ttl,
            )

    def _sweep_expired_locked(self) -> None:
        now = time.monotonic()
        expired = [k for k, e in self._entries.items() if e.expires_at < now]
        for k in expired:
            del self._entries[k]
