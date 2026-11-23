"""Planes de estudio, misiones verificadas y chats guardados (ligeros).

- Catálogo FIJO de temas → lecciones → misiones (curado, verificable).
- La IA solo elige qué temas y en qué orden según la meta del usuario (enfoque mixto).
- Las misiones se comprueban con código, nunca con la IA.
- Todo se guarda en JSON compacto en ~/.config/tux-assistant/ (pocos KB).
"""
import getpass
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

DIR = Path.home() / ".config" / "tux-assistant"
DIR_CHATS = DIR / "chats"
PROGRESO = DIR / "progreso.json"
PRACTICA = "~/tux-practica"
MAX_MENSAJES = 150      # por chat; lo más viejo se descarta
MAX_TEXTO = 4000        # caracteres por mensaje guardado
CHAT_LIBRE = "libre"      # cuaderno de preguntas «General»
CHAT_ERRORES = "errores"  # errores de la terminal (sección aparte)
CHAT_RAPIDAS = "rapidas"  # lo que se pregunta en modo rápido (clic en Tux) queda guardado aquí
# Puntos por misión según la dificultad del tema; el nivel de conocimiento sale de los puntos
XP_POR_DIFICULTAD = {"basico": 10, "avanzado": 25, "experto": 40, "maestro": 60}
NIVELES_CONOCIMIENTO = [  # (nombre, XP mínimo, descripción)
    ("Principiante", 0, "Estás conociendo la terminal"),
    ("Intermedio", 60, "Te mueves solo por el sistema"),
    ("Avanzado", 200, "Resuelves problemas sin ayuda"),
    ("Experto", 450, "Administras y automatizas el sistema"),
    ("Maestro", 800, "Entiendes Linux por dentro"),
    ("Arquitecto Linux", 1400, "Dominas el sistema completo: kernel, contenedores, VMs e IA"),
]
ESTILO_POR_NIVEL = ["principiante", "intermedio", "avanzado", "experto", "experto", "experto"]
DIFICULTAD_NOMBRE = {"basico": "Básico", "avanzado": "Avanzado", "experto": "Experto", "maestro": "Maestro"}

