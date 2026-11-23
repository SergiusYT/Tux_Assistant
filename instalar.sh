#!/usr/bin/env bash
# ============================================================================
#  Tux Assistant — instalador automático
#
#  Instala TODO lo necesario con un solo comando:
#    · paquetes del sistema (Python, Qt, fuentes de emoji, herramientas)
#    · el código de Tux Assistant (si ejecutas este archivo suelto, lo descarga)
#    · el entorno de Python con sus dependencias
#    · Ollama (la IA local) y el modelo de lenguaje
#    · el acceso directo en el menú de aplicaciones y el comando «tux-assistant»
#
#  Uso:
#    bash instalar.sh                 # instalación normal (pregunta lo opcional)
#    bash instalar.sh -y              # sin preguntas (respuestas por defecto)
#    bash instalar.sh --autostart     # además, que Tux arranque al iniciar sesión
#    bash instalar.sh --modelo NOMBRE # usar otro modelo de Ollama
#    bash instalar.sh --sin-modelo    # no descargar el modelo (p. ej. sin internet ahora)
#    bash instalar.sh --sin-ollama    # no instalar Ollama (si ya lo manejas aparte)
#
#  Sin descargar nada antes:
#    curl -fsSL https://raw.githubusercontent.com/SergiusYT/Tux_Assistant/main/instalar.sh | bash
# ============================================================================
set -uo pipefail

REPO_URL="https://github.com/SergiusYT/Tux_Assistant.git"
DESTINO_POR_DEFECTO="$HOME/.local/share/tux-assistant"
MODELO="qwen3:4b-instruct-2507-q4_K_M"
LOG="$HOME/.cache/tux-assistant/instalacion.log"

SIN_PREGUNTAS=0
AUTOSTART=""
DESCARGAR_MODELO=1
INSTALAR_OLLAMA=1
MODELO_FORZADO=""

while [ $# -gt 0 ]; do
    case "$1" in
        -y|--si) SIN_PREGUNTAS=1 ;;
        --autostart) AUTOSTART="si" ;;
        --sin-autostart) AUTOSTART="no" ;;
        --modelo) shift; MODELO_FORZADO="${1:-}" ;;
        --sin-modelo) DESCARGAR_MODELO=0 ;;
        --sin-ollama) INSTALAR_OLLAMA=0; DESCARGAR_MODELO=0 ;;
        -h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Opción desconocida: $1 (usa --help)"; exit 1 ;;
    esac
    shift
done

# ---------- presentación ----------
if [ -t 1 ]; then
    NAR=$'\e[38;5;208m'; VER=$'\e[32m'; ROJ=$'\e[31m'; AMA=$'\e[33m'; GRI=$'\e[90m'; NEG=$'\e[1m'; RST=$'\e[0m'
else
    NAR=""; VER=""; ROJ=""; AMA=""; GRI=""; NEG=""; RST=""
fi
mkdir -p "$(dirname "$LOG")"
: > "$LOG"

PASO=0
TOTAL_PASOS=7
paso()  { PASO=$((PASO + 1)); echo; echo "${NAR}${NEG}[$PASO/$TOTAL_PASOS] $*${RST}"; }
ok()    { echo "  ${VER}✓${RST} $*"; }
aviso() { echo "  ${AMA}!${RST} $*"; }
error() { echo "  ${ROJ}✗ $*${RST}"; }
info()  { echo "  ${GRI}$*${RST}"; }
fallar() { error "$*"; echo; echo "  Revisa el registro: $LOG"; exit 1; }
correr() {  # ejecuta mostrando solo el resumen; todo queda en el registro
    echo "\$ $*" >> "$LOG"
    "$@" >> "$LOG" 2>&1
}
pregunta() {  # pregunta "texto" defecto(s/n) → 0 si sí
    local texto="$1" defecto="$2" r
    if [ "$SIN_PREGUNTAS" = 1 ] || ! { : < /dev/tty; } 2>/dev/null; then
        [ "$defecto" = "s" ]; return
    fi
    if [ "$defecto" = "s" ]; then texto="$texto [S/n] "; else texto="$texto [s/N] "; fi
    read -r -p "  ${NEG}?${RST} $texto" r < /dev/tty || r=""
    r="${r:-$defecto}"
    [[ "$r" =~ ^[sSyY] ]]
}

