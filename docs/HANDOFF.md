# Handoff — как подхватить проект в новом чате

Этот документ — точка входа для любой следующей Claude Code сессии.

## Контекст в одном абзаце

Проект `Phygital-Adobe-Studio` — две независимые CEP-панели (Premiere Pro и After Effects)
+ локальный Python-sidecar. Цель — генерировать изображения и видео через Phygital+ прямо
из Adobe и класть результат на таймлайн / в comp. Архитектура — sidecar pattern (FastAPI
на `localhost:8765` поверх переиспользуемого Python-клиента из `Phygital-bot`). Источник
истины по архитектуре — [ARCHITECTURE.md](ARCHITECTURE.md), по auth — [AUTH.md](AUTH.md),
исходный аудит-обоснование — [AUDIT.md](AUDIT.md), план — [ROADMAP.md](ROADMAP.md).

**Текущая версия:** V1.2-WIP (ветка `feat/history-ux-and-dropdown-fixes`,
коммиты `e510421` + `cda87d3` + `197cb94`). Последний релиз — V1.1 (2026-05-23).
История — [`CHANGELOG.md`](../CHANGELOG.md). Открытые вопросы для следующего
аудита — [`NEXT_AUDIT.md`](NEXT_AUDIT.md).

### Активная ветка — что в ней уже сделано

1. **`EnumDropdown`** — custom dropdown через `position: fixed`, решает
   обрезку native `<select>`-popup'а CEP-iframe'ом. Применён в
   `ParamsAccordion`, `ScenarioPicker`, `ModelPicker`.
2. **History**: `↻ Retry` (восстанавливает draft из `job.params` →
   Generate-таб), `📋 Copy prompt` (через `execCommand` — clipboard API в
   CEP-iframe не secure), click-to-expand preview prompt'а.
