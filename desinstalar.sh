#!/usr/bin/env bash
# ============================================================================
#  Tux Assistant — desinstalador
#  Quita los accesos directos, el arranque automático, la vigilancia de la terminal
#  y el entorno de Python. Pregunta antes de borrar tus datos, el modelo y Ollama.
#    bash desinstalar.sh        # pregunta lo opcional
#    bash desinstalar.sh -y     # quita también datos y modelo, sin preguntar (no toca Ollama)
# ============================================================================
set -uo pipefail
SIN_PREGUNTAS=0
[ "${1:-}" = "-y" ] && SIN_PREGUNTAS=1
APP_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]:-$0}")")" && pwd)"
MODELO="qwen3:4b-instruct-2507-q4_K_M"
[ -f "$HOME/.config/tux-assistant/modelo" ] && MODELO="$(cat "$HOME/.config/tux-assistant/modelo")"

if [ -t 1 ]; then VER=$'\e[32m'; NAR=$'\e[38;5;208m'; NEG=$'\e[1m'; GRI=$'\e[90m'; RST=$'\e[0m'; else VER=""; NAR=""; NEG=""; GRI=""; RST=""; fi
ok()   { echo "  ${VER}✓${RST} $*"; }
info() { echo "  ${GRI}$*${RST}"; }
pregunta() {
    [ "$SIN_PREGUNTAS" = 1 ] && { [ "$2" = "s" ]; return; }
    local r; read -r -p "  ${NEG}?${RST} $1 [s/N] " r < /dev/tty || r=""
    [[ "$r" =~ ^[sSyY] ]]
}

echo; echo "${NAR}${NEG}  Desinstalando Tux Assistant${RST}"; echo

pkill -f "$APP_DIR/main.py" 2>/dev/null && ok "Tux Assistant cerrado"
rm -f "$HOME/.local/bin/tux-assistant" "$HOME/.local/share/applications/tux-assistant.desktop" \
      "$HOME/.config/autostart/tux-assistant.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$HOME/.local/share/applications" 2>/dev/null
ok "Accesos directos y arranque automático quitados"

# Vigilancia de la terminal: el bloque entre marcadores en ~/.bashrc
if [ -f "$HOME/.bashrc" ] && grep -q "# >>> tux-assistant >>>" "$HOME/.bashrc"; then
    cp "$HOME/.bashrc" "$HOME/.bashrc.antes-de-desinstalar-tux"
    sed -i '/# >>> tux-assistant >>>/,/# <<< tux-assistant <<</d' "$HOME/.bashrc"
    ok "Vigilancia de la terminal quitada de ~/.bashrc (copia: ~/.bashrc.antes-de-desinstalar-tux)"
fi

rm -rf "$APP_DIR/venv" "$APP_DIR/__pycache__"
ok "Entorno de Python borrado"

if pregunta "¿Borrar también tus datos (cuadernos, rutas, progreso y XP)?" s; then
    rm -rf "$HOME/.config/tux-assistant" "$HOME/.cache/tux-assistant" "$HOME/tux-practica"
    ok "Datos borrados"
else
    info "Tus datos se quedan en ~/.config/tux-assistant"
fi

if command -v ollama >/dev/null && pregunta "¿Borrar el modelo de IA $MODELO (libera ~2,5 GB)?" s; then
    ollama rm "$MODELO" >/dev/null 2>&1 && ok "Modelo $MODELO borrado" || info "El modelo no estaba descargado"
fi

if command -v ollama >/dev/null && [ "$SIN_PREGUNTAS" = 0 ] && pregunta "¿Desinstalar también Ollama (otros programas podrían usarlo)?" n; then
    sudo systemctl disable --now ollama 2>/dev/null
    sudo rm -f /etc/systemd/system/ollama.service "$(command -v ollama)"
    sudo rm -rf /usr/share/ollama /usr/local/lib/ollama
    sudo userdel ollama 2>/dev/null; sudo groupdel ollama 2>/dev/null
    ok "Ollama desinstalado"
fi

# Si el código se descargó con el instalador (no es tu copia de trabajo), también se borra
if [ "$APP_DIR" = "$HOME/.local/share/tux-assistant" ]; then
    rm -rf "$APP_DIR"
    ok "Código de Tux Assistant borrado"
else
    info "El código se queda en $APP_DIR (es tu copia; bórrala a mano si quieres)"
fi
echo; echo "${VER}${NEG}  Listo. ¡Hasta pronto! 🐧${RST}"; echo
