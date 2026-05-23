# Phygital Adobe Studio — комплексная документация

Документ описывает что такое проект, из чего состоит, как работают end-to-end
пайплайны (image и video), какие у системы есть состояние/persistence,
автозапуск, баланс и оценка стоимости — и собирает в одном месте все
подводные камни, найденные при разработке.

Совместим с (но не заменяет):
- [`HANDOFF.md`](HANDOFF.md) — точка входа в новую Claude-сессию
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — оригинальная архитектурная схема
- [`AUTH.md`](AUTH.md) — auth bootstrap через Playwright

Для установки см. [`INSTALL_WINDOWS.md`](INSTALL_WINDOWS.md) и
[`INSTALL_MACOS.md`](INSTALL_MACOS.md).

---

## 1. Что это и зачем

Две независимые CEP-панели для Adobe (Premiere Pro и After Effects) + локальный
Python sidecar. Цель — запускать генерации Phygital+ (Nano Banana, Kling, Sora,
Seedance, Kling Omni, Kling Motion и т.д.) прямо из Adobe и автоматически
класть результат на таймлайн / в композицию.

**Почему нельзя ходить из CEP напрямую в Phygital+:**

- Phygital+ закрыт за SuperTokens (header-mode JWT + cookies + refresh-роутинг
  `rid:anti-csrf`, обновление `st-access-token` по `/auth/session/refresh`).
- Под корпоративным MITM Cloud.ru нужен `truststore.SSLContext` (CA из системного
  Cert Store / Keychain, а не bundled certifi).
- HTTP/2 multipart с `fileobject`-загрузкой.
- В сумме портировать на JS внутри CEP — 2–3 недели + новые баги. Sidecar
  переиспользует Python-клиент из `Phygital-bot` без переписывания.