3. **`🗑 Delete uploaded source cache`** в History-табе (раньше иконка без
   подписи в Header'e) — с live size-counter + явный confirm.
4. **`GET /jobs` отдаёт `params`** (без `_init_files`). Без этого
   client-side `canRetry` оставался false → Retry/Copy не рендерились.
5. **`/assets/disk-usage` + `DELETE /assets/disk-cache`** в sidecar
   (объявлены до `/{sha256}` — иначе route shadowing).
6. **Progress propagation**: `Workflow._emit_progress()` + on_progress
   callback из `job_runner.run_job` → `JobState.progress` обновляется
   плавно вместо «0% → 100% на completion». Phygital'овский 0..100 / 0..1
   нормализуется в 0..1, дубликаты подавляются.
7. **Synth-progress fallback + first-poll diagnostic** (`197cb94`).
   Если Phygital не отдаёт `progress` — рисуем linear ramp по elapsed
   (image=25s / video=90s, cap 0.95). Реальный API-progress всегда
   побеждает. На первом poll'е логируем полный список keys ответа
   task_status — диагностика: точно ли бэкенд молчит.

### V1.2-WIP — следующий sprint (расширение модельного парка)

In-flight: добавление T2V на нодах 74/100/121 + Topaz Video Upscale (87)
+ GPT Image (98) + Prompt Enhancer через Gemini Text (72).

**Источник истины по shape'ам и опциям нод:**
👉 [`V1.2_T2V_TOPAZ_NOTES.md`](V1.2_T2V_TOPAZ_NOTES.md)

Там — реальные payload'ы из manual recon
(`sidecar/recon-captures/20260531-162221-t2v-manual/`), Topaz dropdowns
(скриншоты + backend codes), версионная матрица Kling/Seedance и open
questions (что ещё надо доcкозать UI'ем). Любая правка
`video_common.py` / `topaz_upscale.py` начинается с прочтения этого файла.

### Подводный камень при тестировании

Sidecar — **отдельный Python-процесс**, перезапуск Pr на него не влияет.
После `git pull` обязательно перезапустить uvicorn (`pkill -f uvicorn` →
`./scripts/install_mac.sh` или ручной `python -m app.main` из `sidecar/`).
Проверка: `lsof -iTCP:8765 -sTCP:LISTEN` должна показывать pid процесса,
запущенного **после** последнего коммита.

## Что прочитать в новом чате (в порядке приоритета)

1. `README.md` корня — карта проекта и связанных репозиториев.
2. Этот файл (HANDOFF.md).
3. `docs/PROJECT_OVERVIEW.md` — как всё работает целиком: компоненты,
   e2e-пайплайны (image и video), persistence, autostart, подводные камни.
4. `docs/ARCHITECTURE.md` — контракт sidecar ↔ панели, ExtendScript-вызовы
   (короче и старее, чем OVERVIEW; OVERVIEW в приоритете).
5. `docs/ROADMAP.md` — определить текущую фазу.
5. Профильные файлы фазы:
   - **sidecar**: `sidecar/README.md`, `sidecar/app/main.py`.
   - **Pr-панель**: `cep-premiere/README.md`, `cep-premiere/CSXS/manifest.xml`,
     `cep-premiere/client/panel.js`, `cep-premiere/host/insert_media.jsx`.
   - **AE-панель**: `cep-ae/README.md`, `cep-ae/CSXS/manifest.xml`,
     `cep-ae/client/panel.js`, `cep-ae/host/insert_media.jsx`.
6. Если фаза трогает Phygital API — `Phygital-bot/client/api.py`, целевой `workflows/<x>.py`,
   `Phygital-bot/nodes_dump.json` для `id`/`params` нужной ноды.
7. Если фаза = **sub-project D (видео)**:
   - Спек: `docs/superpowers/specs/2026-05-21-sub-project-D-video.md`
   - Источник истины по схемам нод и сценариям (vault):
     `01 Projects/Phygital Adobe Studio/Видеоноды Phygital+ — рекон 2026-05-21.md`
   - Fixtures для `build_payload` тестов:
     `sidecar/recon-captures/20260521-133657/extracted/{submit,config}_NN_*.json` (17+17 JSON,
     по одному на каждый task из HAR-сессии 2026-05-21).

## Связанные репозитории на этой машине

Не модифицировать без явной просьбы — это отдельные продукты.

| Путь | Зачем нужен |
|---|---|
| `<USERPROFILE>\Documents\Phygital-bot\` | Источник кода для sidecar: `client/`, `workflows/`, `recon/` |
| `<USERPROFILE>\Documents\Phygital_MCP\` | Альтернативный transport на ту же auth, возможный backend в будущем |
| `<USERPROFILE>\Documents\Adobe-Extensions-Audit\ext_pr\` | Reference: CSXS-манифест Pr CEP 12, bridge-паттерн |
| `<USERPROFILE>\Documents\Adobe-Extensions-Audit\ext_main\` | Reference: AE CEP, готовый `import_file`+`add_to_comp` |

## Правила (для агента)

- **Не коммитить без явной отмашки.** Любой `git commit` / `git push` — только после явного "коммит" / "пуш" от пользователя на конкретное изменение.
- **UI без декоративных эмодзи.** Кнопки/статусы — текстом. См. `feedback_ui_minimal_emoji.md`.
- **Windows-конвенции.** `.bat` — ASCII-only (cp866), stdout python — `reconfigure(encoding='utf-8')`.
  См. `windows_lessons.md`, `windows_port_conventions.md`.
- **Перенос на Mac.** Все пути в `sidecar/` строить через `pathlib` + платформо-зависимые
  AppData / Application Support resolver'ы. Установка / autostart документированы
  в [`cep-premiere/README.md`](../cep-premiere/README.md) — секции
  «Prerequisites — Windows» и «Prerequisites — macOS» симметричны, расхождения
  только в командах (reg add vs defaults write, mklink vs ln -s, taskkill vs kill -pgid).

## Открытые вопросы (ждут решения в фазе)

См. секцию «Открытые вопросы» в конце [ARCHITECTURE.md](ARCHITECTURE.md).

## Что НЕ делать

- Не пытаться портировать SuperTokens auth на JS внутри CEP — это явно отвергнутая альтернатива
  (см. AUDIT.md, таблица альтернатив).
- Не дублировать workflows из `Phygital-bot` копипастой — vendor с pinned commit (решить в Phase 1).
- Не модифицировать `Extensions-LLM-Chat_Pr` и `Extensions-LLM-Chat` — это другие продукты,
  тут только как reference.
- Не подключать CEP-панель напрямую к Phygital API (минуя sidecar) — auth не выживет.