# ---------- Catálogo ----------
# Cada lección: id, titulo, objetivo (qué debe enseñar la IA), mision (texto) y check (verificación en código)
# check: ("existe", ruta, "dir"|"archivo") · ("no_existe", ruta) · ("permisos", ruta, "600")
#        ("contiene", ruta, regex) · ("ejecutable", ruta) · ("instalado", programa)
#        ("respuesta", clave)  → se compara la respuesta del usuario con el dato real del equipo
#        ("todos", [checks...])
TEMAS = {
    "terminal": {
        "dificultad": "basico", "nombre": "Primeros pasos en la terminal", "icono": "⌨️",
        "palabras": "terminal consola comandos basico empezar cero carpetas archivos navegar",
        "lecciones": [
            {"id": "t1", "titulo": "Moverte entre carpetas",
             "objetivo": "qué es la terminal, la carpeta actual, rutas absolutas y relativas; pwd, ls, cd, cd .., cd ~",
             "mision": f"Crea la carpeta `{PRACTICA}` con `mkdir` y entra en ella con `cd`.",
             "check": ("existe", PRACTICA, "dir")},
            {"id": "t2", "titulo": "Crear y leer archivos",
             "objetivo": "touch, echo con > y >>, cat, less; diferencia entre sobrescribir y añadir",
             "mision": f"Crea `{PRACTICA}/hola.txt` que contenga el texto «hola linux».",
             "check": ("contiene", f"{PRACTICA}/hola.txt", r"(?i)hola\s+linux")},
            {"id": "t3", "titulo": "Copiar, mover y borrar",
             "objetivo": "cp, mv (también para renombrar), rm y por qué no hay papelera en la terminal",
             "mision": f"Copia `hola.txt` como `copia.txt` y luego renombra `copia.txt` a `respaldo.txt` (todo en `{PRACTICA}`).",
             "check": ("todos", [("existe", f"{PRACTICA}/respaldo.txt", "archivo"), ("no_existe", f"{PRACTICA}/copia.txt")])},
            {"id": "t4", "titulo": "Pedir ayuda a Linux",
             "objetivo": "man, --help, cómo leer la sinopsis de un comando; type y which para saber si un comando existe antes de usarlo",
             "mision": f"Guarda la ayuda de `ls` en `{PRACTICA}/ayuda-ls.txt` con `ls --help > {PRACTICA}/ayuda-ls.txt`.",
             "check": ("contiene", f"{PRACTICA}/ayuda-ls.txt", r"--all")},
        ],
    },
    "permisos": {
        "dificultad": "basico", "nombre": "Archivos y permisos", "icono": "🔐",
        "palabras": "permisos chmod chown usuarios grupos seguridad ejecutar privado acceso denegado",
        "lecciones": [
            {"id": "p1", "titulo": "Leer permisos con ls -l",
             "objetivo": "usuario, grupo y otros; r, w, x; cómo leer -rw-r--r--; el comando whoami",
             "mision": "Usa `whoami` y escríbeme tu nombre de usuario.",
             "check": ("respuesta", "usuario")},
            {"id": "p2", "titulo": "chmod con números",
             "objetivo": "notación octal 4-2-1, ejemplos 600, 644, 755; por qué evitar 777",
             "mision": f"Crea `{PRACTICA}/secreto.txt` y déjalo para que SOLO tú puedas leerlo y escribirlo.",
             "check": ("permisos", f"{PRACTICA}/secreto.txt", "600")},
            {"id": "p3", "titulo": "Archivos ejecutables",
             "objetivo": "permiso x, chmod +x, por qué se ejecuta con ./ y qué es el shebang #!/bin/bash",
             "mision": f"Crea el script `{PRACTICA}/saludo.sh` (con un `echo` dentro) y hazlo ejecutable.",
             "check": ("todos", [("ejecutable", f"{PRACTICA}/saludo.sh"), ("contiene", f"{PRACTICA}/saludo.sh", r"echo")])},
            {"id": "p4", "titulo": "Carpetas privadas",
             "objetivo": "qué significa x en una carpeta, chmod 700, permisos de tu carpeta personal",
             "mision": f"Crea la carpeta `{PRACTICA}/privado` a la que solo tú puedas entrar.",
             "check": ("permisos", f"{PRACTICA}/privado", "700")},
        ],
    },
    "paquetes": {
        "dificultad": "basico", "nombre": "Instalar y gestionar programas", "icono": "📦",
        "palabras": "instalar programas paquetes apt snap flatpak software actualizar desinstalar repositorios",
        "lecciones": [
            {"id": "k1", "titulo": "Qué es un gestor de paquetes",
             "objetivo": "repositorios, apt update vs apt upgrade, por qué no descargar instaladores de internet",
             "mision": "¿Qué gestor de paquetes usa tu sistema? Escríbeme su nombre.",
             "check": ("respuesta", "gestor")},
            {"id": "k2", "titulo": "Instalar con apt",
             "objetivo": "sudo apt install, qué pide confirmar, apt show, dónde quedan los programas",
             "mision": "Instala el programa `tree` y pruébalo en tu carpeta de práctica.",
             "check": ("instalado", "tree")},
            {"id": "k3", "titulo": "Snap y Flatpak",
             "objetivo": "paquetes universales, snap list, flatpak list, ventajas y desventajas frente a apt",
             "mision": "¿Cuántos snaps tienes instalados? Usa `snap list` y escríbeme el número (sin contar la cabecera).",
             "check": ("respuesta", "snaps")},
            {"id": "k4", "titulo": "Buscar programas",
             "objetivo": "apt search, apt policy, cómo elegir el paquete correcto",
             "mision": "Busca e instala `ncdu`, un analizador de espacio en disco.",
             "check": ("instalado", "ncdu")},
        ],
    },
    "procesos": {
        "dificultad": "basico", "nombre": "Procesos y servicios", "icono": "⚙️",
        "palabras": "procesos servicios ram memoria cpu lento congelado matar cerrar systemctl logs rendimiento",
        "lecciones": [
            {"id": "s1", "titulo": "Ver memoria y procesos",
             "objetivo": "free -h, top/htop, qué es un proceso, RAM usada vs disponible",
             "mision": "¿Cuánta RAM total tiene tu equipo? Usa `free -h` y escríbeme los GB.",
             "check": ("respuesta", "ram_total_gb")},
            {"id": "s2", "titulo": "PID y señales",
             "objetivo": "qué es un PID, pgrep, kill y kill -9, cuándo usar cada uno",
             "mision": "¿Qué PID tiene `gnome-shell`? Usa `pgrep -o gnome-shell` y escríbeme el número.",
             "check": ("respuesta", "pid_gnome")},
            {"id": "s3", "titulo": "Servicios con systemctl",
             "objetivo": "qué es un servicio y systemd, systemctl status, is-active, enable vs start",
             "mision": "¿Está activo el servicio `bluetooth`? Revísalo con `systemctl is-active bluetooth` y respóndeme sí o no.",
             "check": ("respuesta", "bluetooth")},
            {"id": "s4", "titulo": "Leer los registros",
             "objetivo": "journalctl, -u, -b, -p err, cómo encontrar por qué falló algo",
             "mision": "¿Cuántos servicios fallidos tiene tu sistema? Usa `systemctl --failed` y escríbeme el número.",
             "check": ("respuesta", "fallidos")},
        ],
    },
    "redes": {
        "dificultad": "basico", "nombre": "Redes", "icono": "🌐",
        "palabras": "red redes internet wifi ip puertos conexion ping dns router servidor",
        "lecciones": [
            {"id": "r1", "titulo": "Tu dirección IP",
             "objetivo": "IP local vs pública, ip a, interfaces (lo, wlan, eth)",
             "mision": "¿Cuál es la IP local de tu equipo? Usa `ip -4 a` y escríbemela.",
             "check": ("respuesta", "ip_local")},
            {"id": "r2", "titulo": "Router y rutas",
             "objetivo": "puerta de enlace, ip route, ping y cómo diagnosticar «no tengo internet»",
             "mision": "¿Cuál es la IP de tu router (puerta de enlace)? Usa `ip route` y escríbemela.",
             "check": ("respuesta", "gateway")},
            {"id": "r3", "titulo": "Puertos abiertos",
             "objetivo": "qué es un puerto, ss -tln, qué significa LISTEN, por qué importa para la seguridad",
             "mision": "¿Cuántos puertos TCP están escuchando? Usa `ss -tlnH` y escríbeme cuántas líneas salen.",
             "check": ("respuesta", "puertos")},
        ],
    },
    "bash": {
        "dificultad": "basico", "nombre": "Scripts en Bash", "icono": "📜",
        "palabras": "scripts bash automatizar programar variables bucles condicionales shell",
        "lecciones": [
            {"id": "b1", "titulo": "Tu primer script",
             "objetivo": "shebang, echo, chmod +x, ejecutar con ./",
             "mision": f"Crea `{PRACTICA}/hola.sh` que imprima un saludo y hazlo ejecutable.",
             "check": ("todos", [("ejecutable", f"{PRACTICA}/hola.sh"), ("contiene", f"{PRACTICA}/hola.sh", r"echo")])},
            {"id": "b2", "titulo": "Variables y argumentos",
             "objetivo": "variables, comillas, $USER, $1, read",
             "mision": f"Crea `{PRACTICA}/variables.sh` que use al menos una variable (por ejemplo `$USER` o `$1`).",
             "check": ("contiene", f"{PRACTICA}/variables.sh", r"\$\{?\w+")},
            {"id": "b3", "titulo": "Condicionales",
             "objetivo": "if / then / else / fi, test con [ ], -f, -d, comparar números",
             "mision": f"Crea `{PRACTICA}/existe.sh` que use un `if` para comprobar si existe un archivo.",
             "check": ("contiene", f"{PRACTICA}/existe.sh", r"(?s)\bif\b.*\bfi\b")},
            {"id": "b4", "titulo": "Bucles",
             "objetivo": "for ... in ... do ... done, recorrer archivos, while",
             "mision": f"Crea `{PRACTICA}/bucle.sh` con un bucle `for`.",
             "check": ("contiene", f"{PRACTICA}/bucle.sh", r"(?s)\bfor\b.*\bdone\b")},
        ],
    },
    # ---------- Ruta de desarrollador / sysadmin (avanzado → maestro) ----------
    "texto": {
        "dificultad": "avanzado", "nombre": "Texto, tuberías y regex", "icono": "🧵",
        "palabras": "tuberias pipes grep sed awk regex expresiones texto logs filtrar xargs find desarrollador profesional experto",
        "lecciones": [
            {"id": "x1", "titulo": "Tuberías y redirecciones",
             "objetivo": "stdin, stdout, stderr, |, >, >>, 2>, 2>&1, tee; encadenar comandos",
             "mision": f"Guarda la lista de procesos (con `ps aux`) en `{PRACTICA}/procesos.txt` usando una redirección.",
             "check": ("contiene", f"{PRACTICA}/procesos.txt", r"PID")},
            {"id": "x2", "titulo": "grep y expresiones regulares",
             "objetivo": "grep -E, -c, -v, -o, anclas ^ $, clases [ ], cuantificadores; leer /etc/passwd",
             "mision": "¿Cuántas líneas de `/etc/passwd` terminan en `/bin/bash`? Cuéntalas con `grep -c` y escríbeme el número.",
             "check": ("respuesta", "bash_users")},
            {"id": "x3", "titulo": "awk y sed",
             "objetivo": "awk -F, $1, print; sed s/viejo/nuevo/g, -n, p; cuándo usar cada uno",
             "mision": f"Crea `{PRACTICA}/usuarios.txt` con SOLO los nombres de usuario de `/etc/passwd` (uno por línea, sin «:»).",
             "check": ("todos", [("contiene", f"{PRACTICA}/usuarios.txt", r"(?m)^root$"),
                                 ("no_contiene", f"{PRACTICA}/usuarios.txt", r":")])},
            {"id": "x4", "titulo": "find y xargs",
             "objetivo": "find por nombre, tipo, tamaño, fecha, -maxdepth, -exec, xargs -0, combinarlos con seguridad",
             "mision": "¿Cuántos archivos `.conf` hay directamente en `/etc` (sin subcarpetas)? Usa `find` con `-maxdepth 1` y escríbeme el número.",
             "check": ("respuesta", "etc_conf")},
        ],
    },
    "dev": {
        "dificultad": "avanzado", "nombre": "Entorno de desarrollador", "icono": "🛠️",
        "palabras": "desarrollador programar git python venv compilar gcc make path variables entorno codigo profesional",
        "lecciones": [
            {"id": "d1", "titulo": "PATH y tus propios comandos",
             "objetivo": "qué es PATH, export, ~/.bashrc, ~/.local/bin, which, type, alias vs script",
             "mision": f"Crea el script ejecutable `{PRACTICA}/bin/tux-hola` (con shebang y un `echo`).",
             "check": ("todos", [("ejecutable", f"{PRACTICA}/bin/tux-hola"), ("contiene", f"{PRACTICA}/bin/tux-hola", r"^#!")])},
            {"id": "d2", "titulo": "Git desde la terminal",
             "objetivo": "git init, add, commit, log, status, .gitignore, ramas; flujo básico de trabajo",
             "mision": f"Crea un repositorio en `{PRACTICA}/proyecto` con al menos un commit.",
             "check": ("salida", ["git", "-C", f"{PRACTICA}/proyecto", "rev-list", "--count", "HEAD"], r"^[1-9]")},
            {"id": "d3", "titulo": "Entornos virtuales de Python",
             "objetivo": "python3 -m venv, activate, pip dentro del venv, por qué no usar sudo pip",
             "mision": f"Crea un entorno virtual en `{PRACTICA}/venv`.",
             "check": ("ejecutable", f"{PRACTICA}/venv/bin/python")},
            {"id": "d4", "titulo": "Compilar desde el código fuente",
             "objetivo": "gcc, build-essential, compilar y enlazar, ./programa, qué hace make",
             "mision": f"Escribe `{PRACTICA}/hola.c` y compílalo a `{PRACTICA}/hola` con `gcc`.",
             "check": ("todos", [("contiene", f"{PRACTICA}/hola.c", r"main"), ("ejecutable", f"{PRACTICA}/hola")])},
        ],
    },
    "seguridad": {
        "dificultad": "avanzado", "nombre": "Seguridad del sistema", "icono": "🛡️",
        "palabras": "seguridad ssh claves firewall ufw suid permisos especiales puertos hacker proteger servidor experto",
        "lecciones": [
            {"id": "z1", "titulo": "Claves SSH",
             "objetivo": "criptografía de clave pública, ssh-keygen -t ed25519, clave privada vs .pub, ssh-copy-id, permisos de ~/.ssh",
             "mision": "Genera un par de claves SSH con `ssh-keygen -t ed25519` (Tux solo comprueba que exista la clave PÚBLICA).",
             "check": ("glob", "~/.ssh/*.pub")},
            {"id": "z2", "titulo": "SUID, SGID y sticky bit",
             "objetivo": "permisos especiales, la s en ls -l, por qué passwd la necesita, sticky bit en /tmp, riesgos",
             "mision": "Mira `ls -l /usr/bin/passwd`. ¿Qué letra especial aparece en los permisos del dueño? Escríbemela.",
             "check": ("respuesta_fija", r"(^|\W)s(\W|$)|suid|setuid")},
            {"id": "z3", "titulo": "Firewall con ufw",
             "objetivo": "qué filtra un firewall, ufw status, allow/deny, reglas por puerto, por qué importa en un servidor",
             "mision": "¿Está activo el servicio `ufw` en tu equipo? Revísalo con `systemctl is-active ufw` y respóndeme sí o no.",
             "check": ("respuesta", "ufw")},
            {"id": "z4", "titulo": "Superficie de ataque",
             "objetivo": "puertos escuchando en 0.0.0.0 vs 127.0.0.1, ss -tlnp, qué servicio está detrás, cómo cerrarlo",
             "mision": "¿Cuántos puertos TCP escuchan en TODAS las interfaces (0.0.0.0, [::] o *)? Míralo con `ss -tlnH` y escríbeme el número.",
             "check": ("respuesta", "puertos_publicos")},
        ],
    },
    "sistema": {
        "dificultad": "experto", "nombre": "systemd a fondo", "icono": "🧩",
        "palabras": "systemd unidades servicios timers cron arranque journal automatizar sysadmin administrador experto",
        "lecciones": [
            {"id": "y1", "titulo": "Escribir tu propio servicio",
             "objetivo": "anatomía de una unidad .service: [Unit], [Service], [Install], ExecStart, Type; unidades de usuario en ~/.config/systemd/user",
             "mision": "Crea `~/.config/systemd/user/tux-hola.service` con una sección `[Service]` y un `ExecStart=`.",
             "check": ("todos", [("contiene", "~/.config/systemd/user/tux-hola.service", r"\[Service\]"),
                                 ("contiene", "~/.config/systemd/user/tux-hola.service", r"ExecStart=")])},
            {"id": "y2", "titulo": "Timers (el cron moderno)",
             "objetivo": "unidades .timer, OnCalendar, OnBootSec, OnUnitActiveSec, Persistent; systemd-analyze calendar",
             "mision": "Crea `~/.config/systemd/user/tux-hola.timer` que active el servicio (con `OnCalendar=` u `OnUnitActiveSec=`).",
             "check": ("contiene", "~/.config/systemd/user/tux-hola.timer", r"On(Calendar|UnitActiveSec|BootSec)=")},
            {"id": "y3", "titulo": "Activar y depurar unidades",
             "objetivo": "systemctl --user daemon-reload, enable --now, list-timers, status, journalctl --user -u",
             "mision": "Activa tu timer con `systemctl --user enable --now tux-hola.timer`.",
             "check": ("salida", ["systemctl", "--user", "is-enabled", "tux-hola.timer"], r"enabled")},
            {"id": "y4", "titulo": "El journal como un profesional",
             "objetivo": "journalctl --list-boots, -b -1, -p err, --since, -o json, persistencia del journal",
             "mision": "¿Cuántos arranques registra tu journal? Usa `journalctl --list-boots` y escríbeme el número.",
             "check": ("respuesta", "arranques")},
        ],
    },
    "kernel": {
        "dificultad": "experto", "nombre": "Kernel y hardware", "icono": "🧠",
        "palabras": "kernel modulos hardware proc sys sysctl drivers dmesg arranque nucleo experto profundo",
        "lecciones": [
            {"id": "n1", "titulo": "El kernel y sus versiones",
             "objetivo": "qué hace el kernel, espacio de usuario vs kernel, uname -a, versiones y por qué se actualiza",
             "mision": "¿Cuál es la versión exacta de tu kernel? Usa `uname -r` y escríbemela.",
             "check": ("respuesta", "kernel")},
            {"id": "n2", "titulo": "Módulos (drivers)",
             "objetivo": "lsmod, modinfo, modprobe, /etc/modprobe.d, blacklist, drivers de la GPU",
             "mision": "¿Cuántos módulos del kernel están cargados? Cuéntalos con `lsmod` (sin la cabecera) y escríbeme el número.",
             "check": ("respuesta", "modulos")},
            {"id": "n3", "titulo": "/proc, /sys y sysctl",
             "objetivo": "sistemas de archivos virtuales, /proc/cpuinfo, /proc/meminfo, /sys/class, sysctl y /etc/sysctl.d",
             "mision": "¿Qué valor tiene `vm.swappiness` en tu sistema? Míralo con `sysctl vm.swappiness` y escríbeme el número.",
             "check": ("respuesta", "swappiness")},
            {"id": "n4", "titulo": "Discos a bajo nivel",
             "objetivo": "dispositivos de bloque, /sys/block, planificadores de E/S, lsblk -f, UUID y /etc/fstab",
             "mision": "¿Qué planificador de E/S usa tu disco principal? Míralo en `/sys/block/<disco>/queue/scheduler` (el que está entre [ ]).",
             "check": ("respuesta", "planificador")},
        ],
    },
    "contenedores": {
        "dificultad": "maestro", "nombre": "Contenedores (Docker)", "icono": "🐳",
        "palabras": "docker contenedores imagenes dockerfile podman despliegue devops servidor desarrollador maestro",
        "lecciones": [
            {"id": "o1", "titulo": "Imágenes y contenedores",
             "objetivo": "imagen vs contenedor, capas, docker images, docker ps -a, el grupo docker y su riesgo",
             "mision": "¿Cuántas imágenes de Docker tienes? Usa `docker images -q` y escríbeme el número.",
             "check": ("respuesta", "docker_imagenes")},
            {"id": "o2", "titulo": "Tu primer contenedor",
             "objetivo": "docker run, --rm, -it, -p, -v, logs, stop; qué pasa por dentro",
             "mision": "Ejecuta el contenedor de prueba `hello-world`.",
             "check": ("salida", ["docker", "ps", "-a", "--filter", "ancestor=hello-world", "-q"], r"\w")},
            {"id": "o3", "titulo": "Escribir un Dockerfile",
             "objetivo": "FROM, RUN, COPY, WORKDIR, CMD, buenas prácticas y .dockerignore",
             "mision": f"Crea `{PRACTICA}/app/Dockerfile` que empiece con `FROM`.",
             "check": ("contiene", f"{PRACTICA}/app/Dockerfile", r"(?m)^\s*FROM\s+\S+")},
            {"id": "o4", "titulo": "Construir tu imagen",
             "objetivo": "docker build -t, etiquetas, caché de capas, docker history, tamaño de imagen",
             "mision": "Construye tu imagen con la etiqueta `tux-app` (`docker build -t tux-app …`).",
             "check": ("salida", ["docker", "images", "-q", "tux-app"], r"\w")},
        ],
    },
    "rendimiento": {
        "dificultad": "maestro", "nombre": "Depuración y rendimiento", "icono": "🔬",
        "palabras": "rendimiento depurar strace lsof perf lento cuello botella diagnostico optimizar maestro experto",
        "lecciones": [
            {"id": "q1", "titulo": "strace: ver las llamadas al sistema",
             "objetivo": "syscalls, strace -o, -e trace=open,execve, -f, leer una traza",
             "mision": f"Guarda una traza de `ls` con `strace -o {PRACTICA}/traza.txt ls`.",
             "check": ("contiene", f"{PRACTICA}/traza.txt", r"execve\(")},
            {"id": "q2", "titulo": "¿Quién usa ese puerto?",
             "objetivo": "ss -tlnp, lsof -i, fuser; de un puerto a un proceso y a su servicio",
             "mision": "¿Qué programa escucha en el puerto 11434? Averígualo con `ss -tlnp` y escríbeme su nombre.",
             "check": ("respuesta", "puerto_11434")},
            {"id": "q3", "titulo": "Carga del sistema",
             "objetivo": "load average, qué significa respecto a los núcleos, uptime, vmstat, iowait",
             "mision": "¿Cuál es tu carga media del último minuto? Mírala con `uptime` y escríbeme el número.",
             "check": ("respuesta", "carga")},
            {"id": "q4", "titulo": "Espacio en disco al detalle",
             "objetivo": "df -h vs du -sh, inodos (df -i), ncdu, archivos borrados aún abiertos (lsof +L1)",
             "mision": "¿Cuántos GB libres tiene tu partición raíz `/`? Míralo con `df -h /` y escríbeme el número.",
             "check": ("respuesta", "libre_raiz")},
        ],
    },
    # ---------- Más allá de Linux básico: personalización, virtualización e IA ----------
    "personalizacion": {
        "dificultad": "avanzado", "nombre": "Personaliza tu escritorio", "icono": "🎨",
        "palabras": "personalizar personalizacion escritorio gnome temas extensiones alias dotfiles prompt atajos apariencia",
        "lecciones": [
            {"id": "e1", "titulo": "Alias y tu shell a tu medida",
             "objetivo": "alias, ~/.bash_aliases, ~/.bashrc, source, funciones de bash, PS1 y prompts como starship",
             "mision": "Crea al menos un alias en `~/.bash_aliases` (por ejemplo `alias ll='ls -lah'`).",
             "check": ("contiene", "~/.bash_aliases", r"(?m)^\s*alias\s+[\w.-]+=")},
            {"id": "e2", "titulo": "gsettings: el registro de GNOME",
             "objetivo": "gsettings get/set/list-recursively, dconf, esquemas, cambiar tema e iconos desde la terminal",
             "mision": "¿Qué tema GTK usas? Míralo con `gsettings get org.gnome.desktop.interface gtk-theme` y escríbemelo.",
             "check": ("respuesta", "gtk_theme")},
            {"id": "e3", "titulo": "Extensiones de GNOME",
             "objetivo": "gnome-extensions list/enable/disable/info, dónde viven (~/.local/share/gnome-shell/extensions), riesgos",
             "mision": "¿Cuántas extensiones de GNOME tienes activas? Usa `gnome-extensions list --enabled` y escríbeme el número.",
             "check": ("respuesta", "extensiones")},
            {"id": "e4", "titulo": "Tus propios lanzadores",
             "objetivo": "archivos .desktop, [Desktop Entry], Exec, Icon, Terminal, ~/.local/share/applications",
             "mision": "Crea `~/.local/share/applications/tux-practica.desktop` con una sección `[Desktop Entry]` y una línea `Exec=`.",
             "check": ("todos", [("contiene", "~/.local/share/applications/tux-practica.desktop", r"\[Desktop Entry\]"),
                                 ("contiene", "~/.local/share/applications/tux-practica.desktop", r"(?m)^Exec=")])},
        ],
    },
    "virtualizacion": {
        "dificultad": "maestro", "nombre": "Máquinas virtuales (KVM)", "icono": "🖥️",
        "palabras": "maquinas virtuales vm virtualizacion kvm qemu virt-manager virtualbox hipervisor maestro",
        "lecciones": [
            {"id": "v1", "titulo": "¿Tu CPU puede virtualizar?",
             "objetivo": "virtualización por hardware (VT-x/AMD-V), flags vmx/svm en /proc/cpuinfo, BIOS/UEFI",
             "mision": "Cuenta las líneas con `vmx` o `svm` en `/proc/cpuinfo` (`grep -E -c 'vmx|svm' /proc/cpuinfo`) y escríbeme el número.",
             "check": ("respuesta", "virt_cpu")},
            {"id": "v2", "titulo": "KVM: el hipervisor del kernel",
             "objetivo": "qué es un hipervisor, módulos kvm y kvm_intel/kvm_amd, /dev/kvm, grupo kvm",
             "mision": "¿Está cargado el módulo `kvm`? Revísalo con `lsmod | grep kvm` y respóndeme sí o no.",
             "check": ("respuesta", "kvm")},
            {"id": "v3", "titulo": "QEMU y virt-manager",
             "objetivo": "QEMU emula/virtualiza, libvirt organiza, virt-manager es la interfaz; instalar qemu-system",
             "mision": "Ten instalado QEMU (`qemu-system-x86_64`). Si no está: `sudo apt install qemu-system-x86`.",
             "check": ("instalado", "qemu-system-x86_64")},
            {"id": "v4", "titulo": "Discos virtuales",
             "objetivo": "imágenes qcow2 vs raw, crecimiento dinámico, snapshots, qemu-img create/info",
             "mision": f"Crea un disco virtual de 2G: `qemu-img create -f qcow2 {PRACTICA}/vm/disco.qcow2 2G` (crece solo, casi no ocupa).",
             "check": ("salida", ["qemu-img", "info", f"{PRACTICA}/vm/disco.qcow2"], r"file format: qcow2")},
        ],
    },
    "ia": {
        "dificultad": "maestro", "nombre": "IA local en Linux", "icono": "🤖",
        "palabras": "ia inteligencia artificial ollama modelos llm gpu cuda nvidia machine learning python api maestro",
        "lecciones": [
            {"id": "a1", "titulo": "Modelos locales con Ollama",
             "objetivo": "qué es un LLM, ollama list/run/pull/rm, tamaño y cuantización (q4_K_M), por qué local = privado",
             "mision": "¿Cuántos modelos tienes en Ollama? Usa `ollama list` y escríbeme el número.",
             "check": ("respuesta", "modelos_ollama")},
            {"id": "a2", "titulo": "La GPU y la VRAM",
             "objetivo": "nvidia-smi, VRAM vs RAM, por qué un modelo grande va lento si no cabe en la GPU, drivers y CUDA",
             "mision": "¿Cuántos MiB de VRAM tiene tu GPU en total? Míralo con `nvidia-smi` y escríbeme el número.",
             "check": ("respuesta", "vram")},
            {"id": "a3", "titulo": "Crea tu propio modelo",
             "objetivo": "Modelfile: FROM, SYSTEM, PARAMETER temperature; ollama create; cómo funciona Tux por dentro",
             "mision": f"Escribe `{PRACTICA}/ia/Modelfile` que empiece con `FROM` y tenga un `SYSTEM`.",
             "check": ("todos", [("contiene", f"{PRACTICA}/ia/Modelfile", r"(?m)^\s*FROM\s+\S+"),
                                 ("contiene", f"{PRACTICA}/ia/Modelfile", r"(?mi)^\s*SYSTEM\b")])},
            {"id": "a4", "titulo": "Habla con la IA desde código",
             "objetivo": "la API REST de Ollama en localhost:11434, /api/chat, JSON, requests en Python o curl",
             "mision": f"Crea `{PRACTICA}/ia/preguntar.py` que llame a la API de Ollama (debe usar `11434` y `/api/`).",
             "check": ("todos", [("contiene", f"{PRACTICA}/ia/preguntar.py", r"11434"),
                                 ("contiene", f"{PRACTICA}/ia/preguntar.py", r"/api/")])},
        ],
    },
}

