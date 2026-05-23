import { html } from '../lib/html.js';
import { JobCard } from './JobCard.js';

export function JobList({ jobs, api, videoNodes, onAction }) {
  if (!jobs.length) return html`<div class="empty">No jobs yet</div>`;
  const sorted = [...jobs].sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
  return html`
    <div class="job-list">
      ${sorted.map(j => html`<${JobCard} job=${j} api=${api} videoNodes=${videoNodes} onAction=${onAction} />`)}
    </div>
  `;
}