См. таблицу альтернатив в [`ARCHITECTURE.md` §«Почему sidecar»](ARCHITECTURE.md#почему-sidecar).

---

## 2. Карта репозитория

```
sidecar/                       FastAPI приложение на 127.0.0.1:8765
  app/
    main.py                    lifespan + include_router
    config.py                  Settings (env-based)
    paths.py                   resolve_app_data() — кросс-платформенный AppData
    phygital_client/           vendor copy из Phygital-bot (НЕ редактировать)
    workflows/
      base.py                  vendor: WorkflowBase
      image_gen.py             Nano Banana (node 94)
      image_to_image.py        i2i (общий)
      video_base.py            общая база для видео-нод
      video_common.py          сценарии, slot-схемы, дефолтные параметры
      video_kling.py           node 74
      video_seedance.py        node 100
      video_kling_omni.py      node 121
      video_kling_motion.py    node 124
    routers/
      health.py                /health
      auth.py                  /auth/recon
      nodes.py                 /nodes, /nodes/video
      jobs.py                  /jobs, /jobs/{id}, /jobs/{id}/download, ...
      assets.py                /assets — sha256-дедуп
      account.py               /account/balance — обёртка над credits_info
      clips.py                 /clips/extract_frame, /clips/probe — ffmpeg
    services/
      session_bootstrap.py     загрузка session.json, preflight refresh
      session_manager.py       refresh цикл, 418-retry
      task_registry.py         in-memory + jobs.jsonl + restore
      job_runner.py            семафор N=5, submit→poll→download
      asset_cache.py           sha256-дедуп upload'ов
      downloader.py            S3 → downloads/<job_id>/
      playwright_recon.py      headed Chromium логин

cep-premiere/                  CEP-панель Pr (бандл com.phygital.studio.pr)
  CSXS/manifest.xml            host=PPRO, CEP 11 + 12
  client/
    index.html                 entry
    panel.js                   bootstrap (ensureSidecar → render App)
    panel.css                  все стили
    components/                Preact + htm компоненты
      App.js, Header.js, Tabs.js
      GenerateTab.js           слоты + промпт + параметры + submit
      HistoryTab.js            фильтр + список job'ов
      SlotPicker.js, SlotList.js
      ModelPicker.js, ScenarioPicker.js
      ParamsAccordion.js
      PromptInput.js
      SubmitButton.js, CostBar.js
      JobCard.js, JobList.js, JobFilter.js
      Toast.js
    lib/
      api.js                   тонкий fetch-клиент sidecar'а
      host.js                  evalScript-обёртки над host.jsx
      autostart.js             pid-файл + spawn pythonw → /health поллинг
      disk.js                  ASCII-стейджинг для импорта в Pr
      slot_labels.js           friendly-имена слотов (init_img → "Initial image")
      param_labels.js          friendly-имена параметров и enum-значений
      state.js, toast.js, validation.js, slot_schema.js
    vendor/CSInterface.js
  host/host.jsx                ExtendScript: bin/timeline selection, frame export
  tests/                       vitest

cep-ae/                        CEP-панель AE (scaffold)
shared/                        JSON-пресеты нод
docs/                          ← этот документ + ARCHITECTURE/AUTH/ROADMAP/HANDOFF
```

**Источники переиспользуемого кода вне репо (НЕ редактировать):**

| Путь | Зачем |
|---|---|
| `~/Documents/Phygital-bot/` | Источник `phygital_client/` и `workflows/{base,image_gen}` |
| `~/Documents/Phygital_MCP/` | Альтернативный transport на ту же auth (потенциальный backend) |
| `~/Documents/Adobe-Extensions-Audit/ext_pr/` | Reference CSXS-манифеста Pr |
| `~/Documents/Adobe-Extensions-Audit/ext_main/` | Reference AE `importFile`+`add_to_comp` |

---

## 3. Высокоуровневая схема

```
┌─────────────────────────────────────────────────────────────┐
│ Adobe Premiere Pro (CEP host)                               │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ CEP panel: Preact UI (HTML + JS)                        │ │
│ │  ├─ HTTP к 127.0.0.1:8765 (api.js)                      │ │
│ │  ├─ CSInterface.evalScript → host.jsx (host.js)         │ │
│ │  └─ node:child_process spawn pythonw (autostart.js)     │ │
│ └─────────┬──────────────────────────────┬────────────────┘ │
│           │                              │                  │
│           │ evalScript                   │                  │
│           ▼                              │                  │
│ host/host.jsx (ExtendScript ES3 + QE DOM)                   │
│  ├─ getBinSelection / getTimelineSelection                  │
│  ├─ exportTimelineFrame (QE → ffmpeg fallback)              │
│  ├─ getSourceInOut                                          │
│  └─ importToBin                                             │
└──────────────────────────────────────────┼──────────────────┘
                                           │ HTTP
                                           ▼
                  ┌───────────────────────────────────────┐
                  │ Sidecar (FastAPI на 127.0.0.1:8765)   │
                  │  ├─ /health, /auth/recon, /nodes      │
                  │  ├─ /jobs, /jobs/{id}, /assets        │
                  │  ├─ /account/balance                  │
                  │  ├─ /clips/extract_frame, /clips/probe│
                  │  ├─ Semaphore(N=5) на job_runner      │
                  │  └─ TaskRegistry → jobs.jsonl         │
                  └──────────┬────────────────────────────┘
                             │ httpx + h2 + truststore + JWT
                             ▼
                  ┌───────────────────────────────────────┐
                  │ Phygital+ API (app-server-azure)      │
                  │  /api/v2/team/credits_info            │
                  │  /api/v2/workflow/run-by-id           │
                  │  /api/v2/file/upload                  │
                  │  /api/v2/task/* (status, download)    │
                  └───────────────────────────────────────┘
```

---

## 4. End-to-end пайплайны

### 4.1 Image: Nano Banana (node 94, text2img или img2img)

```
[user fills prompt + optional init_img]
        │
        ▼
SubmitButton click
        │
        ▼
client/api.js: POST /jobs {node_id:94, params:{prompt,...}, init_files:{init_img:[path]}}
        │
        ▼ (sidecar)
routers/jobs.py: TaskRegistry.create() → job_id (ULID)
        │
        ▼
job_runner: acquire semaphore (≤5 параллельно)
        │
        ├─ если есть init_files: asset_cache.upload_or_get(path)
        │     ├─ sha256 файла
        │     ├─ если уже в кэше → переиспользовать file_obj_id
        │     └─ иначе POST /api/v2/file/upload → file_obj_id
        │
        ▼
workflows/image_gen.build_payload({prompt, init_img→fileobject_id, ...})
        │
        ▼
client.run_workflow(94, payload) → task_id
        │
        ▼
poll /api/v2/task/{id} every ~1.5s до status="completed"
        │
        ▼
downloader: GET result_url → AppData/PhygitalStudio/downloads/<job_id>/*.png
        │
        ▼
TaskRegistry.update(status=completed, result_paths=[...])
        │
        ▼ (panel, polling /jobs/{id})
JobCard.status="completed" → пользователь жмёт Insert
        │
        ▼
host.js → ExtendScript importToBin(path) → ProjectItem
        │
        ▼ (optional) insertClip → timeline на playhead
```

Реальный пример параметров — см. `sidecar/tests/test_workflow_image_gen.py`.

### 4.2 Video: Kling/Seedance/Omni (i2v со сценариями)

Видео-ноды — мульти-сценарные. Сценарий определяет какие slot'ы обязательны.

```
[user picks scenario, e.g. start_end_prompt for Seedance]
        │
        ▼
ScenarioPicker → app state: scenario, requiredSlots=[start_img, end_frame]
        │
        ▼
SlotPicker для каждого slot'а:
  ├─ "Browse…"        → выбор файла из ОС
  ├─ "From bin"       → getBinSelection() → ProjectItem.getMediaPath
  └─ "From Timeline frame" / "From In/Out" →
       host: exportTimelineFrame() / getSourceInOut() →
       AppData/PhygitalStudio/clips/<sha>.jpg|.mp4
        │
        ▼
client/disk.js: stageToAscii(path)
  ├─ если путь содержит Cyrillic → копировать в C:\ProgramData\PhygitalStudio\imports\<sha>.ext
  └─ иначе вернуть путь как есть
        │
        ▼
SubmitButton: POST /jobs {node_id:100, params:{prompt, scenario, ...},
                          init_files:{start_img:[path], end_frame:[path]}}
        │
        ▼ (sidecar workflows/video_seedance.py)
build_payload:
  ├─ value = [fileobject_id_1, fileobject_id_2, ...]
  ├─ type = "image" (или "video")
  └─ meta.dimensions = [{h, w}, {h, w}, ...]    ← ОБЯЗАТЕЛЬНО parallel array!
        │
        ▼
run_workflow → task_id → poll → download → mp4 в downloads/<job_id>/
        │
        ▼ (panel)
JobCard.completed → Insert → host.jsx importToBin → опционально insertClip
```

### 4.3 Frame extraction из timeline (важный sub-pipeline)

QE DOM (`projectItem.exportFrameJPEG`) на пользовательских билдах Pr 2024/2025
**ломается молча** — `app.enableQE()` возвращает `false`, или вызов отрабатывает
без ошибки но файл не создаётся.

Текущий обход:

```
host.jsx exportTimelineFrame() пытается QE.
  └─ если QE.encoderHost === null OR файл не создан →
       вернуть {ok:false, error:"qe_unavailable"}
        │
        ▼ (panel detects)
host.js getSourceInOut() → mediaPath + inSec + outSec
        │
        ▼
client/api.js: POST /clips/extract_frame {mediaPath, atSec}
        │
        ▼ (sidecar routers/clips.py)
ffmpeg -ss atSec -i mediaPath -vframes 1 -f mjpeg → bytes
        │
        ▼
AppData/PhygitalStudio/clips/<sha>.jpg → отдать путь панели
```

ffmpeg должен быть на `PATH` (см. install-доки).

### 4.4 Auth bootstrap

См. полностью в [`AUTH.md`](AUTH.md). Краткое резюме:

1. sidecar/main.py lifespan: загрузить `session.json`, preflight refresh JWT
   если TTL < 15мин.
2. Если `session.json` нет → 503 на запросах кроме `/auth/recon`.
3. `/auth/recon` → playwright_recon.run() → headed Chromium с persistent context →
   пользователь логинится → cookies захватываются → `session.json`.
4. session_manager на каждый 401/418 SuperTokens → POST `/auth/session/refresh` →
   обновить JWT → повторить запрос.

### 4.5 Cost auto-estimation

```
GenerateTab: useEffect наблюдает за {node, params, slots}
  └─ debounce 600ms, race protection via useRef inFlight
        │
        ▼
api.previewCost(node_id, params) → POST /jobs/preview-cost
        │
        ▼
sidecar: phygital_client.get_credits_price(node_id, payload)
        │
        ▼
CostBar показывает "~N credits" если результат свежий (matches current draft costKey)
SubmitButton: "Generate · ~N credits"
```

Если cost > 100 — CostBar выделяется жёлтым (warning, не блокирующий).

### 4.6 Balance polling

```
Header: useEffect → api.getBalance() каждые 30s пока sidecar online
        │
        ▼ (sidecar account.py)
client.get_credits_info() → POST /api/v2/team/credits_info
        │
        ▼
sum credits_balance across members → {balance, is_infinity, expires_at, user_name}
        │
        ▼
fmtBalance: 0..999→"734", 1k..999k→"12.3k", 1m+→"1.2m", is_infinity→"∞"
```

---

## 5. Sidecar HTTP API (полный контракт)

| Метод | Путь | Тело / параметры | Ответ |
|---|---|---|---|
| `GET` | `/health` | — | `{ok, session_age_sec, jwt_ttl_sec, active_jobs}` |
| `POST` | `/auth/recon` | — | `{started: true}` или 409 |
| `GET` | `/nodes` | — | `{nodes: [{id, name, workflow_class}]}` |
| `GET` | `/nodes/video` | — | `{nodes: [{node_id, model, scenarios, slots, scenario_slots, default_params}]}` |
| `POST` | `/jobs` | `{node_id, params, init_files?}` | `{job_id}` |
| `POST` | `/jobs/preview-cost` | `{node_id, params}` | `{credits, currency}` |
| `GET` | `/jobs` | `?status=&limit=` | `{jobs: [...]}` |
| `GET` | `/jobs/{id}` | — | `{job_id, status, progress, result_paths, error, ...}` |
| `GET` | `/jobs/{id}/download` | `?index=0` | bytes |
| `DELETE` | `/jobs/{id}` | — | 204 |
| `POST` | `/assets` | multipart `file=@...` | `{sha256, file_obj_id, mime, size}` |
| `GET` | `/assets` | — | `{assets: [...]}` |
| `DELETE` | `/assets/{sha256}` | — | 204 |
| `DELETE` | `/assets?all=true` | — | 204 |
| `GET` | `/account/balance` | — | `{ok, balance, currency:"credits", is_infinity, expires_at, user_name}` |
| `POST` | `/clips/extract_frame` | `{mediaPath, atSec}` | `{ok, path}` |
| `POST` | `/clips/probe` | `{mediaPath}` | `{ok, width, height, duration, ...}` |

Статусы job'а: `queued | uploading | submitted | pending | running | downloading | completed | failed | canceled`.

---

## 6. Состояние на диске

| Что | Windows | macOS |
|---|---|---|
| Auth + конфиг | `%LOCALAPPDATA%\PhygitalStudio\` | `~/Library/Application Support/PhygitalStudio/` |
| ASCII-стейджинг для импорта | `C:\ProgramData\PhygitalStudio\imports\` | `/tmp/phygital-imports/` |
| Sidecar PID-файл (autostart) | `%TEMP%\phygital-sidecar.pid` | `$TMPDIR/phygital-sidecar.pid` |

Содержимое AppData/PhygitalStudio:

| Файл/каталог | Что |
|---|---|
| `session.json` | Phygital cookies + JWT + captured_at |
| `user_data/` | Playwright persistent profile |
| `downloads/<job_id>/` | Скачанные результаты, TTL 24h |
| `uploads/<session_id>/` | Загруженные init-картинки, TTL 1h |
| `clips/<sha>.jpg|.mp4` | Кэш фреймов и timeline-вырезок |
| `asset_cache.jsonl` | sha256 → file_obj_id (Phygital upload dedupe) |
| `jobs.jsonl` | Append-only журнал задач для restore |
| `logs/sidecar.log` | Ротация 10MB × 5 |

Всё в `.gitignore`. **Никогда не коммитить `session.json`.**

---

## 7. Автозапуск и lifecycle

`client/lib/autostart.js` решает задачу «sidecar поднимается сам и
перезапускается при reload панели»:

1. На каждый mount панели: читаем PID из `tmpdir/phygital-sidecar.pid`.
2. Если PID есть → `taskkill /T /F` (Windows) или `kill(-pgid, SIGTERM)` (macOS).
3. Ждём 500ms чтобы порт 8765 освободился.
4. Пробим `GET /health` — если живо без нашего PID-файла, значит пользователь
   запустил sidecar вручную (dev-режим) → уважаем, ничего не трогаем.
5. Иначе `spawn(<python>, ['-m','app.main'], {detached:true, stdio:'ignore', windowsHide:true})`,
   пишем PID в файл. Список кандидатов на Python: сначала project-local venv
   (`<sidecarDir>/.venv/bin/python3` или `\.venv\Scripts\pythonw.exe`), затем
   глобальные пути (`/opt/homebrew/bin/python3`, `C:\Python311\pythonw.exe` и т.д.).
6. Поллим `/health` до 15 секунд.

**На quit Pr:** `CSXS ApplicationBeforeQuit` + `beforeunload` →
`stopSpawnedSidecar()` → kill + clearPidFile. Сторонний sidecar (без нашего PID)
не трогаем.

Зачем PID-файл вместо module-scope переменной: при Ctrl+R в CEP DevTools
модуль перезагружается, `spawnedPid = null` теряется — без PID-файла мы бы
оставили в /health старый процесс и не подцепили бы новый код sidecar'а.

---

## 8. UI: соответствие кнопок и функций

| Компонент / кнопка | Что делает |
|---|---|
| `Header` — pill «online/no_session/offline» | Цвет от `/health.status` |
| `Header` — balance pill | Polling `/account/balance` каждые 30s |
| `Tabs` — Generate / History | Переключение представлений |
| `ModelPicker` — список моделей | `GET /nodes` + `GET /nodes/video`, показывает `${name} — image|video` |
| `ScenarioPicker` — список сценариев | Из `scenarios` ноды; hint "Needs: …" по `requiredSlots` |
| `SlotPicker` — «Browse…» / «Add file…» | Native file picker (через CEP fs); disabled когда scalar slot заполнен |
| `SlotPicker` — «From bin» | `host.getBinSelection()` |
| `SlotPicker` — «From Timeline frame» | `host.exportTimelineFrame()` → fallback `/clips/extract_frame` |
| `SlotPicker` — «From Timeline In/Out» | `host.getSourceInOut()` → mediaPath с in/out |
| `SlotList` — × на каждом item'е | Удалить из slot'а |
| `PromptInput` | Textarea + char counter / "required" |
| `ParamsAccordion` | Сворачиваемый блок enum / number / bool параметров с описаниями |
| `CostBar` | Авто-debounced cost estimate; рендерит только при loading/error/warning |
| `SubmitButton` — «Generate · ~N credits» | POST /jobs; disabled пока есть validation-ошибки |
| `JobFilter` chips | Фильтр по статусу с count'ами; muted (40% opacity) при count=0 |
| `JobCard` — «Insert» | host.importToBin (+ insertClip опционально) |
| `JobCard` — «Open folder» | shell open AppData/.../downloads/<job_id> |
| `JobCard` — ⋯ menu — Delete | DELETE /jobs/{id} с подтверждением |
| `Toast` | Авто-dismiss через 4s (success) / 8s (error); click = ручной dismiss |

---

## 9. Persistence и восстановление

- **Sidecar рестарт.** `TaskRegistry` при старте читает `jobs.jsonl` и для каждой
  незавершённой задачи делает poll Phygital `/api/v2/task/{id}` чтобы
  ресинхронизировать статус.
- **Pr рестарт / panel reload.** При загрузке панель делает `GET /jobs?status=…`
  и восстанавливает список. UI-черновик (промпт, slots, параметры) хранится в
  `localStorage` через `client/lib/state.js`.
- **Asset cache.** `asset_cache.jsonl` (sha256 → file_obj_id) переживает рестарт —
  один и тот же файл не заливается на Phygital повторно.

---

## 10. Тесты

```bash
# Sidecar
cd sidecar && python -m pytest -q          # 80 passed, 24 skipped (live)
python -m pytest -m live -v -s             # требует sidecar + сессии

# Pr panel
cd cep-premiere && npm test                # 52 passed, 2 skipped (integration)
PHYGITAL_INTEGRATION=1 npm test            # включает /health-зависимые
```

---

## 11. Подводные камни (всё, что было обнаружено)

### 11.1 ExtendScript / Adobe

**QE DOM ломается молча на ряде билдов Pr.** `exportFrameJPEG` и схожие
QE-методы могут вернуть «успех» без файла или `app.enableQE()` → `false`.
Решение — fallback на ffmpeg через `/clips/extract_frame`.

**ProjectItem не имеет стабильного `id`.** Используем `nodeId` (host.jsx
`_findProjectItemById`).

**ExtendScript = ES3.** Никаких `const`/`let`/arrow/`for..of`/`Array.prototype.find`.
Только `var`, `for(var i=…)`, `Object.hasOwnProperty.call`. JSON делаем
руками через `JSON.stringify` (есть, но капризен).

**Тип ProjectItem'а определяется ненадёжно.** `pi.type` бывает невалидным —
снимаем расширение из `getMediaPath()` и сверяем со списком (см. `_itemKind`).

**CEP при Ctrl+R не очищает Node.js модули.** `spawnedPid` теряется → нужен
PID-файл на диске для cross-reload state.

### 11.2 Windows-специфичные

**MSIX sandbox virtualization.** Когда Claude Code на Windows запущен в MSIX,
он виртуализирует `%LOCALAPPDATA%` под
`%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\…`. Sidecar, запущенный
ИЗ агента, пишет туда — CEP-панель его не видит. **Sidecar надо запускать
руками или autostart'ом панели**, не из агентского терминала.

**Cyrillic-пути ломают Pr import.** `ProjectItem.importFiles(['C:\\Users\\Глеб\\…'])`
падает с MBCS-ошибкой. Решение — `disk.js stageToAscii()` копирует файл в
`C:\ProgramData\PhygitalStudio\imports\<sha>.<ext>` (ASCII-only путь) перед
импортом.

**Дуальные CSXS-ключи.** Pr 2024 = CSXS.11, Pr 2025+ = CSXS.12. PlayerDebugMode
выставлять для обоих.

**Симлинк требует Admin PowerShell.** `New-Item -ItemType SymbolicLink` без admin
fail'ится. Можно через `mklink /D` в cmd.

**`taskkill` без `/T` не убивает uvicorn-воркеров.** Node `process.kill` тоже
только лидера. Только `taskkill /T /F` берёт дерево.

**`pythonw.exe`, не `python.exe`.** `python.exe` открывает console window
поверх Pr.

**`.bat` файлы должны быть ASCII / cp866.** UTF-8 в `.bat` ломает cmd-парсер.

**stdout Python через cmd → mojibake.** Если из sidecar пишутся не-ASCII логи в
stdout, надо `sys.stdout.reconfigure(encoding='utf-8')`.

### 11.3 macOS-специфичные

**TCC: «Files and Folders» prompt при первом запуске.** Когда Pr запускает
python3 как child-процесс CEP, macOS спрашивает доступ к
`~/Library/Application Support/PhygitalStudio/`. Не одобрить = sidecar не
прочитает session.json.

**`/usr/bin/python3` это 3.9.** Avoid. Хочется 3.10+ из Homebrew или python.org.

**Apple Silicon vs Intel Homebrew.** `/opt/homebrew/bin/python3` vs
`/usr/local/bin/python3`. autostart.js пробует оба.

**`kill -pgid TERM` требует `detached:true` при spawn.** Тогда child становится
process-group leader и `process.kill(-pid)` берёт всё дерево.

**`Cmd+W` не выходит из Pr.** Нужен `Cmd+Q` чтобы ApplicationBeforeQuit
выстрелил и stopSpawnedSidecar отработал.

### 11.4 Phygital+ API

**img2img / i2v требуют parallel meta.dimensions.** Если slot имеет несколько
файлов — `value = [fid1, fid2]` и `meta.dimensions = [{h,w},{h,w}]`. Длины
должны совпадать. **Несовпадение = silent cancel задачи через ~30s без
ошибки.** Workflow-классы строят dimensions из размеров файлов перед submit.

**SuperTokens 418 = JWT истёк.** Не 401. session_manager делает refresh + retry.

**Refresh-cookie приходит на каждый ответ, но обновлять надо только если
сменился `sFrontToken`.** Иначе перезапись cookies без причины.

**Cloud.ru MITM режет certifi-bundled CA.** Только `truststore.SSLContext`
(берёт CA из системного хранилища) работает.

**Content moderation Phygital возвращает успех + `error_code:"safety"` в
result.** Не HTTP-ошибка. Workflow обрабатывает и маркирует job как `failed`.

**`get_credits_price` неактуален для некоторых нод.** Возвращает прайс модели
без учёта параметров (длительность, ratio). Не надёжный источник цены.

### 11.5 CEP

**`window.cep_node` не равно `require`.** Внутри CEP `require` работает только
если в manifest.xml установлено `<CEFCommandLine><Parameter>--enable-nodejs</Parameter></CEFCommandLine>`.

**`localStorage` в CEP персистентен.** Используется в `state.js` для черновика.

**CEP CSXS event API асинхронный.** `ApplicationBeforeQuit` стреляет ДО
закрытия — у нас есть ~секунда чтобы убить sidecar.

**ExtendScript коммуникация — только через `evalScript(string)`.** Аргументы
сериализуем через `JSON.stringify`, ответ парсим через `JSON.parse`. Большие
объекты сжимаем где возможно.

**CEF DevTools на `localhost:8099`.** Порт прописан в `.debug`-файле бандла.

### 11.6 Sidecar runtime

**Семафор N=5 на job_runner.** Жёсткий лимит на параллельные задачи в Phygital
(найден эмпирически — больше начинает ronald'ить).

**`asyncio.gather` с задачами разной длительности.** Все ждут самую долгую.
job_runner использует `asyncio.create_task` + регистрирует в TaskRegistry
индивидуально, не gather.

**Lifespan startup переписывает `app.state.get_client`.** Поэтому в pytest
patch'и надо ставить ВНУТРИ `with TestClient(app) as c:` (после старта).

**uvicorn по умолчанию форкает воркеров.** `--workers 1` (наш конфиг) и
`detached:true` при spawn — иначе TaskRegistry рассинхронится между процессами.

---

## 12. Известные ограничения / TODO

- AE-панель (sub-project C) — scaffold готов, реализации нет.
- Cost preview для некоторых видео-нод неточен (Phygital `get_credits_price`
  не учитывает duration/ratio полностью).
- Batch UI ("сгенерировать N вариантов") — не реализован.
- SSE-стрим прогресса — отложен в пользу polling 1.5s.
- UXP-форк Pr-панели — отложен на 2027+ (когда Adobe выпилит CEP).
