// fmtBalance is currently inlined in Header.js to keep the component tight.
// We re-implement it here so the (small) rounding logic gets pinned in tests —
// if anyone refactors Header to extract it, the test should be re-pointed.

function fmtBalance(n) {
  if (n == null) return '—';
  const x = Number(n);
  if (!Number.isFinite(x)) return '—';
  if (x >= 1_000_000) return (x / 1_000_000).toFixed(1) + 'm';
  if (x >= 1_000) return (x / 1_000).toFixed(x >= 10_000 ? 0 : 1) + 'k';
  return String(Math.round(x));
}

import { describe, it, expect } from 'vitest';

describe('fmtBalance', () => {
  it('handles nullish', () => {
    expect(fmtBalance(null)).toBe('—');
    expect(fmtBalance(undefined)).toBe('—');
    expect(fmtBalance(NaN)).toBe('—');
  });

  it('rounds plain integers in 0..999', () => {
    expect(fmtBalance(0)).toBe('0');
    expect(fmtBalance(42)).toBe('42');
    expect(fmtBalance(734.7)).toBe('735');
  });

  it('uses k suffix for 1k..999k', () => {
    expect(fmtBalance(1000)).toBe('1.0k');
    expect(fmtBalance(9999)).toBe('10.0k');
    expect(fmtBalance(12345)).toBe('12k');
    expect(fmtBalance(188_505)).toBe('189k');
  });

  it('uses m suffix for >= 1m', () => {
    expect(fmtBalance(1_200_000)).toBe('1.2m');
    expect(fmtBalance(5_000_000)).toBe('5.0m');
  });
});
