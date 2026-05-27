# Changelog

## V1.2-WIP — ветка `feat/history-ux-and-dropdown-fixes`

Серия UX-фиксов и одна архитектурная починка прогресса. Релизного тега ещё
нет; всё накатывается прямо на ветке. Релевантные коммиты: `e510421`, `cda87d3`.

### Sidecar (`/sidecar/`)

- **`GET /jobs` теперь возвращает `params`** (jobs.py `_state_to_dict`).
  Раньше `params` обрезались при сериализации → CEP-клиент не мог решить,
  есть ли prompt/scenario у job'а, и History-кнопки Retry / Copy prompt
  никогда не рендерились. Из ответа исключается только `_init_files`
  (server-side пути, клиенту не нужны).
- **Прокидывание Phygital `progress` в `JobState`** (workflows/base.py
  + video_base.py + image_gen.py + services/job_runner.py).
  Раньше `wait()`-loop только логировал `data['progress']`, никогда не звал
  `registry.update_status(progress=...)` → `JobState.progress` оставался
  `None` до момента переключения статуса на `completed`, а CEP-UI показывал
  0% всё время генерации и резко прыгал в 100% при завершении. Теперь
  `Workflow._emit_progress()` нормализует значение Phygital (0..100 либо
  0..1 → 0..1, clamp до 1.0), дедуплицирует одинаковые отчёты и через
  callback `on_progress`, выставленный из `job_runner.run_job`, пушит
  фракцию в registry. Исключения в callback логируются и подавляются,
  чтобы не валить poll-loop.
- **Synth-progress fallback + диагностический first-poll лог** (`197cb94`,
  workflows/base.py `_synth_progress` / `EXPECTED_DURATION_S`).
  Если Phygital не отдаёт `progress` (только status/position), `wait()`
  засекает момент перехода в running и рисует linear ramp до
  `SYNTH_PROGRESS_CAP=0.95` по elapsed (image=25s, video=90s). Реальный
  API-progress всегда побеждает synth. На первом poll'е логируется полный
  список keys ответа task_status — диагностика, отдаёт ли бэкенд реально
  поле `progress` или synth единственно возможный путь.
- **`GET /assets/disk-usage` + `DELETE /assets/disk-cache`** (routers/assets.py).
  Возвращают `{count, total_bytes}` и удаляют `*.bin` из `asset_uploads/`
  по запросу UI. Объявлены **до** `/{sha256}`-route'а, иначе FastAPI
  ловил `disk-cache` как валидный sha256 → `cache.delete("disk-cache")`
  → 404.

### CEP Premiere panel (`/cep-premiere/`)

- **`EnumDropdown`** (`components/EnumDropdown.js`) — custom dropdown через
  `position: fixed` + viewport-aware placement (авто-flip вверх если внизу
  <120 px, внутренний `max-height: 240px` со скроллом). Решает баг
  «нативный `<select>`-popup обрезается CEP-iframe'ом» → пользователь не
  мог выбрать опции в маленьком окне. Применён комплексно к
  `ParamsAccordion` (все enum-параметры включая Aspect ratio),
  `ScenarioPicker`, `ModelPicker`.
- **Retry / Copy prompt в History** (`components/JobCard.js`). Для
  completed/failed/canceled jobs с сохранённым prompt'ом или сценарием:
  - `↻ Retry` — восстанавливает draft из `job.params`, переключает на
    Generate-таб (re-pick files, всё остальное — из params).
  - `📋 Copy prompt` — сначала пытается `document.execCommand('copy')`
    через off-screen textarea (CEP-iframe — не secure context,
    `navigator.clipboard.writeText` бросает «Write permission denied»),
    `clipboard` API остаётся как fallback.
  - Click-to-expand preview prompt'a.
- **Disk-cache cleanup в History** (`components/HistoryTab.js`). Кнопка
  «🗑 Delete uploaded source cache (asset_uploads)» с live-счётчиком
  `N files · X MB` и явным confirm-диалогом про то, что результаты в
  History не затрагиваются. Раньше кнопка-иконка жила в Header'e без
  подписи — было непонятно, что именно удаляется.

### Tests

- Sidecar: 171 passed (excluding HAR-dependent suites), 12 новых для
  progress propagation (normalize edge cases + emit dedup + integration
  через `_FakeClient` на `VideoWorkflow` и `ImageGenWorkflow`).
