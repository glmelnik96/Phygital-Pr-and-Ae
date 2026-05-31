"""Тесты EnhancerService — wrapper template + retry.

Wrapper template (V1.2 critical fix): user_prompt передаётся в Gemini Text
не сырым, а обёрнутым в инструкцию «прочитай attached document как
system_prompt». Без этого .md просто игнорируется или пересказывается —
системные промпты не применяются.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.enhancer import (
    ENHANCER_TEXT_PROMPT_TEMPLATE,
    EnhancerError,
    EnhancerService,
    _strip_meta_wrappers,
)


# ── 1. Wrapper template ─────────────────────────────────────────────────────

def test_wrapper_template_contains_user_prompt():
    out = ENHANCER_TEXT_PROMPT_TEMPLATE.format(user_prompt="hello world")
    assert "hello world" in out


def test_wrapper_template_marks_user_section():
    """Маркеры USER DRAFT PROMPT критичны: без них Gemini смешивает
    инструкции с юзер-промптом."""
    out = ENHANCER_TEXT_PROMPT_TEMPLATE.format(user_prompt="x")
    assert "--- USER DRAFT PROMPT ---" in out
    assert "--- END USER DRAFT PROMPT ---" in out


def test_wrapper_template_instructs_about_document():
    """Должно явно указать модели читать прикреплённый документ как
    system_prompt — иначе Gemini Text трактует .md как контекст и
    игнорирует инструкции."""
    out = ENHANCER_TEXT_PROMPT_TEMPLATE.format(user_prompt="x")
    low = out.lower()
    assert "attached document" in low or "instructions" in low


def test_wrapper_template_demands_only_prompt_in_reply():
    """Контракт: «ONLY the enhanced prompt» — без префиксов/preamble."""
    out = ENHANCER_TEXT_PROMPT_TEMPLATE.format(user_prompt="x")
    low = out.lower()
    assert "only" in low and "enhanced prompt" in low


# ── 2. EnhancerService.enhance wires wrapper into Gemini Text ───────────────

@pytest.mark.asyncio
async def test_enhance_passes_wrapped_prompt_to_gemini():
    """Критично: enhancer.py должен передавать ОБЁРНУТЫЙ prompt в
    GeminiTextWorkflow.run_text, а не сырой user_prompt."""
    client = MagicMock()
    svc = EnhancerService(client)

    fake_job = MagicMock()
    fake_job.status = "completed"
    fake_job.result_text = "ENHANCED text"
    fake_job.error = None
    fake_job.raw = {}

    fake_wf = MagicMock()
    fake_wf.run_text = AsyncMock(return_value=fake_job)

    with patch("app.services.enhancer.GeminiTextWorkflow", return_value=fake_wf), \
         patch("app.services.enhancer.get_enhancer_doc_for_node",
               new=AsyncMock(return_value=12345)):
        result = await svc.enhance(
            node_id=94,  # Nano Banana — supported
            user_prompt="девушка идёт по пляжу",
        )

    assert result.enhanced_prompt == "ENHANCED text"
    fake_wf.run_text.assert_awaited_once()
    kwargs = fake_wf.run_text.call_args.kwargs
    # Wrapper применён — сырой user_prompt не должен быть передан без обёртки.
    assert kwargs["prompt"] != "девушка идёт по пляжу"
    assert "девушка идёт по пляжу" in kwargs["prompt"]
    assert "--- USER DRAFT PROMPT ---" in kwargs["prompt"]
    # И system-prompt .md прикладывается как document.
    assert kwargs["document_ids"] == [12345]


@pytest.mark.asyncio
async def test_enhance_rejects_empty_prompt():
    svc = EnhancerService(MagicMock())
    with pytest.raises(EnhancerError, match="empty"):
        await svc.enhance(node_id=94, user_prompt="   ")


@pytest.mark.asyncio
async def test_enhance_rejects_unsupported_node():
    svc = EnhancerService(MagicMock())
    with pytest.raises(EnhancerError, match="not configured"):
        await svc.enhance(node_id=87, user_prompt="x")  # Topaz — нет prompt'а


@pytest.mark.asyncio
async def test_enhance_propagates_image_context():
    """init_img_ids/dims должны попадать в Gemini Text как image-context —
    иначе i2i/i2v энхансер не видит референс."""
    client = MagicMock()
    svc = EnhancerService(client)

    fake_job = MagicMock(status="completed", result_text="E", error=None, raw={})
    fake_wf = MagicMock()
    fake_wf.run_text = AsyncMock(return_value=fake_job)

    with patch("app.services.enhancer.GeminiTextWorkflow", return_value=fake_wf), \
         patch("app.services.enhancer.get_enhancer_doc_for_node",
               new=AsyncMock(return_value=99)):
        await svc.enhance(
            node_id=100,
            user_prompt="walk",
            init_img_ids=[111],
            init_img_dims=[{"width": 1024, "height": 768}],
        )

    kwargs = fake_wf.run_text.call_args.kwargs
    assert kwargs["init_img_ids"] == [111]
    assert kwargs["init_img_dims"] == [{"width": 1024, "height": 768}]


@pytest.mark.asyncio
async def test_enhance_raises_on_failed_job():
    svc = EnhancerService(MagicMock())
    fake_job = MagicMock(status="failed", result_text="", error="timeout", raw={})
    fake_wf = MagicMock()
    fake_wf.run_text = AsyncMock(return_value=fake_job)

    with patch("app.services.enhancer.GeminiTextWorkflow", return_value=fake_wf), \
         patch("app.services.enhancer.get_enhancer_doc_for_node",
               new=AsyncMock(return_value=1)):
        with pytest.raises(EnhancerError, match="gemini-text failed"):
            await svc.enhance(node_id=94, user_prompt="x")


@pytest.mark.asyncio
async def test_enhance_retries_on_stale_doc():
    """«Cannot upload files» → invalidate + один retry. На второй попытке
    отдаём completed — должны вернуть результат без exception."""
    svc = EnhancerService(MagicMock())

    bad = MagicMock(status="failed", result_text="", error="Cannot upload files", raw={})
    good = MagicMock(status="completed", result_text="OK", error=None, raw={})
    fake_wf = MagicMock()
    fake_wf.run_text = AsyncMock(side_effect=[bad, good])

    with patch("app.services.enhancer.GeminiTextWorkflow", return_value=fake_wf), \
         patch("app.services.enhancer.get_enhancer_doc_for_node",
               new=AsyncMock(return_value=1)), \
         patch("app.services.enhancer.invalidate_enhancer_doc",
               new=AsyncMock()) as inv:
        result = await svc.enhance(node_id=94, user_prompt="x")

    assert result.enhanced_prompt == "OK"
    assert fake_wf.run_text.await_count == 2
    inv.assert_awaited_once()


# ── 3. _strip_meta_wrappers — типичные LLM-артефакты ────────────────────────

def test_strip_strips_quoted_string():
    assert _strip_meta_wrappers('"a beautiful image"') == "a beautiful image"


def test_strip_strips_enhanced_prompt_prefix():
    assert _strip_meta_wrappers("Enhanced prompt: a girl") == "a girl"


def test_strip_strips_russian_prefix():
    assert _strip_meta_wrappers("Улучшенный промпт: девушка") == "девушка"


def test_strip_strips_code_fences():
    out = _strip_meta_wrappers("```\nhello world\n```")
    assert out == "hello world"


def test_strip_strips_angle_quotes():
    assert _strip_meta_wrappers("«красный закат»") == "красный закат"


def test_strip_leaves_clean_text_alone():
    assert _strip_meta_wrappers("just a clean prompt") == "just a clean prompt"
