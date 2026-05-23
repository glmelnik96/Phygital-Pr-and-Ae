import { html } from '../lib/html.js';
import { NANO_BANANA_META } from '../lib/slot_schema.js';

// Persistent queue strip: visible from any tab so user всегда видит сколько
// генераций в воздухе. Сворачивается когда нет queued/running. Per-job ×
// дёргает onCancel — App.js маршрутизирует в api.deleteJob (sidecar /jobs
// DELETE удаляет запись; реальный Phygital cancel — TODO в роутере).
const ACTIVE_STATUSES = new Set(['queued', 'running']);

function modelLabel(node_id, videoNodes) {
  if (node_id === NANO_BANANA_META.node_id) return NANO_BANANA_META.model;
  const m = (videoNodes || []).find(n => n.node_id === node_id);
  return m ? m.model : `node ${node_id}`;
}

export function QueueWidget({ jobs, videoNodes, onCancel }) {
  const active = (jobs || []).filter(j => ACTIVE_STATUSES.has(j.status));
  if (active.length === 0) return null;

  // newest first — пользователь только что нажал submit, его джоб должен быть наверху
  const sorted = [...active].sort((a, b) =>
    (b.created_at || '').localeCompare(a.created_at || '')
  );

  return html`
    <div class="queue-widget" title=${`${active.length} active job(s)`}>
      <div class="queue-head">
        <span class="queue-count">${active.length}</span>
        <span class="queue-label">in queue</span>
      </div>
      <div class="queue-list">
        ${sorted.map(j => {
          const prog = Math.round((j.progress || 0) * 100);
          const model = modelLabel(j.node_id, videoNodes);
          const isRunning = j.status === 'running';
          return html`
            <div class=${`queue-item ${j.status}`} title=${`${model} · ${j.job_id}`}>
              <div class="queue-item-bar">
                <div class="queue-item-fill" style=${`width:${isRunning ? prog : 0}%`}></div>
              </div>
              <div class="queue-item-meta">
                <span class="queue-item-name">${model}</span>
                <span class="queue-item-status">
                  ${isRunning ? `${prog}%` : j.status}
                </span>
              </div>
              <button class="queue-item-cancel" title="Cancel"
                      onClick=${() => onCancel && onCancel(j)}>×</button>
            </div>
          `;
        })}
      </div>
    </div>
  `;
}
