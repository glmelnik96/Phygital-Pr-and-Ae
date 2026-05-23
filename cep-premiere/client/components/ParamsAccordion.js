import { html } from '../lib/html.js';
import { useState } from '../vendor/preact-hooks.module.js';
import { paramLabel, paramDescription, valueLabel } from '../lib/param_labels.js';

// Render a single param row. Widget shape is dictated by `opt` (from sidecar
// `describe_video_nodes` → `param_options`). Unknown params fall back to a
// text input so the field is still editable.
function ParamField({ name, value, opt, onChange }) {
  const label = paramLabel(name);
  const desc = paramDescription(name);
  const labelEl = html`<label title=${desc || undefined}>${label}</label>`;

  if (opt && opt.kind === 'enum' && Array.isArray(opt.options)) {
    return html`
      <div class="field">
        ${labelEl}
        <select value=${value} onChange=${e => onChange(name, e.target.value)}>
          ${opt.options.map(o => html`<option value=${o}>${valueLabel(o)}</option>`)}
        </select>
        ${desc ? html`<div class="field-hint">${desc}</div>` : null}
      </div>
    `;
  }
  if (opt && opt.kind === 'bool') {
    const checked = value === true || value === 'true' || value === 1 || value === '1';
    return html`
      <div class="field field-inline">
        <input id=${`p_${name}`} type="checkbox" checked=${checked}
               onChange=${e => onChange(name, e.target.checked)} />
        <label for=${`p_${name}`} title=${desc || undefined}>${label}</label>
        ${desc ? html`<div class="field-hint">${desc}</div>` : null}
      </div>
    `;
  }
  if (opt && opt.kind === 'number') {
    return html`
      <div class="field">
        ${labelEl}
        <input type="number"
               min=${opt.min ?? undefined}
               max=${opt.max ?? undefined}
               step=${opt.step ?? undefined}
               value=${value}
               onInput=${e => onChange(name, e.target.value === '' ? '' : Number(e.target.value))} />
        ${desc ? html`<div class="field-hint">${desc}</div>` : null}
      </div>
    `;
  }
  return html`
    <div class="field">
      ${labelEl}
      <input value=${value} onInput=${e => onChange(name, e.target.value)} />
      ${desc ? html`<div class="field-hint">${desc}</div>` : null}
    </div>
  `;
}

export function ParamsAccordion({ defaults, options, values, onChange }) {
  const [open, setOpen] = useState(false);
  const keys = Object.keys(defaults || {});
  if (keys.length === 0) return null;
  return html`
    <div class="params">
      <div class="params-head" onClick=${() => setOpen(o => !o)}>
        ${open ? '▼' : '▶'} Advanced settings (${keys.length})
      </div>
      ${open && html`
        <div class="params-body">
          ${keys.map(k => html`
            <${ParamField}
              name=${k}
              value=${values[k] ?? defaults[k]}
              opt=${(options || {})[k]}
              onChange=${onChange} />
          `)}
        </div>
      `}
    </div>
  `;
}
