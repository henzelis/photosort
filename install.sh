#!/usr/bin/env bash
# PhotoSort installer for macOS & Linux.
# Usage: curl -fsSL https://raw.githubusercontent.com/henzelis/photosort/main/install.sh | bash
set -euo pipefail

PKG_URL="https://github.com/henzelis/photosort/archive/refs/heads/main.zip"
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

echo "==> Встановлюю PhotoSort..."

if command -v uv >/dev/null 2>&1; then
    uv tool install --force "$PKG_URL" >/dev/null 2>&1 || uv tool install "$PKG_URL"
else
    PY="$(command -v python3 || command -v python || true)"
    if [ -z "$PY" ]; then
        echo "Помилка: потрібен Python 3.9+ (https://www.python.org/downloads/)" >&2
        exit 1
    fi
    VENV="$HOME/.photosort/venv"
    rm -rf "$HOME/.photosort"
    "$PY" -m venv "$VENV"
    "$VENV/bin/pip" install -q --upgrade pip
    "$VENV/bin/pip" install -q "$PKG_URL"
    printf '#!/bin/sh\nexec "%s/bin/photosort" "$@"\n' "$VENV" > "$BIN_DIR/photosort"
    chmod +x "$BIN_DIR/photosort"
fi

if "$BIN_DIR/photosort" --version >/dev/null 2>&1; then
    echo "==> Готово! $("$BIN_DIR/photosort" --version)"
else
    echo "Помилка встановлення — перегляньте вивід вище." >&2
    exit 1
fi

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        echo ""
        echo "⚠ Додайте каталог $BIN_DIR у PATH:"
        echo "   echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.zshrc && source ~/.zshrc"
        echo "   (або ~/.bashrc — залежно від вашої оболонки)"
        ;;
esac

echo ""
echo "Запуск:  photosort          — графічний інтерфейс (браузер)"
echo "         photosort --help   — командний рядок"
