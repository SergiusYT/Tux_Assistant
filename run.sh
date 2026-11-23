#!/usr/bin/env bash
# Lanza Tux Assistant desde la carpeta donde esté instalado (sin rutas fijas)
APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$APP_DIR" || exit 1
exec "$APP_DIR/venv/bin/python" "$APP_DIR/main.py" "$@"
