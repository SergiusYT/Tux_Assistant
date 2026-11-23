"""Semáforo de riesgo: analiza un comando ANTES de que el usuario lo ejecute.

Reglas fijas en código (no IA): el resultado es el mismo siempre y no depende
de que el modelo acierte. Devuelve nivel (verde/amarillo/rojo), motivos y una
explicación de cada parte del comando.
"""
import re
import shlex

VERDE, AMARILLO, ROJO = "verde", "amarillo", "rojo"
ETIQUETA = {VERDE: "🟢 Seguro", AMARILLO: "🟡 Cuidado", ROJO: "🔴 Peligroso"}
_ORDEN = {VERDE: 0, AMARILLO: 1, ROJO: 2}

# Qué hace cada programa (explicación corta para principiantes)
PROGRAMAS = {
    "sudo": "ejecuta lo que sigue como administrador (root)",
    "ls": "lista archivos y carpetas", "cd": "cambia de carpeta", "pwd": "muestra en qué carpeta estás",
    "cp": "copia archivos", "mv": "mueve o renombra archivos", "rm": "borra archivos (sin papelera)",
    "rmdir": "borra carpetas vacías", "mkdir": "crea carpetas", "touch": "crea un archivo vacío o actualiza su fecha",
    "cat": "muestra el contenido de un archivo", "less": "muestra un archivo página por página",
    "head": "muestra las primeras líneas", "tail": "muestra las últimas líneas", "nano": "editor de texto en la terminal",
    "vim": "editor de texto en la terminal", "grep": "busca texto dentro de archivos o salidas",
    "find": "busca archivos por nombre, tamaño, fecha…", "chmod": "cambia los permisos de un archivo",
    "chown": "cambia el dueño de un archivo", "ln": "crea enlaces (accesos directos) a archivos",
    "apt": "gestor de paquetes de Ubuntu/Debian", "apt-get": "gestor de paquetes (versión antigua de apt)",
    "dpkg": "instala o consulta paquetes .deb", "snap": "gestor de paquetes Snap", "flatpak": "gestor de paquetes Flatpak",
    "dnf": "gestor de paquetes de Fedora", "pacman": "gestor de paquetes de Arch",
    "pip": "instala paquetes de Python", "pip3": "instala paquetes de Python",
    "systemctl": "controla los servicios del sistema", "journalctl": "muestra los registros (logs) del sistema",
    "ps": "lista los procesos", "top": "monitor de procesos en vivo", "htop": "monitor de procesos en vivo",
    "kill": "envía una señal (normalmente cerrar) a un proceso", "killall": "cierra procesos por nombre",
    "pkill": "cierra procesos por nombre", "df": "espacio libre en los discos", "du": "cuánto ocupa una carpeta",
    "free": "uso de memoria RAM", "tar": "empaqueta o desempaqueta archivos .tar", "zip": "comprime en .zip",
    "unzip": "descomprime .zip", "wget": "descarga archivos de internet", "curl": "hace peticiones a internet",
    "git": "control de versiones", "ssh": "conexión remota segura", "scp": "copia archivos por ssh",
    "ping": "comprueba si un equipo responde en la red", "ip": "configuración de red",
    "ss": "conexiones y puertos abiertos", "dd": "copia datos byte a byte (discos completos)",
    "mkfs": "formatea una partición", "fdisk": "edita particiones del disco", "parted": "edita particiones del disco",
    "shutdown": "apaga el equipo", "reboot": "reinicia el equipo", "poweroff": "apaga el equipo",
    "echo": "imprime texto", "python3": "ejecuta Python", "bash": "ejecuta un script o una shell bash",
    "sh": "ejecuta un script de shell", "mount": "monta un disco o partición", "umount": "desmonta un disco",
    "passwd": "cambia una contraseña", "useradd": "crea un usuario", "userdel": "borra un usuario",
    "usermod": "modifica un usuario (grupos, permisos…)", "crontab": "programa tareas automáticas",
    "export": "define una variable de entorno", "source": "carga un archivo en la shell actual",
    "which": "dice dónde está un programa", "man": "abre el manual de un comando", "tee": "escribe la salida en un archivo",
    "sed": "edita texto con patrones", "awk": "procesa texto por columnas", "sort": "ordena líneas",
    "uniq": "quita líneas repetidas", "wc": "cuenta líneas, palabras o caracteres", "xargs": "pasa la salida como argumentos",
    "uname": "información del kernel", "whoami": "tu nombre de usuario", "history": "comandos usados antes",
    "shred": "borra un archivo de forma irrecuperable", "wipefs": "borra la firma de un disco",
}

