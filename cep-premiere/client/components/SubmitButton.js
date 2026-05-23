import { html } from '../lib/html.js';
import { useState } from '../vendor/preact-hooks.module.js';
import { validateDraft } from '../lib/validation.js';
import { makeCostKey } from '../lib/state.js';
import { slotLabel } from '../lib/slot_labels.js';
import { toast } from '../lib/toast.js';

// Turn validation errors into one-line user hints. Same field codes the
// validation lib emits, but with friendly slot/scenario names baked in.
function friendlyValidationError(err) {
  if (!err || !err.field) return err && err.message;
  if (err.field === 'prompt') return 'Write a prompt first.';
  if (err.field === 'scenario') return err.message; // already includes model
  if (err.field === 'model_id') return 'Pick a model first.';
  if (err.field.startsWith('slot:')) {
    const name = err.field.slice(5);
    return `Add a file for "${slotLabel(name)}".`;
  }
  return err.message;
}

export function SubmitButton({ snap, api, onSubmitted }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const { draft, videoNodes, health, cost } = snap;
  const v = validateDraft({ videoNodes, draft });
  const disabled = busy || health.status !== 'online' || !v.ok;

  // Show price inline on the button when we have a fresh estimate for the
  // current draft. Stale or missing estimates fall back to "Generate".
  const costKey = makeCostKey(draft);
  const freshCost = cost && cost.key === costKey && typeof cost.price === 'number'
    ? cost.price
    : null;

  async function onClick() {
    setBusy(true); setErr(null);
    try {
      const init_files = {};
      for (const [name, val] of Object.entries(draft.slots)) {
        if (Array.isArray(val)) init_files[name] = val.map(x => x.path);
        else if (val) init_files[name] = val.path;
      }
      const params = { ...draft.params, prompt: draft.prompt, scenario: draft.scenario };
      const out = await api.createJob({ node_id: draft.model_id, params, init_files });
      if (onSubmitted) onSubmitted(out.job_id);
    } catch (e) {
      setErr(e.message || 'submit failed');
      toast.error('Submit failed: ' + e.message);
    } finally {
      setBusy(false);
    }
  }

  const label =
    busy ? 'Submitting…' :
    freshCost != null ? `Generate · ~${freshCost} credits` :
    'Generate';

  return html`
    <div class="submit">
      <button class="primary submit-btn" onClick=${onClick} disabled=${disabled} title=${disabled && !v.ok ? 'Fix the errors below first' : undefined}>
        ${label}
      </button>
      ${!v.ok && v.errors.length > 0
        ? html`<div class="submit-errs">${v.errors.map(e => html`<div>· ${friendlyValidationError(e)}</div>`)}</div>`
        : null}
      ${err ? html`<div class="submit-err">${err}</div>` : null}
    </div>
  `;
}
