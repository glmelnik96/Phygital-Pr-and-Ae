"""Тесты log-redaction patcher'а (H4).

Цель: убедиться что любая попытка logger.info(...) с JWT/Bearer/cookie/
зарегистрированной секрет-строкой записывает в sink уже <redacted-*>,
а не открытый секрет.
"""
from __future__ import annotations

import io
import pytest
from loguru import logger

from app.services.log_redaction import (
    _redact_text,
    install_redaction,
    register_secret,
)


# Реальный пример JWT-структуры (фейковая подпись, но валидный паттерн).
_SAMPLE_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ"
    ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
)


# ── _redact_text (unit) ──────────────────────────────────────────────────────


def test_redacts_jwt():
    text = f"got token {_SAMPLE_JWT} from server"
    out = _redact_text(text)
    assert _SAMPLE_JWT not in out
    assert "<redacted-jwt>" in out


def test_redacts_bearer_header():
    text = "Authorization: Bearer abc123.def456.ghi789xyz"
    out = _redact_text(text)
    assert "abc123.def456.ghi789xyz" not in out
    assert "Bearer <redacted>" in out


def test_redacts_bearer_case_insensitive():
    text = 'sent header bearer ABC.DEF.GHI'
    out = _redact_text(text)
    assert "ABC.DEF.GHI" not in out


def test_redacts_cookie_value_in_dict():
    text = '{"name": "st-refresh-token", "value": "supersecret123"}'
    out = _redact_text(text)
    assert "supersecret123" not in out
    assert "<redacted-cookie>" in out


def test_does_not_touch_innocent_text():
    text = "starting sidecar at port 8765, loaded 3 nodes"
    assert _redact_text(text) == text


def test_redacts_registered_secret():
    register_secret("super-long-sidecar-token-value-here-xxxxxx")
    text = "loaded token super-long-sidecar-token-value-here-xxxxxx for client"
    out = _redact_text(text)
    assert "super-long-sidecar-token-value-here-xxxxxx" not in out
    assert "<redacted>" in out


def test_register_secret_ignores_short_strings():
    register_secret("abc")  # too short
    text = "abc xyz abc"
    # NOT redacted — too short to be a credential, also would corrupt logs.
    assert "abc" in _redact_text(text)


def test_redacts_multiple_in_one_message():
    text = f"first {_SAMPLE_JWT} and Bearer xxx.yyy.zzz end"
    out = _redact_text(text)
    assert _SAMPLE_JWT not in out
    assert "xxx.yyy.zzz" not in out


# ── integration: patcher mutates loguru records ─────────────────────────────


def test_install_redaction_patches_sink_output():
    """Логируем JWT через настоящий loguru — в sink приходит уже redacted."""
    install_redaction()
    buf = io.StringIO()
    sink_id = logger.add(buf, level="DEBUG", format="{message}")
    try:
        logger.info(f"access token = {_SAMPLE_JWT}")
        logger.info("Authorization: Bearer some.real.token1234567")
        output = buf.getvalue()
    finally:
        logger.remove(sink_id)
    assert _SAMPLE_JWT not in output
    assert "some.real.token1234567" not in output
    assert "<redacted-jwt>" in output or "Bearer <redacted>" in output


def test_install_redaction_idempotent():
    """Повторный install не должен ломаться (loguru reconfigure)."""
    install_redaction()
    install_redaction()  # не падает
    install_redaction()
