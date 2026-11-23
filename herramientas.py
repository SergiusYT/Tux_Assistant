"""Herramienta de consulta para Tux: la IA puede pedir comandos de SOLO LECTURA.

La IA decide qué necesita saber del equipo (si algo está instalado, la versión
de un programa, el estado de un servicio, logs, hardware...) y pide un comando.
Aquí se valida contra una lista blanca y se ejecuta sin shell, sin sudo, con
tiempo límite y salida recortada. Nada que pueda modificar el sistema pasa el
filtro (principio de mínimo privilegio, OWASP LLM "excessive agency").
"""
import os
import re
import shlex
import shutil
import subprocess

MAX_SALIDA = 2500
TIMEOUT = 6

HERRAMIENTA_OLLAMA = {
    "type": "function",
    "function": {
        "name": "consultar_sistema",
        "description": (
            "Ejecuta en el equipo del usuario un comando de SOLO LECTURA y devuelve su salida real. "
            "Úsalo cuando necesites un dato que no está en el contexto: si un programa o paquete está "
            "instalado, su versión, el estado de un servicio, logs, hardware, red, archivos de configuración. "
            "No puede instalar, borrar ni cambiar nada."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "comando": {
                    "type": "string",
                    "description": (
                        "Un solo comando de lectura, sin sudo, sin tuberías ni redirecciones. "
                        "Ejemplos: 'dpkg -s vlc', 'snap list', 'systemctl status bluetooth', 'sensors', "
                        "'journalctl -u NetworkManager -n 20', 'apt-cache policy firefox', 'ls /etc/apt/sources.list.d'"
                    ),
                }
            },
            "required": ["comando"],
        },
    },
}

# Comandos permitidos -> subcomandos/primer argumento permitidos (None = cualquier argumento)
_PERMITIDOS = {
    # información general y hardware
    "uname": None, "hostnamectl": {"", "status"}, "lsb_release": None, "uptime": None, "whoami": None,
    "id": None, "groups": None, "lscpu": None, "lsblk": None, "lspci": None, "lsusb": None, "lsmod": None,
    "free": None, "df": None, "sensors": None, "nproc": None, "arch": None, "locale": None, "date": None,
    "inxi": None, "dmidecode": None, "upower": {"-d", "--dump", "-e", "--enumerate", "-i"},
    "nvidia-smi": None, "glxinfo": {"-B"}, "vulkaninfo": {"--summary"}, "fc-list": None,
    "localectl": {"", "status", "list-keymaps"}, "timedatectl": {"", "status", "show"},
    "loginctl": {"", "list-sessions", "show-session", "session-status", "show-user"},
    "xrandr": {"", "--current", "--listmonitors", "-q", "--query"},
    "gsettings": {"get", "list-recursively", "list-keys", "list-schemas"},
    # procesos y servicios
    "ps": None, "pgrep": None, "top": {"-bn1", "-b"}, "pidof": None,
    "systemctl": {"status", "is-active", "is-enabled", "is-failed", "list-units", "list-unit-files",
                  "list-timers", "show", "cat", "--failed", "--version", "--user"},
    "journalctl": None, "dmesg": None, "last": None,
    # paquetes
    "dpkg": {"-l", "-s", "-L", "-S", "--status", "--list", "--listfiles", "--search", "--get-selections",
             "--print-architecture"},
    "dpkg-query": None,
    "apt": {"list", "show", "policy", "search", "depends", "rdepends"},
    "apt-cache": {"policy", "show", "search", "depends", "rdepends", "showpkg", "madison"},
    "snap": {"list", "info", "find", "version", "services", "connections"},
    "flatpak": {"list", "info", "search", "remotes", "--version"},
    "rpm": {"-q", "-qa", "-qi", "-ql", "-qf"}, "dnf": {"list", "info", "search", "repolist", "history"},
    "pacman": {"-Q", "-Qi", "-Ql", "-Qs", "-Qo", "-Ss", "-Si", "-Qq", "-Qe"},
    "zypper": {"search", "info", "se", "if", "repos", "lr"},
    "which": None, "whereis": None, "type": None,
    # red
    "ip": {"a", "addr", "address", "r", "route", "link", "l", "-br", "-s", "-c", "neigh"},
    "nmcli": {"general", "g", "device", "d", "dev", "connection", "c", "con", "radio", "-t", "-f", "-p"},
    "ss": None, "ping": None, "resolvectl": {"status", "dns", "query"}, "getent": {"hosts", "passwd", "group"},
    "iwconfig": None, "rfkill": {"list", ""},
    # archivos (con rutas filtradas)
    "ls": None, "cat": None, "head": None, "tail": None, "stat": None, "file": None, "readlink": None,
    "realpath": None, "du": None, "find": None, "grep": None, "wc": None, "tree": None,
    # usuarios y seguridad (solo estado)
    "ufw": {"status"}, "mokutil": {"--sb-state"}, "aa-status": None, "getenforce": None,
}

