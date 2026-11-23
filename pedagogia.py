"""Capa pedagógica y gestor de contexto mínimo para Tux Assistant.

Ponlo en la misma carpeta que main.py. No ejecuta nada en el sistema:
solo arma el prompt y recoge un contexto pequeño y no sensible.
"""
import datetime
import json
import os
import platform
import re
import shutil
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "tux-assistant" / "config.json"
# Estilo de explicación (lo elige el usuario; no es lo mismo que su nivel de conocimiento, que se gana con XP)
NIVELES = ("principiante", "intermedio", "avanzado", "experto")
NIVEL_POR_DEFECTO = "principiante"


# ---------- Nivel del usuario (adaptación del nivel de detalle) ----------

def cargar_nivel():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            nivel = json.load(f).get("nivel", NIVEL_POR_DEFECTO)
        return nivel if nivel in NIVELES else NIVEL_POR_DEFECTO
    except (OSError, ValueError, AttributeError):
        return NIVEL_POR_DEFECTO


def guardar_nivel(nivel):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"nivel": nivel}, f)


def detectar_cambio_nivel(texto):
    """Devuelve el nivel si el usuario escribe algo como 'nivel avanzado'."""
    m = re.search(r"\bnivel\s+(principiante|intermedio|avanzado|experto)\b", texto.lower())
    return m.group(1) if m else None


_PATRON_IDENTIDAD = re.compile(
    r"\b(qui[eé]n|qu[eé])\s+eres(\s+t[uú])?\W*$|c[oó]mo\s+te\s+llamas|qui[eé]n\s+te\s+(cre[oó]|hizo|program[oó])",
    re.IGNORECASE,
)


def respuesta_identidad(texto):
    """Respuesta fija para '¿quién eres?' / '¿quién te creó?' (los modelos pequeños divagan aquí)."""
    if not _PATRON_IDENTIDAD.search(texto or ""):
        return None
    return (
        "Soy Tux 🐧, tu acompañante para aprender Linux desde el escritorio. "
        "Te explico comandos, errores y conceptos a tu ritmo, sin ejecutar nada por ti. "
        "Puedo armarte un plan de estudio con misiones, analizar si un comando es peligroso "
        "(«analiza <comando>») y explicarte los errores de tu terminal («activar terminal»).\n\n"
        "Me creó un equipo de estudiantes de Ingeniería de la Universidad El Bosque; el dibujo original del pingüino es de Larry Ewing.\n"
        "Escribe «nivel principiante», «nivel intermedio» o «nivel avanzado» para ajustar cuánto detalle te doy."
    )


# ---------- Gestor de contexto (mínimo, sin datos sensibles) ----------

