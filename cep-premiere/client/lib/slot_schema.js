// Node 94 (Nano Banana), 98 (GPT Image), 87 (Topaz Video Upscale) — schemas
// hardcoded here because /nodes/video эндпоинт отдаёт только видео-ноды.
// Видео-ноды (74/100/121/124) приходят с GET /nodes/video.
//
// V1.3 todo: добавить GET /nodes/image и /nodes/upscale в panel и убрать
// эти константы (один источник истины — sidecar's NODES реестр).

// Source: phygital.har → GET /api/v2/nodes/ schema for id=94 (Gemini Image API).
export const NANO_BANANA_META = {
  node_id: 94,
  model: 'Nano Banana',
  slots: { init_img: 'array' },
  // 'generate' = text→image (init_img пустой), 'edit' = image→image.
  // Бэкенд (workflows/image_gen.py:88-93) принимает init_img:[] без проблем —
  // т.е. workflow один, разница только в required-slot'е на UI-стороне.
  scenarios: ['generate', 'edit'],
  scenario_slots: { generate: [], edit: ['init_img'] },
  default_params: {
    model_name: 'v3_1',
    ratio: 'default',
    resolution: 'k1',
  },
  param_options: {
    model_name: { kind: 'enum', options: ['v2', 'v2_5', 'v3', 'v3_1'] },
    ratio: { kind: 'enum', options: [
      'default', 'r_1_1', 'r_2_3', 'r_3_2', 'r_1_4', 'r_4_1',
      'r_1_8', 'r_8_1', 'r_3_4', 'r_4_3', 'r_4_5', 'r_5_4',
      'r_9_16', 'r_16_9', 'r_21_9',
    ] },
    resolution: { kind: 'enum', options: ['default', 'k1', 'k2', 'k4'] },
  },
};

// Source: sidecar/app/workflows/gpt_image.py. Аналогичный slot-флип «empty
// array ↔ image» для inputs.images — на стороне sidecar'а ловится
// автоматически по списку init_img_ids. Здесь — только UI-схема.
export const GPT_IMAGE_META = {
  node_id: 98,
  model: 'GPT Image',
  slots: { images: 'array' },
  // OpenAI gpt-image-1: до 16 reference-картинок за edit-запрос. Sidecar
  // (gpt_image.MAX_INPUT_IMAGES) и router (/jobs 422) валидируют тоже —
  // на UI это нужно чтобы юзер видел лимит ещё до клика по Submit.
  slot_max: { images: 16 },
  // Аналогично Nano Banana: 'generate' = t2i (images:[]), 'edit' = i2i.
  // gpt_image.py:76-85 _images_input() авто-флипает type ↔ "array"/"image"
  // в зависимости от пустоты ids.
  scenarios: ['generate', 'edit'],
  scenario_slots: { generate: [], edit: ['images'] },
  default_params: {
    version: 'v2',
    aspect_ratio: 'auto',
    quality: 'Medium',
    background: 'auto',
    number_of_images: 1,
  },
  param_options: {
    version: { kind: 'enum', options: ['v2'] },
    aspect_ratio: { kind: 'enum', options: ['auto', '1024x1024', '1536x1024', '1024x1536'] },
    quality: { kind: 'enum', options: ['Low', 'Medium', 'High'] },
    background: { kind: 'enum', options: ['auto', 'transparent', 'opaque'] },
    number_of_images: { kind: 'number', min: 1, max: 4, step: 1 },
  },
};

// Source: sidecar/app/workflows/topaz_upscale.py. V1.2: только PROB4
// (Proteus / "General"), single scenario «upscale». 12 params под капотом
// захардкожены — UI выставляет минимум, важный для юзера.
export const TOPAZ_META = {
  node_id: 87,
  model: 'Topaz Video Upscale',
  slots: { init_video: 'scalar' },
  scenarios: ['upscale'],
  scenario_slots: { upscale: ['init_video'] },
  default_params: {
    output_upscale: 'X2',
    output_container: 'mp4',
  },
  param_options: {
    output_upscale: { kind: 'enum', options: ['X2', 'X4'] },
    output_container: { kind: 'enum', options: ['mp4', 'mov'] },
  },
};

// Family — top-level UI taxonomy. Topaz отдельно от Video, потому что не
// принимает prompt и не участвует в VideoScenario (post-processing).
export const FAMILIES = ['image', 'video', 'upscale'];

export function getNodeFamily(meta) {
  if (!meta) return null;
  if (meta.node_id === 94 || meta.node_id === 98) return 'image';
  if (meta.node_id === 87) return 'upscale';
  return 'video';  // 74/100/121/124 и любая будущая видео-нода
}

export function getNodeMeta({ videoNodes, nodeId }) {
  // videoNodes-override имеет приоритет: тесты используют это, чтобы
  // подмешать кастомный node_id=94 без чтения hardcoded'а; в проде
  // ноды 94/98/87 в /nodes/video не приходят, так что fallback ниже
  // отрабатывает естественно.
  if (videoNodes) {
    const found = videoNodes.find(n => n.node_id === nodeId);
    if (found) return found;
  }
  if (nodeId === 94) return NANO_BANANA_META;
  if (nodeId === 98) return GPT_IMAGE_META;
  if (nodeId === 87) return TOPAZ_META;
  return null;
}

export function listAllNodes({ videoNodes }) {
  const out = [NANO_BANANA_META, GPT_IMAGE_META];
  if (videoNodes) out.push(...videoNodes);
  out.push(TOPAZ_META);
  return out;
}

// Список нод одного семейства — для FamilyTabs → ModelPicker.
export function listNodesByFamily({ videoNodes, family }) {
  if (family === 'image') return [NANO_BANANA_META, GPT_IMAGE_META];
  if (family === 'video') return videoNodes ? [...videoNodes] : [];
  if (family === 'upscale') return [TOPAZ_META];
  return [];
}

export function getSlotsForScenario({ videoNodes, nodeId, scenario }) {
  const meta = getNodeMeta({ videoNodes, nodeId });
  if (!meta) return [];
  const names = meta.scenario_slots[scenario];
  if (!names) return [];
  const maxMap = meta.slot_max || {};
  return names.map(name => {
    const slot = { name, kind: meta.slots[name] || 'scalar' };
    if (maxMap[name] !== undefined) slot.max = maxMap[name];
    return slot;
  });
}

// «У этой ноды есть промпт?» — Topaz отвечает false, всё остальное true.
// Используется в UI чтобы спрятать PromptInput + ✨ Enhance toggle для upscale.
export function nodeHasPrompt(meta) {
  if (!meta) return false;
  return getNodeFamily(meta) !== 'upscale';
}
