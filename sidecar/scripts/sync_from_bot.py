"""Vendor copy с Phygital-bot.

Источник по умолчанию: ~/Documents/Phygital-bot/ (рядом с этим репо).
Переопределяется флагом --source.

Что копируется:
  client/{api,auth,session,models}.py  → app/phygital_client/
  workflows/{base,image_gen}.py         → app/workflows/

Что НЕ копируется:
  client/config.py                      — bot-specific (Telegram), у нас свой app/config.py
  workflows/*.py кроме перечисленных    — добавляются в sub-project D (video)

При копировании переписываются импорты:
  from client.X         → from app.phygital_client.X
  from workflows.X      → from app.workflows.X
  import client.X       → import app.phygital_client.X
  import workflows.X    → import app.workflows.X

В app/phygital_client/__init__.py записывается SOURCE_COMMIT (git rev-parse HEAD источника).
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


# Файлы для копирования: (rel_src, rel_dst)
FILES = [
    ("client/api.py",         "app/phygital_client/api.py"),
    ("client/auth.py",        "app/phygital_client/auth.py"),
    ("client/session.py",     "app/phygital_client/session.py"),
    ("client/models.py",      "app/phygital_client/models.py"),
    ("workflows/base.py",     "app/workflows/base.py"),
    ("workflows/image_gen.py", "app/workflows/image_gen.py"),
    ("workflows/image_to_image.py", "app/workflows/image_to_image.py"),
]

IMPORT_REWRITES = [
    (re.compile(r"^from client\."), "from app.phygital_client."),
    (re.compile(r"^from workflows\."), "from app.workflows."),
    (re.compile(r"^import client\."), "import app.phygital_client."),
    (re.compile(r"^import workflows\."), "import app.workflows."),
    # late imports
    (re.compile(r"(\s+)from client\."), r"\1from app.phygital_client."),
    (re.compile(r"(\s+)from workflows\."), r"\1from app.workflows."),
]


def rewrite_imports(text: str) -> str:
    out_lines = []
    for line in text.splitlines(keepends=True):
        for pat, repl in IMPORT_REWRITES:
            line = pat.sub(repl, line)
        out_lines.append(line)
    return "".join(out_lines)


def get_source_commit(source: Path) -> str:
    """git rev-parse HEAD источника. Если git недоступен — возвращает 'unknown'."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(source),
            stderr=subprocess.DEVNULL,
        )
        return out.decode("ascii").strip()
    except Exception:
        return "unknown"


def write_init(dst_root: Path, commit: str) -> None:
    """app/phygital_client/__init__.py с SOURCE_COMMIT."""
    init_path = dst_root / "app" / "phygital_client" / "__init__.py"
    init_path.write_text(
        f'"""Vendor copy from Phygital-bot.\n\n'
        f'Source: Phygital-bot (sibling repo, default path: ~/Documents/Phygital-bot)\n'
        f'Commit: {commit}\n'
        f'Sync: run `python -m scripts.sync_from_bot --apply` to refresh.\n'
        f'\n'
        f'Не редактируй вручную — изменения будут затёрты при следующем sync.\n'
        f'"""\n'
        f'SOURCE_COMMIT = "{commit}"\n',
        encoding="utf-8",
    )


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent  # sidecar/

    ap = argparse.ArgumentParser(description="Vendor copy Phygital-bot → sidecar.")
    ap.add_argument(
        "--source",
        type=Path,
        default=Path.home() / "Documents" / "Phygital-bot",
        help="Путь к Phygital-bot репозиторию (по умолчанию ~/Documents/Phygital-bot)",
    )
    ap.add_argument("--apply", action="store_true", help="Действительно скопировать (без флага — dry-run).")
    args = ap.parse_args()

    source: Path = args.source
    if not source.exists():
        sys.exit(f"FATAL: source not found: {source}")

    commit = get_source_commit(source)
    print(f"Source: {source}")
    print(f"Commit: {commit}")
    print(f"Mode:   {'APPLY' if args.apply else 'DRY-RUN'}")
    print()

    for rel_src, rel_dst in FILES:
        src = source / rel_src
        dst = repo_root / rel_dst
        if not src.exists():
            print(f"  SKIP  {rel_src} -> {rel_dst}  (source missing)")
            continue

        text = src.read_text(encoding="utf-8")
        rewritten = rewrite_imports(text)

        n_changed = sum(1 for a, b in zip(text.splitlines(), rewritten.splitlines()) if a != b)

        print(f"  COPY  {rel_src} -> {rel_dst}  ({n_changed} import lines rewritten)")

        if args.apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(rewritten, encoding="utf-8")

    if args.apply:
        write_init(repo_root, commit)
        print()
        print(f"  WROTE app/phygital_client/__init__.py with SOURCE_COMMIT={commit}")
        print()
        print("Done. Не забудь пройтись по diff и убедиться что импорты валидны:")
        print("  .venv\\Scripts\\python -c \"from app.phygital_client.api import PhygitalClient; from app.workflows.image_gen import ImageGenWorkflow; print('OK')\"")
    else:
        print()
        print("DRY-RUN -- повтори с --apply чтобы реально скопировать.")


if __name__ == "__main__":
    main()
