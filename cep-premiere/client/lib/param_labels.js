// Param + enum-value label maps. Keeps the API contract (raw snake_case
// values sent to Phygital+) decoupled from the UI strings users see.
// Source: sidecar/app/workflows/video_common.py NODE_DEFAULT_PARAMS +
// NODE_PARAM_OPTIONS + NANO_BANANA_META.

export const PARAM_LABELS = {
  // Common
  model:                  'Model variant',
  model_name:             'Model variant',
  ratio:                  'Aspect ratio',
  aspect_ratio:           'Aspect ratio',
  resolution:             'Resolution',
  duration:               'Duration',
  mode:                   'Quality mode',
  sound:                  'Sound',
  cfg_scale:              'Prompt adherence',
  shot_type:              'Shot composition',
  multi_shot:             'Multi-shot',
  seed:                   'Seed',
  camerafixed:            'Lock camera',
  generate_audio:         'Generate audio',
  keep_original_sound:    'Keep original sound',
  character_orientation:  'Orient character by',
};

// One-line description for each param — surfaced via title= tooltip and
// (when ParamsAccordion is expanded) an inline hint.
export const PARAM_DESCRIPTIONS = {
  model:                  'Backbone version. Newer ≠ always better — depends on subject.',
  model_name:             'Backbone version. Newer ≠ always better — depends on subject.',
  ratio:                  'Aspect ratio of the output frame.',
  aspect_ratio:           'Aspect ratio of the output frame.',
  resolution:             'Output frame size. Higher uses more credits.',
  duration:               'Output length in seconds.',
  mode:                   'pro = full quality; std = faster, cheaper.',
  sound:                  'Render an audio track alongside the video.',
  cfg_scale:              '0 = looser interpretation, 1 = strict prompt adherence.',
  shot_type:              'customize lets the prompt drive composition; intelligence/normal lets the model choose.',
  multi_shot:             'Allow the model to cut between multiple shots.',
  seed:                   '-1 for a random seed. Same seed + same inputs ⇒ same output.',
  camerafixed:            'Disable camera movement — useful for product / portrait shots.',
  generate_audio:         'Synthesize an audio track for the clip.',
  keep_original_sound:    'Keep audio from the driving video on the output.',
  character_orientation:  'video = take pose/orientation from the driving video; image = preserve the character image.',
};

// Map enum raw values → user-facing labels. Falls back to raw value when
// missing — better to surface a code than nothing.
export const VALUE_LABELS = {
  // ratio / aspect_ratio
  default:    'Default',
  adaptive:   'Adaptive',
  r_1_1:      '1:1 (square)',
  r_4_3:      '4:3',
  r_3_4:      '3:4',
  r_3_2:      '3:2',
  r_2_3:      '2:3',
  r_16_9:     '16:9 (landscape)',
  r_9_16:     '9:16 (vertical)',
  r_21_9:     '21:9 (cinema)',
  r_1_4:      '1:4',
  r_4_1:      '4:1',
  r_1_8:      '1:8',
  r_8_1:      '8:1',
  r_4_5:      '4:5',
  r_5_4:      '5:4',

  // resolution
  k1:         '1K',
  k2:         '2K',
  k4:         '4K',
  p480:       '480p',
  p720:       '720p',
  p1080:      '1080p',

  // mode
  std:        'Standard (faster)',
  pro:        'Pro (best quality)',
  pro_fast:   'Pro fast',
  pro_1_5:    'Pro 1.5',
  lite:       'Lite',
  v_2_0:      'v2.0',
  v_2_0_fast: 'v2.0 fast',

  // sound (Kling 74 — string enum)
  on:         'On',
  off:        'Off',

  // shot_type
  customize:    'Customize (prompt-driven)',
  intelligence: 'Intelligent (model chooses)',
  normal:       'Normal',

  // duration (Kling 74 string enum)
  sec_3: '3 sec', sec_4: '4 sec', sec_5: '5 sec', sec_6: '6 sec',
  sec_7: '7 sec', sec_8: '8 sec', sec_9: '9 sec', sec_10: '10 sec',
  sec_11: '11 sec', sec_12: '12 sec', sec_13: '13 sec', sec_14: '14 sec', sec_15: '15 sec',

  // model_name (Kling family) — keep clean version strings
  kling_v1:           'Kling v1',
  kling_v1_5:         'Kling v1.5',
  kling_v1_6:         'Kling v1.6',
  kling_v2_master:    'Kling v2 master',
  kling_v2_1_master:  'Kling v2.1 master',
  kling_v2_5_turbo:   'Kling v2.5 turbo',
  kling_v2_6:         'Kling v2.6',
  kling_v3:           'Kling v3',

  // Nano Banana version names
  v2:   'v2',
  v2_5: 'v2.5',
  v3:   'v3',
  v3_1: 'v3.1',

  // Kling Omni model
  omni_1: 'Omni v1',
  omni_3: 'Omni v3',

  // character_orientation
  video: 'Driving video',
  image: 'Character image',
};

export function paramLabel(name) {
  return PARAM_LABELS[name] || name;
}

export function paramDescription(name) {
  return PARAM_DESCRIPTIONS[name] || '';
}

export function valueLabel(raw) {
  if (raw === true) return 'On';
  if (raw === false) return 'Off';
  if (raw == null || raw === '') return '';
  const key = String(raw);
  return VALUE_LABELS[key] || key;
}
