"""Gestor de contexto del sistema para Tux Assistant.

Recoge información amplia del equipo y del Linux instalado para que la IA
responda con comandos y explicaciones correctos para ESTE entorno.

- Parte estática (hardware, distribución, escritorio, paquetes...): se calcula
  una sola vez, en segundo plano, y se guarda en caché.
- Parte dinámica (RAM, CPU, procesos, errores recientes...): se recalcula en
  cada pregunta; es barata.

Todo es de solo lectura: solo se ejecutan comandos de consulta, sin sudo y con
tiempo límite. La información no sale del equipo (la IA es local).
"""
import datetime
import getpass
import glob
import os
import platform
import re
import shutil
import socket
import subprocess
import threading
import time

import psutil

_cache_estatico = None
_claves = {}  # resumen corto que los modelos pequeños sí aprovechan
_lock = threading.Lock()


# ---------- utilidades ----------

def _cmd(args, timeout=2.0):
    """Ejecuta un comando de consulta y devuelve su salida (o '' si falla)."""
    if not shutil.which(args[0]):
        return ""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "LC_ALL": "C"})
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _leer(ruta):
    try:
        with open(ruta, encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except OSError:
        return ""


def _primera_linea(texto):
    return texto.splitlines()[0].strip() if texto else ""


def _gb(n):
    return f"{n / 1024 ** 3:.1f} GB"


def _version(binario, *args):
    salida = _cmd([binario, *(args or ("--version",))], timeout=1.5)
    return _primera_linea(salida)


# ---------- parte estática ----------

def _sistema():
    try:
        osr = platform.freedesktop_os_release()
    except OSError:
        osr = {}
    lineas = [
        f"Distribución: {osr.get('PRETTY_NAME', platform.platform())}"
        + (f" (codename {osr['VERSION_CODENAME']})" if osr.get("VERSION_CODENAME") else ""),
        f"Familia: ID={osr.get('ID', '?')} ID_LIKE={osr.get('ID_LIKE', '-')}",
        f"Kernel: {platform.release()} | Arquitectura: {platform.machine()}",
        f"Arranque: {'UEFI' if os.path.isdir('/sys/firmware/efi') else 'BIOS/Legacy'}",
    ]
    sb = _cmd(["mokutil", "--sb-state"], timeout=1.5)
    if sb:
        lineas.append(f"Secure Boot: {_primera_linea(sb)}")
    virt = _cmd(["systemd-detect-virt"], timeout=1.5)
    lineas.append(f"Virtualización: {virt if virt and virt != 'none' else 'equipo físico'}")
    _claves["distro"] = osr.get("PRETTY_NAME", platform.platform())
    init = _primera_linea(_cmd(["systemctl", "--version"]))
    if init:
        lineas.append(f"Init: {init}")
    lineas.append(f"Hostname: {socket.gethostname()}")
    return "SISTEMA", lineas


def _hardware():
    dmi = "/sys/class/dmi/id/"
    fabricante = _leer(dmi + "sys_vendor")
    modelo = _leer(dmi + "product_name")
    version_prod = _leer(dmi + "product_version")
    lineas = []
    if fabricante or modelo:
        lineas.append(f"Equipo: {fabricante} {modelo} {version_prod}".strip())
    bios = " ".join(filter(None, [_leer(dmi + "bios_vendor"), _leer(dmi + "bios_version"), _leer(dmi + "bios_date")]))
    if bios:
        lineas.append(f"BIOS/UEFI: {bios}")

    modelo_cpu = ""
    for linea in _leer("/proc/cpuinfo").splitlines():
        if linea.startswith("model name"):
            modelo_cpu = linea.split(":", 1)[1].strip()
            break
    freq = psutil.cpu_freq()
    lineas.append(
        f"CPU: {modelo_cpu or platform.processor()} | {psutil.cpu_count(logical=False)} núcleos / "
        f"{psutil.cpu_count()} hilos" + (f" | máx {freq.max:.0f} MHz" if freq and freq.max else "")
    )
    mem, swap = psutil.virtual_memory(), psutil.swap_memory()
    swaps = [l.split()[0] for l in _leer("/proc/swaps").splitlines()[1:]]
    lineas.append(f"RAM: {_gb(mem.total)} | Swap: {_gb(swap.total)} ({', '.join(swaps) or 'sin swap'})")

    # GPU y driver en uso
    gpus = []
    salida_lspci = _cmd(["lspci", "-k"], timeout=2).splitlines()
    for i, linea in enumerate(salida_lspci):
        if any(k in linea for k in ("VGA compatible", "3D controller", "Display controller")):
            nombre = linea.split(": ", 1)[-1]
            driver = ""
            for sig in salida_lspci[i + 1:i + 4]:
                if "Kernel driver in use" in sig:
                    driver = sig.split(":", 1)[1].strip()
            gpus.append(f"{nombre} [driver: {driver or 'ninguno'}]")
    for g in gpus:
        lineas.append(f"GPU: {g}")
    if gpus:
        _claves["gpu"] = " + ".join(gpus)
    nv = _cmd(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"], timeout=3)
    if nv:
        lineas.append(f"NVIDIA (nvidia-smi): {nv}")

    if glob.glob("/sys/class/power_supply/BAT*"):
        lineas.append("Tipo: portátil (tiene batería)")
    return "HARDWARE", lineas


def _almacenamiento():
    lineas = []
    salida = _cmd(["lsblk", "-e7", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,MODEL", "-n"], timeout=2)
    for l in salida.splitlines()[:14]:
        if l.strip():
            lineas.append(l.rstrip())
    return "DISCOS Y PARTICIONES (lsblk)", lineas


def _escritorio():
    env = os.environ
    escritorio = env.get("XDG_CURRENT_DESKTOP", "desconocido")
    lineas = [
        f"Entorno: {escritorio} | Sesión: {env.get('DESKTOP_SESSION', '?')} | "
        f"Servidor gráfico: {env.get('XDG_SESSION_TYPE', '?')}",
    ]
    _claves["escritorio"] = f"{escritorio} en {env.get('XDG_SESSION_TYPE', '?')}"
    if "GNOME" in escritorio.upper():
        v = _version("gnome-shell")
        if v:
            lineas.append(f"Versión escritorio: {v}")
    elif "KDE" in escritorio.upper():
        v = _version("plasmashell")
        if v:
            lineas.append(f"Versión escritorio: {v}")
    dm = os.path.basename(os.path.realpath("/etc/systemd/system/display-manager.service"))
    if dm and dm != "display-manager.service":
        lineas.append(f"Gestor de inicio de sesión: {dm.replace('.service', '')}")
    pantallas = [l.split()[0] for l in _cmd(["xrandr", "--current"]).splitlines() if "*" in l]
    if pantallas:
        lineas.append(f"Resolución: {', '.join(pantallas)}")
    audio = ""
    for l in _cmd(["pactl", "info"]).splitlines():
        if l.startswith("Server Name"):
            audio = l.split(":", 1)[1].strip()
    if audio:
        lineas.append(f"Servidor de audio: {audio}")
    teclado = [l.strip() for l in _cmd(["localectl", "status"]).splitlines() if "Layout" in l or "Locale" in l]
    lineas.extend(teclado[:2])
    zona = _cmd(["timedatectl", "show", "-p", "Timezone", "--value"])
    lineas.append(f"Idioma: {env.get('LANG', '?')}" + (f" | Zona horaria: {zona}" if zona else ""))
    return "ESCRITORIO", lineas


def _usuario():
    shell = env_shell = os.environ.get("SHELL", "")
    version_shell = _version(env_shell) if env_shell else ""
    grupos = _cmd(["id", "-nG"]).split()
    admin = any(g in grupos for g in ("sudo", "wheel", "admin"))
    lineas = [
        f"Usuario: {getpass.getuser()} | Home: {os.path.expanduser('~')} | "
        f"{'puede usar sudo' if admin else 'NO está en el grupo sudo/wheel'}",
        f"Grupos: {' '.join(grupos)}",
        f"Shell: {os.path.basename(shell) or '?'}" + (f" ({version_shell})" if version_shell else ""),
    ]
    terminal = os.environ.get("TERM_PROGRAM") or os.environ.get("TERMINAL") or os.environ.get("TERM", "")
    if terminal:
        lineas.append(f"Terminal: {terminal}")
    return "USUARIO", lineas


def _paquetes():
    lineas = []
    gestores = []
    for nombre, conteo in (
        ("apt", ["dpkg-query", "-f", ".\n", "-W"]),
        ("dnf", ["rpm", "-qa"]),
        ("zypper", ["rpm", "-qa"]),
        ("pacman", ["pacman", "-Qq"]),
    ):
        if shutil.which(nombre):
            n = len(_cmd(conteo, timeout=4).splitlines())
            gestores.append(f"{nombre} ({n} paquetes)" if n else nombre)
    if shutil.which("flatpak"):
        n = len(_cmd(["flatpak", "list", "--app", "--columns=application"], timeout=4).splitlines())
        gestores.append(f"flatpak ({n} apps)")
    if shutil.which("snap"):
        n = max(len(_cmd(["snap", "list"], timeout=4).splitlines()) - 1, 0)
        gestores.append(f"snap ({n} snaps)")
    for extra in ("nix", "brew", "yay", "paru"):
        if shutil.which(extra):
            gestores.append(extra)
    lineas.append("Gestores: " + (", ".join(gestores) or "ninguno detectado"))
    _claves["paquetes"] = ", ".join(g.split(" (")[0] for g in gestores)
    if shutil.which("apt"):
        fuentes = glob.glob("/etc/apt/sources.list.d/*")
        if fuentes:
            nombres = sorted({os.path.basename(f).split(".")[0] for f in fuentes})
            lineas.append(f"Repos APT extra: {', '.join(nombres[:12])}")
    return "PAQUETES", lineas


def _herramientas():
    encontradas = []
    for binario, args in (
        ("python3", ("--version",)), ("pip3", ("--version",)), ("gcc", ("--version",)),
        ("git", ("--version",)), ("node", ("--version",)), ("java", ("-version",)),
        ("docker", ("--version",)), ("podman", ("--version",)), ("code", ("--version",)),
        ("ollama", ("--version",)), ("vim", ("--version",)), ("nano", ("--version",)),
    ):
        if shutil.which(binario):
            m = re.search(r"\d+(\.\d+)+", _version(binario, *args))
            encontradas.append(f"{binario} {m.group(0) if m else ''}".strip())
    servicios = []
    for s in ("NetworkManager", "ufw", "firewalld", "ssh", "sshd", "docker", "bluetooth", "cups", "ollama"):
        if _cmd(["systemctl", "is-active", s], timeout=1) == "active":
            servicios.append(s)
    lineas = [f"Instaladas: {', '.join(encontradas) or 'ninguna de las comunes'}"]
    if servicios:
        lineas.append(f"Servicios activos relevantes: {', '.join(servicios)}")
    return "HERRAMIENTAS", lineas


def _red_estatica():
    lineas = []
    stats = psutil.net_if_stats()
    for nombre, direcciones in psutil.net_if_addrs().items():
        if nombre == "lo" or nombre.startswith("veth"):
            continue
        ipv4 = [d.address for d in direcciones if d.family == socket.AF_INET]
        tipo = "wifi" if os.path.isdir(f"/sys/class/net/{nombre}/wireless") else (
            "virtual" if nombre.startswith(("docker", "veth", "br-", "virbr", "tun", "tap")) else "cable/otro")
        estado = "arriba" if stats.get(nombre) and stats[nombre].isup else "abajo"
        lineas.append(f"{nombre} ({tipo}, {estado}){': ' + ', '.join(ipv4) if ipv4 else ''}")
    activas = _cmd(["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "con", "show", "--active"])
    if activas:
        lineas.append("Conexiones NetworkManager: " + "; ".join(activas.splitlines()[:4]))
    return "RED", lineas[:10]


def _formatear(secciones):
    partes = []
    for titulo, lineas in secciones:
        lineas = [l for l in lineas if l]
        if lineas:
            partes.append(f"[{titulo}]\n" + "\n".join(f"- {l}" for l in lineas))
    return "\n".join(partes)


def contexto_estatico():
    """Información que no cambia durante la sesión (se calcula una vez)."""
    global _cache_estatico
    with _lock:
        if _cache_estatico is None:
            secciones = []
            for f in (_sistema, _hardware, _almacenamiento, _escritorio, _usuario, _paquetes, _herramientas, _red_estatica):
                try:
                    secciones.append(f())
                except Exception:
                    continue
            _cache_estatico = _formatear(secciones)
        return _cache_estatico


def precalentar():
    """Llamar al arrancar (en un hilo) para que la primera pregunta no espere."""
    threading.Thread(target=contexto_estatico, daemon=True).start()


# ---------- parte dinámica ----------

def contexto_dinamico():
    """Estado actual del equipo (se recalcula en cada pregunta)."""
    lineas = []
    ahora = datetime.datetime.now()
    arranque = datetime.datetime.fromtimestamp(psutil.boot_time())
    horas = (ahora - arranque).total_seconds() / 3600
    carga = os.getloadavg()
    lineas.append(f"Fecha y hora: {ahora:%Y-%m-%d %H:%M} | Encendido hace {horas:.1f} h | "
                  f"Carga: {carga[0]:.2f} {carga[1]:.2f} {carga[2]:.2f}")
    mem, swap = psutil.virtual_memory(), psutil.swap_memory()
    lineas.append(f"CPU en uso: {psutil.cpu_percent(interval=0.15):.0f}% | RAM: {_gb(mem.used)} usada de "
                  f"{_gb(mem.total)} ({mem.percent:.0f}%), disponible {_gb(mem.available)} | Swap usada: {_gb(swap.used)}")

    discos = []
    for punto in ("/", "/home", "/boot/efi"):
        try:
            if os.path.ismount(punto) or punto == "/":
                u = psutil.disk_usage(punto)
                discos.append(f"{punto} {u.percent:.0f}% ({_gb(u.free)} libres)")
        except OSError:
            pass
    lineas.append("Espacio: " + " | ".join(discos))

    try:
        bat = psutil.sensors_battery()
        if bat:
            lineas.append(f"Batería: {bat.percent:.0f}% {'cargando' if bat.power_plugged else 'descargando'}")
    except Exception:
        pass
    temps_max = 0
    try:
        temps = []
        for chip, sensores in (psutil.sensors_temperatures() or {}).items():
            if sensores and chip in ("coretemp", "k10temp", "acpitz", "amdgpu", "nvme"):
                t_chip = max(s.current for s in sensores)
                temps.append(f"{chip} {t_chip:.0f}°C")
                if chip in ("coretemp", "k10temp"):
                    temps_max = max(temps_max, t_chip)
        if temps:
            lineas.append("Temperaturas: " + ", ".join(temps[:4]))
    except Exception:
        pass

    procesos = []
    for p in psutil.process_iter(["name", "memory_percent", "cpu_percent"]):
        try:
            procesos.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    top_mem = sorted(procesos, key=lambda p: p["memory_percent"] or 0, reverse=True)[:5]
    lineas.append("Procesos que más RAM usan: " + ", ".join(
        f"{p['name']} {p['memory_percent']:.1f}%" for p in top_mem))
    lineas.append(f"Procesos totales: {len(procesos)}")

    fallidos = _cmd(["systemctl", "--failed", "--no-legend", "--plain"], timeout=1.5)
    unidades = [l.split()[0] for l in fallidos.splitlines() if l.strip()]
    lineas.append("Servicios fallidos: " + (", ".join(unidades[:6]) if unidades else "ninguno"))

    errores = _cmd(["journalctl", "-p", "3", "-b", "-n", "4", "--no-pager", "-o", "cat"], timeout=2)
    if errores:
        lineas.append("Últimos errores del sistema (journal): " + " || ".join(
            e[:120] for e in errores.splitlines()[-4:]))

    try:
        conectado = socket.create_connection(("1.1.1.1", 53), timeout=0.6)
        conectado.close()
        lineas.append("Internet: conectado")
    except OSError:
        lineas.append("Internet: sin conexión")

    alertas = []
    if temps_max >= 85:
        alertas.append(f"CPU muy caliente ({temps_max:.0f}°C; normal en reposo 40-60°C)")
    if mem.percent >= 90:
        alertas.append(f"RAM casi llena ({mem.percent:.0f}%)")
    for punto in ("/", "/home"):
        try:
            if (os.path.ismount(punto) or punto == "/") and psutil.disk_usage(punto).percent >= 90:
                alertas.append(f"disco {punto} casi lleno")
        except OSError:
            pass
    if carga[0] > psutil.cpu_count():
        alertas.append(f"carga de CPU alta ({carga[0]:.1f})")
    if unidades:
        alertas.append(f"servicios fallidos: {', '.join(unidades[:3])}")
    if "Internet: sin conexión" in lineas:
        alertas.append("sin conexión a Internet")
    global _alertas
    _alertas = alertas
    return "[ESTADO ACTUAL]\n" + "\n".join(f"- {l}" for l in lineas)


_alertas = []


_TEMAS_ALERTA = (
    (r"calient|calor|temperatura|ventilador|quema|grados", ("caliente",)),
    (r"lent|se traba|congela|rendimiento|memoria|ram|consum", ("RAM", "carga", "caliente")),
    (r"disco|espacio|almacenamiento|lleno", ("disco",)),
    (r"internet|red|wifi|conexi", ("Internet",)),
    (r"error|falla|fallo|servicio|no arranca|no inicia", ("servicios",)),
)


def alertas_relevantes(pregunta):
    """Alertas actuales que tienen que ver con la pregunta (llamar tras contexto_completo)."""
    encontradas = []
    for patron, claves in _TEMAS_ALERTA:
        if re.search(patron, pregunta or "", re.IGNORECASE):
            encontradas += [a for a in _alertas if any(k in a for k in claves) and a not in encontradas]
    return encontradas


def contexto_completo():
    estatico = contexto_estatico()
    dinamico = contexto_dinamico()
    claves = " · ".join(f"{v}" for v in (
        _claves.get("distro"),
        f"instalar con: {_claves['paquetes']}" if _claves.get("paquetes") else None,
        _claves.get("escritorio"),
        f"GPU: {_claves['gpu']}" if _claves.get("gpu") else None,
    ) if v)
    alertas = ("ALERTAS AHORA: " + "; ".join(_alertas)) if _alertas else "ALERTAS AHORA: ninguna"
    # Estático primero (no cambia: Ollama reutiliza su caché); lo que cambia, al final
    return f"{estatico}\n{dinamico}\nDATOS CLAVE: {claves}\n{alertas}"


if __name__ == "__main__":
    t = time.time()
    e = contexto_estatico()
    t1 = time.time()
    d = contexto_dinamico()
    print(e + "\n" + d)
    print(f"\n# estático {t1 - t:.2f}s | dinámico {time.time() - t1:.2f}s | {len(e + d)} caracteres")


# ---------- datos en vivo según el tema de la pregunta ----------
# Se miden con código en el momento de la pregunta y se pegan al mensaje del
# usuario, así la IA responde con números reales en vez de mandar a ejecutar comandos.

def _mb(n):
    return f"{n / 1024 ** 2:.0f} MB"


def _top_procesos(n=8):
    procs = list(psutil.process_iter(["pid", "name", "memory_info", "username"]))
    for p in procs:
        try:
            p.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    time.sleep(0.4)
    datos = []
    for p in procs:
        try:
            datos.append((p.info["name"], p.info["pid"], p.cpu_percent(None) / psutil.cpu_count(),
                          p.info["memory_info"].rss if p.info["memory_info"] else 0))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    por_cpu = sorted(datos, key=lambda d: d[2], reverse=True)[:n]
    por_ram = sorted(datos, key=lambda d: d[3], reverse=True)[:n]
    return por_cpu, por_ram, len(datos)


def _vivo_ram():
    mem, swap = psutil.virtual_memory(), psutil.swap_memory()
    _, por_ram, _ = _top_procesos()
    return [
        f"RAM total {_gb(mem.total)}, en uso {_gb(mem.used)} ({mem.percent:.0f}%), disponible {_gb(mem.available)}, "
        f"en caché/búfer {_gb(getattr(mem, 'cached', 0) + getattr(mem, 'buffers', 0))}",
        f"Swap: {_gb(swap.used)} usados de {_gb(swap.total)} ({swap.percent:.0f}%)",
        "Procesos que más RAM usan: " + "; ".join(f"{n} (PID {pid}) {_mb(rss)}" for n, pid, _, rss in por_ram),
    ]


def _vivo_cpu():
    por_nucleo = psutil.cpu_percent(interval=0.4, percpu=True)
    freq = psutil.cpu_freq()
    carga = os.getloadavg()
    por_cpu, _, _ = _top_procesos()
    return [
        f"CPU total {sum(por_nucleo) / len(por_nucleo):.0f}% | por hilo: {', '.join(f'{x:.0f}%' for x in por_nucleo)}",
        f"Frecuencia actual {freq.current:.0f} MHz" if freq else "",
        f"Carga media (1/5/15 min): {carga[0]:.2f} / {carga[1]:.2f} / {carga[2]:.2f} con {psutil.cpu_count()} hilos",
        "Procesos que más CPU usan: " + "; ".join(f"{n} (PID {pid}) {c:.1f}%" for n, pid, c, _ in por_cpu),
    ]


def _vivo_procesos():
    por_cpu, por_ram, total = _top_procesos(10)
    return [
        f"Procesos en ejecución: {total}",
        "Top CPU: " + "; ".join(f"{n} (PID {pid}) {c:.1f}%" for n, pid, c, _ in por_cpu),
        "Top RAM: " + "; ".join(f"{n} (PID {pid}) {_mb(rss)}" for n, pid, _, rss in por_ram),
    ]


def _vivo_disco():
    lineas = []
    for part in psutil.disk_partitions():
        if part.mountpoint.startswith(("/snap", "/var/snap", "/run/user")) or "loop" in part.device:
            continue
        try:
            u = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        lineas.append(f"{part.mountpoint} ({part.device}, {part.fstype}): {_gb(u.used)} usados de {_gb(u.total)} "
                      f"({u.percent:.0f}%), libres {_gb(u.free)}")
    io = psutil.disk_io_counters()
    if io:
        lineas.append(f"Desde el arranque: leídos {_gb(io.read_bytes)}, escritos {_gb(io.write_bytes)}")
    return lineas


def _vivo_gpu():
    lineas = []
    nv = _cmd(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,driver_version",
               "--format=csv,noheader"], timeout=3)
    if nv:
        lineas.append(f"NVIDIA (nombre, uso, VRAM usada, VRAM total, temperatura, consumo, driver): {nv}")
        apps = _cmd(["nvidia-smi", "--query-compute-apps=process_name,used_memory", "--format=csv,noheader"], timeout=3)
        if apps:
            lineas.append("Programas usando la GPU NVIDIA: " + "; ".join(apps.splitlines()[:6]))
    if _claves.get("gpu"):
        lineas.append(f"GPUs del equipo: {_claves['gpu']}")
    return lineas


def _vivo_red():
    lineas = []
    stats = psutil.net_if_stats()
    for nombre, dirs in psutil.net_if_addrs().items():
        if nombre == "lo" or nombre.startswith(("veth", "br-", "docker", "virbr", "vmnet")):
            continue
        ipv4 = [d.address for d in dirs if d.family == socket.AF_INET]
        if ipv4 or (stats.get(nombre) and stats[nombre].isup):
            lineas.append(f"{nombre} ({'arriba' if stats.get(nombre) and stats[nombre].isup else 'abajo'}): "
                          f"IP local {', '.join(ipv4) or 'sin IP'}")
    wifi = [l for l in _cmd(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL,RATE", "dev", "wifi", "list", "--rescan", "no"]).splitlines() if l.startswith("yes")]
    if wifi:
        _, ssid, senal, vel = (wifi[0].split(":") + ["", "", "", ""])[:4]
        lineas.append(f"WiFi conectado a '{ssid}' con señal {senal}% ({vel})")
    ruta = _primera_linea(_cmd(["ip", "route", "show", "default"]))
    if ruta:
        lineas.append(f"Ruta por defecto (router): {ruta}")
    try:
        import urllib.request
        publica = urllib.request.urlopen("https://api.ipify.org", timeout=2).read().decode()
        lineas.append(f"IP pública: {publica}")
    except Exception:
        lineas.append("IP pública: no se pudo obtener (¿sin Internet?)")
    io = psutil.net_io_counters()
    lineas.append(f"Tráfico desde el arranque: enviados {_gb(io.bytes_sent)}, recibidos {_gb(io.bytes_recv)}")
    return lineas


def _vivo_bateria():
    try:
        b = psutil.sensors_battery()
    except Exception:
        b = None
    if not b:
        return ["Este equipo no reporta batería"]
    restante = ""
    if b.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) and b.secsleft > 0:
        restante = f", quedan unas {b.secsleft // 3600} h {b.secsleft % 3600 // 60} min"
    return [f"Batería {b.percent:.0f}%, {'conectado al cargador' if b.power_plugged else 'usando batería'}{restante}"]


def _vivo_temperatura():
    lineas = []
    try:
        for chip, sensores in (psutil.sensors_temperatures() or {}).items():
            valores = ", ".join(f"{s.label or chip} {s.current:.0f}°C" for s in sensores[:6])
            lineas.append(f"{chip}: {valores}")
    except Exception:
        pass
    nv = _cmd(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"], timeout=3)
    if nv:
        lineas.append(f"GPU NVIDIA: {nv}°C")
    try:
        for nombre, vent in (psutil.sensors_fans() or {}).items():
            lineas.append(f"Ventilador {nombre}: " + ", ".join(f"{f.current} RPM" for f in vent))
    except Exception:
        pass
    return lineas or ["No hay sensores de temperatura disponibles"]


def _vivo_general():
    arranque = datetime.datetime.fromtimestamp(psutil.boot_time())
    horas = (datetime.datetime.now() - arranque).total_seconds() / 3600
    return [f"Encendido desde {arranque:%Y-%m-%d %H:%M} ({horas:.1f} h)"] + _vivo_ram()[:2] + _vivo_cpu()[:1] + _vivo_disco()[:3]


_TEMAS_VIVO = (
    (r"\bram\b|memoria|swap", _vivo_ram, "RAM"),
    (r"\bcpu\b|procesador|n[uú]cleo|carga", _vivo_cpu, "CPU"),
    (r"proceso|programa.*(abiert|consum|corriendo)|consum|lent|se traba|congela|pesad", _vivo_procesos, "PROCESOS"),
    (r"disco|espacio|almacenamiento|lleno|partici|gigas|\bgb\b", _vivo_disco, "DISCOS"),
    (r"\bgpu\b|gr[aá]fica|nvidia|vram|video", _vivo_gpu, "GPU"),
    (r"\bip\b|\bred\b|wifi|wi-fi|internet|conexi|router|se[nñ]al", _vivo_red, "RED"),
    (r"bater[ií]a|carga(dor|ndo)|enchufad", _vivo_bateria, "BATERÍA"),
    (r"temperatura|calient|calor|grados|ventilador|quema", _vivo_temperatura, "TEMPERATURAS"),
    (r"(estado|c[oó]mo (est[aá]|va)) (de |del )?(mi )?(pc|equipo|sistema|computador|port[aá]til)|rendimiento|uptime|encendid", _vivo_general, "GENERAL"),
)


_PALABRAS_VACIAS = set("""tengo tiene tienes esta está estan están instalado instalada instalados instalar
instalo instala como cómo que qué el la los las un una de del mi mis en mi pc equipo para por con sin si sí no ya
puedo quiero hago hacer funciona funcionando servicio activo activa corriendo programa app aplicacion aplicación
paquete version versión cual cuál donde dónde hay ahora y o me se lo le es son ubuntu linux sistema ver saber""".split())


def _candidatos(pregunta):
    palabras = re.findall(r"[a-záéíóúñ0-9][a-záéíóúñ0-9.+_-]{1,30}", (pregunta or "").lower())
    return [p for p in palabras if p not in _PALABRAS_VACIAS and not p.isdigit()][:3]


def _vivo_programas(pregunta):
    """¿Está instalado X? / ¿Cómo instalo X?: se revisa apt, snap, flatpak y el PATH."""
    lineas = []
    for nombre in _candidatos(pregunta):
        donde = []
        if shutil.which(nombre):
            donde.append(f"ejecutable en {shutil.which(nombre)}")
        if "install ok installed" in _cmd(["dpkg-query", "-W", "-f=${Status}", nombre], timeout=2):
            version = _cmd(["dpkg-query", "-W", "-f=${Version}", nombre], timeout=2)
            donde.append(f"paquete apt instalado (versión {version})")
        snaps = _cmd(["snap", "list", nombre], timeout=3)
        if snaps and "error" not in snaps.lower() and len(snaps.splitlines()) > 1:
            donde.append("snap instalado: " + " ".join(snaps.splitlines()[1].split()[:2]))
        flat = [l for l in _cmd(["flatpak", "list", "--app", "--columns=application,name"], timeout=3).splitlines()
                if nombre in l.lower()]
        if flat:
            donde.append("flatpak instalado: " + flat[0].split()[0])
        if donde:
            lineas.append(f"'{nombre}': SÍ está instalado -> " + "; ".join(donde))
            continue
        # No instalado: ¿de dónde se puede instalar?
        opciones = []
        politica = _cmd(["apt-cache", "policy", nombre], timeout=3)
        m = re.search(r"Candidate:\s*(\S+)", politica)
        if m and m.group(1) != "(none)":
            opciones.append(f"apt (versión {m.group(1)}): sudo apt install {nombre}")
        info = _cmd(["snap", "info", nombre], timeout=4)
        if info.startswith("name:"):
            clasico = "classic" in info
            canal = re.search(r"latest/stable:\s*(\S+)", info)
            opciones.append(f"snap{' (versión ' + canal.group(1) + ')' if canal else ''}: "
                            f"sudo snap install {nombre}{' --classic' if clasico else ''}")
        lineas.append(f"'{nombre}': NO está instalado. " + (
            "Se puede instalar con -> " + " | ".join(opciones) if opciones
            else "No aparece en apt ni en snap con ese nombre exacto (puede estar en flatpak/Flathub o en la web oficial)."))
    return lineas


def _vivo_servicios(pregunta):
    lineas = []
    for nombre in _candidatos(pregunta):
        estado = _cmd(["systemctl", "is-active", nombre], timeout=2)
        if estado and estado != "inactive" or _cmd(["systemctl", "cat", nombre], timeout=2):
            habilitado = _cmd(["systemctl", "is-enabled", nombre], timeout=2)
            lineas.append(f"servicio {nombre}: {estado or 'desconocido'} (arranque automático: {habilitado or '?'})")
            errores = _cmd(["journalctl", "-u", nombre, "-p", "4", "-n", "3", "--no-pager", "-o", "cat"], timeout=3)
            if errores:
                lineas.append(f"avisos/errores recientes de {nombre}: " + " || ".join(e[:110] for e in errores.splitlines()))
    return lineas


def datos_en_vivo(pregunta):
    """Mide ahora mismo los datos de los temas que toca la pregunta. '' si no toca ninguno."""
    bloques, vistos = [], set()
    extras = []
    if re.search(r"instal", pregunta or "", re.IGNORECASE):
        extras.append(("PROGRAMAS", lambda: _vivo_programas(pregunta)))
    if re.search(r"funciona|servicio|activo|corriendo|est[aá] (prendido|encendido)|falla", pregunta or "", re.IGNORECASE):
        extras.append(("SERVICIOS", lambda: _vivo_servicios(pregunta)))
    for titulo, funcion in extras:
        try:
            lineas = [l for l in funcion() if l]
        except Exception:
            continue
        if lineas:
            bloques.append(f"[{titulo}]\n" + "\n".join(f"- {l}" for l in lineas))
    for patron, funcion, titulo in _TEMAS_VIVO:
        if titulo not in vistos and re.search(patron, pregunta or "", re.IGNORECASE):
            vistos.add(titulo)
            try:
                lineas = [l for l in funcion() if l]
            except Exception:
                continue
            bloques.append(f"[{titulo}]\n" + "\n".join(f"- {l}" for l in lineas))
    return "\n".join(bloques)
