import { html } from '../lib/html.js';
import { useEffect, useState } from '../vendor/preact-hooks.module.js';

// Format credit balance into a compact, glance-friendly string.
// 0..999 → "734", 1k..999k → "12.3k", 1m+ → "1.2m".
function fmtBalance(n) {
  if (n == null) return '—';
  const x = Number(n);
  if (!Number.isFinite(x)) return '—';
  if (x >= 1_000_000) return (x / 1_000_000).toFixed(1) + 'm';
  if (x >= 1_000) return (x / 1_000).toFixed(x >= 10_000 ? 0 : 1) + 'k';
  return String(Math.round(x));
}

export function Header({ health, api }) {
  const cls = `pill ${health.status}`;
  const label =
    health.status === 'online' ? 'online' :
    health.status === 'no_session' ? 'no session' :
    health.status === 'offline' ? 'offline' :
    '...';

  // Balance polling. Refreshes every 30s when sidecar is online — matches
  // Phygital+ web UI cadence per HAR recon. Hidden when sidecar offline
  // (call would 503 / clutter the header).
  const [bal, setBal] = useState({ value: null, infinity: false, error: null, loading: false });

  useEffect(() => {
    if (health.status !== 'online') {
      setBal(b => ({ ...b, value: null, error: null }));
      return undefined;
    }
    let cancelled = false;
    async function load() {
      setBal(b => ({ ...b, loading: true }));
      try {
        const r = await api.getBalance();
        if (cancelled) return;
        setBal({ value: r.balance, infinity: !!r.is_infinity, error: null, loading: false });
      } catch (e) {
        if (cancelled) return;
        // 503 = "session_not_ready" — show as "—", not as an error pill.
        const code = e.status || 0;
        const isSession = code === 503;
        setBal({ value: null, infinity: false, error: isSession ? null : (e.message || 'balance error'), loading: false });
      }
    }
    load();
    const id = setInterval(load, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [health.status]);

  const balLabel = bal.infinity ? '∞' : fmtBalance(bal.value);
  const balTitle =
    bal.error ? `Balance: ${bal.error}` :
    bal.value != null ? `Phygital+ credits — refreshes every 30s` :
    'Balance — not available (sidecar offline?)';

  return html`
    <div class="header">
      <div class="title">Phygital Studio</div>
      <div class="header-spacer"></div>
      ${health.status === 'online' ? html`
        <div class="balance" title=${balTitle}>
          <span class="balance-icon">◆</span>
          <span class=${`balance-value${bal.loading ? ' loading' : ''}${bal.error ? ' err' : ''}`}>${balLabel}</span>
        </div>
      ` : null}
      <div class=${cls} title=${`Sidecar: ${label}`}><span class="dot"></span>${label}</div>
    </div>
  `;
}
