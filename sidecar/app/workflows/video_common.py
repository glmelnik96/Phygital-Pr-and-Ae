"""Общие штуки для видео-нод Phygital+: enum сценариев, схема слотов, валидация.

**Источник истины** — recon 2026-05-21: `sidecar/recon-captures/20260521-133657/`
+ vault `Видеоноды Phygital+ — рекон 2026-05-21.md`.

Ноды:
  74  — Kling v3 pro          (model_name="kling_v3", mode="pro")
  100 — Seedance 2.0 p720     (model="v_2_0", resolution="p720")
  121 — Kling Omni 3 pro      (model="omni_3", mode="pro")
  124 — Kling Motion v3 pro   (model_name="kling_v3", mode="pro") + character_orientation
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal


# ── Сценарии ──────────────────────────────────────────────────────────────
class VideoScenario(str, Enum):
    T2V = "t2v"                                # nodes 74 / 100 / 121: только text_prompt
    START_PROMPT = "start_prompt"
    START_END_PROMPT = "start_end_prompt"
    REF_PROMPT = "ref_prompt"                  # Seedance only
    REF_PROMPT_VIDEO = "ref_prompt_video"      # Seedance only
    ELEMENTS_PROMPT = "elements_prompt"        # Kling 74 + Omni 121
    ELEMENTS_PROMPT_VIDEO = "elements_prompt_video"  # Kling 74 + Omni 121
    CHAR_VIDEO_PROMPT = "char_video_prompt"    # Motion only


# ── Тип слота: array (list[int]) vs scalar (int) ──────────────────────────
SlotKind = Literal["array", "scalar"]


# ── Схема слотов каждой ноды ─────────────────────────────────────────────
NODE_SLOTS: dict[int, dict[str, SlotKind]] = {
    74: {
        "init_img": "array",
        "image_tail": "scalar",
        "element_1": "array",
        "element_2": "array",
        "element_3": "array",
    },
    100: {
        "start_img": "scalar",
        "end_frame": "scalar",
        "ref_img": "array",
        "ref_vid": "array",
        "ref_audio": "array",
    },
    121: {
        "first_frame": "scalar",
        "last_frame": "scalar",
        "element_1": "array",
        "element_2": "array",
        "element_3": "array",
        "element_4": "array",
        "video": "scalar",
    },
    124: {
        "char_ref": "scalar",
        "video": "scalar",
    },
}


# ── Какие слоты ОБЯЗАТЕЛЬНЫ в каждом сценарии (для каждой ноды) ──────────
# Сценарии, которые на этой ноде не поддерживаются — отсутствуют в карте.
# T2V — text-to-video, никаких init-файлов не требуется (пустой required list).
SCENARIO_SLOTS: dict[tuple[int, VideoScenario], list[str]] = {
    (74, VideoScenario.T2V):                    [],
    (74, VideoScenario.START_PROMPT):           ["init_img"],
    (74, VideoScenario.START_END_PROMPT):       ["init_img", "image_tail"],
    (74, VideoScenario.ELEMENTS_PROMPT):        ["element_1"],
    (74, VideoScenario.ELEMENTS_PROMPT_VIDEO):  ["element_1"],

    (100, VideoScenario.T2V):                   [],
    (100, VideoScenario.START_PROMPT):          ["start_img"],
    (100, VideoScenario.START_END_PROMPT):      ["start_img", "end_frame"],
    (100, VideoScenario.REF_PROMPT):            ["ref_img"],
    (100, VideoScenario.REF_PROMPT_VIDEO):      ["ref_img", "ref_vid"],

    (121, VideoScenario.T2V):                   [],
    (121, VideoScenario.START_PROMPT):          ["first_frame"],
    (121, VideoScenario.START_END_PROMPT):      ["first_frame", "last_frame"],
    (121, VideoScenario.ELEMENTS_PROMPT):       ["element_1"],
    (121, VideoScenario.ELEMENTS_PROMPT_VIDEO): ["element_1", "video"],

    (124, VideoScenario.CHAR_VIDEO_PROMPT):     ["char_ref", "video"],
}


# ── Дефолтные параметры для preview-cost / generate ──────────────────────
# Источник: phygital.har → /api/v2/nodes/ schema dump + recon submits 2026-05-21.
# Имена и типы значений должны 1:1 совпадать с теми, что принимают workflow.build_payload
# методы (см. video_*.py) и реальный Phygital+ API.
NODE_DEFAULT_PARAMS: dict[int, dict[str, Any]] = {
    74: {  # Kling v3 (phygc-rnd-api-kling) — recon submit_01
        "model_name": "kling_v3",
        "ratio": "r_16_9",
        "duration": "sec_5",
        "mode": "pro",
        "sound": "off",
        "cfg_scale": 0.5,
        "shot_type": "customize",
        "multi_shot": False,
    },
    100: {  # Seedance 2.0 (phygc-rnd-seedance-api) — recon submit_02
        # NB: aspect_ratio (не ratio), duration — int, seed — int, +bool флаги.
        "model": "v_2_0",
        "aspect_ratio": "adaptive",
        "resolution": "p720",
        "duration": 5,
        "seed": -1,
        "camerafixed": False,
        "generate_audio": False,
    },
    121: {  # Kling Omni 3 (phygc-rnd-api-kling-omni) — recon submit_06
        # NB: duration — int, sound — bool.
        "model": "omni_3",
        "ratio": "r_16_9",
        "mode": "pro",
        "duration": 5,
        "sound": False,
        "shot_type": "normal",
        "multi_shot": False,
    },
    124: {  # Kling Motion (phygc-rnd-api-kling-motion) — recon submit_10
        # NB: НЕТ ratio/duration на этой ноде. keep_original_sound — bool.
        "model": "kling_v3",
        "mode": "pro",
        "keep_original_sound": True,
        "character_orientation": "video",
    },
}


NODE_MODEL_LABEL: dict[int, str] = {
    74: "Kling v3 pro",
    100: "Seedance 2.0 p720",
    121: "Kling Omni 3 pro",
    124: "Kling Motion v3 pro",
}


# ── Widget hints для UI (ParamsAccordion в CEP-панели) ───────────────────
# Для каждого параметра ноды описываем как его рендерить:
#   {"kind": "enum",   "options": [...]}                     → <select>
#   {"kind": "bool"}                                          → checkbox
#   {"kind": "number", "min": 0, "max": 1, "step": 0.1}       → <input type=number>
#   {"kind": "string"}                                        → <input type=text>
# Источник истины — phygital.har → GET /api/v2/nodes/ schema dump (2026-05-21):
# полные enum-списки взяты прямо из node definition.params[].options.values.
NODE_PARAM_OPTIONS: dict[int, dict[str, dict[str, Any]]] = {
    74: {  # Kling v3 — phygc-rnd-api-kling, "Generate video from prompt"
        "model_name": {"kind": "enum", "options": [
            "kling_v1", "kling_v1_5", "kling_v1_6", "kling_v2_master",
            "kling_v2_1_master", "kling_v2_5_turbo", "kling_v2_6", "kling_v3",
        ]},
        "ratio": {"kind": "enum", "options": [
            "r_16_9", "r_9_16", "r_1_1", "r_4_3", "r_3_4", "r_3_2", "r_2_3", "r_21_9",
        ]},
        "mode":     {"kind": "enum", "options": ["std", "pro"]},
        "duration": {"kind": "enum", "options": [
            "sec_3", "sec_4", "sec_5", "sec_6", "sec_7", "sec_8",
            "sec_9", "sec_10", "sec_11", "sec_12", "sec_13", "sec_14", "sec_15",
        ]},
        "sound":     {"kind": "enum", "options": ["off", "on"]},
        "cfg_scale": {"kind": "number", "min": 0.0, "max": 1.0, "step": 0.1},
        "shot_type": {"kind": "enum", "options": ["customize", "intelligence"]},
        "multi_shot": {"kind": "bool"},
    },
    100: {  # Seedance 2.0 — phygc-rnd-seedance-api
        "model": {"kind": "enum", "options": [
            "lite", "pro", "pro_fast", "pro_1_5", "v_2_0", "v_2_0_fast",
        ]},
        "aspect_ratio": {"kind": "enum", "options": [
            "r_1_1", "r_4_3", "r_3_4", "r_16_9", "r_9_16", "r_21_9", "adaptive",
        ]},
        "resolution":     {"kind": "enum",   "options": ["p480", "p720", "p1080"]},
        "duration":       {"kind": "number", "min": 3, "max": 15, "step": 1},
        "seed":           {"kind": "number", "min": -1, "max": 2_147_483_647, "step": 1},
        "camerafixed":    {"kind": "bool"},
        "generate_audio": {"kind": "bool"},
    },
    121: {  # Kling Omni 3 — phygc-rnd-api-kling-omni
        "model":      {"kind": "enum",   "options": ["omni_1", "omni_3"]},
        "mode":       {"kind": "enum",   "options": ["std", "pro"]},
        "ratio":      {"kind": "enum",   "options": ["r_16_9", "r_9_16", "r_1_1"]},
        "duration":   {"kind": "number", "min": 3, "max": 15, "step": 1},
        "sound":      {"kind": "bool"},
        "shot_type":  {"kind": "enum",   "options": ["customize", "normal"]},
        "multi_shot": {"kind": "bool"},
    },
    124: {  # Kling Motion — phygc-rnd-api-kling-motion (no ratio/duration!)
        "model":                 {"kind": "enum", "options": ["kling_v2_6", "kling_v3"]},
        "mode":                  {"kind": "enum", "options": ["std", "pro"]},
        "keep_original_sound":   {"kind": "bool"},
        "character_orientation": {"kind": "enum", "options": ["video", "image"]},
    },
}


def validate_slots(
    node_id: int,
    scenario: VideoScenario,
    init_files: dict[str, list[str] | str],
) -> None:
    """Бросает ValueError если набор переданных слотов не соответствует (node, scenario).

    Проверяет:
      1. Сценарий поддерживается нодой.
      2. Все обязательные слоты присутствуют и непусты.
      3. Каждый переданный слот существует в схеме ноды.
      4. Тип слота (array vs scalar) совпадает с переданным значением.
    """
    if node_id not in NODE_SLOTS:
        raise ValueError(f"unknown video node_id={node_id}")

    key = (node_id, scenario)
    if key not in SCENARIO_SLOTS:
        raise ValueError(
            f"scenario {scenario.value!r} not supported by node {node_id}"
        )

    required = SCENARIO_SLOTS[key]
    node_schema = NODE_SLOTS[node_id]

    for slot in required:
        if slot not in init_files or _is_empty(init_files[slot]):
            raise ValueError(
                f"missing required slot {slot!r} for ({node_id},{scenario.value})"
            )

    for slot, val in init_files.items():
        if slot not in node_schema:
            raise ValueError(f"unknown slot {slot!r} for node {node_id}")
        kind = node_schema[slot]
        if kind == "array" and not isinstance(val, list):
            raise ValueError(
                f"slot {slot!r} must be array (list) for node {node_id}, got {type(val).__name__}"
            )
        if kind == "scalar" and isinstance(val, list):
            raise ValueError(
                f"slot {slot!r} must be scalar (single path) for node {node_id}, got list"
            )


def _is_empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, (list, str)) and not v:
        return True
    return False


def describe_video_nodes() -> list[dict[str, Any]]:
    """Матрица для GET /nodes/video — что фронт показывает в UI."""
    out: list[dict[str, Any]] = []
    for node_id, slots in NODE_SLOTS.items():
        scenarios = [
            scenario.value
            for (nid, scenario) in SCENARIO_SLOTS
            if nid == node_id
        ]
        scenario_slots = {
            scenario.value: SCENARIO_SLOTS[(node_id, scenario)]
            for (nid, scenario) in SCENARIO_SLOTS
            if nid == node_id
        }
        out.append({
            "node_id": node_id,
            "model": NODE_MODEL_LABEL.get(node_id, str(node_id)),
            "slots": slots,
            "scenarios": scenarios,
            "scenario_slots": scenario_slots,
            "default_params": NODE_DEFAULT_PARAMS.get(node_id, {}),
            "param_options": NODE_PARAM_OPTIONS.get(node_id, {}),
        })
    return out
