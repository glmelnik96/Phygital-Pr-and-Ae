import { html } from '../lib/html.js';
import { useState, useMemo } from '../vendor/preact-hooks.module.js';
import { JobFilter } from './JobFilter.js';
import { JobList } from './JobList.js';

export function HistoryTab({ snap, api, videoNodes, onAction }) {
  const [filter, setFilter] = useState('all');
  const counts = useMemo(() => {
    const c = { all: snap.jobs.length };
    for (const j of snap.jobs) c[j.status] = (c[j.status] || 0) + 1;
    return c;
  }, [snap.jobs]);
  const jobs = filter === 'all' ? snap.jobs : snap.jobs.filter(j => j.status === filter);
  return html`
    <div class="history">
      <${JobFilter} value=${filter} counts=${counts} onChange=${setFilter} />
      <${JobList} jobs=${jobs} api=${api} videoNodes=${videoNodes} onAction=${onAction} />
    </div>
  `;
}
