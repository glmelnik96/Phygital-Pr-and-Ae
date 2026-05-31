"""Topaz Video Upscale (node 87) — отдельный workflow для post-processing.

Это НЕ video-generation: на вход подаётся уже готовое видео, на выход —
upscaled версия. Поэтому Topaz НЕ участвует в VideoScenario-енумa
(см. video_common.py) — у него ровно одна форма входа: `init_video`.

Источник истины по shape'ам payload'а и параметрам ноды:
  docs/V1.2_T2V_TOPAZ_NOTES.md (раздел 2)
  sidecar/recon-captures/20260531-162221-t2v-manual/ (manual recon)

V1.2 simplification (по решению пользователя 2026-05-31):
  - filter_enhancement_model жёстко = "PROB4" (General / Proteus). Семейный
    селектор UI (Artemis / Nyx / Gaia / Iris / Themis / Dione) отложен на
    V1.3+ — он требует ручного 7-кликового рекона UI→backend-code mapping.
  - UI выставляет только: output_upscale, output_crop_to_fit, output_container,
    interpolation toggle (по умолчанию off). Остальные параметры — backend
    defaults из nodes_dump.
"""
from __future__ import annotations

import uuid
from typing import Any

from app.workflows.video_base import VideoWorkflow


class TopazUpscaleWorkflow(VideoWorkflow):
    WORKFLOW_SCHEMA_ID = 87
    NODE_GLOBAL_ID = "Phygital Creator/phygc-rnd-topaz-video-upscale-api"
    NODE_NAME = "Topaz Video Upscale"
    SERVICE_VERSION = "0.0.1"  # TBD — уточнить из первого реального recon-config_history
    OUTPUT_NAME = "video"

    # V1.2 жёстко фиксируем enhancement model на General/Proteus.
    # Когда добавим UI семейств — этот константный класс-атрибут заменится
    # на параметр build_payload.
    ENHANCEMENT_MODEL_FIXED = "PROB4"

    def build_payload(
        self,
        *,
        init_video: int | str,
        # Output
        output_upscale: str = "X2",                  # X1 / X2 / X3 / X4
        output_crop_to_fit: str = "NULL",            # NULL (Auto) / TRUE / FALSE
        output_container: str = "mp4",               # mp4 / mov / mkv / NULL
        # Frame interpolation (off by default — оставляем V1.2 simple)
        filter_frame_interpolation_params: bool = False,
        filter_frame_interpolation_model: str = "NULL",
        filter_frame_interpolation_slowmo: float = 0,
        filter_frame_interpolation_fps: float = 0,
        filter_frame_interpolation_duplicate: str = "NULL",
        filter_frame_interpolation_duplicate_threshold: float = 0,
        **_extra: Any,
    ) -> dict[str, Any]:
        if not init_video:
            raise ValueError("topaz_upscale: init_video is required")

        self._last_args = dict(
            init_video=init_video,
            output_upscale=output_upscale,
            output_crop_to_fit=output_crop_to_fit,
            output_container=output_container,
            filter_frame_interpolation_params=filter_frame_interpolation_params,
            filter_frame_interpolation_model=filter_frame_interpolation_model,
            filter_frame_interpolation_slowmo=filter_frame_interpolation_slowmo,
            filter_frame_interpolation_fps=filter_frame_interpolation_fps,
            filter_frame_interpolation_duplicate=filter_frame_interpolation_duplicate,
            filter_frame_interpolation_duplicate_threshold=filter_frame_interpolation_duplicate_threshold,
        )

        inputs = [
            self._scalar_slot("init_video", init_video, data_type="video", optional=False),
        ]
        params = [
            self._param("output_upscale", "enum", output_upscale),
            self._param("filter_enhancement_params", "bool", True),
            self._param("filter_enhancement_model", "enum", self.ENHANCEMENT_MODEL_FIXED),
            self._param("filter_frame_interpolation_params", "bool", filter_frame_interpolation_params),
            self._param("filter_frame_interpolation_model", "enum", filter_frame_interpolation_model),
            self._param("filter_frame_interpolation_slowmo", "number", filter_frame_interpolation_slowmo),
            self._param("filter_frame_interpolation_fps", "number", filter_frame_interpolation_fps),
            self._param("filter_frame_interpolation_duplicate", "enum", filter_frame_interpolation_duplicate),
            self._param("filter_frame_interpolation_duplicate_threshold", "number",
                        filter_frame_interpolation_duplicate_threshold),
            self._param("output_crop_to_fit", "enum", output_crop_to_fit),
            self._param("output_container", "enum", output_container),
        ]
        outputs = [{"name": "video", "type": "array", "value": ""}]
        return {
            "id": self.WORKFLOW_SCHEMA_ID,
            "inputs": inputs,
            "params": params,
            "outputs": outputs,
        }

    def _build_config(self, **inputs: Any) -> dict[str, Any]:
        node_uuid = str(uuid.uuid4())
        payload = self.build_payload(**inputs)
        return {
            "nodes": [{
                "globalId": self.NODE_GLOBAL_ID,
                "name": self.NODE_NAME,
                "uuid": node_uuid,
                "taskID": 0,
                "serviceVersion": self.SERVICE_VERSION,
                "inputSocketGroup": {},
                "outputSocketGroup": [
                    {"name": "video", "dataType": "array",
                     "optionalInfo": {"valueOptions": {"itemType": {"dataType": "video"}}},
                     "optional": None, "displayName": None, "value": []}
                ],
                "meta": {
                    **({"taskPrice": self._last_price} if self._last_price else {}),
                    "taskSchema": payload,
                },
                "params": {p["name"]: {"name": p["name"], "type": p["type"], "value": p["value"]}
                           for p in payload["params"]},
                "width": 350,
                "position": {"x": 600, "y": 200},
                "connections": [],
                "height": 617,
            }],
            "executedNodeUuid": node_uuid,
        }


