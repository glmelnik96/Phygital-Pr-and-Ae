import { html } from '../lib/html.js';

const PLACEHOLDER =
  'Describe the result. Example: «handheld dolly-in on a red vintage car at sunset, dust kicked up by the wheels, cinematic.»';

export function PromptInput({ value, onChange }) {
  const len = (value || '').length;
  return html`
    <div class="field">
      <label>
        Prompt
        <span class="field-meta">${len ? `${len} chars` : 'required'}</span>
      </label>
      <textarea rows="3" value=${value} onInput=${e => onChange(e.target.value)}
                placeholder=${PLACEHOLDER}></textarea>
    </div>
  `;
}
