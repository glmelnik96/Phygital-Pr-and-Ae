import { html } from '../lib/html.js';
import { FAMILIES } from '../lib/slot_schema.js';

// V1.2: top-level taxonomy выше ModelPicker'а.
//   Image    — Nano Banana (94) / GPT Image (98)        [t2i / i2i]
//   Video    — Kling / Seedance / Kling Omni / Motion   [t2v / i2v / v2v]
//   Upscale  — Topaz Video Upscale (87)                 [v→hi-res v]
//
// Сабмоды (t2i vs i2i, t2v vs i2v vs v2v) сразу выбираются ScenarioPicker'ом
// — отдельные таб-табы для них раздуют UI без пользы.

const FAMILY_LABELS = {
  image: 'Image',
  video: 'Video',
  upscale: 'Upscale',
};

const FAMILY_TITLES = {
  image: 'Text→Image / Image→Image (Nano Banana, GPT Image)',
  video: 'Text→Video / Image→Video / Video→Video (Kling, Seedance, Omni, Motion)',
  upscale: 'Video upscale (Topaz)',
};

export function FamilyTabs({ value, onChange, disabled }) {
  return html`
    <div class="family-tabs" role="tablist">
      ${FAMILIES.map(f => html`
        <button
          key=${f}
          role="tab"
          class=${`family-tab ${value === f ? 'active' : ''}`}
          aria-selected=${value === f}
          title=${FAMILY_TITLES[f]}
          disabled=${disabled}
          onClick=${() => onChange(f)}
        >${FAMILY_LABELS[f]}</button>
      `)}
    </div>
  `;
}
