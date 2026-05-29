# cep-ae

CEP 11 панель для Adobe After Effects 2023+. Status: scaffold.

## Состав

| Путь | Назначение |
|---|---|
| `CSXS/manifest.xml` | регистрация панели, host AEFT `[23.0,99.9]`, Menu = «Phygital Studio» |
| `client/index.html` | HTML-разметка панели (stub) |
| `client/panel.js` | UI-логика, HTTP-клиент к `localhost:8765` (stub) |
| `host/insert_media.jsx` | ExtendScript: `importFile` + `comp.layers.add` (stub) |
| `.debug` | конфиг remote-debugging для CEP DevTools (порт 8098) |

## Установка для разработки

Windows:

1. `reg add HKCU\Software\Adobe\CSXS.11 /v PlayerDebugMode /t REG_SZ /d 1 /f`
2. Симлинк (CMD admin):
   `mklink /D "%AppData%\Adobe\CEP\extensions\PhygitalStudioAE" "%USERPROFILE%\Documents\Phygital-Adobe-Studio\cep-ae"`
3. Полный рестарт After Effects.
4. Window → Extensions → Phygital Studio.
5. DevTools: `http://localhost:8098/`.

macOS:

1. `defaults write com.adobe.CSXS.11 PlayerDebugMode 1`
2. Симлинк:
   `ln -s "$HOME/Documents/Phygital-Adobe-Studio/cep-ae" "$HOME/Library/Application Support/Adobe/CEP/extensions/PhygitalStudioAE"`
3. Cmd+Q + повторный запуск AE.

## Контракты

ExtendScript и HTTP — те же документы, что и для Pr-панели:
[../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
