import { html } from '../lib/html.js';

export function JobFilter({ value, counts, onChange }) {
  const opts = ['all', 'queued', 'running', 'completed', 'failed', 'canceled'];
  return html`
    <div class="job-filter">
      ${opts.map(o => {
        const c = (counts && counts[o]) || 0;
        const muted = c === 0 && o !== 'all';
        return html`
          <span class=${`fc ${value === o ? 'active' : ''}${muted ? ' muted' : ''}`}
                onClick=${() => onChange(o)}>
            ${o}${c > 0 ? html` <span class="fc-count">${c}</span>` : ''}
          </span>
        `;
      })}
    </div>
  `;
}
