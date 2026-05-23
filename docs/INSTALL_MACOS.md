# Установка на macOS

Premiere Pro 2024+ (CSXS 11/12), Python 3.10+, ffmpeg.

Полная архитектура — [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md).
Подводные камни macOS — там же §11.3.

> Sidecar полностью кросс-платформенный (Python + httpx + truststore + pathlib).
> Установочная церемония отличается от Windows только командами:
> `defaults write` вместо `reg add`, `ln -s` вместо `mklink`,
> `kill -pgid` вместо `taskkill /T`.

---

## ⚡ TL;DR — автоматический установщик

```bash
cd ~/Documents/Phygital-Adobe-Studio
chmod +x scripts/install_mac.sh
./scripts/install_mac.sh
```

Скрипт делает всё, что описано ниже (Homebrew → python@3.11 → ffmpeg → venv
→ pip deps → playwright chromium → CSXS-ключи → симлинк → recon-логин).
Идемпотентен — повторный запуск безопасен.

Флаги:
- `--skip-deps` — не ставить brew/python/ffmpeg
- `--skip-recon` — не открывать логин в конце
- `--reinstall-venv` — снести и пересоздать `sidecar/.venv`

После завершения: `Cmd+Q` Pr (если открыт) → переоткрыть →
`Window → Extensions → Phygital Studio`.

---

## Ручная установка (шаг за шагом)

## 0. Что должно быть установлено заранее

| Зависимость | Версия | Проверить |
|---|---|---|
| Adobe Premiere Pro | 2024 (24.x) или 2025+ (25.x) | `Premiere Pro → About Premiere Pro` |
| Python | 3.10+ (НЕ системный 3.9) | `python3 --version` |
| ffmpeg | любая ≥ 4.x | `ffmpeg -version` |
| Git | любая (есть из Xcode CLI Tools) | `git --version` |
| Homebrew (опционально) | last | `brew --version` |

### Поставить Homebrew (если нет)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Apple Silicon: brew ставится в `/opt/homebrew/`. Intel: в `/usr/local/`.

### Поставить Python (3.10+)

**Не используй системный `/usr/bin/python3` — это 3.9.** Sidecar требует 3.10+.

Через Homebrew:
```bash
brew install python@3.11
```

