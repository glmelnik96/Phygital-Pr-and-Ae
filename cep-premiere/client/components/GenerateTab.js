import { html } from '../lib/html.js';
import { useEffect, useRef } from '../vendor/preact-hooks.module.js';
import { FamilyTabs } from './FamilyTabs.js';
import { ModelPicker } from './ModelPicker.js';
import { ScenarioPicker } from './ScenarioPicker.js';
import { PromptInput } from './PromptInput.js';
import { SlotList } from './SlotList.js';
import { ParamsAccordion } from './ParamsAccordion.js';
import { CostBar } from './CostBar.js';
import { SubmitButton } from './SubmitButton.js';
import {
  listNodesByFamily, getNodeMeta, getNodeFamily,
  getSlotsForScenario, nodeHasPrompt,
} from '../lib/slot_schema.js';
import { saveDraftToStorage, createUploadActions } from '../lib/state.js';
import { pickFilesFromDisk, readFileAsBlob, makeThumbDataURL } from '../lib/disk.js';
import { host, hostQueued } from '../lib/host.js';
import { toast } from '../lib/toast.js';
import { slotLabel } from '../lib/slot_labels.js';

const uploadActions = createUploadActions(null);

function isImageSlotName(name) {
  // Heuristic by spec §3.3 slot map. Image slots are: init_img, image_tail,
  // element_*, start_img, end_frame, ref_img, first_frame, last_frame, char_ref.
  // Non-image: ref_vid, ref_audio, video.
  return !/^(ref_vid|ref_audio|video)$/.test(name);
}

// Собрать file_obj_id+dimensions всех загруженных image-картинок из draft.slots
// для текущего сценария. Используется PromptInput'ом, чтобы передать референс
// в /enhance (i2v/i2v enhancer цепляется за визуальный контекст).
//
// Порядок: как в `slots` из getSlotsForScenario (стабильный для тестов).
// Скипаем: video-слоты, ещё-не-загруженные (нет asset.file_obj_id), failed.
// dims берём из asset.{width,height} — Phygital img2img-quirk требует
// параллельных list'ов equal length, поэтому одинокий fid без dims = drop.
function collectImageRefs(slots, slotValues) {
  const ids = [];
  const dims = [];
  for (const slot of slots) {
    if (!isImageSlotName(slot.name)) continue;
    const raw = slotValues[slot.name];
    const items = slot.kind === 'array' ? (raw || []) : (raw ? [raw] : []);
    for (const it of items) {
      const a = it && it.asset;
      if (!a || a.file_obj_id == null) continue;
      if (a.width == null || a.height == null) continue;
      ids.push(a.file_obj_id);
      dims.push({ width: a.width, height: a.height });
    }
  }
  return { ids, dims };
}

function isVideoSlotName(name) {
  return /^(ref_vid|video)$/.test(name);
}

// Списки расширений ДОЛЖНЫ совпадать с _itemKind в host.jsx — иначе bin/timeline
// и disk будут расходиться (например webm проскочит disk-валидацию, но host
// вернёт kind='unknown' и timeline-ветка отбросит).
const IMAGE_EXTS = ['jpg','jpeg','png','tif','tiff','psd','heic','webp','bmp','gif','exr','dpx','tga'];
const VIDEO_EXTS = ['mp4','mov','avi','mkv','m4v','mxf','webm','flv','mts','m2ts','ts','3gp','3g2','wmv','asf','vob','hevc','h264'];

function extOf(p) {
  const parts = String(p).split('.');
  return parts.length > 1 ? parts.pop().toLowerCase() : '';
}

