#!/bin/bash

APP_DIR="/home/sergio-lozano/tux-assistant"
VENV_PY="$APP_DIR/venv/bin/python"

cd "$APP_DIR"
exec "$VENV_PY" main.py
