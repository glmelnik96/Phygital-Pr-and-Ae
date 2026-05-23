import { html } from '../lib/html.js';
import { slotLabel } from '../lib/slot_labels.js';

// Friendly labels for the VideoScenario enum (sidecar/app/workflows/video_common.py).
// Raw values (e.g. "ref_prompt_video") are too cryptic for users picking a flow.
const SCENARIO_LABELS = {
  start_prompt:           'Start frame + prompt',
  start_end_prompt:       'Start + end frame + prompt',
  ref_prompt:             'Reference image + prompt',
  ref_prompt_video:       'Reference image + reference video',
  elements_prompt:        'Elements + prompt',
  elements_prompt_video:  'Elements + driving video',
  char_video_prompt:      'Character + driving video',
  edit:                   'Image edit (init image + prompt)',
};

export function ScenarioPicker({ scenarios, value, requiredSlots, onChange }) {
  const slotNames = (requiredSlots || []).map(s => slotLabel(s.name));
  const hint = slotNames.length
    ? `Needs: ${slotNames.join(', ')}`
    : 'No files needed — just a prompt.';
  return html`
    <div class="field">
      <label>Scenario</label>
      <select value=${value} onChange=${e => onChange(e.target.value)}>
        ${scenarios.map(s => html`<option value=${s}>${SCENARIO_LABELS[s] || s}</option>`)}
      </select>
      <div class="field-hint scenario-hint">${hint}</div>
    </div>
  `;
}
