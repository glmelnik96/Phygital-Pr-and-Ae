"""Тонкая обёртка над vendored refresh_session(): убирает bot-specific
fallback `_find_fresher_recon_dump`, который смотрит в `Phygital-bot/recon/captures/`.

Sidecar не использует recon-fallback — если refresh не прошёл, мы поднимаем
auth_expired и панель показывает кнопку "войти ещё раз" (POST /auth/recon).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from app.phygital_client.auth import RefreshError, refresh_session
from app.phygital_client.session import Session
from app.services.session_storage import read_secure_json, write_secure_json


class SidecarSessionManager:
    """Совместим с интерфейсом PhygitalClient (нужен .refresh(session)).

    Persisting cookies через session_storage — DPAPI на Windows, chmod 0o600
    на POSIX, атомарная запись везде (см. H3, H12).
    """

    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        self._refresh_lock = asyncio.Lock()

    def load(self) -> Session | None:
        data = read_secure_json(self.storage_path)
        if data is None:
            if not self.storage_path.exists():
                logger.warning(f"Session file not found: {self.storage_path}")
            return None
        s = Session(cookies=data.get("cookies", []))
        captured = data.get("captured_at")
        if captured:
            try:
                s.captured_at = datetime.fromisoformat(captured.replace("Z", "+00:00"))
            except Exception:
                pass
        if not s.access_token:
            logger.warning("Session loaded but st-access-token missing")
        return s

    def save(self, session: Session) -> None:
        session.captured_at = datetime.now(timezone.utc)
        payload = {
            "cookies": session.cookies,
            "captured_at": session.captured_at.isoformat(),
        }
        write_secure_json(self.storage_path, payload)
        logger.info(f"Session saved -> {self.storage_path}")

    async def refresh(self, session: Session) -> Session:
        """Один refresh, под локом, без recon-fallback'а."""
        async with self._refresh_lock:
            try:
                await refresh_session(session)
            except RefreshError as e:
                logger.warning(f"refresh failed: {e}")
                raise
            self.save(session)
            return session