- CEP (Vitest): 67 passed, 2 skipped.

### Известное ограничение

После любого изменения sidecar'а нужно **явно перезапустить Python-процесс**.
Перезагрузка панели или Premiere Pro на sidecar не влияет — он работает
отдельным процессом на `127.0.0.1:8765`. Если progress всё ещё 0%→100% —
проверь `lsof -iTCP:8765 -sTCP:LISTEN`: запущенный процесс должен быть
тот, что собран после коммита `cda87d3`.

## V1.1 — 2026-05-23

### Sidecar (`/sidecar/`)

- **Idempotency-Key для `POST /jobs`** (M8). In-memory TTL-кэш (24h) на
  `app.services.idempotency.IdempotencyStore`. Повторный POST с тем же ключом и
  телом → 200 + закэшированный `job_id`. Тело отличается → 422
  `idempotency_conflict`. Хэш — SHA256 канонизированного JSON.
- **Версионирование `/v1/`** (M11). Все бизнес-роутеры смонтированы дважды:
  без префикса (legacy для текущей панели) и под `/v1/`. `/health` остаётся без
  префикса — autostart-watcher панели опрашивает его как probe.
- **Cursor-pagination для `GET /jobs`** (M9). Параметры `?limit=N&cursor=<job_id>`,
  ответ — `{"jobs": [...], "next_cursor": "<job_id>"|null}`. `+1`-lookahead
  возвращает `next_cursor` без второго запроса.
- **`HEAD /jobs/{id}/download`** (M14). Возвращает только заголовки
  (`Content-Type`, `Content-Length`, `X-Last-Modified-Epoch`). Panel использует
  для preflight'а thumbnails. Shared-резолвер `_resolve_download` для GET и HEAD.

### CEP Premiere panel (`/cep-premiere/`)

- **Persistent job thumbnails** (S4.b). `localStorage` cache на
  `phygital-studio.jobMeta.v1` хранит `{job_id → {localPath, projectItemId}}`.
  После перезагрузки панели `<JobCard>` отдаёт превью через `file:///`-URL —
  blob-URL'ы переживают только текущую сессию CEF, локальные пути — постоянно.
- **Persistent job queue widget** (S5.a). Новый `<QueueWidget>` поверх табов
  показывает все `queued + running` job'ы с progress-bar'ом и × cancel.
- **Cost preview перед Submit** (S5.b). Баланс кредитов переехал в глобальный
  store; `<CostBar>` показывает цену через `POST /jobs/preview-cost`;
  `<SubmitButton>` блокируется, если `price > balance` с надписью «Insufficient
  balance · ~N credits».
- **Auto-fill image slot from active clip** (S5.c). На смене сценария/модели
  первый пустой single-image слот автозаполняется из выделенного клипа на
  таймлайне (если это image-клип). `useRef` гарантирует одно срабатывание на
  пару `(model_id, scenario)`.
- **Cyrillic-path import errors visible** (S4.c). `_importFailReason` детектит
  non-ASCII и подсказывает причину в toast'е («Premiere can't read paths with
  non-ASCII characters»).
- **No-session Sign-in button в Header** (S4.a). При `health.status="no_session"`
  кнопка «Sign in» в шапке открывает `POST /auth/recon`.

### ExtendScript host (`cep-premiere/host/host.jsx`)

- **`importToBin` ↔ `_binByName` race** (S3.a). 8-секундный poll с шагом 150ms
  + fallback `_findImportedByPath` (по `getMediaPath`) — Pr на части билдов
  игнорирует `bin`-arg и кладёт в root.
- **`_findProjectItemById` кэш** (S3.b). `_piCache: {nodeId → ProjectItem}`
  превращает O(N) walk дерева в O(1) lookup для `revealInBin`. Soft-invalidation
  на `importToBin`.
- **`getTimelineSelection` filter `kind:"unknown"`** (S3.e). `_itemKind=='unknown'`
  больше не возвращается клиенту; если ВСЕ выделенные клипы — unknown,
  возвращается `unsupported_kind` вместо `no_selection`.

### Tests

- Sidecar: 168 passed, 2 skipped.
- Client (Vitest): 56 passed, 2 skipped.

### Известное ограничение

Auto-import после reload панели сейчас может ре-импортировать файл в bin, если
он уже там есть. Ответ и план фикса — `docs/NEXT_AUDIT.md`.
