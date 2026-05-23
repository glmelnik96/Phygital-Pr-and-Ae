import { html } from '../lib/html.js';

// Node 94 (Nano Banana) is the only image model; everything else from
// /nodes/video produces video. Tagging in the dropdown removes the "wait,
// is this image or video?" question users hit on first open.
function modelKind(nodeId) {
  return nodeId === 94 ? 'image' : 'video';
}

export function ModelPicker({ nodes, value, onChange }) {
  return html`
    <div class="field">
      <label>Model</label>
      <select value=${value} onChange=${e => onChange(parseInt(e.target.value, 10))}>
        ${nodes.map(n => html`
          <option value=${n.node_id}>${n.model} — ${modelKind(n.node_id)}</option>
        `)}
      </select>
    </div>
  `;
}