Или с [python.org/downloads/macos](https://www.python.org/downloads/macos/) —
обычный .pkg installer (кладёт в `/Library/Frameworks/Python.framework/`).

Проверить:
```bash
python3 --version          # 3.11.x
which python3              # /opt/homebrew/bin/python3 (Apple Silicon)
                           # /usr/local/bin/python3   (Intel)
                           # /Library/Frameworks/...  (python.org)
```

### Поставить ffmpeg

```bash
brew install ffmpeg
ffmpeg -version
```

---

## 1. Склонировать репозиторий

```bash
cd ~/Documents
git clone <repo-url> Phygital-Adobe-Studio
cd Phygital-Adobe-Studio
```

---

## 2. Поставить sidecar-зависимости

```bash
cd sidecar
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

Или глобально (быстрее, грязнее):
```bash
pip3 install loguru truststore pillow-heif playwright pydantic-settings python-ulid h2 fastapi uvicorn httpx
playwright install chromium
```

Autostart-логика панели пробует следующие интерпретаторы по очереди:
- `python3` на `PATH`
- `/opt/homebrew/bin/python3` (Apple Silicon Homebrew)
- `/usr/local/bin/python3` (Intel Homebrew)
- `/Library/Frameworks/Python.framework/Versions/3.{12,11,10}/bin/python3`
- `/usr/bin/python3` (системный 3.9 — fallback, лучше избегать)

Если используется venv, добавь его `bin/python3` в `PATH` через `~/.zshrc`.

---

## 3. Включить CEP debug mode

```bash
defaults write com.adobe.CSXS.11 PlayerDebugMode 1
defaults write com.adobe.CSXS.12 PlayerDebugMode 1
```

**Оба ключа обязательны.** Pr 2024 = CSXS.11, Pr 2025+ = CSXS.12. Если выставлен
только один и Pr запустит «не тот» host, панель просто не появится в Extensions.

После записи — **выйти из Pr полностью (`Cmd+Q`)** и переоткрыть.
Перезагружать всю систему не обязательно.

Откатить:
```bash
defaults delete com.adobe.CSXS.11 PlayerDebugMode
defaults delete com.adobe.CSXS.12 PlayerDebugMode
```

---

## 4. Создать симлинк на панель

```bash
mkdir -p "$HOME/Library/Application Support/Adobe/CEP/extensions"
ln -s "$HOME/Documents/Phygital-Adobe-Studio/cep-premiere" \
      "$HOME/Library/Application Support/Adobe/CEP/extensions/com.phygital.studio.pr"
```

Проверить:
```bash
ls -la "$HOME/Library/Application Support/Adobe/CEP/extensions/com.phygital.studio.pr"
```
Должно показать стрелку на путь репозитория.

`autostart.js` делает `fs.realpathSync()`, поэтому sidecar стартует с реальным
`cwd` (директория репо), а не с символлинка.

---

## 5. Первичный auth recon (один раз)

```bash
cd ~/Documents/Phygital-Adobe-Studio/sidecar
python3 -m scripts.auth_recon
```

(Этот вариант — standalone, sidecar поднимать не надо.
Альтернатива — `python3 -m scripts.cli auth login`, она требует уже
запущенного sidecar'а на `127.0.0.1:8765`.)

Откроется headed Chromium. Залогиниться в Phygital+ — скрипт ловит
SuperTokens cookies и пишет `session.json` в
`~/Library/Application Support/PhygitalStudio/session.json`.

---

## 6. Запустить Premiere Pro

1. **Полностью закрыть Pr** (`Cmd+Q`, не просто `Cmd+W`). CEP сканит расширения
   только при старте процесса.
2. Открыть Pr заново.
3. `Window → Extensions → Phygital Studio`.

Что должно произойти:

- В шапке pill «online» (зелёная) — autostart поднял sidecar.
- Pill с балансом кредитов Phygital+.
- На первом запуске **macOS может запросить TCC-разрешение**: «Premiere Pro
  хочет доступ к Files and Folders / Documents». **Одобрить** — иначе sidecar
  не сможет читать файлы и писать session.json.

Если pill красный:
1. Подождать 15 секунд (autostart polls /health до 15s).
2. DevTools панели: <http://localhost:8099> в Chrome → выбрать
   `Phygital Studio` → Console.
3. Поискать ошибки от `ensureSidecar()`.
4. Проверить, что `python3 --version` отвечает в Terminal.

---

## 7. Проверить, что всё работает

Smoke-test:

1. **Nano Banana text2img.** Выбрать `Nano Banana (image)`, ввести любой
   prompt, жать Generate. Через 10–30 сек в History — completed job.
2. **Insert.** На job-карточке жать `Insert`. Картинка импортируется в bin Pr
   и (опционально) ложится на playhead активной sequence.
3. **Frame extract.** Включить video-сценарий (Kling `start_prompt`), выбрать
   видео в Source Monitor, жать `From Timeline frame`. Кадр должен подцепиться
   (либо QE DOM, либо ffmpeg fallback).

---

## 8. Деинсталляция

```bash
# Удалить симлинк
rm "$HOME/Library/Application Support/Adobe/CEP/extensions/com.phygital.studio.pr"

# Убить остатки sidecar'а
pkill -f "app.main"

# Удалить состояние
rm -rf "$HOME/Library/Application Support/PhygitalStudio"
rm -f /tmp/phygital-sidecar.pid
rm -rf /tmp/phygital-imports

# Выключить CEP debug (опционально)
defaults delete com.adobe.CSXS.11 PlayerDebugMode
defaults delete com.adobe.CSXS.12 PlayerDebugMode
```

---

## 9. Траблшут

### Панель не появляется в `Window → Extensions`

- `PlayerDebugMode = 1` выставлен для **обоих** CSXS.11 и CSXS.12.
- Симлинк существует: `ls -la "$HOME/Library/Application Support/Adobe/CEP/extensions/"`.
- Pr был закрыт через `Cmd+Q`, а не `Cmd+W`. `Cmd+W` оставляет процесс в доке.

### Pill «offline», sidecar не стартует

- В DevTools (`http://localhost:8099`) консоль показывает ENOENT — `python3`
  не находится. Проверить `which python3`. Если Homebrew, и панель не видит —
  убедиться, что `/opt/homebrew/bin` или `/usr/local/bin` в `PATH` для
  GUI-приложений: `launchctl setenv PATH "/opt/homebrew/bin:$PATH"`.
- Порт 8765 занят:
  ```bash
  lsof -nP -iTCP:8765 | grep LISTEN
  ```

### TCC: «Files and Folders» не дали

- `System Settings → Privacy & Security → Files and Folders → Adobe Premiere Pro`
  → включить доступ к `Documents` (и опционально к Downloads).
- После — рестарт Pr.

### Pill «no_session»

- session.json потерян / истёк → `python3 -m scripts.cli auth login`.

### Generate падает с «import failed»

- Кириллица в пути: `disk.js stageToAscii` копирует в `/tmp/phygital-imports/`.
  Проверить, что `/tmp` writable (обычно — да).

### `From Timeline frame` молча ничего не делает

- QE DOM не работает на этом билде. Должен сработать ffmpeg fallback —
  проверить `ffmpeg -version` и DevTools на ошибки `/clips/extract_frame`.

### img2img / i2v завершается через ~30 сек без ошибки

- Silent-cancel Phygital из-за рассинхрона `value` ↔ `meta.dimensions`.
  Перепроверить, что обновлён `workflows/video_*.py` и тесты
  `test_workflow_video_*.py` зелёные.

### Pr тормозит после выхода — `python3` остался

- Sidecar не убит (Pr крашнулся или Cmd+W вместо Cmd+Q).
  ```bash
  pkill -f "app.main"
  rm -f /tmp/phygital-sidecar.pid
  ```
  При следующем mount панели autostart всё равно прибьёт по PID-файлу — но
  если файла нет, надо руками.

### Apple Silicon: «bad CPU type» при запуске python

- Pr под Rosetta, а Homebrew Python собран для arm64. Открыть Premiere Pro в
  Finder → Get Info → снять «Open with Rosetta».
- Альтернатива — поставить Python.org universal binary, который работает в
  обоих режимах.
