#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This build script creates a macOS .app and must run on macOS." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -m PyInstaller --version >/dev/null 2>&1; then
  echo "PyInstaller is missing. Run: python -m pip install -e '.[dev]'" >&2
  exit 1
fi

BROWSER_CACHE="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/Library/Caches/ms-playwright}"
export PLAYWRIGHT_BROWSERS_PATH="$BROWSER_CACHE"
if [[ ! -d "$BROWSER_CACHE" ]] || ! "$PYTHON_BIN" -c \
  'from pathlib import Path; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); ok=Path(p.chromium.executable_path).is_file(); p.stop(); raise SystemExit(0 if ok else 1)'
then
  echo "Chromium is missing. Run: python -m playwright install chromium" >&2
  exit 1
fi

cd "$ROOT_DIR"
"$PYTHON_BIN" -m PyInstaller \
  --clean \
  --noconfirm \
  --windowed \
  --name ProScraper \
  --osx-bundle-identifier com.proscraper.desktop \
  --paths "$ROOT_DIR/src" \
  --collect-all PySide6 \
  --collect-all playwright \
  --add-data "$ROOT_DIR/src/scraper_app/extraction/picker.js:scraper_app/extraction" \
  --add-data "$BROWSER_CACHE:ms-playwright" \
  "$ROOT_DIR/src/scraper_app/main.py"

echo "Created: $ROOT_DIR/dist/ProScraper.app"