# ── UI metadata (используется в /nodes/upscale endpoint) ─────────────────
# Топаз не описан в video_common.NODE_PARAM_OPTIONS — это отдельная категория.
TOPAZ_DEFAULT_PARAMS: dict[str, Any] = {
    "output_upscale": "X2",
    "output_crop_to_fit": "NULL",
    "output_container": "mp4",
    "filter_frame_interpolation_params": False,
    "filter_frame_interpolation_model": "NULL",
    "filter_frame_interpolation_slowmo": 0,
    "filter_frame_interpolation_fps": 0,
}

TOPAZ_PARAM_OPTIONS: dict[str, dict[str, Any]] = {
    "output_upscale":     {"kind": "enum", "options": ["X1", "X2", "X3", "X4"],
                           "label": "Upscale factor"},
    "output_crop_to_fit": {"kind": "enum", "options": ["NULL", "TRUE", "FALSE"],
                           "labels": {"NULL": "Auto", "TRUE": "Yes", "FALSE": "No"},
                           "label": "Crop to fit"},
    "output_container":   {"kind": "enum", "options": ["mp4", "mov", "mkv"],
                           "label": "Container"},
    "filter_frame_interpolation_params": {"kind": "bool", "label": "Frame interpolation"},
    "filter_frame_interpolation_model":  {"kind": "enum",
                                          "options": ["NULL", "AION1", "APF2", "APO8", "CHF3", "CHR2"],
                                          "label": "Interpolation model",
                                          "depends_on": "filter_frame_interpolation_params"},
    "filter_frame_interpolation_slowmo": {"kind": "number", "min": 0, "max": 16, "step": 1,
                                          "label": "Slow-motion rate",
                                          "depends_on": "filter_frame_interpolation_params"},
    "filter_frame_interpolation_fps":    {"kind": "number", "min": 0, "max": 240, "step": 1,
                                          "label": "Target FPS",
                                          "depends_on": "filter_frame_interpolation_params"},
}


def describe_topaz_node() -> dict[str, Any]:
    """Описание ноды для /nodes/upscale endpoint (когда будет добавлен)."""
    return {
        "node_id": TopazUpscaleWorkflow.WORKFLOW_SCHEMA_ID,
        "model": TopazUpscaleWorkflow.NODE_NAME,
        "input_slot": "init_video",
        "default_params": TOPAZ_DEFAULT_PARAMS,
        "param_options": TOPAZ_PARAM_OPTIONS,
        # enhancement_model жёстко PROB4 в V1.2 — UI его не показывает
        "enhancement_model_fixed": TopazUpscaleWorkflow.ENHANCEMENT_MODEL_FIXED,
    }