# Opciones comunes por programa
OPCIONES = {
    "rm": {"-r": "borra carpetas con todo su contenido", "-R": "borra carpetas con todo su contenido",
           "-f": "no pregunta ni avisa (fuerza)", "-rf": "borra carpetas completas sin preguntar",
           "-fr": "borra carpetas completas sin preguntar", "-i": "pregunta antes de borrar cada archivo",
           "-v": "muestra lo que va borrando"},
    "ls": {"-l": "formato largo (permisos, dueño, tamaño)", "-a": "incluye archivos ocultos",
           "-h": "tamaños legibles (K, M, G)", "-la": "formato largo con ocultos", "-lh": "formato largo con tamaños legibles",
           "-lah": "formato largo, ocultos y tamaños legibles", "-R": "recorre subcarpetas"},
    "cp": {"-r": "copia carpetas completas", "-R": "copia carpetas completas", "-i": "pregunta antes de sobrescribir",
           "-v": "muestra lo que copia", "-a": "copia conservando permisos y fechas"},
    "mv": {"-i": "pregunta antes de sobrescribir", "-v": "muestra lo que mueve", "-f": "sobrescribe sin preguntar"},
    "mkdir": {"-p": "crea también las carpetas intermedias"},
    "chmod": {"-R": "aplica a la carpeta y TODO su contenido", "+x": "añade permiso de ejecución",
              "-x": "quita permiso de ejecución", "777": "todos pueden leer, escribir y ejecutar",
              "755": "el dueño todo; los demás leer y ejecutar", "644": "el dueño lee y escribe; los demás solo leen",
              "700": "solo el dueño puede todo", "600": "solo el dueño lee y escribe"},
    "chown": {"-R": "aplica a la carpeta y TODO su contenido"},
    "grep": {"-i": "ignora mayúsculas/minúsculas", "-r": "busca dentro de carpetas", "-n": "muestra el número de línea",
             "-v": "muestra las líneas que NO coinciden", "-c": "cuenta coincidencias"},
    "tar": {"-x": "extrae", "-c": "crea un archivo", "-z": "usa compresión gzip", "-v": "muestra los archivos",
            "-f": "indica el nombre del archivo", "-xzvf": "extrae un .tar.gz mostrando los archivos",
            "-czvf": "crea un .tar.gz mostrando los archivos", "-xvf": "extrae un .tar mostrando los archivos"},
    "ps": {"aux": "todos los procesos de todos los usuarios", "-e": "todos los procesos", "-ef": "todos, formato completo"},
    "kill": {"-9": "cierra a la fuerza (sin dejar guardar)", "-15": "pide cerrar amablemente"},
    "df": {"-h": "tamaños legibles"}, "du": {"-h": "tamaños legibles", "-s": "solo el total", "-sh": "total legible"},
    "free": {"-h": "tamaños legibles", "-m": "en megabytes"},
    "apt": {"install": "instala paquetes", "remove": "desinstala paquetes", "purge": "desinstala y borra su configuración",
            "update": "actualiza la lista de paquetes disponibles", "upgrade": "actualiza los paquetes instalados",
            "autoremove": "borra dependencias que ya nadie usa", "search": "busca paquetes", "show": "información de un paquete",
            "list": "lista paquetes", "-y": "responde «sí» automáticamente a todo"},
    "systemctl": {"start": "arranca un servicio", "stop": "detiene un servicio", "restart": "reinicia un servicio",
                  "enable": "hace que arranque solo al encender", "disable": "evita que arranque al encender",
                  "status": "muestra el estado de un servicio", "--now": "aplica también en este momento"},
    "git": {"clone": "descarga un repositorio", "status": "muestra cambios pendientes", "add": "prepara cambios",
            "commit": "guarda los cambios preparados", "push": "sube cambios", "pull": "baja cambios",
            "reset": "deshace cambios", "--hard": "descarta cambios sin recuperación", "--force": "sobrescribe el remoto",
            "-f": "forzar", "clean": "borra archivos no versionados", "log": "historial de cambios", "diff": "muestra diferencias"},
    "snap": {"install": "instala un snap", "remove": "desinstala un snap", "list": "lista snaps instalados",
             "--classic": "permite acceso completo al sistema (snaps clásicos)"},
    "journalctl": {"-xe": "últimos errores con explicación", "-u": "solo de un servicio", "-f": "sigue en vivo",
                   "-b": "desde el último arranque", "-p": "filtra por prioridad"},
    "dd": {}, "ping": {"-c": "cuántos paquetes enviar"},
    "curl": {"-O": "guarda con el nombre original", "-L": "sigue redirecciones", "-s": "silencioso", "-fsSL": "silencioso, sigue redirecciones y falla si hay error"},
    "wget": {"-O": "nombre del archivo de salida", "-q": "silencioso"},
    "find": {"-name": "por nombre", "-type": "por tipo (f archivo, d carpeta)", "-size": "por tamaño",
             "-delete": "BORRA lo que encuentre", "-exec": "ejecuta un comando por cada resultado"},
}

