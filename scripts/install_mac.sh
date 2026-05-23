#!/usr/bin/env bash
# Phygital Adobe Studio — установщик для macOS.
#
# Что делает:
#   1. Проверяет OS, Premiere Pro, Xcode CLI Tools.
#   2. Ставит Homebrew (если нет).
#   3. Ставит python@3.11 и ffmpeg (если их нет).
#   4. Создаёт venv в sidecar/.venv, ставит python-зависимости и playwright chromium.
#   5. Включает CEP debug mode (CSXS.11 + CSXS.12).
#   6. Создаёт симлинк cep-premiere/ → ~/Library/.../Adobe/CEP/extensions/com.phygital.studio.pr.
#   7. Запускает auth recon (headed Chromium) — пользователь логинится один раз.
#
# Идемпотентен: повторный запуск не сломает уже установленное.
#
# Использование:
#   chmod +x scripts/install_mac.sh
#   ./scripts/install_mac.sh
#
# Флаги:
#   --skip-deps     не ставить brew/python/ffmpeg (только панель + recon)
#   --skip-recon    не запускать recon в конце
#   --reinstall-venv  снести и пересоздать sidecar/.venv
#
# Подробный траблшут — docs/INSTALL_MACOS.md.

set -euo pipefail

# ── helpers ─────────────────────────────────────────────────────────────────
RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; BLU=$'\033[34m'; RST=$'\033[0m'
info()  { printf "%s==>%s %s\n" "$BLU" "$RST" "$*"; }
ok()    { printf "%s OK%s %s\n" "$GRN" "$RST" "$*"; }
warn()  { printf "%s !!%s %s\n" "$YEL" "$RST" "$*" >&2; }
die()   { printf "%s ××%s %s\n" "$RED" "$RST" "$*" >&2; exit 1; }
have()  { command -v "$1" >/dev/null 2>&1; }

# ── args ────────────────────────────────────────────────────────────────────
SKIP_DEPS=0
SKIP_RECON=0
REINSTALL_VENV=0
for arg in "$@"; do
  case "$arg" in
    --skip-deps) SKIP_DEPS=1 ;;
    --skip-recon) SKIP_RECON=1 ;;
    --reinstall-venv) REINSTALL_VENV=1 ;;
    -h|--help)
      sed -n '2,30p' "$0"
      exit 0
      ;;
    *) die "Неизвестный флаг: $arg" ;;
  esac
done

# ── paths ───────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SIDECAR_DIR="$REPO_DIR/sidecar"
PANEL_DIR="$REPO_DIR/cep-premiere"
EXT_DIR="$HOME/Library/Application Support/Adobe/CEP/extensions"
EXT_LINK="$EXT_DIR/com.phygital.studio.pr"

[[ -d "$SIDECAR_DIR" ]] || die "Не нашёл sidecar/ в $REPO_DIR — скрипт запущен не из репо?"
[[ -d "$PANEL_DIR" ]] || die "Не нашёл cep-premiere/ в $REPO_DIR"

# ── 1. OS check ─────────────────────────────────────────────────────────────
info "OS check"
[[ "$(uname)" == "Darwin" ]] || die "Это macOS-only установщик. Для Windows — docs/INSTALL_WINDOWS.md."
MACOS_VER="$(sw_vers -productVersion)"
ok "macOS $MACOS_VER"

