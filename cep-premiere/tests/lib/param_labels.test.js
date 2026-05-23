import { describe, it, expect } from 'vitest';
import { paramLabel, paramDescription, valueLabel, VALUE_LABELS, PARAM_LABELS } from '../../client/lib/param_labels.js';

describe('param_labels', () => {
  it('paramLabel returns a friendly label for every known param', () => {
    // Names mirror sidecar NODE_DEFAULT_PARAMS / NODE_PARAM_OPTIONS keys.
    const params = [
      'model', 'model_name', 'ratio', 'aspect_ratio', 'resolution', 'duration', 'mode',
      'sound', 'cfg_scale', 'shot_type', 'multi_shot', 'seed', 'camerafixed',
      'generate_audio', 'keep_original_sound', 'character_orientation',
    ];
    for (const p of params) {
      expect(PARAM_LABELS[p], `${p} missing label`).toBeTruthy();
    }
  });

  it('paramLabel falls back to raw name', () => {
    expect(paramLabel('mystery_param')).toBe('mystery_param');
  });

  it('paramDescription returns empty string for unknown', () => {
    expect(paramDescription('mystery_param')).toBe('');
  });

  it('valueLabel handles every common enum value', () => {
    // Just a smoke check on the major value categories we render.
    expect(valueLabel('r_16_9')).toContain('16:9');
    expect(valueLabel('r_9_16')).toContain('9:16');
    expect(valueLabel('pro')).toContain('Pro');
    expect(valueLabel('sec_5')).toBe('5 sec');
    expect(valueLabel('p720')).toBe('720p');
    expect(valueLabel('kling_v3')).toBe('Kling v3');
    expect(valueLabel('omni_3')).toBe('Omni v3');
  });

  it('valueLabel handles booleans + nullish', () => {
    expect(valueLabel(true)).toBe('On');
    expect(valueLabel(false)).toBe('Off');
    expect(valueLabel(null)).toBe('');
    expect(valueLabel('')).toBe('');
  });

  it('valueLabel falls back to raw value for unknown', () => {
    expect(valueLabel('mystery_value')).toBe('mystery_value');
  });

  it('VALUE_LABELS covers every Kling-style ratio code', () => {
    // Defensive: panel won't show raw r_1_4 / r_4_1 codes to user.
    const ratios = ['r_1_1', 'r_4_3', 'r_3_4', 'r_3_2', 'r_2_3', 'r_16_9', 'r_9_16', 'r_21_9'];
    for (const r of ratios) {
      expect(VALUE_LABELS[r], `${r} missing label`).toBeTruthy();
    }
  });
});
