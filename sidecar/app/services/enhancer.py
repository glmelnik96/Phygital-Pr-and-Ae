"""Prompt enhancer service (V1.2).

Two-step pipeline:
  1. Gemini Text (node 72) with model-specific system-prompt (docs/
     enhancer_prompts/*.md, кэш — enhancer_docs.py).
  2. Возвращаем enhanced prompt (result_text) вызывающему — он сам
     решает, отправить ли его в целевую ноду как есть или показать
     юзеру для подтверждения.

Дизайн:
  * EnhancerService **не запускает** целевую модель — это делает JobRunner
    после того, как UI получил enhanced prompt и пользователь подтвердил.
    Так юзер может править результат и не платит за плохой ран.
  * `init_img_ids` / `init_img_dims` пробрасываются в Gemini Text как
    image-context — энхансер увидит референс и сошлётся на него (i2i / i2v).
  * Семантика `node_id` — это **целевая** нода (94, 98, 74, 100, 121, 124),
    а **не** 72. Сервис сам подгружает правильный system-prompt.
  * Ошибки Phygital'а ('Cannot upload files') ловим один раз: после
    invalidate'а кэша и одного ретрая. Дальше — падаем явно.
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from app.phygital_client.api import PhygitalClient
from app.phygital_client.models import GenerationJob
from app.services.enhancer_docs import (
    enhancer_filename_for_node,
    get_enhancer_doc_for_node,
    invalidate_enhancer_doc,
)
from app.workflows.gemini_text import GeminiTextWorkflow


class EnhancerError(Exception):
    """Raised when enhancement failed (validation / Gemini / extraction)."""


# Текст-обёртка для Gemini Text. Реальные инструкции — в .md-документе
# (см. enhancer_docs.py + docs/enhancer_prompts/*.md), который мы прикрепляем
# через documents=[doc_id]. Шейп взят 1:1 из Phygital-bot/workflows/brand_*.py:
# фикс. text_prompt + content-truthful документ — единственный надёжный способ
# заставить Gemini Text трактовать .md как system_prompt (без обёртки модель
# часто просто описывает документ или игнорит его).
#
# Хвостовой `--- USER DRAFT PROMPT ---` маркер избавляет Gemini от иллюзии,
# что юзер-промпт — это часть инструкций (мы наблюдали смесь, когда передаешь
# просто `prompt=user_prompt`).
ENHANCER_TEXT_PROMPT_TEMPLATE = (
    "The attached document contains your complete instructions for this task "
    "(role, output contract, model-specific rules, scenarios, what to avoid). "
    "Read it and follow every rule.\n"
    "\n"
    "Output ONLY the enhanced prompt — no preamble, no quotes, no commentary, "
    "no meta-text. The very first character of your reply is the first "
    "character of the enhanced prompt.\n"
    "\n"
    "--- USER DRAFT PROMPT ---\n"
    "{user_prompt}\n"
    "--- END USER DRAFT PROMPT ---"
)


class EnhancerService:
    """Two-step prompt-enhancement pipeline.

    Usage::

        svc = EnhancerService(client)
        result = await svc.enhance(
            node_id=100,                 # target = Seedance
            user_prompt="девушка идёт по пляжу",
            init_img_ids=[12345],
            init_img_dims=[{"width": 1024, "height": 1024}],
        )
        print(result.enhanced_prompt)
    """

    def __init__(
        self,
        client: PhygitalClient,
        *,
        gemini_model: str = "pro_3_1",
        gemini_thinking_level: str = "high",
    ) -> None:
        self.client = client
        self.gemini_model = gemini_model
        self.gemini_thinking_level = gemini_thinking_level

    def supports(self, node_id: int) -> bool:
        """True если у нас есть system-prompt для этой целевой ноды."""
        return enhancer_filename_for_node(node_id) is not None

    async def enhance(
        self,
        *,
        node_id: int,
        user_prompt: str,
        init_img_ids: list[int] | None = None,
        init_img_dims: list[dict[str, int]] | None = None,
    ) -> "EnhanceResult":
        """Прогнать `user_prompt` через Gemini Text с system-prompt'ом
        для `node_id` и вернуть enhanced prompt.

        Returns EnhanceResult с enhanced_prompt и raw-jobом (для отладки).
        Raises EnhancerError при невосстановимой ошибке.
        """
        if not user_prompt or not user_prompt.strip():
            raise EnhancerError("user_prompt is empty")
        if not self.supports(node_id):
            raise EnhancerError(
                f"enhancer not configured for node_id={node_id}"
            )

        filename = enhancer_filename_for_node(node_id)
        assert filename is not None  # supports() уже проверил

        # Один аплоад/cache hit + один ретрай на случай протухшего file_obj_id.
        job = await self._run_with_retry(
            node_id=node_id,
            filename=filename,
            user_prompt=user_prompt,
            init_img_ids=init_img_ids or [],
            init_img_dims=init_img_dims or [],
        )

        if job.status != "completed":
            raise EnhancerError(
                f"gemini-text failed: status={job.status} error={job.error!r}"
            )
        text = (job.result_text or "").strip()
        if not text:
            raise EnhancerError("gemini-text returned empty enhanced prompt")

        # Подчищаем типичные артефакты LLM: ведущие/закрывающие кавычки,
        # одинокие кодовые ограждения, "Enhanced prompt:" префикс.
        text = _strip_meta_wrappers(text)

        logger.info(
            f"[enhancer] node {node_id}: {len(user_prompt)}→{len(text)} chars"
        )
        return EnhanceResult(
            enhanced_prompt=text,
            target_node_id=node_id,
            system_prompt_file=filename,
            raw=job.raw,
        )

    async def _run_with_retry(
        self,
        *,
        node_id: int,
        filename: str,
        user_prompt: str,
        init_img_ids: list[int],
        init_img_dims: list[dict[str, int]],
    ) -> GenerationJob:
        wrapped_prompt = ENHANCER_TEXT_PROMPT_TEMPLATE.format(
            user_prompt=user_prompt
        )
        for attempt in (1, 2):
            doc_id = await get_enhancer_doc_for_node(self.client, node_id)
            wf = GeminiTextWorkflow(
                self.client,
                model=self.gemini_model,
                thinking_level=self.gemini_thinking_level,
            )
            job = await wf.run_text(
                prompt=wrapped_prompt,
                init_img_ids=init_img_ids,
                init_img_dims=init_img_dims,
                document_ids=[doc_id],
            )
            if job.status == "completed":
                return job
            # Признак протухшего file_obj_id — переуплоадим один раз.
            err = (job.error or "").lower()
            if attempt == 1 and "cannot upload files" in err:
                logger.warning(
                    f"[enhancer] stale doc detected ({filename}), invalidating + retry"
                )
                await invalidate_enhancer_doc(filename)
                continue
            return job
        # unreachable — цикл всегда отдаёт return на attempt=2
        return job  # type: ignore[return-value]


class EnhanceResult:
    """Результат одного enhance() — namedtuple-lite без зависимости от
    pydantic, чтобы JobRunner мог сериализовать как захочет."""

    __slots__ = ("enhanced_prompt", "target_node_id", "system_prompt_file", "raw")

    def __init__(
        self,
        *,
        enhanced_prompt: str,
        target_node_id: int,
        system_prompt_file: str,
        raw: Any,
    ) -> None:
        self.enhanced_prompt = enhanced_prompt
        self.target_node_id = target_node_id
        self.system_prompt_file = system_prompt_file
        self.raw = raw

    def to_dict(self) -> dict[str, Any]:
        return {
            "enhanced_prompt": self.enhanced_prompt,
            "target_node_id": self.target_node_id,
            "system_prompt_file": self.system_prompt_file,
        }


def _strip_meta_wrappers(text: str) -> str:
    """Уберём типичные LLM-артефакты, нарушающие "ONLY enhanced prompt" контракт.

    System-prompt'ы говорят «выводи только сам промпт без обёрток», но
    модели регулярно прилепляют ведущие кавычки, code fences или префикс
    `Enhanced prompt: ...`. Чистим консервативно — только очевидные кейсы.
    """
    s = text.strip()
    # Префиксы (case-insensitive, на первой строке).
    lowered = s.lower()
    for prefix in (
        "enhanced prompt:",
        "enhanced:",
        "prompt:",
        "here is the enhanced prompt:",
        "here's the enhanced prompt:",
        "вот улучшенный промпт:",
        "улучшенный промпт:",
    ):
        if lowered.startswith(prefix):
            s = s[len(prefix):].lstrip()
            lowered = s.lower()
    # Code fences.
    if s.startswith("```"):
        # отрежем первую строку (```… или ```lang) и последнюю ```
        lines = s.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        s = "\n".join(lines).strip()
    # Парные кавычки вокруг всего текста.
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'", "«"):
        # «…» обрабатываем отдельно (закрытие не равно открытию)
        s = s[1:-1].strip()
    elif s.startswith("«") and s.endswith("»"):
        s = s[1:-1].strip()
    return s