// Превращаем code-style ошибки host'а в человекочитаемые подсказки.
function friendlyHostError(e) {
  const code = (e && e.result && e.result.error) || e.message || 'unknown';
  const reason = e && e.result && e.result.reason;
  // Лог полного error в DevTools — для bin/timeline кейсов attempts-строка
  // несёт точный путь которая API сдалась первой.
  if (typeof console !== 'undefined' && e && e.result) {
    // eslint-disable-next-line no-console
    console.warn('[host error]', code, reason || '');
  }
  const map = {
    no_source_monitor: 'Source Monitor unavailable in this Pr build',
    no_source_monitor_clip: 'Load a clip into the Source Monitor first (double-click clip in Project bin)',
    no_active_sequence: 'No active sequence — open or create a sequence in Premiere',
    no_playhead: 'Could not read playhead position from active sequence',
    // Включаем reason — обычно содержит attempts=... с диагностикой какие
    // API селекции сработали (полезно когда юзер РЕАЛЬНО выделил айтем,
    // но getSelection() пуст из-за фокуса в CEP-панели).
    no_selection: 'Select an item in the Project bin first' +
                  (reason ? ' (debug: ' + String(reason).slice(0, 120) + ')' : ''),
    no_clip_at_playhead: 'Move the playhead over a video/image clip in the active sequence',
    no_clip_at_range: 'No clip under the Timeline In/Out marks (or playhead if no marks)',
    no_project_item: 'Clip under playhead has no linked project item',
    no_media_path: 'Clip media path is empty (offline / merged clip?)',
    marks_outside_clip: 'Timeline In/Out marks do not overlap any clip on the sequence',
    unsupported_kind: 'Selected item is not an image/video/audio file' +
                      (reason ? ' (debug: ' + String(reason).slice(0, 120) + ')' : ''),
    invalid_range: 'In/Out marks are missing or inverted — set marks on the timeline (I / O)',
    export_failed: 'Frame export failed' + (reason ? ' — ' + reason : ''),
  };
  return map[code] || (reason || code);
}