# ── 2. Premiere Pro ─────────────────────────────────────────────────────────
info "Поиск Adobe Premiere Pro"
PR_APPS=()
while IFS= read -r line; do PR_APPS+=("$line"); done < <(
  find /Applications -maxdepth 2 -type d -name "Adobe Premiere Pro*" 2>/dev/null
)
if [[ ${#PR_APPS[@]} -eq 0 ]]; then
  warn "Premiere Pro не найден в /Applications. Установка продолжится, но панель не появится пока не поставишь Pr."
else
  for app in "${PR_APPS[@]}"; do ok "Найден: $app"; done
fi

# ── 3. Xcode CLI tools (нужен git) ─────────────────────────────────────────
if ! have git; then
  info "Ставлю Xcode Command Line Tools (gui-диалог появится)"
  xcode-select --install || true
  warn "Заверши установку CLT в GUI, потом перезапусти скрипт."
  exit 1
fi
ok "git $(git --version | awk '{print $3}')"

# ── 4. Homebrew + deps ──────────────────────────────────────────────────────
if [[ $SKIP_DEPS -eq 0 ]]; then
  if ! have brew; then
    info "Ставлю Homebrew"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Apple Silicon: brew установится в /opt/homebrew, надо подцепить PATH
    if [[ -x /opt/homebrew/bin/brew ]]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [[ -x /usr/local/bin/brew ]]; then
      eval "$(/usr/local/bin/brew shellenv)"
    fi
  fi
  ok "brew $(brew --version | head -1 | awk '{print $2}')"

  # python3: Homebrew после `brew install python@3.11` НЕ перетирает /usr/bin/python3
  # (системный 3.9). Поэтому если на PATH старый python3 — берём явный путь из
  # brew --prefix python@3.11, иначе пользователь получит venv на 3.9.
  if ! have python3 || ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    info "Ставлю python@3.11 через brew (текущий python3 < 3.10)"
    brew install python@3.11
    BREW_PY_PREFIX="$(brew --prefix python@3.11)"
    PYBIN="$BREW_PY_PREFIX/bin/python3.11"
    [[ -x "$PYBIN" ]] || die "brew install python@3.11 вроде прошёл, но $PYBIN не нашёлся"
  else
    PYBIN="$(command -v python3)"
  fi
  PYVER="$("$PYBIN" --version 2>&1 | awk '{print $2}')"
  ok "python $PYVER ($PYBIN)"

  if ! have ffmpeg; then
    info "Ставлю ffmpeg через brew"
    brew install ffmpeg
  fi
  ok "ffmpeg $(ffmpeg -version | head -1 | awk '{print $3}')"
else
  warn "--skip-deps: пропускаю brew/python/ffmpeg"
  have python3 || die "python3 не найден, повтори без --skip-deps"
  PYBIN="$(command -v python3)"
  have ffmpeg  || warn "ffmpeg не найден — frame extract будет работать только через QE DOM (нестабильно)"
fi

# ── 5. venv + pip ───────────────────────────────────────────────────────────
VENV_DIR="$SIDECAR_DIR/.venv"
if [[ $REINSTALL_VENV -eq 1 && -d "$VENV_DIR" ]]; then
  info "Удаляю старый venv"
  rm -rf "$VENV_DIR"
fi

if [[ ! -d "$VENV_DIR" ]]; then
  info "Создаю venv → $VENV_DIR (на базе $PYBIN)"
  "$PYBIN" -m venv "$VENV_DIR"
fi
ok "venv $VENV_DIR"

# Не активируем venv (`source activate`) — работаем напрямую через путь к
# интерпретатору. Активация ломает `set -u` (PS1) и не нужна для модульных
# вызовов.

# venv-python: путь, который ИМЕННО будет искать autostart.js
# (см. cep-premiere/client/lib/autostart.js — он пробует <sidecar>/.venv/bin/python3 первым).
VENV_PY="$VENV_DIR/bin/python3"
[[ -x "$VENV_PY" ]] || die "venv создан, но $VENV_PY не нашёлся"

info "pip install -e \"sidecar[dev]\""
"$VENV_PY" -m pip install --upgrade pip wheel >/dev/null
"$VENV_PY" -m pip install -e "$SIDECAR_DIR[dev]"
ok "pip deps установлены"

info "playwright install chromium"
"$VENV_PY" -m playwright install chromium
ok "Chromium для Playwright установлен"

# Smoke-test: импортнём app + V1.1 модули — если упало, дальше нет смысла продолжать.
info "Smoke-test: import app.main + V1.1 modules"
(cd "$SIDECAR_DIR" && "$VENV_PY" -c "
import app.main
from app.services.idempotency import IdempotencyStore, hash_request_body
assert hash_request_body({'a': 1})  # sanity
print('app.main + V1.1 import OK')
") || die "Sidecar не импортируется — проверь pip-зависимости вручную"

# ── 6. CEP debug mode ───────────────────────────────────────────────────────
info "Включаю CEP PlayerDebugMode для CSXS.11 и CSXS.12"
defaults write com.adobe.CSXS.11 PlayerDebugMode 1
defaults write com.adobe.CSXS.12 PlayerDebugMode 1
ok "PlayerDebugMode = 1 (CSXS.11 + CSXS.12)"

# ── 7. Symlink панели ──────────────────────────────────────────────────────
mkdir -p "$EXT_DIR"
if [[ -L "$EXT_LINK" ]]; then
  CURRENT_TARGET="$(readlink "$EXT_LINK")"
  if [[ "$CURRENT_TARGET" == "$PANEL_DIR" ]]; then
    ok "Симлинк уже указывает на $PANEL_DIR"
  else
    warn "Симлинк указывает на $CURRENT_TARGET — пересоздаю"
    rm "$EXT_LINK"
    ln -s "$PANEL_DIR" "$EXT_LINK"
    ok "Симлинк обновлён → $PANEL_DIR"
  fi
elif [[ -e "$EXT_LINK" ]]; then
  die "$EXT_LINK существует и не является симлинком — удали руками и перезапусти"
else
  ln -s "$PANEL_DIR" "$EXT_LINK"
  ok "Симлинк создан → $PANEL_DIR"
fi

# ── 8. Auth recon ──────────────────────────────────────────────────────────
SESSION_FILE="$HOME/Library/Application Support/PhygitalStudio/session.json"

if [[ $SKIP_RECON -eq 1 ]]; then
  warn "--skip-recon: пропускаю логин. Запусти позже:"
  echo "    cd \"$SIDECAR_DIR\" && \"$VENV_PY\" -m scripts.auth_recon"
elif [[ -f "$SESSION_FILE" ]]; then
  info "session.json уже существует ($SESSION_FILE)"
  read -r -p "Перелогиниться заново? [y/N] " RESP
  if [[ "$RESP" =~ ^[Yy]$ ]]; then
    info "Запускаю headed Chromium"
    (cd "$SIDECAR_DIR" && "$VENV_PY" -m scripts.auth_recon)
  else
    ok "Использую существующую сессию"
  fi
else
  info "Запускаю auth recon (откроется Chromium, залогинься в Phygital+)"
  (cd "$SIDECAR_DIR" && "$VENV_PY" -m scripts.auth_recon)
fi

# ── 9. Финал ───────────────────────────────────────────────────────────────
echo
ok "Установка V1.1 завершена."
echo
cat <<EOF
Что нового в V1.1 (см. CHANGELOG.md):
  • Sidecar: Idempotency-Key, /v1/ versioning, cursor-pagination, HEAD download.
  • Panel:   persistent thumbnails, queue widget с cancel, cost preview,
             auto-fill image slot из активного клипа таймлайна.

Дальше:
  1. ${BLU}Полностью закрой${RST} Premiere Pro: Cmd+Q (не Cmd+W).
  2. Открой Pr заново → Window → Extensions → Phygital Studio.
  3. macOS попросит ${YEL}Files and Folders${RST} разрешение для python3 —
     одобри (нужно sidecar'у для чтения файлов из bin).
  4. В шапке панели должны загореться pill «online» и баланс кредитов.
  5. После генерации увидишь персистентный queue-widget сверху и thumbnails
     в History — они переживут перезагрузку панели.

Если что-то не так — docs/INSTALL_MACOS.md → секция «Траблшут».
EOF
