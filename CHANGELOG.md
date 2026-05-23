# Changelog

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
