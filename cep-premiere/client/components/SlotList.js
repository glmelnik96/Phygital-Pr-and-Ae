import { html } from '../lib/html.js';
import { SlotPicker } from './SlotPicker.js';

export function SlotList({ slots, values, onPick, onClear }) {
  if (!slots.length) return html`<div class="slot-list-empty">No slots required for this scenario</div>`;
  return html`
    <div class="slot-list">
      ${slots.map(s => html`
        <${SlotPicker}
          name=${s.name} kind=${s.kind} max=${s.max}
          value=${values[s.name]}
          onPick=${src => onPick(s, src)}
          onClear=${item => onClear(s, item)}
        />
      `)}
    </div>
  `;
}
