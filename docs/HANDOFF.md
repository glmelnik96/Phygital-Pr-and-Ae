# Handoff — как подхватить проект в новом чате

Этот документ — точка входа для любой следующей Claude Code сессии.

## Контекст в одном абзаце

Проект `Phygital-Adobe-Studio` — две независимые CEP-панели (Premiere Pro и After Effects)
+ локальный Python-sidecar. Цель — генерировать изображения и видео через Phygital+ прямо
из Adobe и класть результат на таймлайн / в comp. Архитектура — sidecar pattern (FastAPI
на `localhost:8765` поверх переиспользуемого Python-клиента из `Phygital-bot`). Источник
истины по архитектуре — [ARCHITECTURE.md](ARCHITECTURE.md), по auth — [AUTH.md](AUTH.md),
исходный аудит-обоснование — [AUDIT.md](AUDIT.md), план — [ROADMAP.md](ROADMAP.md).

**Текущая версия: V1.1** (2026-05-23). История — [`CHANGELOG.md`](../CHANGELOG.md).
Открытые вопросы для следующего аудита — [`NEXT_AUDIT.md`](NEXT_AUDIT.md).

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
| `C:\Users\Глеб\Documents\Phygital-bot\` | Источник кода для sidecar: `client/`, `workflows/`, `recon/` |
| `C:\Users\Глеб\Documents\Phygital_MCP\` | Альтернативный transport на ту же auth, возможный backend в будущем |
| `C:\Users\Глеб\Documents\Adobe-Extensions-Audit\ext_pr\` | Reference: CSXS-манифест Pr CEP 12, bridge-паттерн |
| `C:\Users\Глеб\Documents\Adobe-Extensions-Audit\ext_main\` | Reference: AE CEP, готовый `import_file`+`add_to_comp` |

## Правила (для агента)

- **Не коммитить без явной отмашки.** См. `~/.claude/projects/.../memory/feedback_commits.md`.
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