_RUTAS_SISTEMA = r"(/|/\*|~|~/|~/\*|\$HOME|\$HOME/\*|\*|\.\.|/(bin|boot|dev|etc|home|lib\w*|opt|proc|root|sbin|srv|sys|usr|var)(/\S*)?)"
_PAQUETES_VITALES = r"(python3|systemd|libc6|gnome-shell|ubuntu-desktop|xorg|linux-image\S*|grub\S*|sudo|apt|dpkg|network-manager|bash|coreutils)"

# (patrón, nivel, motivo). Se evalúan sobre el comando completo.
_REGLAS = [
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", ROJO, "Es una «bomba fork»: crea procesos sin fin y congela el equipo."),
    (rf"\brm\s+(-\w*[rR]\w*f\w*|-\w*f\w*[rR]\w*|(-[rR]|--recursive)\s+(-f|--force)|(-f|--force)\s+(-[rR]|--recursive))\s+(--no-preserve-root\s+)?{_RUTAS_SISTEMA}(\s|$)",
     ROJO, "Borra carpetas del sistema o tu carpeta personal completa, sin preguntar y sin papelera."),
    (r"--no-preserve-root", ROJO, "Desactiva la protección que impide borrar todo el sistema."),
    (r"\bdd\b.*\bof=/dev/", ROJO, "Escribe directamente sobre un disco: puede borrar todas tus particiones."),
    (r"\b(mkfs(\.\w+)?|wipefs|shred)\b", ROJO, "Formatea o destruye datos de forma irrecuperable."),
    (r"\b(fdisk|parted|gdisk)\b(?!\s+-l)", ROJO, "Modifica las particiones del disco; un error puede dejar el sistema sin arrancar."),
    (r">\s*/dev/(sd|nvme|hd|vd)\w*", ROJO, "Sobrescribe un disco completo."),
    (r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z)?sh\b", ROJO, "Descarga código de internet y lo ejecuta sin que puedas revisarlo."),
    (rf"\bch(mod|own)\s+(-\w*R\w*|--recursive)\s+\S+\s+{_RUTAS_SISTEMA}(\s|$)", ROJO,
     "Cambia permisos/dueño de carpetas del sistema completas: puede romper programas y la seguridad."),
    (r"\bchmod\s+(-\w+\s+)*0?777\b", AMARILLO, "777 deja que cualquier usuario o programa modifique el archivo."),
    (r">\s*/(etc|boot|usr|bin|sbin|lib)\S*", ROJO, "Sobrescribe un archivo del sistema."),
    (r"\bmv\b.*\s/dev/null\b", ROJO, "Mover algo a /dev/null lo hace desaparecer para siempre."),
    (rf"\b(apt|apt-get|dnf|pacman)\s+(remove|purge|autoremove|-R\w*)\b.*\b{_PAQUETES_VITALES}\b", ROJO,
     "Desinstala un componente vital: el sistema o el escritorio pueden dejar de funcionar."),
    (r"\brm\s+(-\w*[rRf]\w*|--recursive|--force)\b", AMARILLO, "Borra sin papelera: lo borrado no se puede recuperar."),
    (r"\bfind\b.*\s-delete\b", AMARILLO, "Borra todo lo que encuentre; prueba primero sin -delete."),
    (r"\bch(mod|own)\s+(-\w*R\w*|--recursive)\b", AMARILLO, "Afecta a la carpeta y a TODO lo que contiene."),
    (r"\b(apt|apt-get|dnf|pacman|snap|flatpak)\s+(remove|purge|autoremove|uninstall|-R\w*)\b", AMARILLO,
     "Desinstala software; revisa la lista de paquetes que va a quitar antes de aceptar."),
    (r"\b(shutdown|reboot|poweroff|halt)\b", AMARILLO, "Apaga o reinicia el equipo: guarda tu trabajo antes."),
    (r"\b(kill|pkill|killall)\b.*(-9|-KILL)\b", AMARILLO, "Cierra a la fuerza: el programa no podrá guardar nada."),
    (r"\b(userdel|usermod|passwd|visudo|groupdel)\b", AMARILLO, "Cambia usuarios, grupos o contraseñas."),
    (r"\bgit\s+(reset\s+--hard|clean\s+-\w*f|push\s+(-f|--force))", AMARILLO, "Descarta o sobrescribe cambios de git sin recuperación."),
    (r"\bsudo\s+pip3?\s+install|--break-system-packages", AMARILLO, "Puede romper el Python del sistema; usa un entorno virtual (venv)."),
    (r"\bsystemctl\s+(stop|disable|mask)\b", AMARILLO, "Detiene o desactiva un servicio; algo puede dejar de funcionar."),
    (r"(^|[^>])>\s*[^\s>&]", AMARILLO, "El símbolo > sobrescribe el archivo de destino (usa >> para añadir)."),
    (r"\bsudo\b", AMARILLO, "Usa sudo: corre como administrador, revisa bien el comando."),
]


