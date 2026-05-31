import { getNodeMeta, getSlotsForScenario, nodeHasPrompt } from './slot_schema.js';

export function validateDraft({ videoNodes, draft }) {
  const errors = [];
  if (!draft) return { ok: false, errors: [{ field: 'draft', message: 'No draft' }] };

  const meta = getNodeMeta({ videoNodes, nodeId: draft.model_id });
  if (!meta) return { ok: false, errors: [{ field: 'model_id', message: 'Unknown model' }] };

  if (!meta.scenarios.includes(draft.scenario)) {
    errors.push({ field: 'scenario', message: `Scenario ${draft.scenario} not valid for ${meta.model}` });
  }

  // Topaz (87) и любые будущие prompt-less ноды не валидируем по prompt'у —
  // иначе Submit для upscale-family навсегда disabled («Write a prompt first»).
  if (nodeHasPrompt(meta) && (!draft.prompt || !draft.prompt.trim())) {
    errors.push({ field: 'prompt', message: 'Prompt required' });
  }

  const required = getSlotsForScenario({ videoNodes, nodeId: draft.model_id, scenario: draft.scenario });
  for (const { name, kind } of required) {
    const val = draft.slots && draft.slots[name];
    const empty =
      val == null ||
      (Array.isArray(val) && val.length === 0) ||
      (kind === 'scalar' && !val);
    if (empty) errors.push({ field: `slot:${name}`, message: `Slot ${name} required` });
  }

  return { ok: errors.length === 0, errors };
}