def obtener_contexto_minimo():
    """Solo lo necesario para que una respuesta sirva en ESTA distribución.

    No incluye hostname, IPs, procesos, discos ni nada de /home
    (eso se agrega aparte, solo cuando la pregunta lo necesita).
    """
    ctx = {}
    try:
        ctx["distribucion"] = platform.freedesktop_os_release().get("PRETTY_NAME", "desconocida")
    except OSError:
        ctx["distribucion"] = platform.platform()
    ctx["kernel"] = platform.release()
    ctx["fecha_hora"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ctx["escritorio"] = os.environ.get("XDG_CURRENT_DESKTOP", "desconocido")
    ctx["sesion"] = os.environ.get("XDG_SESSION_TYPE", "desconocida")
    ctx["shell"] = os.path.basename(os.environ.get("SHELL", "desconocida"))
    for gestor in ("apt", "dnf", "pacman", "zypper"):
        if shutil.which(gestor):
            ctx["gestor_paquetes"] = gestor
            break
    return ctx


def _formatear_contexto(ctx):
    return "\n".join(f"- {k}: {v}" for k, v in ctx.items())


# ---------- Capa pedagógica ----------

INSTRUCCIONES_NIVEL = {
    "principiante": (
        "Principiante: palabras simples, define cada término técnico la primera vez, "
        "no asumas que conoce la terminal. Si das un comando, explica cada parte en pocas palabras."
    ),
    "intermedio": (
        "Intermedio: no definas lo elemental; explica el porqué y solo las opciones menos obvias."
    ),
    "avanzado": (
        "Avanzado: directo, solución y motivo técnico, sin definir conceptos básicos."
    ),
    "experto": (
        "Experto: habla de colega a colega. Ve al detalle interno (kernel, systemd, syscalls, /proc, /sys), "
        "menciona alternativas, casos límite y la página de man o el archivo de configuración exacto. Sin definiciones."
    ),
}

# Líneas objetivo y tope duro de tokens por nivel (respuestas ágiles por defecto)
LINEAS_POR_NIVEL = {"principiante": 7, "intermedio": 5, "avanzado": 3, "experto": 5}
TOKENS_POR_NIVEL = {"principiante": 350, "intermedio": 260, "avanzado": 200, "experto": 300}
FACTOR_DETALLE = 3  # cuando el usuario pide explícitamente más detalle

PATRON_DETALLE = re.compile(
    r"(expl[ií]ca(me)?\s+(m[aá]s|mejor|a fondo|bien)|m[aá]s\s+detalle|paso\s+a\s+paso|"
    r"en\s+detalle|profundiza|ampl[ií]a|no\s+entend[ií]|^\s*(sigue|contin[uú]a)\b)",
    re.IGNORECASE,
)


def pide_mas_detalle(texto):
    """True si el usuario pide una explicación más larga ('explícame más', 'paso a paso'...)."""
    return bool(PATRON_DETALLE.search(texto or ""))


def max_tokens(nivel, detalle=False):
    base = TOKENS_POR_NIVEL.get(nivel, TOKENS_POR_NIVEL[NIVEL_POR_DEFECTO])
    return base * FACTOR_DETALLE if detalle else base


def construir_system_prompt(nivel, contexto, usuario, detalle=False):
    instr_nivel = INSTRUCCIONES_NIVEL.get(nivel, INSTRUCCIONES_NIVEL[NIVEL_POR_DEFECTO])
    if detalle:
        largo = "El usuario pidió más detalle: explica paso a paso, pero sin relleno."
    else:
        lineas = LINEAS_POR_NIVEL.get(nivel, 7)
        largo = (f"MÁXIMO {lineas} líneas. Ve al grano. Si el tema da para más, termina con: "
                 "«¿Quieres que te lo explique más a fondo?»")
    return f"""Eres Tux 🐧, acompañante pedagógico en el escritorio Linux de {usuario}. Respondes en español, cercano.
Meta: que el usuario ENTIENDA y gane autonomía, no solo resolverle la tarea.

FORMATO (obligatorio):
- Sin saludos, sin repetir la pregunta, sin despedidas ni resumen final. No numeres las partes.
- Empieza explicando qué pasa y por qué (1-2 frases). Luego el comando solo en su propia línea, rodeado de
  acentos graves, y debajo una viñeta por cada parte. Prefiere herramientas actuales (apt sobre apt-get, ss sobre netstat).
- SOLO si el comando es riesgoso (sudo que borra o modifica el sistema, rm, chmod/chown -R, dd): una línea
  "⚠️" con el riesgo y cómo verificar antes. Si no hay riesgo real, no escribas ninguna advertencia.
- Si enseñaste un concepto nuevo, cierra con UNA pregunta corta para comprobar que lo entendió.
- {largo}

EJEMPLO de respuesta bien hecha (imita el estilo, no el contenido):
El archivo no tiene permiso de ejecución, por eso Linux no te deja correrlo como programa.
`chmod +x script.sh`
- `chmod`: cambia los permisos de un archivo.
- `+x`: añade el permiso de ejecución.
- `script.sh`: el archivo al que se lo das.
Después ya puedes correrlo con `./script.sh`. ¿Sabes qué significa el `./` del inicio?

HERRAMIENTA: tienes consultar_sistema para ver datos reales del equipo con comandos de solo lectura.
Úsala SIEMPRE que la respuesta dependa de algo que no esté en el contexto: si un programa está instalado
(dpkg -s, snap list, flatpak list, which), versiones, estado de servicios (systemctl status), logs (journalctl),
archivos de configuración, red o hardware. No adivines: consulta y responde con lo que salió.
Un comando por consulta (puedes hacer varias). Nunca menciones la herramienta ni su nombre al usuario.
REGLAS: Solo CONSULTAS; nunca instalas ni cambias nada, ni digas que lo hiciste. Los comandos que modifican el
sistema se los das al usuario para que él los ejecute. Si no estás seguro, dilo; no inventes comandos, rutas ni opciones. Usa la distribución y el gestor de paquetes del contexto. Si pegan un error,
explica qué significa antes de la solución.

NIVEL: {instr_nivel}

CONTEXTO DEL EQUIPO DEL USUARIO (datos reales, solo lectura). Úsalos para dar comandos y rutas correctos
para ESTE sistema (distribución, gestor de paquetes, GPU, escritorio, Wayland/X11...). No los recites ni
hagas listas de ellos salvo que el usuario pregunte por su equipo; en ese caso responde con los datos exactos.
Mira siempre DATOS CLAVE y ALERTAS AHORA (al final): si una alerta tiene que ver con la pregunta, menciónala
con su valor. Para principiantes, si hay una forma gráfica o un atajo del escritorio (p. ej. tecla Impr Pant
en GNOME, Centro de Software, Configuración), dila primero y luego el comando.
{contexto if isinstance(contexto, str) else _formatear_contexto(contexto)}

FUNCIONES DE TUX (si preguntan qué puedes hacer): planes de estudio con misiones que compruebas en su equipo
(«＋ Nuevo plan de estudio» en el selector del chat o escribir «quiero aprender…»); semáforo de riesgo de un comando
(«analiza <comando>»); explicar comandos que fallan en la terminal («activar terminal»); niveles («nivel avanzado»);
ver lo que sabes del equipo («qué sabes de mi pc»).

IDENTIDAD: te llamas Tux. Habla siempre como Tux; no te describas como herramienta ni como modelo de lenguaje.
Solo si preguntan quién te creó: un equipo de estudiantes de Ingeniería de la Universidad El Bosque; el dibujo original del pingüino es de Larry Ewing. Nunca nombres a una sola persona como creadora."""