export function GenerateTab({ snap, actions, api, store, onSubmitted }) {
  const { draft, videoNodes, health } = snap;
  // Backfill для draft'ов из localStorage до V1.2 (где не было family).
  // Без этого FamilyTabs упадёт в `value=undefined` и ни одна вкладка не
  // будет активна, а ModelPicker отдаст пустой список.
  const meta = getNodeMeta({ videoNodes, nodeId: draft.model_id });
  const family = draft.family || getNodeFamily(meta) || 'image';
  const nodesInFamily = listNodesByFamily({ videoNodes, family });
  const scenarios = meta ? meta.scenarios : [];
  const slots = getSlotsForScenario({ videoNodes, nodeId: draft.model_id, scenario: draft.scenario });
  const showPrompt = nodeHasPrompt(meta);

  useEffect(() => { saveDraftToStorage(draft); }, [JSON.stringify(draft)]);

  // Auto-fill image slot from active clip. Триггерится один раз на сценарий —
  // пока сценарий не меняется, ничего не делаем (даже если юзер очистил
  // слот вручную, не хотим назойливо переподтягивать). Берём first empty
  // single-image слот; для array-слотов auto-fill двусмысленен (один файл
  // из многих) — пропускаем. Тихо no-op если под playhead'ом не image.
  const autoFilledForScenarioRef = useRef(null);
  useEffect(() => {
    if (health.status !== 'online') return undefined;
    const scenKey = `${draft.model_id}|${draft.scenario}`;
    if (autoFilledForScenarioRef.current === scenKey) return undefined;
    const firstEmptyImg = slots.find(s =>
      s.kind !== 'array' && isImageSlotName(s.name) && !draft.slots[s.name]
    );
    if (!firstEmptyImg) return undefined;
    autoFilledForScenarioRef.current = scenKey;
    let cancelled = false;
    (async () => {
      let sel;
      try { sel = await host.getTimelineSelection(true); }
      catch (_) { return; }  // нет sequence / нет clip под playhead — silent
      if (cancelled) return;
      const items = (sel && sel.items) || [];
      const imgItem = items.find(it => it.kind === 'image');
      if (!imgItem) return;
      // Race-guard: за время host-вызова юзер мог сам положить файл.
      if (store.get().draft.slots[firstEmptyImg.name]) return;
      try {
        await ingestPath(firstEmptyImg, imgItem.path, 'auto', imgItem.name);
        toast.success(`Auto-filled "${slotLabel(firstEmptyImg.name)}" from timeline`);
      } catch (_) { /* upload failure shows its own toast */ }
    })();
    return () => { cancelled = true; };
  }, [draft.model_id, draft.scenario, health.status]);

  async function ingestPath(slot, path, source, displayName) {
    const name = displayName || path.split(/[\\/]/).pop();
    const blob = await readFileAsBlob(path);
    const thumb = await makeThumbDataURL(blob).catch(() => null);
    const item = { source, path, name, thumb };
    if (slot.kind === 'array') {
      const cur = store.get().draft.slots[slot.name] || [];
      actions.setSlot(slot.name, [...cur, item]);
    } else {
      actions.setSlot(slot.name, item);
    }
    try {
      const { entry, cached } = await uploadActions.upload({ api, blob, filename: name });
      const enriched = { ...item, asset: entry, cached };
      if (slot.kind === 'array') {
        const cur2 = (store.get().draft.slots[slot.name] || []).map(x => x.path === path ? enriched : x);
        actions.setSlot(slot.name, cur2);
      } else actions.setSlot(slot.name, enriched);
    } catch (e) {
      const err = { ...item, error: e.message };
      if (slot.kind === 'array') {
        const cur2 = (store.get().draft.slots[slot.name] || []).map(x => x.path === path ? err : x);
        actions.setSlot(slot.name, cur2);
      } else actions.setSlot(slot.name, err);
      toast.error('Upload failed: ' + e.message);
    }
  }

  async function onPick(slot, source) {
    const isImageSlot = isImageSlotName(slot.name);
    const isVideoSlot = isVideoSlotName(slot.name);
    try {
      // 1) Disk picker — общий для image и video. Передаём фильтр расширений в
      //    showOpenDialogEx, чтобы юзер не выбрал видео на image-слот (и наоборот).
      //    Дополнительно валидируем расширение после picker'а: на части билдов CEP
      //    параметр fileTypes игнорируется, поэтому fallback обязателен.
      if (source === 'disk') {
        const accept = isVideoSlot ? VIDEO_EXTS : (isImageSlot ? IMAGE_EXTS : []);
        const paths = await pickFilesFromDisk({ multi: slot.kind === 'array', accept });
        if (!paths || paths.length === 0) return;
        for (const p of paths) {
          const ext = extOf(p);
          if (isImageSlot && !IMAGE_EXTS.includes(ext)) {
            toast.warning(`Slot "${slot.name}" needs an image, got .${ext || '?'}`);
            continue;
          }
          if (isVideoSlot && !VIDEO_EXTS.includes(ext)) {
            toast.warning(`Slot "${slot.name}" needs a video, got .${ext || '?'}`);
            continue;
          }
          await ingestPath(slot, p, 'disk');
        }
        return;
      }

      // 2) Image-only: «Timeline frame» — кадр под playhead'ом активной sequence.
      //    Бросаем QE DOM frame export (rv=false без файла на части билдов Pr) —
      //    вместо этого host возвращает source-relative секунду + путь к исходнику,
      //    sidecar /extract-frame дёргает ffmpeg. Если клип под playhead'ом сам
      //    image-файл (PNG/JPG на дорожке) — берём его напрямую, без ffmpeg.
      if (source === 'timeline_frame') {
        if (!isImageSlot) {
          toast.warning('Timeline frame works only for image slots');
          return;
        }
        let src;
        try {
          src = await host.getTimelineFrameSource();
        } catch (e) {
          // eslint-disable-next-line no-console
          console.error('[getTimelineFrameSource]', e.result || e);
          toast.error('Timeline frame: ' + friendlyHostError(e));
          return;
        }
        // Если на дорожке уже статичная картинка — ingest напрямую, минуя ffmpeg.
        if (src.kind === 'image') {
          await ingestPath(slot, src.path, 'timeline_frame', `${src.clipName || 'frame'}.${extOf(src.path) || 'jpg'}`);
          return;
        }
        // Иначе извлекаем кадр через ffmpeg на sidecar'е.
        let fr;
        try {
          fr = await api.extractFrame({ source_path: src.path, at_sec: Number(src.atSec) });
        } catch (e) {
          const detail = (e.body && e.body.detail) || {};
          // eslint-disable-next-line no-console
          console.error('[extractFrame] detail:', detail, 'path was:', src.path);
          const reason = detail.hint || detail.reason || detail.error || e.message || 'unknown';
          const extra = detail.suffix ? ` [suffix=${detail.suffix}]` :
                        detail.path ? ` [path=${detail.path}]` : '';
          toast.error('ffmpeg frame failed: ' + reason + extra);
          return;
        }
        await ingestPath(slot, fr.path, 'timeline_frame', `frame_${Math.floor(Number(src.atSec) * 1000)}ms.jpg`);
        return;
      }

      // 3) Video-only: «Timeline In/Out» — клип из АКТИВНОЙ SEQUENCE на таймлайне
      //    в пределах sequence In/Out марок. host вычисляет source-relative in/out
      //    топового видео-клипа, sidecar /clip-video режет фрагмент через ffmpeg.
      if (source === 'timeline_io') {
        if (!isVideoSlot) {
          toast.warning('Timeline In/Out works only for video slots');
          return;
        }
        let io;
        try {
          io = await host.getTimelineInOutSource();
        } catch (e) {
          // eslint-disable-next-line no-console
          console.error('[getTimelineInOutSource]', e.result || e);
          toast.error('Timeline In/Out: ' + friendlyHostError(e));
          return;
        }
        // eslint-disable-next-line no-console
        console.log('[timeline_io] path=', io.path, 'in=', io.inSec, 'out=', io.outSec, 'clipName=', io.clipName);
        let clip;
        try {
          clip = await api.clipVideo({
            source_path: io.path,
            in_sec: Number(io.inSec),
            out_sec: Number(io.outSec),
          });
        } catch (e) {
          const detail = (e.body && e.body.detail) || {};
          // eslint-disable-next-line no-console
          console.error('[clipVideo] full detail:', detail, 'path was:', io.path);
          // Surface reason BEFORE error code — `reason` несёт WHY (suffix_not_allowed,
          // source_not_found, resolve_failed, etc.); error — это generic bucket.
          const reason = detail.hint || detail.reason || detail.error || e.message || 'unknown';
          const extra = detail.suffix ? ` [suffix=${detail.suffix}]` :
                        detail.path ? ` [path=${detail.path}]` :
                        detail.protocol ? ` [proto=${detail.protocol}]` : '';
          toast.error('ffmpeg clip failed: ' + reason + extra);
          return;
        }
        const displayName = `${io.clipName || 'clip'}_${Number(io.inSec).toFixed(2)}-${Number(io.outSec).toFixed(2)}.mp4`;
        await ingestPath(slot, clip.path, 'timeline_io', displayName);
        return;
      }

      // 3b) Legacy «Source In/Out» — оставляем для обратной совместимости (если
      //     юзер всё-таки хочет работать из Source Monitor). Кнопка скрыта в
      //     SlotPicker, но source-имя остаётся валидным.
      if (source === 'source_io') {
        if (!isVideoSlot) {
          toast.warning('Source In/Out works only for video slots');
          return;
        }
        let io;
        try {
          io = await host.getSourceInOut();
        } catch (e) {
          // eslint-disable-next-line no-console
          console.error('[getSourceInOut]', e.result || e);
          toast.error('Source In/Out: ' + friendlyHostError(e));
          return;
        }
        let clip;
        try {
          clip = await api.clipVideo({
            source_path: io.path,
            in_sec: Number(io.inSec),
            out_sec: Number(io.outSec),
          });
        } catch (e) {
          const detail = (e.body && e.body.detail) || {};
          // eslint-disable-next-line no-console
          console.error('[clipVideo source_io] detail:', detail, 'path was:', io.path);
          const reason = detail.hint || detail.reason || detail.error || e.message || 'unknown';
          const extra = detail.suffix ? ` [suffix=${detail.suffix}]` : '';
          toast.error('ffmpeg clip failed: ' + reason + extra);
          return;
        }
        const displayName = `${io.name || 'clip'}_${Number(io.inSec).toFixed(2)}-${Number(io.outSec).toFixed(2)}.mp4`;
        await ingestPath(slot, clip.path, 'source_io', displayName);
        return;
      }

      // 4) Generic bin / timeline / source_monitor picks. Auto-frame-extract убран —
      //    для image-слотов из видео-клипа теперь явный пункт «Timeline frame».
      let pickResult = null;
      if (source === 'bin')                   pickResult = await host.getBinSelection();
      else if (source === 'timeline')         pickResult = await host.getTimelineSelection(true);
      else if (source === 'source_monitor')   pickResult = await host.getSourceMonitorItem();
      if (!pickResult) return;

      const items = pickResult.items || (pickResult.item ? [pickResult.item] : []);
      for (const it of items) {
        // Двойная проверка: host.kind + расширение пути. host._itemKind может
        // вернуть 'unknown' для редкого формата — тогда полагаемся на ext.
        const ext = extOf(it.path);
        const isImageFile = it.kind === 'image' || IMAGE_EXTS.includes(ext);
        const isVideoFile = it.kind === 'video' || VIDEO_EXTS.includes(ext);
        if (isImageSlot && isVideoFile) {
          toast.warning('Video clip on image slot — use "Timeline frame" or "Browse..." for a still');
          continue;
        }
        if (isImageSlot && !isImageFile) {
          toast.warning(`Slot "${slot.name}" needs an image, got ${it.kind || ext || '?'}`);
          continue;
        }
        if (isVideoSlot && !isVideoFile) {
          toast.warning(`Slot "${slot.name}" needs a video, got ${it.kind || ext || '?'}`);
          continue;
        }
        await ingestPath(slot, it.path, source, it.name);
      }
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('[onPick]', source, e.result || e);
      toast.error('Source pick: ' + friendlyHostError(e));
    }
  }

  function onClear(slot, item) {
    if (slot.kind === 'array') {
      const cur = draft.slots[slot.name] || [];
      const next = cur.filter(x => x !== item);
      if (next.length === 0) actions.clearSlot(slot.name);
      else actions.setSlot(slot.name, next);
    } else {
      actions.clearSlot(slot.name);
    }
  }

  const disabled = health.status !== 'online';

  return html`
    <div class=${`generate ${disabled ? 'disabled' : ''}`}>
      <${FamilyTabs} value=${family} disabled=${disabled}
        onChange=${f => actions.setFamily(f, { videoNodes })} />
      <${ModelPicker} nodes=${nodesInFamily} value=${draft.model_id}
        onChange=${id => actions.setModel(id, { videoNodes })} />
      <${ScenarioPicker} scenarios=${scenarios} value=${draft.scenario}
        requiredSlots=${slots}
        onChange=${s => actions.setScenario(s, { videoNodes })} />
      ${showPrompt
        ? html`<${PromptInput} draft=${draft} actions=${actions} api=${api}
                imageRefs=${collectImageRefs(slots, draft.slots)} />`
        : null}
      <${SlotList} slots=${slots} values=${draft.slots}
        onPick=${onPick} onClear=${onClear} />
      <${ParamsAccordion} defaults=${meta ? meta.default_params : {}}
        options=${meta ? meta.param_options : {}}
        values=${draft.params} onChange=${actions.setParam} />
      <${CostBar} snap=${snap} api=${api} store=${store} />
      <${SubmitButton} snap=${snap} api=${api} onSubmitted=${onSubmitted} />
    </div>
  `;
}
