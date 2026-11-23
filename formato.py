"""Convierte las respuestas de Tux (markdown sencillo) en HTML para Qt.

Qt solo entiende un subconjunto de HTML/CSS, por eso los bloques de código
se dibujan con tablas. Se usa tanto en la burbuja como en el chat.
"""
import html
import re
from urllib.parse import quote, unquote

import emoji
import riesgo

# Paleta (coherente con el resto de la interfaz)
NARANJA = "#FF7A3D"
TEXTO = "#ECECF1"
TEXTO_SUAVE = "#A0A0B0"
FONDO_CODIGO = "#08080C"
BORDE_CODIGO = "#2A2A36"
FONDO_INLINE = "#262632"
AMBAR = "#F5B544"
ROJO = "#FF5C5C"
MONO = "'JetBrains Mono','Fira Code','Ubuntu Mono','DejaVu Sans Mono',monospace"

_RE_BLOQUE = re.compile(r"```[^\n]*\n(.*?)(?:```|$)", re.DOTALL)
_RE_BLOQUE_LANG = re.compile(r"```([^\n]*)\n(.*?)(?:```|$)", re.DOTALL)
_RE_LINEA_COMANDO = re.compile(r"^\s*`([^`]+)`\s*:?\s*$")
_RE_INLINE = re.compile(r"`([^`\n]+)`")
_RE_NEGRITA = re.compile(r"\*\*(.+?)\*\*")
_RE_VINETA = re.compile(r"^\s*[-*•]\s+(.*)$")
_RE_NUMERO = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")


def _inline(texto):
    """Escapa HTML y aplica `código` y **negrita** dentro de una línea.

    Cada `código` es un enlace «copiartxt:»: un clic lo copia al portapapeles.
    """
    partes = []
    ultimo = 0
    for m in _RE_INLINE.finditer(texto):
        partes.append(_negrita(html.escape(texto[ultimo:m.start()])))
        partes.append(
            f'<a href="copiartxt:{quote(m.group(1))}" style="text-decoration:none; color:{NARANJA};">'
            f'<span style="font-family:{MONO}; background-color:{FONDO_INLINE}; '
            f'color:{NARANJA};">&nbsp;{html.escape(m.group(1))}&nbsp;</span></a>'
        )
        ultimo = m.end()
    partes.append(_negrita(html.escape(texto[ultimo:])))
    return "".join(partes)


def _negrita(texto_escapado):
    """**negrita** y emojis a color (Qt 5 no dibuja la fuente de emojis)."""
    return emoji.a_html(_RE_NEGRITA.sub(r"<b>\1</b>", texto_escapado))


def _tarjeta_codigo(codigo, indice, con_copiar=True, prompt=True):
    """Bloque estilo terminal: '$' naranja, monoespaciado y enlace Copiar."""
    lineas = [l for l in codigo.strip("\n").split("\n")]
    signo = f'<span style="color:{NARANJA};">$</span>&nbsp;' if prompt else ""
    cuerpo = "<br>".join(
        f'{signo}<span style="color:{TEXTO};">{html.escape(l).replace(" ", "&nbsp;")}</span>'
        for l in lineas
    )
    # Semáforo de riesgo en la tarjeta (solo si hay algo de qué avisar)
    insignia = ""
    if prompt:
        nivel = riesgo.analizar(codigo)["nivel"]
        if nivel == riesgo.ROJO:
            insignia = f'<span style="color:{ROJO}; font-size:9pt; font-weight:600;">● peligroso</span><br>'
        elif nivel == riesgo.AMARILLO:
            insignia = f'<span style="color:{AMBAR}; font-size:9pt;">● cuidado</span><br>'
    copiar = (
        f'<td align="right" valign="top" style="padding:6px 8px 0 0;">{insignia}'
        f'<a href="copiar:{indice}" style="color:{TEXTO_SUAVE}; text-decoration:none; '
        f'font-size:9pt;">⧉ Copiar</a></td>'
        if con_copiar else (f'<td align="right" valign="top" style="padding:6px 8px 0 0;">{insignia}</td>' if insignia else "")
    )
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" '
        f'style="background-color:{FONDO_CODIGO}; border:1px solid {BORDE_CODIGO}; '
        f'margin-top:6px; margin-bottom:6px;"><tr>'
        f'<td style="padding:8px 10px; font-family:{MONO}; font-size:10.5pt;">{cuerpo}</td>'
        f"{copiar}</tr></table>"
    )


