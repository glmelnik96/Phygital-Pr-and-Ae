import { html } from '../lib/html.js';
import { useState } from '../vendor/preact-hooks.module.js';
import { isEnhancedFresh } from '../lib/state.js';
import { toast } from '../lib/toast.js';

const PLACEHOLDER =
  'Describe the result. Example: «handheld dolly-in on a red vintage car at sunset, dust kicked up by the wheels, cinematic.»';

// V1.2: ✨ Enhance preview-and-confirm flow.
//
// Toggle OFF → стандартное поведение: что юзер набрал, то и уйдёт в /jobs.
// Toggle ON  → появляется кнопка «✨ Enhance», по клику — вызов /enhance,
//              ответ показывается в editable-поле под исходным промптом.
//              SubmitButton использует enhanced-текст, если он свежий
//              (isEnhancedFresh: совпадает (model_id, prompt) пара).
//
// Любая правка исходного prompt'а или смена model_id сбрасывает preview
// (см. setPrompt / setModel в lib/state.js) — UI это видит по
// `isEnhancedFresh(draft) === false` и просит юзера re-enhance.
export function PromptInput({ draft, actions, api }) {
  const [enhancing, setEnhancing] = useState(false);
  const value = draft.prompt || '';
  const len = value.length;
  const enhanceOn = !!draft.enhance_prompt;
  const fresh = isEnhancedFresh(draft);

  async function onEnhanceClick() {
    if (enhancing) return;
    if (!value.trim()) {
      toast.warning('Write a prompt first, then click ✨ Enhance.');
      return;
    }
    setEnhancing(true);
    actions.setEnhancedBusy(true);
    try {
      const out = await api.enhancePrompt({
        node_id: draft.model_id,
        prompt: value,
      });
      actions.setEnhancedResult({
        prompt: value,
        model_id: draft.model_id,
        text: out.enhanced_prompt,
      });
    } catch (e) {
      const detail = (e.body && e.body.detail) || {};
      const reason = detail.message || detail.error || e.message || 'enhance failed';
      actions.setEnhancedError(reason);
      toast.error('Enhance failed: ' + reason);
    } finally {
      setEnhancing(false);
    }
  }

  return html`
    <div class="field prompt-field">
      <label>
        Prompt
        <span class="field-meta">${len ? `${len} chars` : 'required'}</span>
      </label>
      <textarea rows="3" value=${value}
                onInput=${e => actions.setPrompt(e.target.value)}
                placeholder=${PLACEHOLDER}></textarea>

      <div class="enhance-row">
        <label class="enhance-toggle" title="Run the prompt through a model-tuned enhancer (Gemini Text) before submit.">
          <input type="checkbox" checked=${enhanceOn}
                 onChange=${e => actions.setEnhanceToggle(e.target.checked)} />
          <span>✨ Enhance prompt</span>
        </label>
        ${enhanceOn ? html`
          <button class="primary-soft enhance-btn"
                  disabled=${enhancing || !value.trim()}
                  onClick=${onEnhanceClick}
                  title="Run /enhance now and preview the result">
            ${enhancing ? 'Enhancing…' : (fresh ? 'Re-enhance' : '✨ Enhance now')}
          </button>
        ` : null}
      </div>

      ${enhanceOn && draft.enhanced_error ? html`
        <div class="enhance-err">Enhance error: ${draft.enhanced_error}</div>
      ` : null}

      ${enhanceOn && draft.enhanced_prompt != null ? html`
        <div class=${`enhance-preview ${fresh ? '' : 'stale'}`}>
          <div class="enhance-preview-head">
            <span class="enhance-preview-label">
              ${fresh ? 'Enhanced prompt (editable)' : 'Enhanced prompt — stale (re-enhance to refresh)'}
            </span>
            <button class="header-icon-btn"
                    title="Discard enhanced version"
                    onClick=${() => actions.clearEnhancedPreview()}>×</button>
          </div>
          <textarea rows="4" value=${draft.enhanced_prompt}
                    onInput=${e => actions.editEnhancedPrompt(e.target.value)}></textarea>
          <div class="enhance-hint">
            ${fresh
              ? 'Submit will use this enhanced text. Edit it freely.'
              : 'Original prompt or model changed — click Re-enhance to refresh, or × to discard.'}
          </div>
        </div>
      ` : null}
    </div>
  `;
}