# Opciones que convierten un comando de lectura en uno que modifica o ejecuta cosas
_OPCIONES_PROHIBIDAS = {
    "find": {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls"},
    "journalctl": {"--vacuum-size", "--vacuum-time", "--vacuum-files", "--rotate", "--flush", "--sync"},
    "dmesg": {"-c", "-C", "--clear", "--read-clear"},
    "nmcli": {"up", "down", "delete", "modify", "add", "connect", "disconnect", "set", "on", "off", "reload"},
    "systemctl": {"start", "stop", "restart", "enable", "disable", "mask", "unmask", "kill", "edit",
                  "set-property", "isolate", "reboot", "poweroff", "daemon-reload"},
    "nvidia-smi": {"-pm", "-pl", "-r", "--gpu-reset", "-ac", "-rac", "-c", "-e", "-lgc", "-rgc"},
    "ip": {"add", "del", "delete", "set", "flush", "change", "replace"},
    "date": {"-s", "--set"},
    "ping": set(),
}

# Nada de secretos: claves, contraseñas, perfiles de navegador, tokens
_RUTAS_SENSIBLES = re.compile(
    r"(\.ssh|\.gnupg|shadow|gshadow|sudoers|id_rsa|id_ed25519|\.pem$|\.key$|keyring|\.mozilla|"
    r"\.config/(google-chrome|chromium|BraveSoftware)|token|secret|passw|\.env$|credential|\.aws|\.kube|"
    r"\.netrc|\.git-credentials|\.docker/config|wallet|/proc/\d+/environ|\.bash_history|\.zsh_history)",
    re.IGNORECASE,
)

_METACARACTERES = re.compile(r"[|;&><`$\\\n]")


def validar(comando):
    """Devuelve (lista_de_argumentos, None) si es seguro, o (None, motivo) si no."""
    comando = (comando or "").strip()
    if not comando:
        return None, "comando vacío"
    if _METACARACTERES.search(comando):
        return None, "no se permiten tuberías, redirecciones, variables ni varios comandos"
    try:
        args = shlex.split(comando)
    except ValueError:
        return None, "comando mal formado"
    if args[0] in ("sudo", "su", "doas", "pkexec"):
        return None, "no se permite sudo: Tux solo consulta, no administra"
    base = os.path.basename(args[0])

    # Cualquier programa instalado puede consultarse con --version (salvo los destructivos)
    if len(args) == 2 and args[1] in ("--version", "-V", "version"):
        if re.match(r"(rm|dd|mkfs.*|shred|wipefs|shutdown|reboot|poweroff|halt|kill.*|pkill|fdisk|parted)$", base):
            return None, "no se consultan programas destructivos"
        return ([base, args[1]], None) if shutil.which(base) else (None, f"{base} no está instalado")

    if base not in _PERMITIDOS:
        return None, f"'{base}' no está en la lista de comandos de solo lectura"
    sub = _PERMITIDOS[base]
    primero = args[1] if len(args) > 1 else ""
    if sub is not None and primero not in sub:
        return None, f"'{base} {primero}' no está permitido (solo: {', '.join(sorted(s for s in sub if s)) or 'sin argumentos'})"
    prohibidas = _OPCIONES_PROHIBIDAS.get(base, set())
    if any(a in prohibidas for a in args[1:]):
        return None, "esa opción modifica el sistema"
    if base == "ping" and not any(a.startswith("-c") for a in args):
        args = [args[0], "-c", "3"] + args[1:]
    if base == "journalctl" and not any(a.startswith(("-n", "--lines")) for a in args):
        args += ["-n", "40"]
    if base == "journalctl":
        args.append("--no-pager")
    if base == "systemctl":
        args.append("--no-pager")
    for a in args[1:]:
        if _RUTAS_SENSIBLES.search(os.path.expanduser(a)):
            return None, "esa ruta puede contener datos privados (claves, contraseñas...)"
    if base == "cat" and len(args) == 1:
        return None, "cat necesita un archivo"
    return [base] + [os.path.expanduser(a) for a in args[1:]], None


def _filtro(etapa, lineas):
    """Emula en Python (sin shell) los filtros típicos tras una tubería."""
    try:
        partes = shlex.split(etapa)
    except ValueError:
        return None
    if not partes:
        return None
    nombre, opciones = partes[0], partes[1:]
    if nombre in ("grep", "egrep"):
        flags = [o for o in opciones if o.startswith("-")]
        patron = next((o for o in opciones if not o.startswith("-")), None)
        if patron is None:
            return None
        ignorar = any("i" in f for f in flags)
        invertir = any("v" in f for f in flags)
        try:
            rx = re.compile(patron, re.IGNORECASE if ignorar else 0)
        except re.error:
            rx = re.compile(re.escape(patron), re.IGNORECASE if ignorar else 0)
        return [l for l in lineas if bool(rx.search(l)) != invertir]
    if nombre in ("head", "tail"):
        n = 10
        for i, o in enumerate(opciones):
            if o == "-n" and i + 1 < len(opciones) and opciones[i + 1].isdigit():
                n = int(opciones[i + 1])
            elif re.fullmatch(r"-n?\d+", o):
                n = int(o.lstrip("-n"))
        return lineas[:n] if nombre == "head" else lineas[-n:]
    if nombre == "wc" and opciones == ["-l"]:
        return [str(len(lineas))]
    if nombre in ("sort", "uniq"):
        return sorted(set(lineas)) if nombre == "uniq" else sorted(lineas)
    return None


def ejecutar(comando):
    """Ejecuta uno o varios comandos ('a && b', 'a; b') y tuberías hacia grep/head/tail/wc.

    Siempre devuelve texto (salida real o el motivo del rechazo).
    """
    comando = (comando or "").strip()
    partes = [c.strip() for c in re.split(r"&&|;|\n", comando) if c.strip()]
    if len(partes) > 1:
        return "\n\n".join(f"$ {c}\n{ejecutar(c)}" for c in partes[:4])
    etapas = [e.strip() for e in comando.split("|")]
    if len(etapas) > 1:
        salida = _ejecutar_uno(etapas[0], recortar=False)
        if salida.startswith("[RECHAZADO]"):
            return salida
        lineas = salida.splitlines()
        for etapa in etapas[1:]:
            lineas = _filtro(etapa, lineas)
            if lineas is None:
                return f"[RECHAZADO] tras '|' solo se admite grep, head, tail, wc -l, sort o uniq"
        return _recortar("\n".join(lineas) or "(sin coincidencias)")
    return _ejecutar_uno(comando)


def _recortar(salida):
    if len(salida) > MAX_SALIDA:
        return salida[:MAX_SALIDA] + f"\n…[recortado, {len(salida)} caracteres en total]"
    return salida


def _ejecutar_uno(comando, recortar=True):
    args, motivo = validar(comando)
    if args is None:
        return f"[RECHAZADO] {motivo}"
    if not shutil.which(args[0]):
        return f"[NO DISPONIBLE] '{args[0]}' no está instalado en este equipo"
    try:
        r = subprocess.run(
            args, capture_output=True, text=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL,
            env={**os.environ, "LC_ALL": "C", "SYSTEMD_PAGER": "", "PAGER": "cat"},
        )
    except subprocess.TimeoutExpired:
        return f"[TIEMPO AGOTADO] el comando tardó más de {TIMEOUT}s"
    except OSError as e:
        return f"[ERROR] {e}"
    salida = (r.stdout or "") + (("\n[stderr] " + r.stderr.strip()) if r.stderr.strip() else "")
    salida = salida.strip() or "(sin salida)"
    if r.returncode != 0:
        salida = f"[código de salida {r.returncode}]\n" + salida
    return _recortar(salida) if recortar else salida
