import { html } from '../lib/html.js';
import { slotLabel, slotHint } from '../lib/slot_labels.js';

function thumbFor(item) {
  if (item.thumb) return html`<img class="slot-thumb" src=${item.thumb} alt="" />`;
  return html`<div class="slot-thumb placeholder"></div>`;
}

// Видео-слоты: ref_vid (Seedance), video (Omni / Motion).
// Всё остальное обрабатываем как image-слот.
function isVideoSlot(name) {
  return /^(ref_vid|video)$/.test(name);
}

export function SlotPicker({ name, kind, max, value, onPick, onClear }) {
  const items = kind === 'array' ? (value || []) : (value ? [value] : []);
  // При наличии max'а для array-слота блокируем добавление, как только
  // достигнут потолок — иначе юзер натолкнётся на 422 от sidecar'а после
  // долгой загрузки. max приходит из slot_schema.GPT_IMAGE_META.slot_max.
  const atCap = kind === 'array' && typeof max === 'number' && items.length >= max;
  const canAddMore = (kind === 'array' && !atCap) || items.length === 0;
  const videoSlot = isVideoSlot(name);
  const typeLabel = videoSlot ? 'video' : 'image';
  const arrayHint = kind === 'array'
    ? (typeof max === 'number' ? ` (up to ${max})` : ' (you can add multiple)')
    : '';
  const friendly = slotLabel(name);
  const hint = slotHint(name);

  // Three buttons only. Primary CTA is "Browse..." (the workflow users
  // converge to first). The other two help when the source already lives
  // in Premiere — but they're secondary, hence the muted styling in CSS.
  const browseTitle = videoSlot
    ? 'Pick a video file from disk (mp4/mov/mkv/…)'
    : 'Pick an image file from disk (jpg/png/tif/…)';
  const binTitle = videoSlot
    ? 'Use the currently selected video in the Project bin'
    : 'Use the currently selected image in the Project bin';
  const fromTimelineLabel = videoSlot ? 'From Timeline In/Out' : 'From Timeline frame';
  const fromTimelineSource = videoSlot ? 'timeline_io' : 'timeline_frame';
  const fromTimelineTitle = videoSlot
    ? 'Use Timeline In/Out marks on the active sequence — ffmpeg clips the topmost video clip'
    : 'Grab the still under the playhead from the topmost clip in the active sequence (via ffmpeg)';

  return html`
    <div class="slot">
      <div class="slot-head">
        <div class="slot-name-row">
          <span class="slot-name">${friendly}</span>
          <span class="slot-kind" title=${`Expects a ${typeLabel} file${arrayHint}`}>· ${typeLabel}${kind === 'array' ? (typeof max === 'number' ? ` · up to ${max}` : ' · multiple') : ''}</span>
        </div>
        ${hint ? html`<div class="slot-hint">${hint}</div>` : null}
      </div>
      <div class="slot-sources">
        <button class="primary-soft" title=${browseTitle}
                onClick=${() => onPick && onPick('disk')} disabled=${!canAddMore}>
          ${items.length === 0 ? 'Browse…' : 'Add file…'}
        </button>
        <button title=${binTitle}
                onClick=${() => onPick && onPick('bin')}>From bin</button>
        <button title=${fromTimelineTitle}
                onClick=${() => onPick && onPick(fromTimelineSource)}>${fromTimelineLabel}</button>
      </div>
      ${items.length === 0
        ? html`<div class="slot-empty">Nothing picked yet — choose a source above.</div>`
        : items.map(it => html`
          <div class="slot-item">
            ${thumbFor(it)}
            <div class="slot-item-meta">
              <div class="slot-item-name" title=${it.path || it.name}>${it.name}</div>
              <div class="slot-item-sub">
                ${it.asset && it.asset.width ? `${it.asset.width}×${it.asset.height}` : ''}
                ${it.cached ? html`<span class="slot-cached">cached</span>` : ''}
                ${it.error ? html`<span class="slot-err" title=${it.error}>upload failed</span>` : ''}
              </div>
            </div>
            <button class="slot-remove" title="Remove" onClick=${() => onClear && onClear(it)}>×</button>
          </div>
        `)}
    </div>
  `;
}