def _aviso(texto):
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" style="margin-top:6px; margin-bottom:4px;">'
        f'<tr><td width="3" style="background-color:{AMBAR};"></td>'
        f'<td style="padding:6px 10px; background-color:#2A2216; color:#F7D9A4;">{_inline(texto)}</td>'
        f"</tr></table>"
    )


def extraer_comandos(texto):
    """Lista de comandos (bloques ``` y líneas que son solo `comando`), en orden."""
    comandos = []

    def _guardar(m):
        if m.group(1).strip().lower() == "texto":  # bloques informativos: no son comandos
            return ""
        comandos.append(m.group(2).strip())
        return "\x00"
    resto = _RE_BLOQUE_LANG.sub(_guardar, texto)
    salida = []
    i = 0
    for linea in resto.split("\n"):
        if "\x00" in linea:
            salida.append(comandos[i]); i += 1
            continue
        m = _RE_LINEA_COMANDO.match(linea)
        if m:
            salida.append(m.group(1).strip())
    return salida


def md_a_html(texto, con_copiar=True):
    """Markdown sencillo → HTML de Qt. Devuelve (html, comandos)."""
    texto = (texto or "").strip()
    comandos = []

    # 1) Bloques ``` se sustituyen por marcadores para no tocar su contenido
    bloques = []
    def _guardar(m):
        bloques.append((m.group(1).strip().lower(), m.group(2)))
        return f"\x00{len(bloques) - 1}\x00"
    texto = _RE_BLOQUE_LANG.sub(_guardar, texto)

    piezas = []
    parrafo = []

    def cerrar_parrafo():
        if parrafo:
            piezas.append(
                f'<p style="margin:0 0 8px 0; line-height:135%;">{"<br>".join(parrafo)}</p>'
            )
            parrafo.clear()

    for linea in texto.split("\n"):
        marcador = re.fullmatch(r"\s*\x00(\d+)\x00\s*", linea)
        if marcador:
            cerrar_parrafo()
            lang, codigo = bloques[int(marcador.group(1))]
            if lang == "texto":  # información, no comandos: sin '$' ni Copiar
                piezas.append(_tarjeta_codigo(codigo, -1, False, prompt=False))
                continue
            comandos.append(codigo.strip())
            piezas.append(_tarjeta_codigo(codigo, len(comandos) - 1, con_copiar))
            continue

        cmd = _RE_LINEA_COMANDO.match(linea)
        if cmd:
            cerrar_parrafo()
            comandos.append(cmd.group(1).strip())
            piezas.append(_tarjeta_codigo(cmd.group(1), len(comandos) - 1, con_copiar))
            continue

        if not linea.strip():
            cerrar_parrafo()
            continue

        if linea.lstrip().startswith(("⚠️", "⚠")):
            cerrar_parrafo()
            piezas.append(_aviso(linea.strip()))
            continue

        vin = _RE_VINETA.match(linea) or _RE_NUMERO.match(linea)
        if vin:
            contenido = vin.group(vin.lastindex)
            simbolo = f"{vin.group(1)}." if vin.re is _RE_NUMERO else "•"
            parrafo.append(
                f'&nbsp;&nbsp;<span style="color:{NARANJA};">{simbolo}</span>&nbsp;{_inline(contenido)}'
            )
            continue

        parrafo.append(_inline(linea.strip()))

    cerrar_parrafo()
    cuerpo = "".join(piezas) or "&nbsp;"
    return f'<div style="color:{TEXTO};">{cuerpo}</div>', comandos


def resumen(texto, max_chars=170):
    """Primera idea de la respuesta (hasta el final de una frase) para la burbuja."""
    limpio = _RE_BLOQUE.sub("\n\n", texto or "")
    # Solo el primer párrafo de texto (se detiene en línea vacía, comando, viñeta o aviso)
    lineas = []
    for l in limpio.split("\n"):
        l = l.strip()
        especial = _RE_LINEA_COMANDO.match(l) or l.startswith(("⚠", "-", "*", "•"))
        if not l or especial:
            if lineas:
                break
            continue
        lineas.append(l)
    plano = " ".join(lineas)
    if len(plano) <= max_chars:
        return plano, False
    corte = plano[:max_chars]
    fin = max(corte.rfind(". "), corte.rfind("? "), corte.rfind("! "), corte.rfind(": "))
    if fin > 60:
        return corte[:fin + 1], True
    return corte[:corte.rfind(" ")] + "…", True


def texto_de_enlace(href):
    """Texto a copiar de un enlace «copiartxt:…» (o None)."""
    return unquote(href[len("copiartxt:"):]) if href.startswith("copiartxt:") else None
