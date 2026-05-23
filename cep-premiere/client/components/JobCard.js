import { html } from '../lib/html.js';
import { useState, useEffect, useRef } from '../vendor/preact-hooks.module.js';
import { fmtDuration, jobAgeMs } from '../lib/format.js';
import { NANO_BANANA_META } from '../lib/slot_schema.js';

const STATUS_CLS = {
  queued: 'q', running: 'r', completed: 'ok', failed: 'fail', canceled: 'fail',
};

const SCENARIO_LABELS = {
  start_prompt:           'Start frame + prompt',
  start_end_prompt:       'Start + end frame',
  ref_prompt:             'Reference + prompt',
  ref_prompt_video:       'Reference image + reference video',
  elements_prompt:        'Elements + prompt',
  elements_prompt_video:  'Elements + driving video',
  char_video_prompt:      'Character + driving video',
  edit:                   'Image edit',
};

function modelLabel(node_id, videoNodes) {
  if (node_id === NANO_BANANA_META.node_id) return NANO_BANANA_META.model;
  const m = (videoNodes || []).find(n => n.node_id === node_id);
  return m ? m.model : `node ${node_id}`;
}

// Click-outside hook for the ⋯ overflow menu.
function useDismissOnOutside(open, onClose) {
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) onClose(); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [open]);
  return ref;
}

export function JobCard({ job, videoNodes, onAction }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useDismissOnOutside(menuOpen, () => setMenuOpen(false));

  const cls = STATUS_CLS[job.status] || 'q';
  const age = fmtDuration(jobAgeMs(job));
  const prog = Math.round((job.progress || 0) * 100);
  const params = job.params || {};
  const scenario = params.scenario || params.scenario_value;
  const scenLabel = SCENARIO_LABELS[scenario] || scenario;
  const prompt = params.prompt || params.text_prompt || '';
  const model = modelLabel(job.node_id, videoNodes);
  const isDone = job.status === 'completed';
  const isFailed = job.status === 'failed' || job.status === 'canceled';

  return html`
    <div class=${`job-card ${cls}`}>
      <div class="job-head">
        <div class="job-title-row">
          <span class="job-title" title=${`node_id=${job.node_id}`}>${model}</span>
          ${scenLabel ? html`<span class="job-scenario">${scenLabel}</span>` : null}
        </div>
        <span class="job-age" title=${`job_id=${job.job_id}`}>${age}</span>
      </div>
      ${prompt ? html`<div class="job-prompt" title=${prompt}>${prompt}</div>` : null}
      <div class="job-status">
        ${job.status}${job.status === 'running' ? ` · ${prog}%` : ''}
      </div>
      ${job.error ? html`<div class="job-error" title=${job.error}>${job.error}</div>` : null}
      ${job.resultBlobUrl
        ? html`<img class="job-thumb" src=${job.resultBlobUrl} alt="" />`
        : null}
      <div class="job-actions">
        ${isDone ? html`
          <button class="primary-soft" onClick=${() => onAction('show', job)}>Show in bin</button>
          <button onClick=${() => onAction('download', job)}>Download</button>
        ` : null}
        ${isFailed
          ? html`<button class="primary-soft" onClick=${() => onAction('retry', job)}>Retry</button>`
          : null}
        <div class="job-menu" ref=${menuRef}>
          <button class="job-menu-btn" title="More" onClick=${() => setMenuOpen(o => !o)}>⋯</button>
          ${menuOpen ? html`
            <div class="job-menu-pop">
              <div class="job-menu-item danger" onClick=${() => { setMenuOpen(false); onAction('delete', job); }}>Delete</div>
            </div>
          ` : null}
        </div>
      </div>
    </div>
  `;
}
