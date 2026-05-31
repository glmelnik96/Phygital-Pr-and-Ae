"""POST /enhance — prompt enhancer для V1.2 preview-flow.

Дизайн (Q5+Q7): CEP-панель вызывает /enhance отдельно от /jobs, получает
enhanced prompt и показывает его юзеру в editable-поле. Юзер правит при
необходимости и нажимает Submit, который уже создаёт обычный job через
POST /jobs с финальным текстом. Это разводит «потратить $$ на промпт-думанье»
и «потратить $$ на финальную генерацию» — пользователь видит и подтверждает
оба шага явно.

Topaz (87) и Gemini Text (72) сюда не приходят — у первого нет промпта,
второй сам энхансер. Валидация — через EnhancerService.supports().
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.enhancer import EnhancerError, EnhancerService

router = APIRouter()


class EnhanceRequest(BaseModel):
    node_id: int = Field(
        ...,
        description="Target node_id (94/98/74/100/121/124). Topaz 87 и Gemini 72 не поддерживаются.",
    )
    prompt: str = Field(..., min_length=1, description="User's draft prompt to enhance.")
    init_img_ids: list[int] = Field(
        default_factory=list,
        description="Опциональные file_obj_id референсных картинок (для i2i/i2v).",
    )
    init_img_dims: list[dict[str, int]] = Field(
        default_factory=list,
        description="Параллельный init_img_ids список {width, height} — см. img2img dimensions quirk.",
    )


class EnhanceResponse(BaseModel):
    enhanced_prompt: str
    target_node_id: int
    system_prompt_file: str
    # raw намеренно не возвращаем — содержит полный Phygital task-dump,
    # для UI бесполезно, для debug — смотрим в логах sidecar'а.


@router.post("/enhance", response_model=EnhanceResponse)
async def enhance(body: EnhanceRequest, request: Request) -> EnhanceResponse:
    """Прогнать prompt через Gemini Text(72) с system-prompt'ом для node_id."""
    # Параллельные длины init_img_ids ↔ init_img_dims — единый sanity-check
    # (бэкенд Phygital'а молча отменяет таск через ~30s, если несовпадает).
    if body.init_img_ids and len(body.init_img_ids) != len(body.init_img_dims):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "init_img_dims_length_mismatch",
                "ids": len(body.init_img_ids),
                "dims": len(body.init_img_dims),
            },
        )

    get_client = request.app.state.get_client
    client = await get_client()
    try:
        svc = EnhancerService(client)
        if not svc.supports(body.node_id):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "enhancer_not_supported",
                    "node_id": body.node_id,
                    "message": "enhancer не настроен для этой ноды (Topaz/Gemini-сами-энхансеры)",
                },
            )
        try:
            result = await svc.enhance(
                node_id=body.node_id,
                user_prompt=body.prompt,
                init_img_ids=body.init_img_ids or None,
                init_img_dims=body.init_img_dims or None,
            )
        except EnhancerError as e:
            raise HTTPException(
                status_code=502,
                detail={"error": "enhancer_failed", "message": str(e)},
            )
    finally:
        await client.__aexit__(None, None, None)

    return EnhanceResponse(
        enhanced_prompt=result.enhanced_prompt,
        target_node_id=result.target_node_id,
        system_prompt_file=result.system_prompt_file,
    )
