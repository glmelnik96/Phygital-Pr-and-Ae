# Phygital-Adobe-Studio

Две независимые CEP-панели (Adobe Premiere Pro и After Effects) + локальный Python-sidecar.
Цель — генерировать изображения и видео через Phygital+ (Sora, VEO, Runway, Kling, Nano Banana,
Flux, GPT Image и др.) прямо из интерфейса Adobe и автоматически класть результат на таймлайн
(Pr) или в активный composition (AE).

**Status (2026-05-21):**
- Sub-project A (sidecar MVP) — реализация завершена, 74 теста.
- Sub-project B (Pr-панель) — реализация завершена, 34 теста, проходит manual E2E.
- Sub-project C (AE-панель) — не начато.
- Sub-project D (видеоноды) — реализовано в sidecar, доступно через Pr-панель.

## Документация

| Документ | О чём |
|---|---|
| [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) | Как работает целиком: компоненты, e2e пайплайны, persistence, подводные камни |
| [docs/INSTALL_WINDOWS.md](docs/INSTALL_WINDOWS.md) | Пошаговая установка на Windows + траблшут |
| [docs/INSTALL_MACOS.md](docs/INSTALL_MACOS.md) | Пошаговая установка на macOS + траблшут |
| [docs/AUDIT.md](docs/AUDIT.md) | Исходный аудит: что переиспользуется, реалистичность, риски |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Sidecar + CEP, потоки данных, контракты HTTP |
| [docs/AUTH.md](docs/AUTH.md) | Бутстрап Phygital-сессии через Playwright recon |
| [docs/ROADMAP.md](docs/ROADMAP.md) | План работ по фазам |
| [docs/HANDOFF.md](docs/HANDOFF.md) | Как подхватить проект в новом Claude Code чате |

## Структура

```
sidecar/        Python FastAPI поверх client/ и workflows/ из Phygital-bot
cep-premiere/   CEP 12 панель для Premiere Pro 2024+
cep-ae/         CEP 11 панель для After Effects 2023+
shared/         JSON-пресеты нод, общие промпт-доки
docs/           аудит, архитектура, auth, roadmap, handoff
```

## Источники переиспользуемого кода (вне этого репо)

- `C:\Users\Глеб\Documents\Phygital-bot\` — `client/` + `workflows/` = база sidecar'а.
- `C:\Users\Глеб\Documents\Phygital_MCP\` — альтернативный transport (MCP) поверх той же auth-логики.
- `C:\Users\Глеб\Documents\Adobe-Extensions-Audit\ext_pr\` — клон Extensions-LLM-Chat_Pr,
  справочно (CSXS-манифест, bridge-паттерн CEP↔ExtendScript).
- `C:\Users\Глеб\Documents\Adobe-Extensions-Audit\ext_main\` — клон Extensions-LLM-Chat (AE),
  справочно (готовые `import_file`+`add_to_comp` в `host/index.jsx`).

Эти проекты — независимые продукты. Phygital-Adobe-Studio их не модифицирует, только
читает как референс и (для sidecar'а) переиспользует Python-модули из Phygital-bot.

## Запуск

Каждая панель документирует свою установку отдельно. Sidecar стартует
**автоматически** из CEP-панели — отдельно его запускать не нужно.

- **Premiere Pro panel** → [`cep-premiere/README.md`](cep-premiere/README.md) —
  prerequisites для Windows и macOS, autostart-схема, manual E2E чек-лист.
- **After Effects panel** → `cep-ae/README.md` (будет добавлен в sub-project C).

Контракт между sidecar и панелями — `http://127.0.0.1:8765`, идентичный
на обеих платформах. Один путь session.json:
- Windows: `%LOCALAPPDATA%\PhygitalStudio\session.json`
- macOS:   `~/Library/Application Support/PhygitalStudio/session.json`

## Перенос на macOS

Sidecar — кросс-платформенный (Python, FastAPI, httpx, truststore, pathlib).
Pr-панель autostart знает оба `pythonw`/`python3`-набора путей и оба способа
убить process tree (`taskkill /T /F` vs `kill -pgid TERM`). Подробности —
[`cep-premiere/README.md`](cep-premiere/README.md) → секция «Prerequisites — macOS».
