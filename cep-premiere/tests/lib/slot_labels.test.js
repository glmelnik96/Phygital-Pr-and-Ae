import { describe, it, expect } from 'vitest';
import { SLOT_LABELS, SLOT_HINTS, slotLabel, slotHint } from '../../client/lib/slot_labels.js';

describe('slot_labels', () => {
  it('returns a friendly label for every known slot name', () => {
    // Names must match the source-of-truth slot map: sidecar/app/workflows/video_common.py
    // NODE_SLOTS + NANO_BANANA_META.slots. If a new slot lands and no label is
    // added, this test catches it (no fallback for unknown names in the table).
    const names = [
      'init_img', 'image_tail',                                  // Nano Banana / Kling 74
      'start_img', 'end_frame', 'ref_img', 'ref_vid', 'ref_audio', // Seedance 100
      'first_frame', 'last_frame',                               // Omni 121
      'char_ref', 'video',                                       // Motion 124 + Omni 121
      'element_1', 'element_2', 'element_3', 'element_4',
    ];
    for (const n of names) {
      expect(SLOT_LABELS[n], `${n} missing label`).toBeTruthy();
      // Label must not still be the raw snake_case (that's the "no friendly label" tell)
      expect(SLOT_LABELS[n]).not.toBe(n);
    }
  });

  it('slotLabel() falls back to raw name when unknown', () => {
    expect(slotLabel('nonexistent_slot')).toBe('nonexistent_slot');
  });

  it('slotHint() returns string (possibly empty) and never throws', () => {
    expect(typeof slotHint('init_img')).toBe('string');
    expect(slotHint('init_img').length).toBeGreaterThan(0);
    expect(slotHint('unknown')).toBe('');
  });

  it('every label slot has a corresponding hint', () => {
    for (const n of Object.keys(SLOT_LABELS)) {
      expect(SLOT_HINTS[n], `${n} missing hint`).toBeTruthy();
    }
  });
});