cat <<EOF

${NAR}${NEG}   ████████╗██╗   ██╗██╗  ██╗    Tux Assistant${RST}
${NAR}${NEG}   ╚══██╔══╝██║   ██║╚██╗██╔╝    ${RST}${GRI}Agente pedagógico para aprender Linux${RST}
${NAR}${NEG}      ██║   ██║   ██║ ╚███╔╝     ${RST}${GRI}IA 100 % local · Universidad El Bosque${RST}
${NAR}${NEG}      ██║   ██║   ██║ ██╔██╗     ${RST}
${NAR}${NEG}      ██║   ╚██████╔╝██╔╝ ██╗    ${RST}${GRI}Instalador automático${RST}
${NAR}${NEG}      ╚═╝    ╚═════╝ ╚═╝  ╚═╝${RST}
EOF

# ---------- comprobaciones ----------
paso "Comprobando tu sistema"
[ "$(uname -s)" = "Linux" ] || fallar "Tux Assistant solo funciona en Linux."
[ "$(id -u)" -ne 0 ] || fallar "No ejecutes el instalador como root ni con sudo: ejecútalo con tu usuario (pedirá la contraseña cuando haga falta)."
case "$(uname -m)" in
    x86_64|aarch64|arm64) ok "Arquitectura $(uname -m)" ;;
    *) aviso "Arquitectura $(uname -m): Ollama podría no estar disponible." ;;
esac
if [ -r /etc/os-release ]; then
    . /etc/os-release
    ok "Distribución: ${PRETTY_NAME:-Linux}"
fi
if command -v apt-get >/dev/null; then GESTOR=apt
elif command -v dnf >/dev/null; then GESTOR=dnf
elif command -v pacman >/dev/null; then GESTOR=pacman
elif command -v zypper >/dev/null; then GESTOR=zypper
else fallar "No encontré un gestor de paquetes compatible (apt, dnf, pacman o zypper)."; fi
ok "Gestor de paquetes: $GESTOR"

RAM_GB=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
ok "Memoria RAM: ${RAM_GB} GB"
if [ -n "$MODELO_FORZADO" ]; then
    MODELO="$MODELO_FORZADO"
elif [ "${RAM_GB:-8}" -lt 6 ]; then
    MODELO="qwen2.5:1.5b"
    aviso "Con menos de 6 GB de RAM usaré un modelo más liviano: $MODELO"
fi
LIBRE_GB=$(df -Pk "$HOME" | awk 'NR==2 {printf "%d", $4/1024/1024}')
if [ "${LIBRE_GB:-0}" -lt 5 ]; then
    aviso "Solo hay ${LIBRE_GB} GB libres en tu carpeta personal: el modelo ocupa unos 2,5 GB."
else
    ok "Espacio libre: ${LIBRE_GB} GB"
fi
if curl -fsS --max-time 8 -o /dev/null https://ollama.com 2>/dev/null || wget -q --spider --timeout=8 https://ollama.com 2>/dev/null \
   || timeout 6 bash -c '</dev/tcp/ollama.com/443' 2>/dev/null; then
    ok "Conexión a internet"
else
    aviso "No pude comprobar la conexión a internet: las descargas podrían fallar."
fi

echo
info "Se pedirá tu contraseña para instalar paquetes del sistema y Ollama."
sudo -v || fallar "Hace falta permiso de administrador (sudo) para instalar los paquetes."
( while true; do sudo -n true; sleep 50; kill -0 "$$" 2>/dev/null || exit; done ) 2>/dev/null &
MANTENER_SUDO=$!
trap 'kill $MANTENER_SUDO 2>/dev/null' EXIT