_CON_ARCHIVOS = {"rm", "cp", "mv", "mkdir", "rmdir", "touch", "cat", "less", "head", "tail", "nano", "vim",
                 "chmod", "chown", "ln", "du", "tar", "zip", "unzip", "cd", "ls", "find", "shred", "source", "bash", "sh"}


def _subir(actual, nuevo):
    return nuevo if _ORDEN[nuevo] > _ORDEN[actual] else actual


def analizar(comando):
    """Analiza un comando. Devuelve {'nivel', 'motivos', 'partes'}."""
    comando = (comando or "").strip().lstrip("$").strip()
    nivel, motivos = VERDE, []
    for patron, n, motivo in _REGLAS:
        if re.search(patron, comando):
            # 'sudo' solo cuenta si no hay ya un motivo más concreto
            if patron == r"\bsudo\b" and motivos:
                continue
            if all(motivo != m for _, m in motivos):
                motivos.append((n, motivo))
            nivel = _subir(nivel, n)
    # Si es rojo, solo se muestran los motivos graves (menos ruido)
    motivos = [m for n, m in motivos if n == nivel or nivel != ROJO]
    return {"nivel": nivel, "motivos": motivos, "partes": explicar_partes(comando)}


def explicar_partes(comando):
    """Lista de (token, explicación) para los tokens que sabemos explicar."""
    try:
        tokens = shlex.split(comando)
    except ValueError:
        tokens = comando.split()
    partes, programa, sub = [], None, None
    for tok in tokens:
        if tok in ("|", "&&", ";", "||"):
            partes.append((tok, {"|": "pasa la salida al siguiente comando", "&&": "si lo anterior salió bien, ejecuta lo siguiente",
                                 ";": "ejecuta lo siguiente pase lo que pase", "||": "si lo anterior falló, ejecuta lo siguiente"}[tok]))
            programa = None
            continue
        if programa is None or (programa == "sudo" and tok in PROGRAMAS):
            if tok in PROGRAMAS:
                partes.append((tok, PROGRAMAS[tok]))
                programa = tok
                continue
            if programa is None:
                programa = tok
                partes.append((tok, "el programa que se ejecuta"))
                continue
        opciones = OPCIONES.get(programa, {})
        if tok in opciones:
            partes.append((tok, opciones[tok]))
        elif tok.startswith("-") and len(tok) > 2 and not tok.startswith("--") and all(f"-{c}" in opciones for c in tok[1:]):
            partes.append((tok, " + ".join(opciones[f"-{c}"] for c in tok[1:])))
        elif tok.startswith("of=/dev/") or tok.startswith("if="):
            partes.append((tok, "dispositivo o archivo de entrada/salida"))
        elif not tok.startswith("-") and len(partes) < 12:
            if re.fullmatch(r"[~/.].*|.*\.\w{1,5}|.*/.*", tok):
                partes.append((tok, "el archivo o carpeta sobre el que actúa"))
            elif programa in ("apt", "apt-get", "snap", "flatpak", "dnf", "pacman", "pip", "pip3") and sub:
                partes.append((tok, "nombre del paquete"))
            elif programa == "systemctl" and sub:
                partes.append((tok, "nombre del servicio"))
            elif programa in ("kill",) and tok.isdigit():
                partes.append((tok, "PID: número que identifica al proceso"))
            elif programa in _CON_ARCHIVOS:
                partes.append((tok, "el archivo o carpeta sobre el que actúa"))
        if programa in OPCIONES and tok in OPCIONES[programa] and not tok.startswith("-"):
            sub = tok
    return partes


