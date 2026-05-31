import { html } from '../lib/html.js';
import { EnumDropdown } from './EnumDropdown.js';

// V1.2: family-таг убран — FamilyTabs выше уже отделяет Image/Video/Upscale.
// Список nodes приходит pre-filtered (listNodesByFamily в GenerateTab).
// Если в семействе одна нода (image=1 пока — пусть будет 2 после Topaz;
// upscale=1) — всё равно показываем dropdown для консистентного UI.
export function ModelPicker({ nodes, value, onChange }) {
  const items = (nodes || []).map(n => ({ value: n.node_id, label: n.model }));
  return html`
    <div class="field">
      <label>Model</label>
      <${EnumDropdown} options=${items} value=${value} onChange=${onChange} />
    </div>
  `;
}
