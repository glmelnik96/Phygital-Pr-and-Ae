// Friendly labels + helper hints for every slot name across all supported
// nodes. Source of truth for slot names: sidecar/app/workflows/video_common.py
// (NODE_SLOTS) + NANO_BANANA_META.slots. New slot name → add it here too.

export const SLOT_LABELS = {
  // Nano Banana (id 94)
  init_img:     'Initial image',
  image_tail:   'End image',

  // Seedance (id 100)
  start_img:    'Start frame',
  end_frame:    'End frame',
  ref_img:      'Reference image',
  ref_vid:      'Reference video',
  ref_audio:    'Reference audio',

  // Kling Omni (id 121)
  first_frame:  'First frame',
  last_frame:   'Last frame',

  // Kling Motion (id 124)
  char_ref:     'Character reference',
  video:        'Driving video',

  // Shared across 74/121
  element_1:    'Element 1',
  element_2:    'Element 2',
  element_3:    'Element 3',
  element_4:    'Element 4',
};

// One-line hint shown below the slot label. Helps users understand WHAT
// the slot is for at a glance, without forcing them to consult docs.
export const SLOT_HINTS = {
  init_img:     'Image that will be edited / first frame of the video.',
  image_tail:   'Optional. End frame the video should interpolate toward.',
  start_img:    'First frame of the generated video.',
  end_frame:    'Last frame — the model interpolates start → end.',
  ref_img:      'Subject / style reference. Not used as a video frame.',
  ref_vid:      'Motion reference: rhythm and camera move are copied.',
  ref_audio:    'Audio track to drive lip-sync / beat-aware motion.',
  first_frame:  'First frame of the generated clip.',
  last_frame:   'Last frame of the generated clip.',
  char_ref:     'Image of the character that should appear in the result.',
  video:        'Driving video — composition / motion is preserved.',
  element_1:    'Visual element to compose into the result.',
  element_2:    'Visual element to compose into the result.',
  element_3:    'Visual element to compose into the result.',
  element_4:    'Visual element to compose into the result.',
};

export function slotLabel(name) {
  return SLOT_LABELS[name] || name;
}

export function slotHint(name) {
  return SLOT_HINTS[name] || '';
}
