# Roadmap

Фазы без сроков, по приоритету. Каждая фаза — отдельный Claude Code чат (см. [HANDOFF.md](HANDOFF.md)).

## Phase 0 — Scaffold (done, 2026-05-21)

Структура каталогов, манифесты CEP, заглушки HTTP, документация. Кода нет.

## Phase 1 — Sidecar MVP

Цель: sidecar отвечает на `/health`, `/auth/recon`, `/nodes`, `/jobs` (только image-генерация
через `Nano Banana` для проверки end-to-end).

- [ ] Vendoring / submodule стратегия для `Phygital-bot/client` + `workflows/image_gen.py`
  (решить в начале фазы — vendor copy с pinned commit предпочтительнее submodule'а из-за
  репозитория Phygital-bot, который не публичный).
- [ ] FastAPI приложение (`sidecar/app/main.py`): lifecycle (startup → preflight session,
  shutdown → cancel running jobs).
- [ ] `TaskRegistry` (in-memory + `jobs.jsonl`-журнал, restore при старте).
- [ ] `POST /jobs` для `node_id=94` (Nano Banana) → submit → poll → download → отдать путь.
- [ ] Smoke test: `curl POST /jobs` с минимальным prompt → итоговый файл на диске.

## Phase 2 — CEP Premiere MVP

Цель: панель в Pr 2024+ с текстовым промптом и одной нодой; результат — на таймлайн.

- [ ] Заполнить `cep-premiere/CSXS/manifest.xml` (бандл-id, host, размеры — уже сделано в scaffold).
- [ ] `cep-premiere/client/panel.js`: HTTP-клиент к localhost:8765, минимальный UI
  (prompt + кнопка Generate + статус).
- [ ] `cep-premiere/host/insert_media.jsx`: `importFile` + `insertClip` на playhead активной
  sequence. Тест на video-файле и image-файле (Pr делает image-clip с дефолтным duration).
- [ ] Ручной чек: установка через симлинк в `%AppData%\Adobe\CEP\extensions\PhygitalStudioPr`,
  включить PlayerDebugMode, открыть Window → Extensions → Phygital Studio.

## Phase 3 — CEP AE MVP

Симметрично фазе 2, но проще: AE-импорт элементарен (`importFile` → `comp.layers.add`).

- [ ] `cep-ae/client/panel.js`: тот же HTTP-клиент.
- [ ] `cep-ae/host/insert_media.jsx`: `app.project.importFile` → активная comp →
  `comp.layers.add(footage, duration)` на playhead.

## Phase 4 — Video-workflows

Добавить video-ноды на sidecar:

- [ ] `sidecar/app/workflows/sora.py` (по образцу `image_gen.py` — `WORKFLOW_SCHEMA_ID`,
  params типа `seconds`, `aspect_ratio`). ID и payload снять через recon на одной
  ручной генерации в UI Phygital.
- [ ] `sidecar/app/workflows/veo.py`, `runway_i2v.py`, `kling_omni.py` — то же.
- [ ] Сценарий init-image для i2v: panel → `POST /jobs/{id}/upload` → `file_obj_id` →
  `POST /jobs` с `init_files=[file_obj_id]`.

## Phase 5 — Polish (done, 2026-05-23 → V1.1)

- [x] Очередь в UI (`<QueueWidget>` поверх табов: queued + running с per-job cancel).
- [x] Estimate стоимости перед запуском (`<CostBar>` + `POST /jobs/preview-cost`,
      Submit блокируется при `price > balance`).
- [x] Persist UI-state между запусками Pr (`phygital-studio.jobMeta.v1` в
      `localStorage`: `localPath`, `projectItemId`; thumbnails через `file:///`).
- [x] Toast-нотификации о готовности (auto-import + success/warning toast).
- [x] Auto-fill image slot from active clip (`<GenerateTab>` useRef-страж).

V1.1 sidecar polish (parallel):
- [x] M8 Idempotency-Key для `POST /jobs` (24h TTL, in-memory).
- [x] M9 cursor-pagination на `GET /jobs`.
- [x] M11 `/v1/` версионирование (dual-mount, legacy без префикса работает).
- [x] M14 `HEAD /jobs/{id}/download` для preflight'а thumbnails.

Полный список — [`CHANGELOG.md`](../CHANGELOG.md). Открытые вопросы → [`NEXT_AUDIT.md`](NEXT_AUDIT.md).

## Phase 6 — Mac parity

- [ ] Тест sidecar'а на Mac (truststore + system CA, Playwright Chromium для Mac).
- [ ] Симлинки CEP в `~/Library/Application Support/Adobe/CEP/extensions/`.
- [ ] Установочный скрипт (`install.sh` для Mac, `install.bat` для Win) — копирует /
  симлинкует панели, проверяет PlayerDebugMode, запускает sidecar.

## Future / опционально

- Phygital_MCP integration: вместо собственного HTTP-слоя — переиспользовать MCP-сервер
  как backend. Откладывается до решения по Phase 2 Phygital_MCP (`phygital_run_node`).
- Cloud.ru FM chat в панели для генерации промптов (как в Extensions-LLM-Chat_Pr).
- UXP-форк Pr-панели — на 2027+, когда Adobe deprecate'нет CEP.
