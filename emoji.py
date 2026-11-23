"""Emojis a color dentro de Qt 5.

Qt 5 no dibuja la fuente Noto Color Emoji (salen cajitas). Aquí cada emoji se
convierte una sola vez en un PNG pequeño (~2 KB) con Pillow, se guarda en caché
y se inserta en el HTML como <img>. Si Pillow o la fuente faltan, el emoji se
quita para no mostrar cajitas.
"""
import hashlib
import os
import re
from pathlib import Path

FUENTE = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "tux-assistant" / "emoji"
TAM_PNG = 40  # px del PNG guardado (se muestra a ~16-18 px; nítido en pantallas HiDPI)

# Secuencias de emoji: base + modificadores de tono + selector de variación + uniones ZWJ + teclas 1️⃣
_BASE = (r"[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌀-⏿←-⇿〰〽"
         r"㊗㊙©®‼⁉™ℹⓂ▪-◾⤴⤵]")
_MOD = r"[\U0001F3FB-\U0001F3FF]?️?"
RE_EMOJI = re.compile(
    rf"(?:[0-9#*]️?⃣)|(?:[\U0001F1E6-\U0001F1FF]{{2}})|(?:{_BASE}{_MOD}(?:‍{_BASE}{_MOD})*)"
)
# Símbolos que la fuente normal sí tiene: se dejan como texto (se ven bien y heredan el color)
_COMO_TEXTO = set("●•›‹▰▱✓✕⧉←→↑↓▸▾")

_fuente = None
_disponible = None


def _cargar_fuente():
    global _fuente, _disponible
    if _disponible is None:
        try:
            from PIL import ImageFont
            _fuente = ImageFont.truetype(FUENTE, 109)
            _disponible = True
        except Exception:
            _disponible = False
    return _disponible


def ruta_png(e):
    """PNG en caché para el emoji e (lo crea si no existe). None si no se puede."""
    if not _cargar_fuente():
        return None
    nombre = hashlib.md5(e.encode("utf-8")).hexdigest()[:12] + ".png"
    ruta = CACHE / nombre
    if ruta.exists():
        return ruta
    try:
        from PIL import Image, ImageDraw
        lienzo = Image.new("RGBA", (160, 136), (0, 0, 0, 0))
        ImageDraw.Draw(lienzo).text((4, 0), e, font=_fuente, embedded_color=True)
        caja = lienzo.getbbox()
        if not caja:
            return None
        img = lienzo.crop(caja)
        lado = max(img.size)
        cuadrado = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
        cuadrado.paste(img, ((lado - img.width) // 2, (lado - img.height) // 2))
        CACHE.mkdir(parents=True, exist_ok=True)
        cuadrado.resize((TAM_PNG, TAM_PNG), Image.LANCZOS).save(ruta, optimize=True)
        return ruta
    except Exception:
        return None


def a_html(texto, tam=17):
    """Reemplaza emojis (en texto YA escapado para HTML) por <img> a color."""
    def _img(m):
        e = m.group(0)
        if e in _COMO_TEXTO:
            return e
        ruta = ruta_png(e)
        if not ruta:
            return ""
        return f'<img src="{ruta.as_posix()}" width="{tam}" height="{tam}" style="vertical-align:middle;">'
    return RE_EMOJI.sub(_img, texto)


def quitar(texto):
    """Quita emojis (para widgets de texto plano donde no caben imágenes)."""
    return re.sub(r"\s{2,}", " ", RE_EMOJI.sub(lambda m: m.group(0) if m.group(0) in _COMO_TEXTO else "", texto)).strip()


def icono(e, tam=18):
    """QIcon con el emoji (para botones/menús)."""
    from PyQt5.QtGui import QIcon
    ruta = ruta_png(e)
    return QIcon(str(ruta)) if ruta else QIcon()
