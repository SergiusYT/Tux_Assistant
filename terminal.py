"""Vigilancia de terminal: Tux se entera cuando un comando de bash falla.

Un bloque pequeño en ~/.bashrc (entre marcadores, se puede quitar) escribe el
ÚLTIMO comando fallido en un archivo de menos de 1 KB que se sobrescribe cada
vez. No se registra nada más de lo que el usuario escribe.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import herramientas

BASHRC = Path.home() / ".bashrc"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "tux-assistant"
ARCHIVO_ERROR = CACHE / "ultimo_error"
INICIO, FIN = "# >>> tux-assistant >>>", "# <<< tux-assistant <<<"

# 130 = Ctrl+C, 148 = Ctrl+Z, 141 = tubería cerrada: no son errores reales
HOOK = rf'''{INICIO}
# Avisa a Tux Assistant del último comando que falló (se quita con «desactivar terminal»)
__tux_err() {{
  local c=$? n l
  if [ "$c" -ne 0 ] && [ "$c" -ne 130 ] && [ "$c" -ne 148 ] && [ "$c" -ne 141 ]; then
    l=$(HISTTIMEFORMAT= history 1); n=${{l%%[!0-9 ]*}}
    if [ "$n" != "$__tux_n" ]; then
      __tux_n=$n
      printf '%s\t%s\t%s\n' "$c" "$PWD" "${{l#"$n"}}" > "{ARCHIVO_ERROR}" 2>/dev/null
    fi
  fi
  return $c
}}
case ";$PROMPT_COMMAND;" in *";__tux_err;"*) ;; *) PROMPT_COMMAND="__tux_err${{PROMPT_COMMAND:+;$PROMPT_COMMAND}}";; esac
{FIN}
'''


def instalado():
    try:
        return INICIO in BASHRC.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def instalar():
    """Añade el bloque a ~/.bashrc (una sola vez). Devuelve True si quedó instalado."""
    CACHE.mkdir(parents=True, exist_ok=True)
    if instalado():
        return True
    try:
        with open(BASHRC, "a", encoding="utf-8") as f:
            f.write("\n" + HOOK)
        return True
    except OSError:
        return False


def desinstalar():
    """Quita el bloque de ~/.bashrc y borra el archivo de error."""
    try:
        texto = BASHRC.read_text(encoding="utf-8")
    except OSError:
        return False
    nuevo = re.sub(rf"\n?{re.escape(INICIO)}.*?{re.escape(FIN)}\n?", "\n", texto, flags=re.DOTALL)
    if nuevo != texto:
        BASHRC.write_text(nuevo.rstrip("\n") + "\n", encoding="utf-8")
    try:
        ARCHIVO_ERROR.unlink()
    except OSError:
        pass
    return True


def marca():
    """mtime del archivo de error (para detectar cambios sin leerlo)."""
    try:
        return ARCHIVO_ERROR.stat().st_mtime
    except OSError:
        return None


def leer_error():
    """Devuelve {'codigo', 'carpeta', 'comando'} o None."""
    try:
        linea = ARCHIVO_ERROR.read_text(encoding="utf-8", errors="ignore").strip("\n")
        codigo, carpeta, comando = linea.split("\t", 2)
        return {"codigo": int(codigo), "carpeta": carpeta, "comando": comando.strip()}
    except (OSError, ValueError):
        return None


# Comandos que devuelven 1 normalmente sin que sea un error (grep sin coincidencias, test falso…)
_FALLO_NORMAL = re.compile(r"^\s*(grep|egrep|fgrep|rg|diff|cmp|test|\[|\[\[|false|which|type|pgrep|command)\b")
# Programas interactivos: al salir con código ≠ 0 normalmente no hay nada que explicar
_INTERACTIVOS = re.compile(r"^\s*(nano|vim?|nvim|less|more|man|top|htop|ssh|python3?|ipython|node|mysql|psql|tux)\b")


def vale_la_pena(err):
    """Filtra fallos que no merecen interrumpir al usuario."""
    if not err or not err["comando"]:
        return False
    cmd = err["comando"]
    if err["codigo"] == 1 and _FALLO_NORMAL.match(cmd):
        return False
    if _INTERACTIVOS.match(cmd) and err["codigo"] != 127:
        return False
    return True


def _sugerencia_paquete(programa):
    """Usa command-not-found de Ubuntu (solo lectura) para saber qué paquete lo trae."""
    cnf = "/usr/lib/command-not-found"
    if not os.path.exists(cnf) or not re.fullmatch(r"[\w.+-]+", programa):
        return ""
    try:
        r = subprocess.run([cnf, "--", programa], capture_output=True, text=True, timeout=4,
                           env={**os.environ, "LC_ALL": "C.UTF-8"})
        texto = (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""
    install = re.findall(r"(sudo (?:apt|snap) install [^\n]+)", texto)
    if install:
        return install[0].strip()
    similares = re.findall(r"command '([\w.+-]+)' from", texto)
    return f"¿quisiste decir {similares[0]}?" if similares else ""


def _mensaje_real(comando, carpeta):
    """Vuelve a correr el comando SOLO si pasa la lista blanca de solo lectura, para ver el error real."""
    args, motivo = herramientas.validar(comando)
    if not args:
        return ""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=4, cwd=carpeta if os.path.isdir(carpeta) else None,
                           env={**os.environ, "LC_ALL": "C.UTF-8"})
    except (OSError, subprocess.TimeoutExpired):
        return ""
    salida = (r.stderr or "").strip() or ((r.stdout or "").strip() if r.returncode else "")
    return "\n".join(salida.splitlines()[:3])[:300]


_COMUNES = ["apt", "sudo", "git", "ls", "cd", "cp", "mv", "rm", "mkdir", "cat", "nano", "snap", "flatpak",
            "python3", "pip", "systemctl", "journalctl", "chmod", "chown", "grep", "find", "top", "htop", "ping",
            "curl", "wget", "tar", "unzip", "ssh", "code", "docker", "make", "touch", "echo", "man", "df", "du", "free"]
_SUBCOMANDOS = {
    "apt": ["install", "remove", "purge", "update", "upgrade", "full-upgrade", "autoremove", "search", "show", "list", "policy"],
    "snap": ["install", "remove", "list", "find", "info", "refresh", "run"],
    "flatpak": ["install", "uninstall", "list", "search", "update", "run", "info"],
    "systemctl": ["start", "stop", "restart", "reload", "status", "enable", "disable", "is-active", "is-enabled", "list-units", "mask", "unmask"],
    "git": ["clone", "status", "add", "commit", "push", "pull", "log", "diff", "checkout", "switch", "branch", "merge", "init", "fetch", "stash", "reset"],
}
_ejecutables = None


def _parecido(programa):
    """Comando instalado más parecido a lo que se escribió (apd → apt)."""
    global _ejecutables
    import difflib
    # letras invertidas en comandos cortos: «sl» → «ls», «tpo» → «top»
    for comun in _COMUNES:
        if len(programa) == len(comun) and programa != comun and sorted(programa) == sorted(comun):
            return comun
    m = difflib.get_close_matches(programa, _COMUNES, n=1, cutoff=0.6)
    if m:
        return m[0]
    if _ejecutables is None:
        _ejecutables = set()
        for d in os.environ.get("PATH", "").split(":"):
            try:
                _ejecutables.update(os.listdir(d))
            except OSError:
                pass
    m = difflib.get_close_matches(programa, sorted(_ejecutables), n=1, cutoff=0.75)
    return m[0] if m else ""


def _subcomando_mal_escrito(cmd):
    """«apt instal» → ('instal', 'install')."""
    import difflib
    partes = cmd.split()
    if partes[:1] == ["sudo"]:
        partes = partes[1:]
    if len(partes) < 2 or partes[0] not in _SUBCOMANDOS or partes[1].startswith("-"):
        return None
    validos = _SUBCOMANDOS[partes[0]]
    if partes[1] in validos:
        return None
    m = difflib.get_close_matches(partes[1], validos, n=1, cutoff=0.6)
    return (partes[1], m[0]) if m else None


def explicacion_rapida(err):
    """Explicación instantánea (sin IA) + mensaje real si se pudo obtener.

    Devuelve (texto_markdown, mensaje_error_real).
    """
    cmd, codigo = err["comando"], err["codigo"]
    try:
        programa = cmd.split()[0] if cmd.split()[0] != "sudo" else cmd.split()[1]
    except IndexError:
        programa = cmd
    real = ""
    # Con sudo, un comando inexistente devuelve 1 («sudo: 'apd': command not found»), no 127
    if codigo != 127 and cmd.split()[:1] == ["sudo"] and programa and not shutil.which(programa):
        codigo = 127
    if codigo == 127:
        parecido = _parecido(programa)
        if parecido and parecido != programa and shutil.which(parecido):
            corregido = cmd.replace(programa, parecido, 1)
            return (f"`{programa}` no existe: parece un error de escritura. ¿Quisiste decir `{parecido}`?\n`{corregido}`", "")
        sug = _sugerencia_paquete(programa)
        txt = f"`{programa}` no existe en tu sistema: no está instalado o lo escribiste mal."
        if sug.startswith("sudo"):
            txt += f" Lo trae este paquete:\n`{sug}`"
        elif sug:
            txt += f" {sug[0].upper()}{sug[1:]}"
    elif codigo == 126:
        txt = (f"El archivo existe pero no tiene permiso de ejecución. Dáselo con:\n`chmod +x {programa}`"
               if "/" in programa else "No tienes permiso para ejecutar eso.")
    elif _subcomando_mal_escrito(cmd):
        malo, bueno = _subcomando_mal_escrito(cmd)
        txt = f"`{malo}` no es una orden válida aquí. ¿Quisiste decir `{bueno}`?\n`{cmd.replace(malo, bueno, 1)}`"
    else:
        real = _mensaje_real(cmd, err["carpeta"])
        if re.search(r"permission denied|permiso denegado|are you root|superuser", real, re.I):
            txt = "Te faltan permisos: ese comando necesita ser administrador (sudo) o el archivo no es tuyo."
        elif re.search(r"no such file|no existe|cannot access|not found", real, re.I):
            txt = "La ruta o el archivo que escribiste no existe en esa carpeta. Revisa el nombre con `ls`."
        elif re.search(r"could not get lock|lock-frontend|is another process using", real, re.I):
            txt = "Otro programa está usando apt (quizás una actualización automática). Espera un minuto y repite."
        else:
            txt = f"El comando terminó con error (código {codigo})."
    return txt, real


def pregunta_para_ia(err, real):
    """Mensaje que se envía a la IA cuando el usuario pide «Explícame más»."""
    p = (f"Mi comando `{err['comando']}` falló con código de salida {err['codigo']} "
         f"(estaba en la carpeta {err['carpeta']}).")
    if real:
        p += f" El mensaje fue: «{real}»."
    return p + " ¿Qué significa y cómo lo arreglo?"


def disponible():
    return shutil.which("bash") is not None


# ---------- Sacarle provecho: clasificar errores, estadísticas y lección recomendada ----------

TIPOS = {
    "escritura": "Errores de escritura",
    "no_instalado": "Programa no instalado",
    "permisos": "Faltan permisos",
    "ruta": "Ruta o archivo inexistente",
    "apt_bloqueado": "apt ocupado",
    "otro": "Otros",
}

# Programa → lección que enseña justo eso (ids del catálogo de aprendizaje.py)
_LECCION_POR_PROGRAMA = {
    "git": "d2", "docker": "o2", "systemctl": "s3", "journalctl": "y4", "ssh": "z1", "ssh-keygen": "z1",
    "chmod": "p2", "chown": "p1", "pip": "d3", "pip3": "d3", "python3": "d3", "gcc": "d4", "make": "d4",
    "apt": "k2", "apt-get": "k2", "snap": "k3", "flatpak": "k3", "kill": "s2", "ss": "r3", "ip": "r1", "ping": "r2",
    "grep": "x2", "awk": "x3", "sed": "x3", "find": "x4", "ufw": "z3", "qemu-img": "v4", "ollama": "a1",
    "tar": "t3", "cp": "t3", "mv": "t3", "rm": "t3", "cd": "t1", "ls": "t1", "cat": "t2",
}
_LECCION_POR_TIPO = {"escritura": "t4", "no_instalado": "k2", "permisos": "p1", "ruta": "t1", "apt_bloqueado": "k1"}


def programa_de(cmd):
    partes = (cmd or "").split()
    if partes[:1] == ["sudo"]:
        partes = partes[1:]
    return partes[0] if partes else ""


def clasificar(err, explicacion, real=""):
    texto = f"{explicacion} {real}".lower()
    if "error de escritura" in texto or "quisiste decir" in texto:
        return "escritura"
    if "no existe en tu sistema" in texto or err.get("codigo") == 127:
        return "no_instalado"
    if "permis" in texto or err.get("codigo") == 126:
        return "permisos"
    if "otro programa está usando apt" in texto:
        return "apt_bloqueado"
    if "no existe en esa carpeta" in texto or "no such file" in texto:
        return "ruta"
    return "otro"


def leccion_recomendada(err, tipo):
    """Id de la lección del catálogo que ayuda a no repetir este error (o None)."""
    prog = programa_de(err.get("comando", ""))
    # «git psuh»: el programa existe y lo mal escrito es la orden → lección de ese programa
    if tipo == "escritura" and prog in _LECCION_POR_PROGRAMA and shutil.which(prog):
        return _LECCION_POR_PROGRAMA[prog]
    if tipo in ("escritura", "permisos", "ruta", "apt_bloqueado"):
        return _LECCION_POR_TIPO[tipo] if tipo != "permisos" or prog not in ("chmod", "chown") else _LECCION_POR_PROGRAMA[prog]
    return _LECCION_POR_PROGRAMA.get(prog) or _LECCION_POR_TIPO.get(tipo)


ESTADISTICAS = Path.home() / ".config" / "tux-assistant" / "terminal.json"


def cargar_estadisticas():
    import json
    try:
        datos = json.loads(ESTADISTICAS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        datos = {}
    datos.setdefault("silencioso", False)
    datos.setdefault("eventos", [])  # [timestamp, tipo, programa] (máx. 300: unos pocos KB)
    datos.setdefault("ultimo", "")
    datos.setdefault("repeticiones", 0)
    return datos


def guardar_estadisticas(datos):
    import json
    ESTADISTICAS.parent.mkdir(parents=True, exist_ok=True)
    datos["eventos"] = datos["eventos"][-300:]
    ESTADISTICAS.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def registrar(err, tipo):
    """Guarda el evento y devuelve cuántas veces seguidas ha fallado ESTE mismo comando."""
    import time as _t
    datos = cargar_estadisticas()
    datos["eventos"].append([int(_t.time()), tipo, programa_de(err["comando"])])
    if datos["ultimo"] == err["comando"]:
        datos["repeticiones"] += 1
    else:
        datos["ultimo"], datos["repeticiones"] = err["comando"], 1
    guardar_estadisticas(datos)
    return datos["repeticiones"]


def resumen_semana(datos=None):
    """{'total', 'por_tipo': [(tipo, n)], 'programa': (prog, n) | None, 'hoy'}."""
    import time as _t
    from collections import Counter
    datos = datos or cargar_estadisticas()
    ahora = _t.time()
    semana = [e for e in datos["eventos"] if ahora - e[0] < 7 * 86400]
    hoy = sum(1 for e in semana if ahora - e[0] < 86400)
    tipos = Counter(e[1] for e in semana).most_common()
    progs = Counter(e[2] for e in semana if e[2]).most_common(1)
    return {"total": len(semana), "por_tipo": tipos, "programa": progs[0] if progs else None, "hoy": hoy}


# Lecciones que forman un repaso útil según el tipo de error (además de la lección principal)
_RUTA_POR_TIPO = {
    "escritura": ["t4", "e1", "d1"],      # pedir ayuda (--help, man) · alias para no escribir de más · PATH/which
    "no_instalado": ["k1", "k2", "k4"],   # qué es un gestor · instalar con apt · buscar paquetes
    "permisos": ["p1", "p2", "p3"],
    "ruta": ["t1", "t2", "t3"],
    "apt_bloqueado": ["k1", "k2"],
}


def ruta_recomendada(lid, tipo, lecciones_catalogo, temas_catalogo):
    """Lista de 2-4 lecciones para un repaso: la que evita el error + las que lo complementan."""
    ruta = [lid] if lid in lecciones_catalogo else []
    for extra in _RUTA_POR_TIPO.get(tipo, []):
        if extra not in ruta:
            ruta.append(extra)
    if len(ruta) < 2 and lid in lecciones_catalogo:  # completa con las siguientes del mismo tema
        ids = [l["id"] for l in temas_catalogo[lecciones_catalogo[lid]["tema"]]["lecciones"]]
        for extra in ids[ids.index(lid) + 1:] + ids[:ids.index(lid)]:
            if extra not in ruta:
                ruta.append(extra)
            if len(ruta) >= 3:
                break
    return ruta[:4]
