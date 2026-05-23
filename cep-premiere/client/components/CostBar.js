import { html } from '../lib/html.js';
import { useEffect, useRef } from '../vendor/preact-hooks.module.js';
import { makeCostKey } from '../lib/state.js';
import { validateDraft } from '../lib/validation.js';

const DEBOUNCE_MS = 600;

export function CostBar({ snap, api, store }) {
  const { draft, videoNodes, health } = snap;
  const key = makeCostKey(draft);
  const cost = snap.cost || { key: null };
  const stale = cost.key !== key;
  const v = validateDraft({ videoNodes, draft });

  const inFlight = useRef(null);  // current key being requested (for race protection)

  // Auto-estimate cost. Phygital+ /get_credits_price is cheap and the form
  // is small, so debounced refetch on every change keeps the price live
  // without users having to remember to press a button. Skipped when the
  // draft is invalid (would just 4xx) or when sidecar is offline.
  useEffect(() => {
    if (health.status !== 'online') return undefined;
    if (!v.ok) return undefined;
    if (!stale) return undefined;     // already fresh

    const t = setTimeout(async () => {
      inFlight.current = key;
      store.set({ cost: { key, price: null, loading: true, error: null } });
      try {
        const out = await api.previewCost({
          node_id: draft.model_id,
          params: { ...draft.params, prompt: draft.prompt },
        });
        if (inFlight.current !== key) return;  // a newer draft superseded us
        store.set({ cost: { key, price: out.price ?? out.credits ?? null, loading: false, error: null } });
      } catch (e) {
        if (inFlight.current !== key) return;
        store.set({ cost: { key, price: null, loading: false, error: e.message || 'cost failed' } });
      }
    }, DEBOUNCE_MS);
    return () => clearTimeout(t);
    // makeCostKey covers everything that affects price.
  }, [key, health.status, v.ok]);

  // Render: passive status row — price preview, balance warning, errors.
  // SubmitButton тоже показывает price inline; bar нужен для warning'ов и
  // когда price > 100 credits / balance недостаточен.
  if (!v.ok) return null;
  if (cost.loading && cost.key === key) {
    return html`<div class="cost"><span class="cost-stale">Estimating cost…</span></div>`;
  }
  if (cost.error && cost.key === key) {
    return html`<div class="cost"><span class="cost-err">Cost estimate failed: ${cost.error}</span></div>`;
  }
  if (cost.key === key && typeof cost.price === 'number') {
    const price = cost.price;
    const bal = snap.balance || {};
    // Балансу с infinity (внутренний/тестовый аккаунт) проверка не нужна.
    const insufficient =
      !bal.infinity &&
      typeof bal.value === 'number' &&
      price > bal.value;
    const high = price > 100;
    if (insufficient) {
      return html`<div class="cost cost-warn-only">
        Insufficient balance — ${price} credits required, ${bal.value} available
      </div>`;
    }
    if (high) {
      return html`<div class="cost cost-warn-only">This generation will cost ~${price} credits</div>`;
    }
  }
  return null;
}