def a_markdown(comando, resultado=None):
    """Respuesta lista para el chat (formato de formato.md_a_html)."""
    r = resultado or analizar(comando)
    comando = comando.strip().lstrip("$").strip()
    lineas = [f"**{ETIQUETA[r['nivel']]}**"]
    if r["motivos"]:
        lineas += [("⚠️ " if r["nivel"] == ROJO else "- ") + m for m in r["motivos"]]
    else:
        lineas.append("No encontré nada que borre, formatee o cambie el sistema.")
    lineas += ["", f"`{comando}`"]
    for tok, exp in r["partes"]:
        lineas.append(f"- `{tok}`: {exp}")
    if r["nivel"] == ROJO:
        lineas += ["", "Mi consejo: no lo ejecutes si no sabes exactamente de dónde salió. Pregúntame qué querías lograr y buscamos una forma segura."]
    elif r["nivel"] == AMARILLO:
        lineas += ["", "Revisa bien las rutas y nombres antes de pulsar Enter."]
    return "\n".join(lineas)


# Detecta peticiones de análisis en el chat
_PATRON_PETICION = re.compile(
    r"^\s*(?:/riesgo|analiza(?:r|me)?(?:\s+este)?(?:\s+comando)?|(?:¿\s*)?es\s+seguro(?:\s+ejecutar)?)\s*:?\s*(.+?)\s*\??\s*$"
    r"|^\s*\$\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def peticion_analisis(texto):
    """Si el usuario pide analizar un comando, devuelve el comando; si no, None."""
    m = _PATRON_PETICION.match(texto or "")
    if not m:
        return None
    cmd = (m.group(1) or m.group(2) or "").strip().strip("`").strip()
    return cmd or None
