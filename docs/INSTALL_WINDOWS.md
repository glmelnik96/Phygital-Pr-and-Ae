# Установка на Windows

Премьер 2024+ (CSXS 11/12), Python 3.10+, ffmpeg.

Полная архитектура — [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md).
Подводные камни Windows — там же §11.2.

---

## 0. Что должно быть установлено заранее

| Зависимость | Версия | Проверить |
|---|---|---|
| Adobe Premiere Pro | 2024 (24.x) или 2025+ (25.x) | `Help → About Premiere Pro` |
| Python | 3.10 / 3.11 / 3.12 | `python --version` или `pythonw --version` |
| ffmpeg | любая ≥ 4.x | `ffmpeg -version` |
| Git | любая | `git --version` |
| Node.js | **не нужен отдельно** — CEP содержит свой |

### Поставить Python (если нет)

С [python.org/downloads](https://www.python.org/downloads/) — обычный installer.
**Обязательно** галка «Add Python to PATH» на первом экране.

После — открыть **новый** PowerShell и проверить:
```powershell
python --version
pythonw --version
```

### Поставить ffmpeg

Простейший вариант — через winget:
```powershell
winget install -e --id Gyan.FFmpeg
```

Или вручную: скачать `ffmpeg-release-essentials.zip` с
[gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) → распаковать в
`C:\ffmpeg\` → добавить `C:\ffmpeg\bin` в системный `PATH`.

Проверить: `ffmpeg -version` в **новом** PowerShell.

---

## 1. Склонировать репозиторий

```powershell
cd $env:USERPROFILE\Documents
git clone <repo-url> Phygital-Adobe-Studio
cd Phygital-Adobe-Studio
```

Если SSH-ключ в `~/.ssh/` не виден OpenSSH (например, из-за нелатинских
символов в имени профиля Windows), временно зеркало `~/.ssh/` в путь
без таких символов и указать на него через `GIT_SSH_COMMAND`:
```powershell
$env:GIT_SSH_COMMAND = "ssh -i <PATH_TO_MIRROR>\.ssh\<key_name> -o IdentitiesOnly=yes"
git clone git@github.com:<owner>/<repo>.git Phygital-Adobe-Studio
```

---

## 2. Поставить sidecar-зависимости

```powershell
cd sidecar
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
playwright install chromium
```

> Если `Activate.ps1` ругается на execution policy:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

Альтернатива без venv (быстрее, но грязнее) — глобальный pip:
```powershell
pip install loguru truststore pillow-heif playwright pydantic-settings python-ulid h2 fastapi uvicorn httpx
playwright install chromium
```

Autostart-логика панели пробует следующие интерпретаторы по очереди:
- `pythonw` на `PATH`
- `C:\Python310\pythonw.exe`
- `C:\Python311\pythonw.exe`
- `C:\Python312\pythonw.exe`

Если используется venv — добавь его `Scripts\pythonw.exe` в `PATH` или
ставь Python глобально.

---

## 3. Включить CEP debug mode

В обычном PowerShell (без admin):
```powershell
reg add "HKCU\Software\Adobe\CSXS.11" /v PlayerDebugMode /t REG_SZ /d 1 /f
reg add "HKCU\Software\Adobe\CSXS.12" /v PlayerDebugMode /t REG_SZ /d 1 /f
```

**Оба ключа обязательны.** Pr 2024 использует CSXS.11, Pr 2025+ — CSXS.12. Если
выставлен только один и Pr запустит «не тот» host, панель просто не появится в
меню Extensions и никакой ошибки не покажет.

---

## 4. Создать симлинк на панель

**В admin PowerShell** (нужен для `SymbolicLink`):
```powershell
mkdir "$env:APPDATA\Adobe\CEP\extensions" -Force
New-Item -ItemType SymbolicLink `
  -Path "$env:APPDATA\Adobe\CEP\extensions\com.phygital.studio.pr" `
  -Target "$env:USERPROFILE\Documents\Phygital-Adobe-Studio\cep-premiere"
```

Альтернатива без admin — `mklink /D` в admin cmd (тоже требует прав):
```cmd
mklink /D "%APPDATA%\Adobe\CEP\extensions\com.phygital.studio.pr" ^
          "%USERPROFILE%\Documents\Phygital-Adobe-Studio\cep-premiere"
```

Кириллица в `%USERPROFILE%` (`C:\Users\<имя>\…`) работает — `autostart.js`
делает `fs.realpathSync()` и сидкар стартует с реальным cwd, а не с символлинка.

---

## 5. Первичный auth recon (один раз)

```powershell
cd $env:USERPROFILE\Documents\Phygital-Adobe-Studio\sidecar
python -m scripts.cli auth login
```

Откроется headed Chromium. Залогиниться в Phygital+ обычным образом —
скрипт ловит SuperTokens cookies, пишет `session.json` в
`%LOCALAPPDATA%\PhygitalStudio\session.json`.

> **MSIX sandbox gotcha.** Если PowerShell запущен «изнутри» Claude Code на
> Windows (MSIX-режим), то `%LOCALAPPDATA%` виртуализируется в
> `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\…`, и CEP-панель,
> запущенная в реальном Pr, этого session.json не увидит. **Запускай auth
> recon из обычной PowerShell-сессии, а не из агента.** То же касается всех
> ручных запусков `python -m app.main`.

---

## 6. Запустить Premiere Pro

1. **Полностью закрыть** уже открытый Pr (`File → Exit` или `Alt+F4`). CEP сканит
   расширения только при старте процесса — простой Reload Window не подцепит
   новый симлинк.
2. Открыть Pr заново.
3. `Window → Extensions → Phygital Studio`.

Что должно произойти:

- В шапке панели появляется pill «online» (зелёная) — sidecar autostart-нулся
  и `/health` отвечает.
- Рядом — pill с балансом кредитов Phygital+.
- Можно выбрать модель, заполнить промпт, нажать Generate.

Если pill красный (offline):
1. Подождать 15 секунд (autostart polls /health до 15s).
2. Открыть DevTools панели: <http://localhost:8099> в Chrome → выбрать
   `Phygital Studio` → Console.
3. Поискать ошибки от `ensureSidecar()`.
4. Проверить, что `pythonw --version` отвечает в PowerShell.

---

## 7. Проверить, что всё работает

Smoke-test:

1. **Nano Banana text2img.** Выбрать `Nano Banana (image)`, ввести любой prompt,
   жать Generate. Через 10–30 сек в History должен появиться completed job.
2. **Insert.** Жать `Insert` на job-карточке. Картинка должна импортироваться
   в bin Pr и (опционально) лечь на playhead активной sequence.
3. **Frame extract.** Включить любой video-сценарий (Kling `start_prompt`),
   выбрать видео в Source Monitor, жать `From Timeline frame`. Должен
   подцепиться кадр (либо через QE DOM, либо ffmpeg fallback на sidecar'е).

---

## 8. Деинсталляция

```powershell
# Удалить симлинк
Remove-Item "$env:APPDATA\Adobe\CEP\extensions\com.phygital.studio.pr"

# Убить остатки sidecar'а
Get-Process pythonw -ErrorAction SilentlyContinue | Stop-Process

# Удалить состояние
Remove-Item -Recurse "$env:LOCALAPPDATA\PhygitalStudio"
Remove-Item -Recurse "$env:TEMP\phygital-sidecar.pid" -ErrorAction SilentlyContinue
Remove-Item -Recurse "C:\ProgramData\PhygitalStudio" -ErrorAction SilentlyContinue

# Выключить CEP debug (опционально)
reg delete "HKCU\Software\Adobe\CSXS.11" /v PlayerDebugMode /f
reg delete "HKCU\Software\Adobe\CSXS.12" /v PlayerDebugMode /f
```

---

## 9. Траблшут

### Панель не появляется в `Window → Extensions`

- `PlayerDebugMode = 1` выставлен для CSXS.11 **и** CSXS.12.
- Симлинк ведёт на правильный путь (`Get-Item` его покажет).
- Pr был **полностью** закрыт и переоткрыт (а не Reload Window).
- В `manifest.xml` `<Host Name="PPRO">` — это так и есть, проверять не надо.

### Pill «offline», sidecar не стартует

- В `pythonw` нет нужных пакетов → активировать venv и `pip install -e .` ещё раз.
- В DevTools (<http://localhost:8099>) консоль ругается на ENOENT — Python не
  находится. Поставить глобально или прописать `C:\Python311\` в `PATH`.
- Порт 8765 занят чужим процессом:
  ```powershell
  Get-NetTCPConnection -LocalPort 8765 | Select OwningProcess
  Get-Process -Id <PID>
  ```

### Pill «no_session»

- session.json потерян / истёк → перезапустить `python -m scripts.cli auth login`.
- Если запускал из MSIX-окружения — повторить из обычной PowerShell.

### Generate падает с «import failed»

- В V1.1 ASCII-staging убран — Pr 2024.2+ ест кириллические UTF-8 пути
  напрямую. Если всё-таки `importFiles` падает: открыть CEP DevTools
  (`http://localhost:8099`), искать ошибку от `host.jsx` `importToBin`.
  Возможные причины: байты с Phygital повредились / Content-Type соврал
  (PNG-заголовок поверх JPEG-байт) — посмотреть, что лежит в
  `%LOCALAPPDATA%\PhygitalStudio\downloads-panel\`. `disk_save.js _sniffExt`
  должен переименовать расширение под реальные magic-байты — если файл
  пришёл с расширением `.png`, а sniff не сработал, это баг sniff'а.

### `From Timeline frame` молча ничего не делает

- QE DOM сломан на твоём билде Pr. Должен сработать ffmpeg fallback —
  проверить, что `ffmpeg` в `PATH` и что в DevTools нет ошибок от
  `/clips/extract_frame`.

### img2img / i2v завершается через ~30 сек без ошибки

- Это silent-cancel от Phygital из-за рассинхрона `value` ↔ `meta.dimensions`.
  Перепроверить, что обновлён `workflows/video_*.py` и тесты
  `test_workflow_video_*.py` зелёные.

### Pr тормозит после выхода — `pythonw` остался

- Sidecar не убит. Это бывает если Pr крашнулся (а не закрылся через `Alt+F4`).
  Убить руками: `Get-Process pythonw | Stop-Process`. PID-файл в `%TEMP%`
  при следующем старте панели тоже отработает.