# ---------- paquetes del sistema ----------
paso "Instalando paquetes del sistema"
case "$GESTOR" in
    apt)
        PAQUETES=(python3 python3-venv python3-pip python3-pyqt5 python3-psutil python3-requests python3-pil
                  python3-pygame git curl zstd pciutils iproute2 fonts-noto-color-emoji libxcb-xinerama0
                  libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0
                  libxcb-render-util0 libxcb-shape0 libxcb-xfixes0)
        [ "${ID:-}" = "ubuntu" ] && PAQUETES+=(command-not-found)
        info "Actualizando la lista de paquetes…"
        correr sudo apt-get update || aviso "apt-get update dio errores (sigo igual)."
        INSTALAR=(sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends) ;;
    dnf)
        PAQUETES=(python3 python3-pip python3-qt5 python3-psutil python3-requests python3-pillow python3-pygame git
                  curl zstd pciutils iproute google-noto-color-emoji-fonts xcb-util-cursor xcb-util-wm
                  xcb-util-image xcb-util-keysyms xcb-util-renderutil libxkbcommon-x11)
        INSTALAR=(sudo dnf install -y) ;;
    pacman)
        PAQUETES=(python python-pip python-pyqt5 python-psutil python-requests python-pillow python-pygame git curl
                  zstd pciutils iproute2 noto-fonts-emoji xcb-util-cursor xcb-util-wm xcb-util-image
                  xcb-util-keysyms xcb-util-renderutil libxkbcommon-x11)
        INSTALAR=(sudo pacman -S --needed --noconfirm) ;;
    zypper)
        PAQUETES=(python3 python3-pip python3-qt5 python3-psutil python3-requests python3-Pillow python3-pygame git
                  curl zstd pciutils iproute2 google-noto-coloremoji-fonts libxcb-cursor0 libxkbcommon-x11-0)
        INSTALAR=(sudo zypper --non-interactive install) ;;
esac
info "Instalando ${#PAQUETES[@]} paquetes (puede tardar unos minutos)…"
if correr "${INSTALAR[@]}" "${PAQUETES[@]}"; then
    ok "Paquetes del sistema instalados"