# Los temas van de básico a maestro (las rutas se recorren en este orden)
_ORDEN_DIFICULTAD = {"basico": 0, "avanzado": 1, "experto": 2, "maestro": 3}
TEMAS = dict(sorted(TEMAS.items(), key=lambda kv: _ORDEN_DIFICULTAD[kv[1].get("dificultad", "basico")]))
# Nombre visible de cada estilo de explicación (la clave interna es la que usa pedagogia.py)
NOMBRE_ESTILO = {"principiante": "Paso a paso", "intermedio": "Explicado", "avanzado": "Al grano", "experto": "Técnico a fondo"}

LECCIONES = {l["id"]: dict(l, tema=t) for t, d in TEMAS.items() for l in d["lecciones"]}


# ---------- Datos reales para las misiones de respuesta ----------

def _salida(args):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=4, env={**os.environ, "LC_ALL": "C"})
        return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _ram_gb():
    try:
        with open("/proc/meminfo") as f:
            kb = int(re.search(r"MemTotal:\s+(\d+)", f.read()).group(1))
        return kb / 1024 / 1024
    except (OSError, AttributeError):
        return None


def dato_real(clave):
    """Valor real del equipo para comparar con la respuesta del usuario."""
    if clave == "nucleos":
        return str(os.cpu_count())
    if clave == "usuario":
        return getpass.getuser()
    if clave == "gestor":
        return next((g for g in ("apt", "dnf", "pacman", "zypper") if shutil.which(g)), "")
    if clave == "snaps":
        lineas = _salida(["snap", "list"]).splitlines()
        return str(max(len(lineas) - 1, 0))
    if clave == "ram_total_gb":
        gb = _ram_gb()
        return f"{gb:.1f}" if gb else ""
    if clave == "pid_gnome":
        return _salida(["pgrep", "-o", "gnome-shell"])
    if clave == "bluetooth":
        return "sí" if _salida(["systemctl", "is-active", "bluetooth"]) == "active" else "no"
    if clave == "fallidos":
        return str(len([l for l in _salida(["systemctl", "--failed", "--no-legend", "--plain"]).splitlines() if l.strip()]))
    if clave == "ip_local":
        m = re.search(r"\bsrc (\S+)", _salida(["ip", "-4", "route", "get", "1.1.1.1"]))
        return m.group(1) if m else ""
    if clave == "gateway":
        m = re.search(r"default via (\S+)", _salida(["ip", "route", "show", "default"]))
        return m.group(1) if m else ""
    if clave == "puertos":
        return str(len([l for l in _salida(["ss", "-tlnH"]).splitlines() if l.strip()]))
    if clave == "puertos_publicos":
        return str(len([l for l in _salida(["ss", "-tlnH"]).splitlines()
                        if re.search(r"\s(0\.0\.0\.0|\[::\]|\*):\d+", l)]))
    if clave == "bash_users":
        try:
            return str(sum(1 for l in open("/etc/passwd") if l.rstrip().endswith("/bin/bash")))
        except OSError:
            return ""
    if clave == "etc_conf":
        try:
            return str(sum(1 for f in os.listdir("/etc") if f.endswith(".conf") and os.path.isfile("/etc/" + f)))
        except OSError:
            return ""
    if clave == "ufw":
        return "sí" if _salida(["systemctl", "is-active", "ufw"]) == "active" else "no"
    if clave == "arranques":
        return str(len([l for l in _salida(["journalctl", "--list-boots", "--no-pager"]).splitlines()
                        if re.match(r"\s*-?\d+\s", l)]))
    if clave == "kernel":
        return os.uname().release
    if clave == "modulos":
        try:
            return str(sum(1 for _ in open("/proc/modules")))
        except OSError:
            return ""
    if clave == "swappiness":
        try:
            return open("/proc/sys/vm/swappiness").read().strip()
        except OSError:
            return ""
    if clave == "planificador":
        raiz = _salida(["findmnt", "-no", "SOURCE", "/"])
        m = re.search(r"/dev/(nvme\d+n\d+|[shv]d[a-z]|mmcblk\d+)", raiz)
        if m:
            try:
                return re.search(r"\[(\S+)\]", open(f"/sys/block/{m.group(1)}/queue/scheduler").read()).group(1)
            except (OSError, AttributeError):
                return ""
        return ""
    if clave == "docker_imagenes":
        if not shutil.which("docker"):
            return ""
        salida = _salida(["docker", "images", "-q"])
        return str(len(set(salida.split()))) if salida or _salida(["docker", "info", "--format", "{{.ID}}"]) else ""
    if clave == "puerto_11434":
        m = re.search(r'users:\(\("([^"]+)"', _salida(["ss", "-tlnpH", "sport = :11434"]))
        return m.group(1) if m else ""
    if clave == "carga":
        return f"{os.getloadavg()[0]:.2f}"
    if clave == "gtk_theme":
        return _salida(["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"]).strip("'")
    if clave == "extensiones":
        lineas = [l for l in _salida(["gnome-extensions", "list", "--enabled"]).splitlines() if l.strip()]
        return str(len(lineas)) if lineas else ""
    if clave == "virt_cpu":
        try:
            return str(sum(1 for l in open("/proc/cpuinfo") if re.search(r"\b(vmx|svm)\b", l)))
        except OSError:
            return ""
    if clave == "kvm":
        try:
            return "sí" if any(l.startswith("kvm") for l in open("/proc/modules")) else "no"
        except OSError:
            return ""
    if clave == "modelos_ollama":
        lineas = _salida(["ollama", "list"]).splitlines()
        return str(max(len(lineas) - 1, 0)) if lineas else ""
    if clave == "vram":
        return _salida(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"]).split("\n")[0].strip()
    if clave == "libre_raiz":
        st = os.statvfs("/")
        return f"{st.f_bavail * st.f_frsize / 1024 ** 3:.1f}"
    return ""


_TOLERANCIA = {"vram": 64, "extensiones": 1, "ram_total_gb": 1.5, "puertos": 1, "puertos_publicos": 1, "modulos": 5, "carga": 1.0,
               "libre_raiz": 3, "docker_imagenes": 1}


def comparar_respuesta(clave, texto):
    """(acierto, valor_real)."""
    real = dato_real(clave)
    if not real:
        return True, "(no pude medirlo, te lo doy por bueno)"
    t = (texto or "").lower()
    if clave in ("bluetooth", "ufw", "kvm"):
        dijo_si = bool(re.search(r"\b(s[ií]|activo|active|yes)\b", t)) and not re.search(r"\b(no|inactivo|inactive)\b", t)
        return dijo_si == (real == "sí"), real
    if clave in ("nucleos", "snaps", "ram_total_gb", "pid_gnome", "fallidos", "puertos", "puertos_publicos",
                 "bash_users", "etc_conf", "arranques", "modulos", "swappiness", "docker_imagenes", "carga", "libre_raiz",
                 "extensiones", "virt_cpu", "modelos_ollama", "vram"):
        numeros = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", t)]
        tol = _TOLERANCIA.get(clave, 0)
        return any(abs(n - float(real)) <= tol for n in numeros), real
    return real.lower() in t, real


# ---------- Verificación de misiones ----------

def _ruta(r):
    return Path(os.path.expanduser(r))


def verificar(check, respuesta=""):
    """Devuelve (ok, detalle). detalle explica qué falta si no está bien."""
    tipo = check[0]
    if tipo == "todos":
        for sub in check[1]:
            ok, det = verificar(sub, respuesta)
            if not ok:
                return False, det
        return True, ""
    if tipo == "existe":
        p = _ruta(check[1])
        ok = p.is_dir() if check[2] == "dir" else p.is_file()
        return ok, "" if ok else f"No encuentro `{check[1]}` ({'carpeta' if check[2] == 'dir' else 'archivo'})."
    if tipo == "no_existe":
        ok = not _ruta(check[1]).exists()
        return ok, "" if ok else f"`{check[1]}` todavía existe."
    if tipo == "permisos":
        p = _ruta(check[1])
        if not p.exists():
            return False, f"No encuentro `{check[1]}`."
        actual = oct(p.stat().st_mode & 0o777)[2:]
        return actual == check[2], "" if actual == check[2] else f"Tiene permisos {actual}; deberían quedar en {check[2]}."
    if tipo == "contiene":
        p = _ruta(check[1])
        if not p.is_file():
            return False, f"No encuentro el archivo `{check[1]}`."
        try:
            ok = bool(re.search(check[2], p.read_text(encoding="utf-8", errors="ignore")[:20000]))
        except OSError:
            return False, f"No pude leer `{check[1]}`."
        return ok, "" if ok else f"`{check[1]}` existe, pero no tiene lo que pide la misión."
    if tipo == "no_contiene":
        p = _ruta(check[1])
        try:
            ok = p.is_file() and not re.search(check[2], p.read_text(encoding="utf-8", errors="ignore")[:20000])
        except OSError:
            ok = False
        return ok, "" if ok else f"`{check[1]}` todavía tiene algo que no debería."
    if tipo == "glob":
        import glob
        ok = bool(glob.glob(os.path.expanduser(check[1])))
        return ok, "" if ok else "Todavía no encuentro lo que pide la misión."
    if tipo == "salida":
        args = [os.path.expanduser(a) for a in check[1]]
        ok = bool(re.search(check[2], _salida(args)))
        return ok, "" if ok else "Lo revisé en tu equipo y todavía no está hecho."
    if tipo == "respuesta_fija":
        ok = bool(re.search(check[1], (respuesta or "").strip().lower()))
        return ok, "" if ok else "Esa no es. Vuelve a mirar la salida del comando con calma."
    if tipo == "ejecutable":
        p = _ruta(check[1])
        if not p.is_file():
            return False, f"No encuentro `{check[1]}`."
        ok = os.access(p, os.X_OK)
        return ok, "" if ok else f"`{check[1]}` existe pero aún no es ejecutable."
    if tipo == "instalado":
        ok = shutil.which(check[1]) is not None
        return ok, "" if ok else f"`{check[1]}` todavía no está instalado."
    if tipo == "respuesta":
        ok, real = comparar_respuesta(check[1], respuesta)
        return ok, "" if ok else "Esa no es la respuesta que veo en tu equipo. Revisa la salida del comando con calma."
    return False, "Misión desconocida."


def es_mision_de_respuesta(leccion):
    return leccion["check"][0] in ("respuesta", "respuesta_fija")


# ---------- Progreso y planes ----------

def _leer_json(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def _escribir_json(ruta, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, ruta)


def cargar_progreso():
    p = _leer_json(PROGRESO, {})
    p.setdefault("completadas", [])
    p.setdefault("saltadas", [])
    p.setdefault("planes", {})
    p.setdefault("cuadernos", {CHAT_LIBRE: {"nombre": "General"}})
    p["cuadernos"].setdefault(CHAT_LIBRE, {"nombre": "General"})
    # v2: cada ruta lleva SU progreso y SUS misiones (las rutas son independientes)
    for plan in p["planes"].values():
        if "completadas" not in plan:
            plan["completadas"] = [l for l in plan["lecciones"] if l in p["completadas"]]
            plan["saltadas"] = [l for l in plan["lecciones"] if l in p["saltadas"]]
        plan.setdefault("saltadas", [])
        plan.setdefault("misiones", {})   # lid → {"mision": texto, "check": [...]} creada por la IA para esta ruta
        plan.setdefault("vistas", [])     # lecciones ya explicadas (no se repite la explicación ni la misión)
    if not p.get("v2"):
        en_planes = {l for pl in p["planes"].values() for l in pl["completadas"]}
        p["completadas"] = [l for l in p["completadas"] if l not in en_planes]  # lo de fuera de rutas sigue sumando XP
        p["saltadas"] = []
        p["v2"] = True
    return p


def guardar_progreso(p):
    _escribir_json(PROGRESO, p)


def crear_plan(progreso, nombre, meta, temas, lecciones=None):
    """Crea un plan con las lecciones de los temas elegidos (en orden). Devuelve su id.

    lecciones: lista explícita (p. ej. un repaso que empieza en una lección concreta).
    """
    temas = [t for t in temas if t in TEMAS] or ["terminal"]
    if not lecciones:
        lecciones = [l["id"] for t in temas for l in TEMAS[t]["lecciones"]]
    pid = f"plan{int(time.time() * 1000)}"
    while pid in progreso["planes"]:  # id único aunque se creen dos rutas en el mismo instante
        pid += "x"
    progreso["planes"][pid] = {"nombre": nombre[:40], "meta": meta[:200], "temas": temas, "lecciones": lecciones,
                               "completadas": [], "saltadas": [], "misiones": {}, "vistas": []}
    guardar_progreso(progreso)
    return pid


def borrar_plan(progreso, pid):
    plan = progreso["planes"].pop(pid, None)
    if plan:  # el XP ganado se conserva aunque se borre la ruta
        progreso["xp_planes_borrados"] = progreso.get("xp_planes_borrados", 0) + \
            sum(xp_leccion(l) for l in plan.get("completadas", []) if l in LECCIONES)
    guardar_progreso(progreso)
    try:
        (DIR_CHATS / f"{pid}.json").unlink()
    except OSError:
        pass


def leccion_actual(progreso, pid):
    """(leccion, indice_1_based, total) o (None, total, total) si terminó."""
    plan = progreso["planes"].get(pid)
    if not plan:
        return None, 0, 0
    hechas = set(plan.get("completadas", [])) | set(plan.get("saltadas", []))
    for i, lid in enumerate(plan["lecciones"], 1):
        if lid not in hechas:
            return leccion_de_plan(plan, lid), i, len(plan["lecciones"])
    n = len(plan["lecciones"])
    return None, n, n


def leccion_de_plan(plan, lid):
    """La lección del catálogo con la misión PROPIA de esta ruta (si la IA ya la creó)."""
    leccion = dict(LECCIONES[lid])
    propia = plan.get("misiones", {}).get(lid)
    if propia:
        leccion["mision"] = propia["mision"]
        if propia.get("pasos"):
            leccion["pasos"] = propia["pasos"]
            leccion["check"] = ("todos", [p["check"] for p in propia["pasos"]])
        else:
            leccion["check"] = _a_tupla(propia["check"])
        leccion["mision_propia"] = True
    return leccion


def pasos_hechos(plan, lid):
    return set(plan.setdefault("pasos_ok", {}).get(lid, []))


def marcar_paso(progreso, pid, lid, indice):
    plan = progreso["planes"].get(pid)
    if plan is not None:
        hechos = plan.setdefault("pasos_ok", {}).setdefault(lid, [])
        if indice not in hechos:
            hechos.append(indice)
            guardar_progreso(progreso)


def _a_tupla(check):
    """Los checks guardados en JSON vuelven como listas; verificar() trabaja igual con tuplas."""
    if isinstance(check, list):
        return tuple(_a_tupla(c) if isinstance(c, list) and c and isinstance(c[0], (list, str)) and c[0] in
                     ("existe", "no_existe", "permisos", "contiene", "no_contiene", "ejecutable", "instalado",
                      "respuesta", "respuesta_fija", "glob", "salida", "todos") else c for c in check)
    return check


def marcar(progreso, lid, saltada=False, pid=None):
    """Marca la lección como hecha (o saltada) EN ESA RUTA; sin pid cuenta fuera de rutas."""
    base = progreso["planes"].get(pid) if pid else progreso
    lista = base.setdefault("saltadas" if saltada else "completadas", [])
    if lid not in lista:
        lista.append(lid)
    guardar_progreso(progreso)


def marcar_vista(progreso, pid, lid):
    plan = progreso["planes"].get(pid)
    if plan is not None and lid not in plan.setdefault("vistas", []):
        plan["vistas"].append(lid)
        guardar_progreso(progreso)


def completadas_todas(progreso):
    """Lecciones hechas en cualquier ruta (para el avance por temas)."""
    hechas = set(progreso["completadas"])
    for plan in progreso["planes"].values():
        hechas |= set(plan.get("completadas", []))
    return hechas


def xp_leccion(lid):
    return XP_POR_DIFICULTAD[TEMAS[LECCIONES[lid]["tema"]].get("dificultad", "basico")]


def xp_total(progreso):
    """Cada misión de cada ruta suma su XP (las rutas son independientes)."""
    total = sum(xp_leccion(l) for l in progreso["completadas"] if l in LECCIONES)
    for plan in progreso["planes"].values():
        total += sum(xp_leccion(l) for l in plan.get("completadas", []) if l in LECCIONES)
    return total + progreso.get("xp_planes_borrados", 0)


def nivel_conocimiento(xp):
    """(indice, nombre, descripcion, xp_del_nivel, xp_del_siguiente o None)."""
    idx = max(i for i, (_, minimo, _) in enumerate(NIVELES_CONOCIMIENTO) if xp >= minimo)
    nombre, minimo, desc = NIVELES_CONOCIMIENTO[idx]
    siguiente = NIVELES_CONOCIMIENTO[idx + 1][1] if idx + 1 < len(NIVELES_CONOCIMIENTO) else None
    return idx, nombre, desc, minimo, siguiente


def estilo_sugerido(progreso, estilo_actual):
    """Autonomía progresiva: al subir de nivel de conocimiento, Tux explica menos lo básico. None si no toca."""
    orden = ["principiante", "intermedio", "avanzado", "experto"]
    objetivo = ESTILO_POR_NIVEL[nivel_conocimiento(xp_total(progreso))[0]]
    actual = estilo_actual if estilo_actual in orden else "principiante"
    return objetivo if orden.index(objetivo) > orden.index(actual) else None


def nivel_sugerido(progreso, nivel_actual):
    """Autonomía progresiva: devuelve el nuevo nivel si toca subir, o None."""
    orden = ["principiante", "intermedio", "avanzado"]
    hechas = len(progreso["completadas"])
    objetivo = "principiante"
    for nivel in ("intermedio", "avanzado"):
        if hechas >= UMBRAL_NIVEL[nivel]:
            objetivo = nivel
    if orden.index(objetivo) > orden.index(nivel_actual):
        return objetivo
    return None


# ---------- Selección de temas (IA + respaldo por palabras) ----------

def prompt_seleccion(meta, nivel):
    catalogo = "\n".join(f"- {t}: {d['nombre']} [{d.get('dificultad', 'basico')}] ({len(d['lecciones'])} lecciones)"
                         for t, d in TEMAS.items())
    return (
        "Eres un tutor de Linux. Elige del catálogo los temas que sirven para la meta del estudiante, en el orden "
        "en que conviene aprenderlos. Para nivel principiante incluye 'terminal' primero salvo que la meta sea muy "
        "específica de otro tema. Ordena de básico a maestro. Si la meta es ser experto, profesional, desarrollador, "
        "sysadmin o «dominar Linux», arma una ruta larga que incluya los temas avanzados, experto y maestro (hasta 16 temas); "
        "si no, usa entre 1 y 4 temas. Responde SOLO JSON: "
        '{"nombre": "nombre corto del plan (máx 4 palabras)", "temas": ["id", ...]}\n\n'
        f"CATÁLOGO:\n{catalogo}\n\nNIVEL: {nivel}\nMETA DEL ESTUDIANTE: {meta}"
    )


def parsear_seleccion(texto):
    try:
        m = re.search(r"\{.*\}", texto or "", re.DOTALL)
        datos = json.loads(m.group(0)) if m else {}
    except ValueError:
        datos = {}
    temas = []
    for t in datos.get("temas", []) if isinstance(datos.get("temas"), list) else []:
        t = str(t).strip().lower()
        if t in TEMAS and t not in temas:
            temas.append(t)
    nombre = str(datos.get("nombre") or "").strip()[:40]
    return nombre, temas[:len(TEMAS)]


_RE_RUTA_COMPLETA = re.compile(r"experto|maestro|profesional|desarrollador|dominar|sysadmin|teso|arquitecto|todo linux", re.I)


def ajustar_seleccion(meta, temas):
    """Si la meta es dominar Linux, la ruta incluye TODO el catálogo (básico → maestro) en orden."""
    if _RE_RUTA_COMPLETA.search(meta or ""):
        return list(TEMAS)
    return temas


def seleccion_por_palabras(meta, nivel):
    """Respaldo sin IA: temas cuyas palabras clave aparecen en la meta."""
    t = meta.lower()
    temas = [k for k, d in TEMAS.items() if any(p in t for p in d["palabras"].split())]
    if not temas:
        temas = ["terminal", "permisos", "paquetes"]
    if re.search(r"experto|maestro|profesional|desarrollador|dominar|sysadmin|teso|top|todo", t):
        temas = list(TEMAS)  # ruta completa, de básico a maestro
    if nivel == "principiante" and "terminal" not in temas:
        temas.insert(0, "terminal")
    return temas[:len(TEMAS)]


def resumen_plan(plan, progreso):
    hechas = set(plan.get("completadas", []))
    lineas = []
    for t in plan["temas"]:
        d = TEMAS[t]
        n_hechas = sum(1 for l in d["lecciones"] if l["id"] in hechas)
        lineas.append(f"- {d['icono']} **{d['nombre']}** · {n_hechas}/{len(d['lecciones'])}")
    return "\n".join(lineas)


def contexto_leccion(plan, leccion, i, total):
    """Texto que se añade al prompt de sistema cuando se está en un plan."""
    return (
        f"\n\nESTÁS DANDO UNA CLASE. Plan «{plan['nombre']}» (meta del estudiante: {plan['meta']}). "
        f"Lección {i} de {total}: «{leccion['titulo']}». Enseña SOLO esto: {leccion['objetivo']}. "
        "CONECTA la lección con la meta del estudiante: di en una frase por qué esto le sirve para esa meta y usa "
        "ejemplos de esa misma situación (si la meta habla de errores que cometió, usa esos errores como ejemplo). "
        "Empieza directo por el concepto. Explica con un ejemplo práctico y corto. NO inventes ejercicios ni misiones: "
        "la misión se muestra aparte. Si el estudiante pregunta algo de la lección, respóndelo en ese contexto."
    )


def tarjeta_mision(leccion):
    """Texto de la tarjeta de misión. Con varios pasos se listan todos (todos cuentan para completarla)."""
    pasos = leccion.get("pasos")
    if pasos:
        lista = "\n".join(f"{i}. {p['texto']}" for i, p in enumerate(pasos, 1))
        return (f"🎯 **Misión:** {leccion['mision']}\n{lista}\n"
                "Pulsa «Comprobar» cuando quieras: reviso cada paso en tu equipo.")
    pie = ("Escríbeme la respuesta aquí y la compruebo con tu equipo."
           if es_mision_de_respuesta(leccion)
           else "Cuando termines escribe «listo» y lo compruebo en tu equipo.")
    return f"🎯 **Misión:** {leccion['mision']}\n{pie} (Si te atascas: «pista» o «saltar»)"


# ---------- Chats guardados ----------

def cargar_chat(cid):
    datos = _leer_json(DIR_CHATS / f"{cid}.json", [])
    return [{"text": m.get("t", ""), "is_user": bool(m.get("u")), "time": m.get("s", 0)}
            for m in datos if isinstance(m, dict)]


def guardar_chat(cid, mensajes):
    recorte = mensajes[-MAX_MENSAJES:]
    datos = [{"t": m["text"][:MAX_TEXTO], "u": 1 if m["is_user"] else 0, "s": int(m.get("time", 0))}
             for m in recorte if m.get("text")]
    _escribir_json(DIR_CHATS / f"{cid}.json", datos)


def espacio_usado():
    """Bytes que ocupa todo lo guardado (para transparencia)."""
    total = 0
    for p in DIR.rglob("*.json"):
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total


# ---------- Cuadernos de preguntas (varios, como chats) ----------

def crear_cuaderno(progreso):
    cid = f"c{int(time.time() * 1000)}"
    while cid in progreso["cuadernos"]:
        cid += "x"
    n = len(progreso["cuadernos"]) + 1
    progreso["cuadernos"][cid] = {"nombre": f"Cuaderno {n}"}
    guardar_progreso(progreso)
    return cid


def nombrar_cuaderno(progreso, cid, primera_pregunta):
    """El cuaderno toma el nombre de su primera pregunta (como los chats)."""
    c = progreso["cuadernos"].get(cid)
    if not c or cid == CHAT_LIBRE or c.get("nombrado"):
        return
    nombre = re.sub(r"\s+", " ", primera_pregunta).strip(" ¿?¡!.")
    c["nombre"] = (nombre[:30].rsplit(" ", 1)[0] + "…") if len(nombre) > 32 else nombre
    c["nombrado"] = True
    guardar_progreso(progreso)


def borrar_cuaderno(progreso, cid):
    if cid == CHAT_LIBRE:
        guardar_chat(cid, [])  # el General no se borra, se vacía
        return
    progreso["cuadernos"].pop(cid, None)
    guardar_progreso(progreso)
    try:
        (DIR_CHATS / f"{cid}.json").unlink()
    except OSError:
        pass


def contar_mensajes(cid):
    return len(_leer_json(DIR_CHATS / f"{cid}.json", []))


def agregar_a_chat(cid, texto, is_user=False):
    """Añade un mensaje a un chat guardado sin tenerlo abierto (p. ej. errores de terminal)."""
    mensajes = cargar_chat(cid)
    mensajes.append({"text": texto, "is_user": is_user, "time": time.time()})
    guardar_chat(cid, mensajes)


def asegurar_rapidas(progreso):
    """El cuaderno «Preguntas rápidas» existe siempre que se usa el modo rápido."""
    if CHAT_RAPIDAS not in progreso["cuadernos"]:
        progreso["cuadernos"][CHAT_RAPIDAS] = {"nombre": "Preguntas rápidas", "nombrado": True}
        guardar_progreso(progreso)
    return CHAT_RAPIDAS


def titular_cuaderno(progreso, cid, titulo):
    """Título puesto por la IA tras la primera conversación del cuaderno."""
    c = progreso["cuadernos"].get(cid)
    if c is not None:
        c["nombre"], c["nombrado"], c["titulo_ia"] = titulo[:40], True, True
        guardar_progreso(progreso)


# ---------- Misiones propias de cada ruta (las crea la IA, las comprueba el código) ----------

CLAVES_RESPUESTA = {
    "nucleos": "número de núcleos de CPU", "usuario": "nombre de usuario", "gestor": "gestor de paquetes",
    "ram_total_gb": "RAM total en GB", "ip_local": "IP local", "gateway": "IP del router", "kernel": "versión del kernel",
    "puertos": "puertos TCP escuchando", "fallidos": "servicios fallidos", "snaps": "snaps instalados",
    "bluetooth": "si bluetooth está activo (sí/no)", "swappiness": "valor de vm.swappiness",
    "modulos": "módulos del kernel cargados", "libre_raiz": "GB libres en /", "gtk_theme": "tema GTK",
    "bash_users": "líneas de /etc/passwd que terminan en /bin/bash", "etc_conf": "archivos .conf en /etc",
}


def prompt_mision(plan, leccion, usadas):
    """Pide a la IA una misión NUEVA de 2-3 pasos para esta ruta, que el código pueda comprobar paso a paso."""
    claves = "; ".join(f"{k} = {v}" for k, v in CLAVES_RESPUESTA.items())
    ya = "\n".join(f"- {u}" for u in usadas) or "- (ninguna)"
    return (
        "Eres un tutor de Linux. Crea UNA misión práctica de 2 o 3 PASOS para esta lección. La misión DEBE tener "
        "sentido con la META DE LA RUTA: practica justo lo que el estudiante necesita para esa meta (si la meta habla de "
        "errores que cometió, la misión practica cómo evitarlos). Los pasos van en orden y juntos forman un ejercicio "
        "completo de la lección. Distinta de las misiones ya usadas.\n"
        "Cada paso se comprueba en el equipo con UNO de estos tipos:\n"
        '- {"tipo":"existe","ruta":"~/tux-practica/...","clase":"dir" o "archivo"}\n'
        '- {"tipo":"contiene","ruta":"~/tux-practica/...","texto":"texto que debe tener el archivo"}\n'
        '- {"tipo":"permisos","ruta":"~/tux-practica/...","modo":"600"}\n'
        '- {"tipo":"ejecutable","ruta":"~/tux-practica/..."}\n'
        '- {"tipo":"instalado","programa":"nombre"}\n'
        f'- {{"tipo":"respuesta","clave":"una de: {claves}"}} (el estudiante escribe un dato y Tux lo compara)\n'
        "Si un paso es ver información (la salida de un comando), pide GUARDARLA en un archivo de ~/tux-practica con `>` "
        "y compruébalo con «contiene» y un texto que SIEMPRE aparece en esa salida. El nombre del archivo debe aparecer "
        "en el texto del paso. "
        "Rutas SIEMPRE dentro de ~/tux-practica/. Cada paso en 1 frase, en español, con comandos entre acentos graves. "
        'Responde SOLO JSON: {"mision": "objetivo general en 1 frase", "pasos": [{"texto": "...", "check": {...}}, ...]}\n\n'
        f"META DE LA RUTA: {plan.get('meta', '')}\n"
        f"LECCIÓN: {leccion['titulo']} — enseña: {leccion['objetivo']}\n"
        f"EJEMPLO DE MISIÓN DEL CATÁLOGO (no la copies): {LECCIONES[leccion['id']]['mision']}\n"
        f"MISIONES YA USADAS:\n{ya}"
    )


def _check_de(c):
    """Un check en JSON de la IA → lista validada (o None)."""
    if not isinstance(c, dict):
        return None
    tipo = c.get("tipo")
    if tipo == "existe":
        ruta = _ruta_practica(c.get("ruta"))
        return ["existe", ruta, "dir" if str(c.get("clase", "")).startswith("d") else "archivo"] if ruta else None
    if tipo == "contiene":
        ruta, txt = _ruta_practica(c.get("ruta")), str(c.get("texto") or "").strip()
        return ["contiene", ruta, "(?i)" + re.escape(txt)] if ruta and 0 < len(txt) <= 60 else None
    if tipo == "permisos":
        ruta, modo = _ruta_practica(c.get("ruta")), str(c.get("modo") or "")
        return ["permisos", ruta, modo] if ruta and re.fullmatch(r"[0-7]{3}", modo) else None
    if tipo == "ejecutable":
        ruta = _ruta_practica(c.get("ruta"))
        return ["ejecutable", ruta] if ruta else None
    if tipo == "instalado":
        prog = str(c.get("programa") or "")
        return ["instalado", prog] if re.fullmatch(r"[\w.+-]{1,40}", prog) else None
    if tipo == "respuesta":
        clave = str(c.get("clave") or "")
        return ["respuesta", clave] if clave in CLAVES_RESPUESTA else None
    return None


def _ruta_practica(ruta):
    ruta = str(ruta or "").strip()
    if (not ruta.startswith("~/tux-practica") or ".." in ruta or "/./" in ruta or "//" in ruta
            or re.search(r"[\s;|&$`*?]", ruta)):
        return None
    return ruta.rstrip("/")


def _paso_coherente(texto, check):
    """La comprobación debe corresponder a lo que dice el paso (si no, la IA se inventó algo que no cuadra)."""
    t = texto.lower()
    tipo = check[0]
    if tipo in ("existe", "contiene", "permisos", "ejecutable"):
        nombre = os.path.basename(check[1]).lower()
        return bool(nombre) and nombre in t
    if tipo == "instalado":
        return check[1].lower() in t
    return True


def parsear_mision(texto):
    """JSON de la IA → (mision, pasos) validado; pasos = [{"texto", "check"}]. None si no sirve."""
    try:
        m = re.search(r"\{.*\}", texto or "", re.DOTALL)
        datos = json.loads(m.group(0)) if m else {}
    except ValueError:
        return None
    mision = str(datos.get("mision") or "").strip()
    pasos = []
    for paso in datos.get("pasos") or []:
        if not isinstance(paso, dict):
            continue
        txt = str(paso.get("texto") or "").strip()
        check = _check_de(paso.get("check"))
        if check and 8 <= len(txt) <= 240 and _paso_coherente(txt, check):
            pasos.append({"texto": txt, "check": check})
    if not pasos and isinstance(datos.get("check"), dict):  # formato de un solo paso
        check = _check_de(datos["check"])
        if check:
            pasos = [{"texto": mision, "check": check}]
    if not (10 <= len(mision) <= 320) or not pasos:
        return None
    return mision, pasos[:3]


def guardar_mision(progreso, pid, lid, mision, pasos):
    plan = progreso["planes"].get(pid)
    if plan is not None:
        plan.setdefault("misiones", {})[lid] = {"mision": mision, "pasos": pasos}
        guardar_progreso(progreso)


def misiones_usadas(progreso, lid, excepto=None):
    """Misiones que ya salieron para esta lección en otras rutas (para no repetirlas)."""
    usadas = [LECCIONES[lid]["mision"]]
    for pid, plan in progreso["planes"].items():
        if pid != excepto and lid in plan.get("misiones", {}):
            usadas.append(plan["misiones"][lid]["mision"])
    return usadas



def asegurar_pasos_posibles(pasos):
    """Evita misiones imposibles: si un paso pide guardar la salida de un comando y comprobar un texto,
    se ejecuta ese comando (solo si es de solo lectura) y se confirma que el texto aparece de verdad.
    Si no aparece, se cambia por una palabra real de la salida; si el comando no se puede probar,
    la comprobación se relaja a «el archivo existe»."""
    import herramientas
    arreglados = []
    for paso in pasos:
        check = list(paso["check"])
        if check[0] == "contiene":
            m = re.search(r"`?([^`>]+?)\s*>\s*`?(~/tux-practica/[^\s`'\"]+)", paso["texto"])
            if m and os.path.basename(m.group(2)) == os.path.basename(check[1]):
                args, _ = herramientas.validar(m.group(1).strip().strip("`\"'"))
                salida = ""
                if args:
                    try:
                        salida = subprocess.run(args, capture_output=True, text=True, timeout=5).stdout
                    except (OSError, subprocess.TimeoutExpired):
                        salida = ""
                if salida and not re.search(check[2], salida):
                    palabra = next((w for w in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúñ][\w-]{3,}", salida[:400])), None)
                    check[2] = re.escape(palabra) if palabra else check[2]
                elif not salida:
                    check = ["existe", check[1], "archivo"]
            else:
                check = ["existe", check[1], "archivo"] if not m else check
        arreglados.append({"texto": paso["texto"], "check": check})
    return arreglados