else
    aviso "Algunos paquetes no se pudieron instalar juntos; los intento uno por uno…"
    FALTAN=()
    for p in "${PAQUETES[@]}"; do correr "${INSTALAR[@]}" "$p" || FALTAN+=("$p"); done
    if [ ${#FALTAN[@]} -gt 0 ]; then
        aviso "No disponibles en tu distribución (Tux intentará seguir sin ellos): ${FALTAN[*]}"
    else
        ok "Paquetes del sistema instalados"
    fi
fi
command -v python3 >/dev/null || fallar "No se pudo instalar Python 3."
command -v git >/dev/null || fallar "No se pudo instalar git."

# ---------- código de Tux Assistant ----------
paso "Preparando Tux Assistant"
ORIGEN="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo "")"
if [ -n "$ORIGEN" ] && [ -f "$ORIGEN/main.py" ] && [ -f "$ORIGEN/aprendizaje.py" ]; then
    APP_DIR="$ORIGEN"
    ok "Uso la copia de esta carpeta: $APP_DIR"
else
    APP_DIR="$DESTINO_POR_DEFECTO"
    if [ -d "$APP_DIR/.git" ]; then
        info "Actualizando la copia existente en $APP_DIR…"
        correr git -C "$APP_DIR" pull --ff-only || aviso "No pude actualizarla (sigo con la que hay)."
    else
        info "Descargando Tux Assistant…"
        mkdir -p "$(dirname "$APP_DIR")"
        correr git clone --depth 1 "$REPO_URL" "$APP_DIR" || fallar "No se pudo descargar Tux Assistant desde $REPO_URL"
    fi
    ok "Código en $APP_DIR"
fi
chmod +x "$APP_DIR/run.sh" "$APP_DIR/instalar.sh" "$APP_DIR/desinstalar.sh" 2>/dev/null

# ---------- entorno de Python ----------
paso "Creando el entorno de Python"
cd "$APP_DIR" || fallar "No puedo entrar a $APP_DIR"
if [ ! -x venv/bin/python ]; then
    correr python3 -m venv --system-site-packages venv || fallar "No se pudo crear el entorno virtual (¿falta python3-venv?)."
    ok "Entorno virtual creado"
else
    ok "Entorno virtual existente reutilizado"
fi
VPY="$APP_DIR/venv/bin/python"
correr "$VPY" -m pip install --upgrade pip || aviso "No pude actualizar pip (sigo igual)."
info "Instalando dependencias de Python…"
correr "$VPY" -m pip install "PyQt5>=5.15" "psutil>=5.9" "requests>=2.31" "Pillow>=10" \
    || aviso "pip dio errores; compruebo qué quedó instalado…"
correr "$VPY" -m pip install "pygame>=2.5" || aviso "pygame no se pudo instalar: Tux funcionará sin sonido."
if "$VPY" -c "import PyQt5.QtWidgets, psutil, requests, PIL" >> "$LOG" 2>&1; then
    ok "Dependencias de Python listas"
else
    fallar "Faltan dependencias de Python esenciales (PyQt5, psutil, requests o Pillow)."
fi
"$VPY" -c "import pygame" >/dev/null 2>&1 && ok "Sonido disponible (pygame)" || aviso "Sin pygame: Tux no hará sonidos."

# ---------- Ollama y el modelo ----------
paso "Instalando la IA local (Ollama)"
if command -v ollama >/dev/null; then
    ok "Ollama ya está instalado ($(ollama --version 2>/dev/null | head -1))"
elif [ "$INSTALAR_OLLAMA" = 0 ]; then
    aviso "Sin instalar Ollama (--sin-ollama): Tux necesita Ollama para la IA."
else
    info "Descargando e instalando Ollama desde ollama.com…"
    curl -fsSL https://ollama.com/install.sh -o /tmp/instalar-ollama.sh >> "$LOG" 2>&1 \
        || fallar "No se pudo descargar el instalador de Ollama."
    correr sh /tmp/instalar-ollama.sh || fallar "La instalación de Ollama falló."
    rm -f /tmp/instalar-ollama.sh
    command -v ollama >/dev/null || fallar "Ollama no quedó instalado."
    ok "Ollama instalado"
fi
api_lista() { curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; }
if command -v ollama >/dev/null && ! api_lista; then
    if systemctl list-unit-files 2>/dev/null | grep -q '^ollama.service'; then
        correr sudo systemctl enable --now ollama || true
    fi
    if ! api_lista; then
        nohup ollama serve >> "$LOG" 2>&1 &
    fi
    for _ in $(seq 1 30); do api_lista && break; sleep 1; done
fi
if command -v ollama >/dev/null; then
    api_lista && ok "Ollama está funcionando" || aviso "Ollama no responde todavía; Tux lo arrancará al abrirse."
fi

if [ "$DESCARGAR_MODELO" = 1 ]; then
    if ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$MODELO"; then
        ok "Modelo $MODELO ya descargado"
    else
        info "Descargando el modelo $MODELO (unos 2,5 GB, solo esta vez)…"
        if ollama pull "$MODELO"; then
            ok "Modelo $MODELO listo"
        else
            aviso "No se pudo descargar el modelo. Puedes hacerlo luego con:  ollama pull $MODELO"
        fi
    fi
else
    aviso "Sin descargar el modelo (--sin-modelo). Hazlo luego con:  ollama pull $MODELO"
fi
if [ "$MODELO" != "qwen3:4b-instruct-2507-q4_K_M" ]; then
    mkdir -p "$HOME/.config/tux-assistant"
    echo "$MODELO" > "$HOME/.config/tux-assistant/modelo"
    info "Tux usará el modelo $MODELO"
fi

# ---------- accesos directos ----------
paso "Creando el acceso directo y el comando tux-assistant"
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
ln -sf "$APP_DIR/run.sh" "$HOME/.local/bin/tux-assistant"
ok "Comando: tux-assistant"
ESCRITORIO="$HOME/.local/share/applications/tux-assistant.desktop"
cat > "$ESCRITORIO" <<EOF
[Desktop Entry]
Type=Application
Name=Tux Assistant
GenericName=Asistente para aprender Linux
Comment=Agente pedagógico con IA local que te enseña Linux en tu escritorio
Exec=$APP_DIR/run.sh
Icon=$APP_DIR/assets/tux.png
Terminal=false
Categories=Education;Utility;
Keywords=linux;terminal;aprender;tux;ia;asistente;
StartupNotify=false
EOF
chmod +x "$ESCRITORIO"
command -v update-desktop-database >/dev/null && correr update-desktop-database "$HOME/.local/share/applications"
ok "Aparece en tu menú de aplicaciones como «Tux Assistant»"
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) aviso "~/.local/bin no está en tu PATH: el comando tux-assistant funcionará al abrir una terminal nueva." ;;
esac

if [ -z "$AUTOSTART" ]; then
    if pregunta "¿Quieres que Tux arranque solo al iniciar sesión?" n; then AUTOSTART=si; else AUTOSTART=no; fi
fi
AUTOARRANQUE="$HOME/.config/autostart/tux-assistant.desktop"
if [ "$AUTOSTART" = si ]; then
    mkdir -p "$HOME/.config/autostart"
    cp "$ESCRITORIO" "$AUTOARRANQUE"
    ok "Tux arrancará al iniciar sesión"
else
    rm -f "$AUTOARRANQUE"
    info "Sin arranque automático (puedes activarlo con: bash instalar.sh --autostart)"
fi

# ---------- comprobación final ----------
paso "Comprobación final"
ERRORES=0
"$VPY" -c "import PyQt5.QtWidgets, psutil, requests, PIL" >/dev/null 2>&1 && ok "Python y librerías" || { error "Librerías de Python"; ERRORES=1; }
if command -v ollama >/dev/null; then ok "Ollama"; elif [ "$INSTALAR_OLLAMA" = 1 ]; then error "Ollama"; ERRORES=1; fi
if [ "$DESCARGAR_MODELO" = 1 ]; then
    ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$MODELO" && ok "Modelo $MODELO" || aviso "Modelo pendiente de descargar"
fi
[ -f "$ESCRITORIO" ] && ok "Acceso directo"
(cd "$APP_DIR" && "$VPY" -m py_compile main.py aprendizaje.py cuaderno.py) >> "$LOG" 2>&1 && ok "Código verificado" \
    || { error "El código no compila (ver registro)"; ERRORES=1; }

echo
if [ "$ERRORES" = 0 ]; then
    echo "${VER}${NEG}  🐧 ¡Tux Assistant quedó instalado!${RST}"
else
    echo "${AMA}${NEG}  Tux Assistant se instaló con avisos. Revisa: $LOG${RST}"
fi
cat <<EOF

  ${NEG}Cómo abrirlo:${RST}  menú de aplicaciones → «Tux Assistant»,  o en una terminal:  tux-assistant
  ${NEG}Cómo se usa:${RST}   clic en Tux = pregunta rápida · doble clic = cuaderno completo · clic derecho = cerrar
  ${NEG}Desinstalar:${RST}   bash "$APP_DIR/desinstalar.sh"
  ${GRI}Registro de la instalación: $LOG${RST}

EOF
if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && pregunta "¿Abrir Tux Assistant ahora?" s; then
    nohup "$APP_DIR/run.sh" >/dev/null 2>&1 &
    ok "Abriendo Tux Assistant…"
fi
