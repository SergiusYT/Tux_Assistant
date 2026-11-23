"""Componentes visuales del «Cuaderno de Tux» (no es un chat de burbujas).

- Las respuestas son TARJETAS con secciones: qué pasa, comando desarmado
  (cada parte con su etiqueta debajo), avisos, pregunta de comprobación con
  botones y pie de transparencia (qué datos del equipo se usaron).
- Ruta: mapa de nodos del plan de estudio.
- Progreso: nivel, misiones y ajustes.
"""
import html
import re

from PyQt5.QtCore import Qt, QRect, QRectF, QSize, QPoint, QPointF, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QCursor
from PyQt5.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QLayout, QLineEdit, QPushButton,
                             QScrollArea, QSizePolicy, QToolTip, QVBoxLayout, QWidget)

import emoji
import riesgo
from formato import md_a_html, _inline, texto_de_enlace, NARANJA, TEXTO, TEXTO_SUAVE, AMBAR, ROJO

FONDO = "#0E0E14"
TARJETA = "#16161F"
BORDE = "#262633"
VERDE = "#4ADE80"
MONO = "JetBrains Mono, Fira Code, Ubuntu Mono, DejaVu Sans Mono"
SANS = "Inter, Ubuntu, Noto Sans, sans-serif"
COLORES_TOKEN = ["#FF7A3D", "#4FD1C5", "#B794F4", "#68D391", "#F687B3", "#63B3ED", "#F6E05E"]


def rich(texto, tam=17):
    """Texto plano → HTML con emojis a color."""
    return emoji.a_html(html.escape(texto or ""), tam)


def etiqueta_seccion(texto, color=NARANJA):
    lbl = QLabel(texto.upper())
    f = QFont()
    f.setPointSizeF(8.5)
    f.setBold(True)
    f.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color:{color}; background:transparent;")
    return lbl


def boton(texto, primario=False, pequeno=False):
    b = QPushButton(texto)
    b.setCursor(Qt.PointingHandCursor)
    alto = 24 if pequeno else 28
    b.setFixedHeight(alto)
    if primario:
        estilo = (f"QPushButton {{ background:{NARANJA}; color:#141418; border:none; border-radius:{alto // 2}px;"
                  f" padding:0 14px; font-weight:700; font-size:10pt; }}"
                  f"QPushButton:hover {{ background:#FF9461; }}")
    else:
        estilo = (f"QPushButton {{ background:transparent; color:{TEXTO}; border:1px solid #34344A;"
                  f" border-radius:{alto // 2}px; padding:0 12px; font-size:10pt; }}"
                  f"QPushButton:hover {{ border-color:{NARANJA}; color:#FFFFFF; }}")
    b.setStyleSheet(estilo)
    return b


def etiqueta_rich(html_txt, tam_pt=10.5, color=TEXTO):
    lbl = QLabel()
    lbl.setTextFormat(Qt.RichText)
    lbl.setWordWrap(True)
    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
    lbl.setOpenExternalLinks(False)
    lbl.setText(html_txt)
    lbl.setStyleSheet(f"color:{color}; font-size:{tam_pt}pt; background:transparent; font-family:{SANS};")
    lbl.linkActivated.connect(lambda href, l=lbl: _copiar_enlace(href, l))
    return lbl


def _copiar_enlace(href, widget):
    """Clic en un `código` del texto → se copia."""
    txt = texto_de_enlace(href)
    if txt:
        QApplication.clipboard().setText(txt)
        QToolTip.showText(QCursor.pos(), f"Copiado: {txt}", widget)


# ---------- Flow layout (las partes del comando se acomodan en varias filas) ----------

class FlowLayout(QLayout):
    def __init__(self, parent=None, espacio_h=10, espacio_v=8):
        super().__init__(parent)
        self._items = []
        self._h, self._v = espacio_h, espacio_v
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._acomodar(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._acomodar(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _acomodar(self, rect, solo_medir):
        x, y, alto_fila = rect.x(), rect.y(), 0
        for it in self._items:
            hint = it.sizeHint()
            if x + hint.width() > rect.right() + 1 and alto_fila > 0:
                x, y = rect.x(), y + alto_fila + self._v
                alto_fila = 0
            if not solo_medir:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._h
            alto_fila = max(alto_fila, hint.height())
        return y + alto_fila - rect.y()


# ---------- Comando desarmado ----------

class ParteComando(QWidget):
    """Un token del comando, subrayado en color, con su significado debajo."""

    def __init__(self, token, explicacion, color):
        super().__init__()
        self.setAttribute(Qt.WA_StyledBackground, False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        t = QLabel(html.escape(token))
        t.setStyleSheet(f"color:{color}; font-family:{MONO}; font-size:11pt; font-weight:700; background:transparent;")
        barra = QFrame()
        barra.setFixedHeight(2)
        barra.setStyleSheet(f"background:{color}; border:none;")
        lay.addWidget(t)
        lay.addWidget(barra)
        ancho = max(t.sizeHint().width(), 64)
        if explicacion:
            e = QLabel(rich(explicacion, 12))
            e.setTextFormat(Qt.RichText)
            e.setWordWrap(True)
            e.setStyleSheet(f"color:{TEXTO_SUAVE}; font-size:9pt; background:transparent;")
            ancho = max(ancho, min(118, max(64, len(explicacion) * 3)))
            e.setFixedWidth(ancho)
            lay.addWidget(e)
        t.setMinimumWidth(min(ancho, t.sizeHint().width()))
        self.setFixedWidth(ancho)
        lay.addStretch()


def caja_desplazable(html_txt, color_borde="#22222E", fondo="#050507"):
    """Texto monoespaciado SIN cortes de línea, con desplazamiento lateral si es largo.

    Así un comando o una salida larga se ven completos y no ensanchan la tarjeta.
    """
    lbl = QLabel(html_txt)
    lbl.setTextFormat(Qt.RichText)
    lbl.setWordWrap(False)
    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    lbl.setStyleSheet("background:transparent; padding:0;")
    scroll = QScrollArea()
    scroll.setWidget(lbl)
    scroll.setWidgetResizable(True)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
    scroll.setMinimumWidth(40)
    scroll.setFixedHeight(lbl.sizeHint().height() + 12)  # espacio para la barra lateral fina
    scroll.setStyleSheet(
        "QScrollArea, QScrollArea > QWidget > QWidget { background:transparent; }"
        "QScrollBar:horizontal { background:transparent; height:6px; margin:0; }"
        "QScrollBar::handle:horizontal { background:#3A3A50; border-radius:3px; min-width:24px; }"
        f"QScrollBar::handle:horizontal:hover {{ background:{NARANJA}; }}"
        "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }")
    return scroll


class BloqueComando(QWidget):
    """Comando: cabecera con semáforo, partes explicadas (fuera de la terminal) y terminal con Copiar."""

    def __init__(self, comando, partes):
        super().__init__()
        self.comando = comando
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(8)

        cab = QHBoxLayout()
        cab.setSpacing(6)
        cab.addWidget(etiqueta_seccion("Comando", TEXTO_SUAVE))
        cab.addStretch()
        nivel = riesgo.analizar(comando)["nivel"]
        color, texto = {riesgo.VERDE: (VERDE, "seguro"), riesgo.AMARILLO: (AMBAR, "cuidado"),
                        riesgo.ROJO: (ROJO, "peligroso")}[nivel]
        pill = QLabel(f"● {texto}")
        pill.setStyleSheet(f"color:{color}; font-size:9pt; font-weight:600; background:transparent;")
        pill.setToolTip("Semáforo de riesgo: lo calcula Tux con reglas fijas, no la IA")
        cab.addWidget(pill)
        lay.addLayout(cab)

        # 1) Cada parte con su significado, sobre la tarjeta (fuera de la terminal)
        if partes:
            cont = QWidget()
            flow = FlowLayout(cont, 12, 10)
            for i, (tok, exp) in enumerate(partes):
                flow.addWidget(ParteComando(tok, exp, COLORES_TOKEN[i % len(COLORES_TOKEN)]))
            lay.addWidget(cont)
        # 2) La terminal: solo el comando, completo (desplazable) y con Copiar
        lay.addWidget(self._linea_terminal(comando))

    def _linea_terminal(self, comando):
        caja = QFrame()
        caja.setObjectName("terminal")
        caja.setStyleSheet("#terminal { background:#050507; border:1px solid #26263A; border-radius:8px; }")
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(10, 7, 6, 3)
        fila.setSpacing(8)
        lineas = "<br>".join(
            f'<span style="color:{VERDE};">❯</span>&nbsp;<span style="color:#E8E8E8;">{html.escape(l).replace(" ", "&nbsp;")}</span>'
            for l in comando.split("\n"))
        texto = caja_desplazable(f'<span style="font-family:{MONO}; font-size:10pt;">{lineas}</span>')
        copiar = QPushButton("⧉ Copiar")
        copiar.setCursor(Qt.PointingHandCursor)
        copiar.setFixedHeight(24)
        copiar.setStyleSheet(f"QPushButton {{ background:#1A1A24; color:{TEXTO}; border:1px solid #2E2E3E; border-radius:6px;"
                             f" padding:0 8px; font-size:9.5pt; }} QPushButton:hover {{ border-color:{NARANJA}; color:#FFFFFF; }}")
        copiar.clicked.connect(lambda: (self._copiar(), copiar.setText("✓ Copiado")))
        fila.addWidget(texto, 1)
        fila.addWidget(copiar, 0, Qt.AlignTop)
        return caja

    def _copiar(self):
        QApplication.clipboard().setText(self.comando)
        QToolTip.showText(QCursor.pos(), "Copiado ✓", self)


def bloque_salida(texto):
    """Salida o ejemplo (no es un comando): sin semáforo ni Copiar, con desplazamiento lateral."""
    caja = QFrame()
    caja.setObjectName("salida")
    caja.setStyleSheet("#salida { background:#0A0A0F; border:1px solid #22222E; border-radius:8px; }")
    lay = QVBoxLayout(caja)
    lay.setContentsMargins(10, 6, 8, 3)
    lay.setSpacing(2)
    lay.addWidget(etiqueta_seccion("Salida de ejemplo", "#6E6E82"))
    contenido = "<br>".join(html.escape(l).replace(" ", "&nbsp;") for l in texto.split("\n")[:30])
    lay.addWidget(caja_desplazable(f'<span style="font-family:{MONO}; font-size:9.5pt; color:{TEXTO_SUAVE};">{contenido}</span>'))
    return caja


def es_comando(texto):
    """¿El bloque es algo que se ejecuta, o es una salida/ejemplo?"""
    import shutil
    primera = (texto or "").strip().split("\n")[0].split()
    if not primera:
        return False
    prog = primera[1] if primera[0] == "sudo" and len(primera) > 1 else primera[0]
    prog = prog.lstrip("$").strip() or (primera[1] if len(primera) > 1 else "")
    return (prog in riesgo.PROGRAMAS or prog.startswith(("./", "/", "~/")) or shutil.which(prog) is not None
            or bool(re.fullmatch(r"[\w.-]+=.*", prog)))


# ---------- Tarjeta de respuesta ----------

_RE_LINEA_CMD = re.compile(r"^\s*`([^`]+)`\s*:?\s*$")
_RE_BLOQUE = re.compile(r"```([^\n]*)\n(.*?)(?:```|$)", re.DOTALL)
_RE_VINETA_PARTE = re.compile(r"^\s*[-*•]\s+`([^`]+)`\s*[:=—–-]\s*(.+)$")
_RE_SEMAFORO = re.compile(r"^\*\*(🟢|🟡|🔴)\s*(.+?)\*\*\s*$")


def _partes_de(cmd, explicaciones):
    """Une las viñetas del modelo («- `tok`: qué hace») con los tokens del comando."""
    try:
        import shlex
        tokens = shlex.split(cmd)
    except ValueError:
        tokens = cmd.split()
    if not tokens or len(tokens) > 9 or "\n" in cmd:
        return None
    por_regla = dict(riesgo.explicar_partes(cmd))
    partes = []
    for tok in tokens:
        exp = explicaciones.get(tok)
        if exp is None:
            exp = next((v for k, v in explicaciones.items() if tok in k.split()), None)
        if exp is None:
            exp = por_regla.get(tok, "")
        exp = re.sub(r"\s+", " ", exp).strip().rstrip(".")
        if len(exp) > 60:
            exp = exp[:57].rsplit(" ", 1)[0] + "…"
        partes.append((tok, exp))
    return partes


def _ya_desarmado(token, secciones):
    for sec in secciones:
        if sec[0] == "comando" and sec[2]:
            toks = {t for t, _ in sec[2]}
            if token in toks or all(t in toks for t in token.split()):
                return True
    return False


def analizar_respuesta(texto):
    """Texto de Tux → lista de secciones [(tipo, datos...)]."""
    texto = (texto or "").strip()
    secciones = []
    if texto.startswith("🎯"):
        return [("mision", texto)]
    if texto.startswith(("✅", "❌")):
        return [("estado", "ok" if texto.startswith("✅") else "error", texto)]
    if texto.startswith("💥"):
        resto = re.sub(r"^💥\s*", "", texto)
        extras, lineas = [], []
        for l in resto.split("\n"):
            if l.startswith("🎓"):
                m = re.search(r"«(.+?)»", l)
                datos = re.search(r"⟦(.+?)⟧", l)
                cmd = re.search(r"Falló `([^`]+)`", resto)
                if m:
                    carga = f"{datos.group(1) if datos else m.group(1)}|{cmd.group(1) if cmd else ''}"
                    extras.append(("accion", f"Aprende a evitarlo: {m.group(1)}", f"aprender:{carga}"))
            elif l.startswith("🔁"):
                extras.insert(0, ("aviso", l.lstrip("🔁 ").strip()))
            else:
                lineas.append(l)
        return ([("titulo", "Falló un comando en tu terminal", ROJO)] + analizar_respuesta("\n".join(lineas))
                + [e for e in extras if e[0] == "aviso"]
                + [("accion", "Explícame más", "explicar_error")] + [e for e in extras if e[0] == "accion"])

    bloques = []
    texto = _RE_BLOQUE.sub(lambda m: (bloques.append((m.group(1).strip().lower(), m.group(2).strip())),
                                      f"\x00{len(bloques) - 1}\x00")[1], texto)
    lineas = texto.split("\n")

    # Viñetas que explican partes de un comando: se usan como etiquetas del comando desarmado
    explicaciones = {}
    for l in lineas:
        m = _RE_VINETA_PARTE.match(l)
        if m:
            explicaciones[m.group(1).strip()] = m.group(2).strip()

    parrafo = []

    def cerrar():
        if parrafo:
            secciones.append(("texto", "\n".join(parrafo)))
            parrafo.clear()

    for l in lineas:
        s = l.strip()
        marcador = re.fullmatch(r"\x00(\d+)\x00", s)
        if marcador:
            cerrar()
            lang, cod = bloques[int(marcador.group(1))]
            if lang == "texto" or not es_comando(cod):
                secciones.append(("info", cod))
            else:
                secciones.append(("comando", cod, _partes_de(cod, explicaciones)))
            continue
        sem = _RE_SEMAFORO.match(s)
        if sem:
            cerrar()
            secciones.append(("semaforo", {"🟢": riesgo.VERDE, "🟡": riesgo.AMARILLO, "🔴": riesgo.ROJO}[sem.group(1)]))
            continue
        cmd = _RE_LINEA_CMD.match(l)
        if cmd:
            cerrar()
            secciones.append(("comando", cmd.group(1).strip(), _partes_de(cmd.group(1).strip(), explicaciones)))
            continue
        vin = _RE_VINETA_PARTE.match(l)
        if vin and _ya_desarmado(vin.group(1).strip(), secciones):
            continue  # ya se ve como etiqueta en el comando desarmado
        if s.startswith(("🔎 Revisé", "📊 Medí")):
            cerrar()
            secciones.append(("transparencia", s))
            continue
        if s.startswith("(Dime «explícame más»"):
            cerrar()
            secciones.append(("continuar",))
            continue
        if s.startswith(("⚠️", "⚠")):
            cerrar()
            secciones.append(("aviso", s.lstrip("⚠️ ").strip()))
            continue
        if not s:
            cerrar()
            continue
        parrafo.append(l)
    cerrar()

    # La última frase con «?» se convierte en pregunta de comprobación con botones
    for i in range(len(secciones) - 1, -1, -1):
        tipo = secciones[i][0]
        if tipo in ("transparencia", "continuar"):
            continue
        if tipo == "texto":
            partes = secciones[i][1].rstrip()
            if partes.endswith("?"):
                # Se ignoran los puntos dentro de `código` al buscar dónde empieza la última frase
                tapado = re.sub(r"`[^`]*`", lambda m: "x" * len(m.group(0)), partes)
                cortes = [m.end() for m in re.finditer(r"[.!:\n]\s+", tapado)]
                inicio = cortes[-1] if cortes else 0
                antes, pregunta = partes[:inicio].strip(), partes[inicio:].strip()
            else:
                pregunta = ""
            if pregunta and len(pregunta) < 220:
                nuevas = ([("texto", antes)] if antes else []) + [("pregunta", pregunta)]
                secciones[i:i + 1] = nuevas
        break
    return secciones


class Tarjeta(QFrame):
    """Respuesta de Tux con secciones. accion(nombre) para los botones."""
    accion = pyqtSignal(str)

    def __init__(self, texto, final=True):
        super().__init__()
        self.setObjectName("tarjeta")
        self.setStyleSheet(f"#tarjeta {{ background:{TARJETA}; border:1px solid {BORDE}; border-radius:14px; }}")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(14, 12, 14, 12)
        self.lay.setSpacing(9)
        self.texto = ""
        self.actualizar(texto, final)

    def _limpiar(self):
        while self.lay.count():
            it = self.lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                _borrar_layout(it.layout())

    def actualizar(self, texto, final=True):
        self.texto = texto
        self._limpiar()
        if not final:
            # Mientras llega la respuesta: vista simple (reconstruir widgets en cada trozo sería lento)
            self.lay.addWidget(etiqueta_rich(md_a_html(texto, con_copiar=False)[0]))
            return
        secciones = analizar_respuesta(texto)
        # «Qué pasa» solo si la respuesta empieza explicando y luego viene un comando
        tipos = [s[0] for s in secciones]
        tiene_comando = ("texto" in tipos and "comando" in tipos and tipos.index("texto") < tipos.index("comando")
                         and "titulo" not in tipos)
        primer_texto = True
        pies = [s[1] for s in secciones if s[0] == "transparencia"]
        borde = BORDE
        for sec in secciones:
            tipo = sec[0]
            if tipo == "texto":
                if primer_texto and tiene_comando:
                    self.lay.addWidget(etiqueta_seccion("Qué pasa"))
                primer_texto = False
                self.lay.addWidget(etiqueta_rich(md_a_html(sec[1], con_copiar=False)[0]))
            elif tipo == "comando":
                self.lay.addWidget(BloqueComando(sec[1], sec[2]))
            elif tipo == "info":
                self.lay.addWidget(bloque_salida(sec[1]))
            elif tipo == "semaforo":
                color, nombre, desc = {
                    riesgo.VERDE: (VERDE, "Seguro", "No borra, formatea ni cambia el sistema"),
                    riesgo.AMARILLO: (AMBAR, "Cuidado", "Puede cambiar algo: revisa antes de ejecutarlo"),
                    riesgo.ROJO: (ROJO, "Peligroso", "Puede causar daño serio o irreversible"),
                }[sec[1]]
                borde = color
                self.lay.addWidget(BannerSemaforo(color, nombre, desc))
            elif tipo == "aviso":
                self.lay.addWidget(Aviso(sec[1]))
            elif tipo == "pregunta":
                self.lay.addWidget(self._pregunta(sec[1]))
            elif tipo == "transparencia":
                if sec[1] == pies[0]:
                    self.lay.addWidget(self._transparencia(pies))
            elif tipo == "continuar":
                fila = QHBoxLayout()
                b = boton("Continúa la explicación", pequeno=True)
                b.clicked.connect(lambda: self.accion.emit("continuar"))
                fila.addWidget(b)
                fila.addStretch()
                self.lay.addLayout(fila)
            elif tipo == "mision":
                borde = NARANJA
                self._mision(sec[1])
            elif tipo == "titulo":
                borde = sec[2]
                self.lay.addWidget(etiqueta_seccion(sec[1], sec[2]))
            elif tipo == "accion":
                fila = QHBoxLayout()
                b = boton(sec[1], primario=not sec[2].startswith("aprender:"), pequeno=True)
                b.clicked.connect(lambda _, x=sec[2]: self.accion.emit(x))
                fila.addWidget(b)
                fila.addStretch()
                self.lay.addLayout(fila)
            elif tipo == "estado":
                borde = VERDE if sec[1] == "ok" else ROJO
                self.lay.addWidget(etiqueta_rich(md_a_html(sec[2], con_copiar=False)[0]))
                fila = QHBoxLayout()
                fila.setSpacing(6)
                if sec[1] == "ok" and "Siguiente lección" in sec[2]:
                    b = boton("Siguiente lección", primario=True, pequeno=True)
                    b.clicked.connect(lambda: self.accion.emit("siguiente"))
                    fila.addWidget(b)
                elif sec[1] == "error":
                    for nombre, acc, prim in (("Volver a comprobar", "comprobar", True), ("Pista", "pista", False)):
                        b = boton(nombre, primario=prim, pequeno=True)
                        b.clicked.connect(lambda _, x=acc: self.accion.emit(x))
                        fila.addWidget(b)
                if fila.count():
                    fila.addStretch()
                    self.lay.addLayout(fila)
        self.setStyleSheet(f"#tarjeta {{ background:{TARJETA}; border:1px solid {borde}; border-radius:14px; }}")

    def _pregunta(self, texto):
        caja = QFrame()
        caja.setObjectName("pregunta")
        caja.setStyleSheet(f"#pregunta {{ background:#1D1D29; border-radius:10px; }}")
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        lay.addWidget(etiqueta_seccion("Comprueba si lo entendiste", "#B794F4"))
        lay.addWidget(etiqueta_rich(md_a_html(texto, con_copiar=False)[0], 10))
        fila = QHBoxLayout()
        fila.setSpacing(6)
        b1 = boton("Responder", primario=True, pequeno=True)
        b1.clicked.connect(lambda: self.accion.emit("responder"))
        b2 = boton("Explícamelo", pequeno=True)
        b2.clicked.connect(lambda: self.accion.emit("explicame"))
        fila.addWidget(b1)
        fila.addWidget(b2)
        fila.addStretch()
        lay.addLayout(fila)
        return caja

    def _transparencia(self, lineas):
        filas = "<br>".join(f'<span style="color:#55556A;">◉</span>&nbsp; {_inline(re.sub(r"^(🔎|📊)\s*", "", l))}'
                            for l in lineas)
        lbl = etiqueta_rich(f'<span style="color:#8A8A9E;">{filas}</span>', 8.5, "#8A8A9E")
        lbl.setToolTip("Transparencia: lo que Tux consultó o midió en tu equipo para esta respuesta")
        return lbl

    def _mision(self, texto):
        cuerpo = re.sub(r"^🎯\s*\*\*Misi[oó]n:\*\*\s*", "", texto)
        lineas = cuerpo.split("\n")
        pasos = [l for l in lineas[1:] if re.match(r"^\d+\.\s", l)]
        cuerpo = lineas[0]
        cab = QHBoxLayout()
        cab.addWidget(etiqueta_seccion("Misión práctica"))
        cab.addStretch()
        verif = QLabel("se comprueba en tu equipo")
        verif.setStyleSheet(f"color:{TEXTO_SUAVE}; font-size:9pt; background:transparent;")
        cab.addWidget(verif)
        self.lay.addLayout(cab)
        self.lay.addWidget(etiqueta_rich(md_a_html(cuerpo, con_copiar=False)[0], 11))
        for paso in pasos:  # cada paso es un objetivo: todos cuentan para completar la misión
            num, txt = paso.split(".", 1)
            fila_p = QHBoxLayout()
            fila_p.setSpacing(8)
            bola = QLabel(num.strip())
            bola.setFixedSize(22, 22)
            bola.setAlignment(Qt.AlignCenter)
            bola.setStyleSheet(f"background:#2A1A12; color:{NARANJA}; border:1px solid {NARANJA}; border-radius:11px;"
                               f" font-size:9pt; font-weight:800;")
            fila_p.addWidget(bola, 0, Qt.AlignTop)
            fila_p.addWidget(etiqueta_rich(md_a_html(txt.strip(), con_copiar=False)[0], 10), 1)
            self.lay.addLayout(fila_p)
        fila = QHBoxLayout()
        fila.setSpacing(6)
        b1 = boton("Comprobar", primario=True)
        b1.clicked.connect(lambda: self.accion.emit("comprobar"))
        b2 = boton("Pista")
        b2.clicked.connect(lambda: self.accion.emit("pista"))
        b3 = boton("Saltar")
        b3.clicked.connect(lambda: self.accion.emit("saltar"))
        for b in (b1, b2, b3):
            fila.addWidget(b)
        fila.addStretch()
        self.lay.addLayout(fila)


def _borrar_layout(layout):
    while layout.count():
        it = layout.takeAt(0)
        if it.widget():
            it.widget().deleteLater()
        elif it.layout():
            _borrar_layout(it.layout())


class BannerSemaforo(QFrame):
    def __init__(self, color, nombre, desc):
        super().__init__()
        self.setObjectName("banner")
        self.setStyleSheet(f"#banner {{ background:transparent; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 2)
        lay.setSpacing(10)
        luces = QLabel()
        luces.setTextFormat(Qt.RichText)
        apagado = "#2E2E3C"
        puntos = "".join(
            f'<span style="color:{c if c == color else apagado}; font-size:15pt;">●</span>'
            for c in (VERDE, AMBAR, ROJO))
        luces.setText(puntos)
        luces.setStyleSheet("background:transparent;")
        txt = QLabel(f'<span style="color:{color}; font-size:12pt; font-weight:700;">{nombre}</span><br>'
                     f'<span style="color:{TEXTO_SUAVE}; font-size:9.5pt;">{desc}</span>')
        txt.setTextFormat(Qt.RichText)
        txt.setStyleSheet("background:transparent;")
        lay.addWidget(luces)
        lay.addWidget(txt, 1)


class Aviso(QFrame):
    def __init__(self, texto):
        super().__init__()
        self.setObjectName("aviso")
        self.setStyleSheet(f"#aviso {{ background:#2A2216; border-left:3px solid {AMBAR}; border-radius:6px; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lbl = etiqueta_rich(md_a_html(texto, con_copiar=False)[0].replace(f"color:{TEXTO}", "color:#F7D9A4"), 9.5, "#F7D9A4")
        lay.addWidget(lbl)


class PreguntaUsuario(QWidget):
    """La pregunta del usuario se muestra como título de la entrada del cuaderno."""

    def __init__(self, texto):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 10, 2, 0)
        lay.setSpacing(8)
        marca = QFrame()
        marca.setFixedWidth(3)
        marca.setStyleSheet(f"background:{NARANJA}; border-radius:1px;")
        lbl = QLabel(rich(texto, 16))
        lbl.setTextFormat(Qt.RichText)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl.setStyleSheet(f"color:#FFFFFF; font-size:11pt; font-weight:600; background:transparent; font-family:{SANS};")
        lay.addWidget(marca)
        lay.addWidget(lbl, 1)


# ---------- Nivel (anillo) ----------

class AnilloNivel(QWidget):
    def __init__(self, tam=34, grosor=3.5):
        super().__init__()
        self.tam, self.grosor = tam, grosor
        self.fraccion = 0.0
        self.texto = ""
        self.setFixedSize(tam, tam)

    def fijar(self, fraccion, texto=""):
        self.fraccion = max(0.0, min(1.0, fraccion))
        self.texto = texto
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        m = self.grosor / 2 + 1
        r = QRectF(m, m, self.tam - 2 * m, self.tam - 2 * m)
        pen = QPen(QColor("#2A2A38"), self.grosor)
        p.setPen(pen)
        p.drawEllipse(r)
        pen.setColor(QColor(NARANJA))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(r, 90 * 16, int(-360 * 16 * self.fraccion))
        if self.texto:
            f = QFont()
            f.setPointSizeF(self.tam / 4.2)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor(TEXTO))
            p.drawText(self.rect(), Qt.AlignCenter, self.texto)


# ---------- Ruta (mapa de nodos) ----------

class Nodo(QWidget):
    """Círculo del mapa con la línea que lo une al anterior/siguiente."""

    def __init__(self, estado, primero, ultimo):
        super().__init__()
        self.estado, self.primero, self.ultimo = estado, primero, ultimo
        self.setFixedWidth(26)
        self.setMinimumHeight(40)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, 16
        linea = QPen(QColor("#3A3A50"), 2)
        p.setPen(linea)
        if not self.primero:
            p.drawLine(int(cx), 0, int(cx), int(cy - 8))
        if not self.ultimo:
            p.drawLine(int(cx), int(cy + 8), int(cx), self.height())
        if self.estado == "hecho":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(VERDE))
            p.drawEllipse(QRectF(cx - 7, cy - 7, 14, 14))
            p.setPen(QPen(QColor("#0E0E14"), 2))
            p.drawLine(int(cx - 3), int(cy), int(cx - 1), int(cy + 3))
            p.drawLine(int(cx - 1), int(cy + 3), int(cx + 4), int(cy - 3))
        elif self.estado == "actual":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 122, 61, 60))
            p.drawEllipse(QRectF(cx - 11, cy - 11, 22, 22))
            p.setBrush(QColor(NARANJA))
            p.drawEllipse(QRectF(cx - 7, cy - 7, 14, 14))
        elif self.estado == "saltada":
            p.setPen(QPen(QColor("#5A5A6E"), 2, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(cx - 6, cy - 6, 12, 12))
        else:
            p.setPen(QPen(QColor("#3A3A4C"), 2))
            p.setBrush(QColor(FONDO))
            p.drawEllipse(QRectF(cx - 6, cy - 6, 12, 12))


class FilaLeccion(QWidget):
    continuar = pyqtSignal()

    def __init__(self, leccion, estado, primero, ultimo):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(Nodo(estado, primero, ultimo))
        col = QVBoxLayout()
        col.setContentsMargins(0, 6, 0, 8)
        col.setSpacing(2)
        color = {"hecho": TEXTO_SUAVE, "actual": "#FFFFFF", "saltada": "#6E6E82"}.get(estado, "#8A8A9E")
        titulo = QLabel(html.escape(leccion["titulo"]))
        titulo.setStyleSheet(f"color:{color}; font-size:10pt; font-weight:{700 if estado == 'actual' else 500}; background:transparent;")
        col.addWidget(titulo)
        if estado == "actual":
            sub = etiqueta_rich(md_a_html(leccion["mision"], con_copiar=False)[0].replace(f"color:{TEXTO}", f"color:{TEXTO_SUAVE}"),
                                8.5, TEXTO_SUAVE)
            col.addWidget(sub)
            b = boton("Continuar lección", primario=True, pequeno=True)
            b.clicked.connect(self.continuar.emit)
            fila = QHBoxLayout()
            fila.setContentsMargins(0, 4, 0, 0)
            fila.addWidget(b)
            fila.addStretch()
            col.addLayout(fila)
        lay.addLayout(col, 1)


class TarjetaTemaRuta(QFrame):
    """Un tema del plan en la vista Lista: cabecera con avance y sus lecciones con estado y XP."""
    continuar = pyqtSignal()

    def __init__(self, tema, lecciones, estados, abierta):
        super().__init__()
        import aprendizaje
        dif = tema.get("dificultad", "basico")
        color = COLORES_DIFICULTAD.get(dif, NARANJA)
        xp = aprendizaje.XP_POR_DIFICULTAD.get(dif, 10)
        hechas = sum(1 for e in estados.values() if e == "hecho")
        total = len(lecciones)
        en_curso = "actual" in estados.values()
        self.setObjectName("temaRuta")
        borde = NARANJA if en_curso else (VERDE if hechas == total else BORDE)
        self.setStyleSheet(f"#temaRuta {{ background:{TARJETA}; border:1px solid {borde}; border-radius:12px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        cab = QFrame()
        cab.setCursor(Qt.PointingHandCursor)
        cab.setStyleSheet("background:transparent;")
        fc = QHBoxLayout(cab)
        fc.setContentsMargins(0, 0, 0, 0)
        fc.setSpacing(10)
        icono = QLabel(rich(tema["icono"], 24))
        icono.setTextFormat(Qt.RichText)
        icono.setStyleSheet("background:transparent;")
        fc.addWidget(icono)
        col = QVBoxLayout()
        col.setSpacing(3)
        nombre = QLabel(f'<span style="color:#FFFFFF; font-size:10.5pt; font-weight:700;">{html.escape(tema["nombre"])}</span>'
                        f'&nbsp;&nbsp;<span style="color:{color}; font-size:8pt; font-weight:800;">'
                        f'{aprendizaje.DIFICULTAD_NOMBRE.get(dif, dif).upper()}</span>')
        nombre.setTextFormat(Qt.RichText)
        nombre.setStyleSheet("background:transparent;")
        barra = BarraProgreso(hechas / total)
        barra.setFixedSize(160, 5)
        col.addWidget(nombre)
        col.addWidget(barra)
        fc.addLayout(col, 1)
        cuenta = QLabel(f"{hechas}/{total}")
        cuenta.setStyleSheet(f"color:{VERDE if hechas == total else TEXTO_SUAVE}; font-size:9.5pt; font-weight:700; background:transparent;")
        fc.addWidget(cuenta)
        self.flecha = QLabel("▾" if abierta else "▸")
        self.flecha.setStyleSheet(f"color:{TEXTO_SUAVE}; font-size:11pt; background:transparent;")
        fc.addWidget(self.flecha)
        lay.addWidget(cab)

        self.cuerpo = QWidget()
        cl = QVBoxLayout(self.cuerpo)
        cl.setContentsMargins(0, 4, 0, 0)
        cl.setSpacing(4)
        for lec in lecciones:
            cl.addWidget(self._fila(lec, estados[lec["id"]], xp))
        lay.addWidget(self.cuerpo)
        self.cuerpo.setVisible(abierta)
        cab.mousePressEvent = lambda _e: self._alternar()

    def _alternar(self):
        self.cuerpo.setVisible(not self.cuerpo.isVisible())
        self.flecha.setText("▾" if self.cuerpo.isVisible() else "▸")

    def _fila(self, lec, estado, xp):
        fila = QFrame()
        fila.setObjectName("filaLec")
        actual = estado == "actual"
        fila.setStyleSheet(f"#filaLec {{ background:{'#2A1A12' if actual else 'transparent'}; border-radius:8px; }}")
        fl = QHBoxLayout(fila)
        fl.setContentsMargins(8, 6, 8, 6)
        fl.setSpacing(10)
        marca, color = {"hecho": ("✓", VERDE), "actual": ("▶", NARANJA), "saltada": ("↷", "#6E6E82")}.get(estado, ("○", "#55556A"))
        m = QLabel(marca)
        m.setFixedWidth(16)
        m.setAlignment(Qt.AlignCenter)
        m.setStyleSheet(f"color:{color}; font-size:11pt; font-weight:800; background:transparent;")
        fl.addWidget(m)
        col = QVBoxLayout()
        col.setSpacing(2)
        titulo = QLabel(html.escape(lec["titulo"]))
        titulo.setWordWrap(True)
        titulo.setStyleSheet(f"color:{'#FFFFFF' if actual else (TEXTO if estado == 'hecho' else '#8A8A9E')}; font-size:10pt;"
                             f" font-weight:{700 if actual else 500}; background:transparent;")
        col.addWidget(titulo)
        if actual:
            sub = etiqueta_rich(md_a_html(lec["mision"], con_copiar=False)[0].replace(f"color:{TEXTO}", f"color:{TEXTO_SUAVE}"),
                                9, TEXTO_SUAVE)
            col.addWidget(sub)
            b = boton("Estudiar esta lección ›", primario=True, pequeno=True)
            b.clicked.connect(self.continuar.emit)
            fb = QHBoxLayout()
            fb.setContentsMargins(0, 4, 0, 0)
            fb.addWidget(b)
            fb.addStretch()
            col.addLayout(fb)
        fl.addLayout(col, 1)
        chip = QLabel(f"+{xp} XP")
        chip.setStyleSheet(f"color:{VERDE if estado == 'hecho' else '#8A8A9E'}; font-size:8.5pt; font-weight:700;"
                           f" background:#1E1E2A; border-radius:8px; padding:2px 6px;")
        fl.addWidget(chip, 0, Qt.AlignTop)
        return fila


class PanelRuta(QWidget):
    """Planes (chips) + mapa del plan elegido + formulario de nuevo plan."""
    abrir_plan = pyqtSignal(str)      # id del plan → continuar lección
    crear_plan = pyqtSignal(str)      # meta
    borrar_plan = pyqtSignal(str)

    SUGERENCIAS = ["Empezar desde cero", "Volverme un experto en Linux (nivel desarrollador)", "Entender los permisos",
                   "Redes e internet", "Automatizar con scripts", "Docker y contenedores", "Mi PC va lento"]

    def __init__(self):
        super().__init__()
        self.plan_visible = None
        self.vista = "grafo"   # grafo (todos los planes) o lista (el plan elegido)
        self.ventana_grafo = None
        self.revelar_pid = None  # plan recién creado: su ruta se dibuja animada
        self.mostrando_rutas = False  # listado de todas las rutas desplegado
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(4, 6, 4, 6)
        self.lay.setSpacing(10)

    def refrescar(self, progreso, temas, lecciones, leccion_actual, plan_preferido=None):
        _borrar_layout(self.lay)
        planes = progreso["planes"]
        if plan_preferido in planes:
            self.plan_visible = plan_preferido
        if self.plan_visible not in planes:
            self.plan_visible = next(iter(planes), None)

        args = (progreso, temas, lecciones, leccion_actual)
        if planes:
            # Igual que los cuadernos: una cabecera con la ruta actual y el listado de todas al desplegar
            self.lay.addWidget(self._cabecera_rutas(planes, args))
            if self.mostrando_rutas:
                self._listado_rutas(planes, args)
                return

        if not self.plan_visible:
            self._formulario(progreso, temas, lecciones, leccion_actual, solo=True)
            return

        plan = planes[self.plan_visible]
        hechas = set(plan.get("completadas", []))   # cada ruta tiene su propio avance
        saltadas = set(plan.get("saltadas", []))
        actual, i, total = leccion_actual(progreso, self.plan_visible)
        n_hechas = sum(1 for l in plan["lecciones"] if l in hechas)

        cab = QHBoxLayout()
        anillo = AnilloNivel(42, 4)
        anillo.fijar(n_hechas / max(total, 1), f"{n_hechas}/{total}")
        cab.addWidget(anillo)
        info = QLabel(f'<span style="color:#FFFFFF; font-size:12pt; font-weight:700;">{rich(plan["nombre"])}</span><br>'
                      f'<span style="color:{TEXTO_SUAVE}; font-size:9.5pt;">Meta: {rich(plan["meta"].replace("`", "")[:90], 12)}</span>')
        info.setTextFormat(Qt.RichText)
        info.setWordWrap(True)
        info.setStyleSheet("background:transparent;")
        cab.addWidget(info, 1)
        papelera = QPushButton()
        papelera.setIcon(emoji.icono("🗑️"))
        papelera.setFixedSize(34, 34)
        papelera.setCursor(Qt.PointingHandCursor)
        papelera.setToolTip("Borrar este plan")
        papelera.setStyleSheet(f"QPushButton {{ background:#1A1A24; border:1px solid #2E2E3E; border-radius:17px; }}"
                               f"QPushButton:hover {{ background:#3A1A1A; border-color:{ROJO}; }}")
        cab.addWidget(papelera, 0, Qt.AlignTop)
        self.lay.addLayout(cab)
        confirmacion = self._tarjeta_borrar(plan["nombre"])
        confirmacion.hide()
        papelera.clicked.connect(lambda: confirmacion.setVisible(not confirmacion.isVisible()))
        self.lay.addWidget(confirmacion)

        # Vista: grafo dinámico de todos los planes o lista del plan elegido
        args = (progreso, temas, lecciones, leccion_actual)
        fila_vista = QHBoxLayout()
        fila_vista.setSpacing(4)
        for clave, nombre in (("grafo", "Grafo"), ("lista", "Lista")):
            b = QPushButton(nombre)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(24)
            activo = self.vista == clave
            b.setStyleSheet(f"QPushButton {{ background:{'#26263A' if activo else 'transparent'}; color:{'#FFFFFF' if activo else TEXTO_SUAVE};"
                            f" border:none; border-radius:8px; padding:0 12px; font-size:10pt; font-weight:600; }}")
            b.clicked.connect(lambda _, c=clave: (setattr(self, "vista", c), self.refrescar(*args)))
            fila_vista.addWidget(b)
        fila_vista.addStretch()
        ampliar = QPushButton("Ampliar mapa ⤢")
        ampliar.setCursor(Qt.PointingHandCursor)
        ampliar.setStyleSheet(f"QPushButton {{ background:transparent; color:{NARANJA}; border:none; font-size:10pt; font-weight:600; }}")
        ampliar.clicked.connect(lambda: self._ampliar(args))
        fila_vista.addWidget(ampliar)
        self.lay.addLayout(fila_vista)

        if self.vista == "grafo":
            grafo = GrafoEstudio(progreso, temas, lecciones, leccion_actual, self.plan_visible, alto=430)
            grafo.abrir_plan.connect(self.abrir_plan.emit)
            if self.revelar_pid == self.plan_visible:
                grafo.revelar()  # (main limpia revelar_pid a los 3 s; refrescos seguidos solo reinician la animación)
            self.lay.addWidget(grafo)
            leyenda = QWidget()
            fl = FlowLayout(leyenda, 10, 4)
            for k, (pid, pl) in enumerate(planes.items()):
                if pid != self.plan_visible:
                    continue  # leyenda solo de la ruta que se está viendo
                c = COLORES_PLAN[k % len(COLORES_PLAN)]
                lbl = QLabel(f'<span style="color:{c};">━━</span>&nbsp;<span style="color:{TEXTO_SUAVE};">{html.escape(pl["nombre"])}</span>')
                lbl.setTextFormat(Qt.RichText)
                lbl.setStyleSheet("font-size:9.5pt; background:transparent;")
                fl.addWidget(lbl)
            self.lay.addWidget(leyenda)
            if actual:
                caja = QFrame()
                caja.setObjectName("actual")
                caja.setStyleSheet(f"#actual {{ background:{TARJETA}; border:1px solid #4A2A16; border-radius:12px; }}")
                cl = QVBoxLayout(caja)
                cl.setContentsMargins(12, 10, 12, 12)
                cl.setSpacing(6)
                cl.addWidget(etiqueta_seccion(f"Lección actual · {i}/{total}"))
                t = QLabel(html.escape(actual["titulo"]))
                t.setStyleSheet("color:#FFFFFF; font-size:10.5pt; font-weight:700; background:transparent;")
                cl.addWidget(t)
                b = boton("Estudiar esta lección ›", primario=True, pequeno=True)
                b.clicked.connect(lambda: self.abrir_plan.emit(self.plan_visible))
                fb = QHBoxLayout()
                fb.addWidget(b)
                fb.addStretch()
                cl.addLayout(fb)
                self.lay.addWidget(caja)
            self.lay.addStretch()
            return

        # Lista: una tarjeta por tema; la del tema en curso abierta, las demás plegadas (clic para abrir)
        ids = plan["lecciones"]
        por_tema = []
        for lid in ids:
            t = lecciones[lid]["tema"]
            if not por_tema or por_tema[-1][0] != t:
                por_tema.append((t, []))
            por_tema[-1][1].append(lid)
        for t, lids in por_tema:
            estados = {lid: ("hecho" if lid in hechas else "saltada" if lid in saltadas
                             else "actual" if actual and lid == actual["id"] else "pendiente") for lid in lids}
            tarjeta = TarjetaTemaRuta(temas[t], [lecciones[l] for l in lids], estados,
                                      abierta="actual" in estados.values())
            tarjeta.continuar.connect(lambda p=self.plan_visible: self.abrir_plan.emit(p))
            self.lay.addWidget(tarjeta)
        if not actual:
            fin = QLabel(rich("🏆 Plan completado. ¡Buen trabajo!"))
            fin.setTextFormat(Qt.RichText)
            fin.setStyleSheet(f"color:{VERDE}; font-size:10pt; font-weight:700; background:transparent;")
            self.lay.addWidget(fin)

        self.lay.addStretch()

    def _ampliar(self, args):
        self.ventana_grafo = VentanaGrafo(*args, self.plan_visible)
        self.ventana_grafo.abrir_plan.connect(self.abrir_plan.emit)
        self.ventana_grafo.show()

    def _cabecera_rutas(self, planes, args):
        plan = planes.get(self.plan_visible) or next(iter(planes.values()))
        caja = QFrame()
        caja.setObjectName("cabRutas")
        caja.setCursor(Qt.PointingHandCursor)
        caja.setStyleSheet(f"#cabRutas {{ background:{TARJETA}; border:1px solid #2E2E3E; border-radius:10px; }}"
                           f"#cabRutas:hover {{ border-color:#4A2A16; }}")
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(12, 6, 8, 6)
        texto = QLabel(f'<span style="color:{NARANJA}; font-size:8.5pt; font-weight:700;">RUTA DE APRENDIZAJE</span><br>'
                       f'<span style="color:#FFFFFF; font-size:11pt; font-weight:700;">{rich(plan["nombre"], 14)}</span>')
        texto.setTextFormat(Qt.RichText)
        texto.setStyleSheet("background:transparent;")
        fila.addWidget(texto, 1)
        boton_rutas = QPushButton("Cerrar ▴" if self.mostrando_rutas else f"Mis rutas ({len(planes)}) ▾")
        boton_rutas.setCursor(Qt.PointingHandCursor)
        boton_rutas.setStyleSheet(f"QPushButton {{ background:transparent; border:none; color:{NARANJA}; font-size:10pt;"
                                  f" font-weight:600; }}")

        def alternar(*_):
            self.mostrando_rutas = not self.mostrando_rutas
            self.refrescar(*args)
        boton_rutas.clicked.connect(alternar)
        caja.mousePressEvent = alternar
        fila.addWidget(boton_rutas)
        return caja

    def _listado_rutas(self, planes, args):
        """Todas las rutas: icono, nombre, meta, avance y la lección en curso. Clic para abrirla."""
        progreso, temas, lecciones, leccion_actual = args
        nueva = boton("+  Nueva ruta de aprendizaje", primario=True)

        def nueva_ruta():
            self.mostrando_rutas = False
            self._formulario(*args)
        nueva.clicked.connect(nueva_ruta)
        self.lay.addWidget(nueva)
        for pid, plan in reversed(list(planes.items())):
            hechas = len(plan.get("completadas", []))
            total = len(plan["lecciones"])
            actual, i, _ = leccion_actual(progreso, pid)
            activo = pid == self.plan_visible
            fila = QFrame()
            fila.setObjectName("filaRutaActiva" if activo else "filaRuta")
            fila.setCursor(Qt.PointingHandCursor)
            fila.setStyleSheet(f"#filaRuta {{ background:{TARJETA}; border:1px solid {BORDE}; border-radius:10px; }}"
                               f"#filaRuta:hover {{ border-color:{NARANJA}; }}"
                               f"#filaRutaActiva {{ background:#21160F; border:1px solid {NARANJA}; border-radius:10px; }}")
            fl = QHBoxLayout(fila)
            fl.setContentsMargins(10, 9, 10, 9)
            fl.setSpacing(10)
            anillo = AnilloNivel(40, 3.5)
            anillo.fijar(hechas / max(total, 1), "✓" if actual is None else f"{hechas}/{total}")
            fl.addWidget(anillo, 0, Qt.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(2)
            iconos = "".join(temas[t]["icono"] for t in plan["temas"][:5])
            titulo = QLabel(rich(plan["nombre"], 13))
            titulo.setTextFormat(Qt.RichText)
            titulo.setStyleSheet("color:#FFFFFF; font-size:10.5pt; font-weight:700; background:transparent;")
            meta = QLabel(rich(f"{iconos}  {plan['meta'].replace('`', '')[:60]}", 12))
            meta.setTextFormat(Qt.RichText)
            meta.setStyleSheet(f"color:{TEXTO_SUAVE}; font-size:9pt; background:transparent;")
            en_curso = QLabel(f"▶ Lección {i}: {html.escape(actual['titulo'])}" if actual else "🏆 Ruta completada")
            en_curso.setStyleSheet(f"color:{NARANJA if actual else VERDE}; font-size:9pt; font-weight:600; background:transparent;")
            col.addWidget(titulo)
            col.addWidget(meta)
            col.addWidget(en_curso)
            fl.addLayout(col, 1)

            def abrir(_e, p=pid):
                self.mostrando_rutas = False
                self.plan_visible = p
                self.refrescar(*args)
            fila.mousePressEvent = abrir
            self.lay.addWidget(fila)
        self.lay.addStretch()

    def _tarjeta_borrar(self, nombre):
        """Confirmación clara, a todo el ancho y sin textos cortados."""
        caja = QFrame()
        caja.setObjectName("borrar")
        caja.setStyleSheet(f"#borrar {{ background:#2A1416; border:1px solid {ROJO}; border-radius:12px; }}")
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        titulo = QLabel(f"¿Borrar el plan «{html.escape(nombre)}»?")
        titulo.setWordWrap(True)
        titulo.setStyleSheet("color:#FFFFFF; font-size:11pt; font-weight:700; background:transparent;")
        sub = QLabel("Se borra la ruta y su cuaderno. Tus misiones hechas y tu XP se conservan.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#F2B8B8; font-size:9.5pt; background:transparent;")
        fila = QHBoxLayout()
        fila.setSpacing(8)
        cancelar = boton("Cancelar")
        cancelar.clicked.connect(caja.hide)
        borrar = QPushButton("Sí, borrar plan")
        borrar.setCursor(Qt.PointingHandCursor)
        borrar.setFixedHeight(30)
        borrar.setStyleSheet(f"QPushButton {{ background:{ROJO}; color:#FFFFFF; border:none; border-radius:15px;"
                             f" padding:0 16px; font-weight:700; font-size:10pt; }} QPushButton:hover {{ background:#FF7A7A; }}")
        borrar.clicked.connect(lambda: self.borrar_plan.emit(self.plan_visible))
        fila.addWidget(cancelar, 1)
        fila.addWidget(borrar, 1)
        lay.addWidget(titulo)
        lay.addWidget(sub)
        lay.addLayout(fila)
        return caja

    def mostrar_armando(self, progreso, temas, lecciones, leccion_actual, meta):
        """Mientras la IA elige los temas: el grafo hace un barrido tipo radar y se ven los pasos."""
        _borrar_layout(self.lay)
        self.lay.addWidget(etiqueta_seccion("Armando tu plan"))
        titulo = QLabel(rich(f"«{meta[:70]}»", 14))
        titulo.setTextFormat(Qt.RichText)
        titulo.setWordWrap(True)
        titulo.setStyleSheet("color:#FFFFFF; font-size:11pt; font-weight:700; background:transparent;")
        self.lay.addWidget(titulo)
        grafo = GrafoEstudio(progreso, temas, lecciones, leccion_actual, None, alto=430)
        grafo.armar()
        self.lay.addWidget(grafo)
        pasos = QLabel()
        pasos.setTextFormat(Qt.RichText)
        pasos.setStyleSheet(f"font-family:{MONO}; font-size:9.5pt; background:transparent;")
        self.lay.addWidget(pasos)
        self.lay.addStretch()
        etapas = ["Analizando tu meta", "Revisando tu nivel y lo que ya hiciste", "Eligiendo temas del catálogo",
                  "Ordenando de básico a experto", "Trazando tu ruta"]
        from PyQt5.QtCore import QTimer
        estado = {"i": 0}

        def avanzar():
            try:
                i = min(estado["i"], len(etapas) - 1)
                filas = []
                for k, e in enumerate(etapas[:i + 1]):
                    listo = k < i
                    filas.append(f'<span style="color:{VERDE if listo else NARANJA};">{"✓" if listo else "❯"}</span>'
                                 f'&nbsp;<span style="color:{TEXTO if listo else "#FFFFFF"};">{e}{"" if listo else "…"}</span>')
                pasos.setText("<br>".join(filas))
            except RuntimeError:  # el panel ya cambió (el plan llegó): no hay nada que actualizar
                return
            estado["i"] += 1
            if estado["i"] < len(etapas):
                QTimer.singleShot(1100, avanzar)
        avanzar()

    def _ver(self, pid, *args):
        self.plan_visible = pid
        self.refrescar(*args)

    def _formulario(self, progreso, temas, lecciones, leccion_actual, solo=False):
        if not solo:
            self.plan_visible = None
            _borrar_layout(self.lay)
        caja = QFrame()
        caja.setObjectName("form")
        caja.setStyleSheet(f"#form {{ background:{TARJETA}; border:1px solid {BORDE}; border-radius:14px; }}")
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)
        lay.addWidget(etiqueta_seccion("Nuevo plan de estudio"))
        lay.addWidget(etiqueta_rich("¿Qué quieres aprender o para qué lo necesitas? Tux elige los temas y el orden.", 10))
        entrada = QLineEdit()
        entrada.setPlaceholderText("Ej: quiero manejar servidores")
        entrada.setStyleSheet(f"QLineEdit {{ background:#0A0A0F; color:{TEXTO}; border:1px solid #34344A; border-radius:8px;"
                              f" padding:7px 10px; font-size:10pt; }} QLineEdit:focus {{ border-color:{NARANJA}; }}")
        lay.addWidget(entrada)
        sug = QWidget()
        flow = FlowLayout(sug, 6, 6)
        for s in self.SUGERENCIAS:
            b = boton(s, pequeno=True)
            b.clicked.connect(lambda _, t=s: entrada.setText(t))
            flow.addWidget(b)
        lay.addWidget(sug)
        crear = boton("Crear mi plan", primario=True)

        def enviar():
            meta = entrada.text().strip()
            if meta:
                crear.setEnabled(False)
                crear.setText("Armando tu plan…")
                self.crear_plan.emit(meta)
        crear.clicked.connect(enviar)
        entrada.returnPressed.connect(enviar)
        fila = QHBoxLayout()
        fila.addWidget(crear)
        fila.addStretch()
        lay.addLayout(fila)
        if not solo:
            volver = QPushButton("‹ Volver")
            volver.setCursor(Qt.PointingHandCursor)
            volver.setStyleSheet(f"QPushButton {{ background:transparent; color:{TEXTO_SUAVE}; border:none; font-size:10pt; text-align:left; }}")
            volver.clicked.connect(lambda: self.refrescar(progreso, temas, lecciones, leccion_actual))
            self.lay.addWidget(volver)
        self.lay.addWidget(caja)
        self.lay.addStretch()
        entrada.setFocus()


# ---------- Progreso ----------

class PanelProgreso(QWidget):
    """Dos cosas distintas: tu NIVEL DE CONOCIMIENTO (se gana con XP de misiones) y
    CÓMO TE EXPLICA TUX (un estilo que eliges tú)."""
    cambiar_nivel = pyqtSignal(str)      # estilo de explicación
    alternar_terminal = pyqtSignal(bool)
    ver_contexto = pyqtSignal()

    ESTILOS = [
        ("principiante", "Paso a paso", "Te explico cada término", "chmod = cambia permisos"),
        ("intermedio", "Explicado", "El porqué y lo menos obvio", "+x: ejecutar scripts"),
        ("avanzado", "Al grano", "Solución y motivo técnico", "chmod u+x script.sh"),
        ("experto", "Técnico a fondo", "Internals y casos límite", "chmod(2), umask, ACLs"),
    ]

    def __init__(self):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(4, 6, 4, 6)
        self.lay.setSpacing(12)

    def refrescar(self, progreso, temas, estilo, info_nivel, xp, niveles, terminal_activa, kb, xp_por_dificultad):
        _borrar_layout(self.lay)
        hechas = set(progreso["completadas"]).union(*[set(pl.get("completadas", [])) for pl in progreso["planes"].values()])
        idx, nombre, desc, minimo, siguiente = info_nivel

        # --- Nivel de conocimiento (XP) ---
        self.lay.addWidget(etiqueta_seccion("Tu nivel de conocimiento"))
        cab = QHBoxLayout()
        cab.setSpacing(12)
        anillo = AnilloNivel(70, 6)
        anillo.fijar((xp - minimo) / (siguiente - minimo) if siguiente else 1.0, f"{xp}")
        anillo.setToolTip("Puntos de experiencia (XP) ganados con misiones comprobadas")
        cab.addWidget(anillo)
        txt = (f'<span style="color:#FFFFFF; font-size:14pt; font-weight:800;">{html.escape(nombre)}</span><br>'
               f'<span style="color:{TEXTO_SUAVE}; font-size:10pt;">{html.escape(desc)} · {xp} XP</span><br>')
        if siguiente:
            sig_nombre = niveles[idx + 1][0]
            txt += f'<span style="color:{NARANJA}; font-size:10pt;">{siguiente - xp} XP para {html.escape(sig_nombre)}</span>'
        else:
            txt += f'<span style="color:{VERDE}; font-size:10pt;">Nivel máximo alcanzado</span>'
        info = QLabel(txt)
        info.setTextFormat(Qt.RichText)
        info.setStyleSheet("background:transparent;")
        cab.addWidget(info, 1)
        self.lay.addLayout(cab)
        self.lay.addWidget(EscaleraNiveles(niveles, idx))
        pts = " · ".join(f"{k.capitalize() if k != 'basico' else 'Básico'} {v} XP" for k, v in xp_por_dificultad.items())
        nota = QLabel(f"Cada misión comprobada da puntos según su dificultad: {pts}")
        nota.setWordWrap(True)
        nota.setStyleSheet("color:#6E6E82; font-size:9pt; background:transparent;")
        self.lay.addWidget(nota)

        # --- Temas: tarjetas en cuadrícula, agrupadas por dificultad ---
        self.lay.addWidget(etiqueta_seccion("Temas", TEXTO_SUAVE))
        grupos = {}
        for t, d in temas.items():
            grupos.setdefault(d.get("dificultad", "basico"), []).append((t, d))
        for dif in ("basico", "avanzado", "experto", "maestro"):
            if dif not in grupos:
                continue
            color = COLORES_DIFICULTAD[dif]
            hechas_dif = sum(1 for _, d in grupos[dif] for l in d["lecciones"] if l["id"] in hechas)
            total_dif = sum(len(d["lecciones"]) for _, d in grupos[dif])
            cab_g = QLabel(f'<span style="color:{color}; font-size:9.5pt; font-weight:800;">'
                           f'{ {"basico": "BÁSICO", "avanzado": "AVANZADO", "experto": "EXPERTO", "maestro": "MAESTRO"}[dif] }</span>'
                           f'<span style="color:#6E6E82; font-size:9pt;">&nbsp;&nbsp;{xp_por_dificultad[dif]} XP por misión · '
                           f'{hechas_dif}/{total_dif}</span>')
            cab_g.setTextFormat(Qt.RichText)
            cab_g.setStyleSheet("background:transparent; padding-top:4px;")
            self.lay.addWidget(cab_g)
            rejilla_t = QWidget()
            flow_t = FlowLayout(rejilla_t, 8, 8)
            for t, d in grupos[dif]:
                k = sum(1 for l in d["lecciones"] if l["id"] in hechas)
                flow_t.addWidget(TarjetaTema(d, k, len(d["lecciones"]), color, xp_por_dificultad[dif]))
            self.lay.addWidget(rejilla_t)

        # --- Cómo te explica Tux (estilo, lo eliges tú) ---
        self.lay.addWidget(etiqueta_seccion("Cómo te explica Tux", "#B794F4"))
        sub = QLabel("Es independiente de tu nivel: elige cómo quieres que te hable.")
        sub.setStyleSheet(f"color:{TEXTO_SUAVE}; font-size:9.5pt; background:transparent;")
        self.lay.addWidget(sub)
        rejilla = QWidget()
        flow = FlowLayout(rejilla, 8, 8)
        for clave, titulo, descripcion, ejemplo in self.ESTILOS:
            flow.addWidget(TarjetaEstilo(clave, titulo, descripcion, ejemplo, clave == estilo, self.cambiar_nivel.emit))
        self.lay.addWidget(rejilla)

        # --- Tux y tu equipo ---
        self.lay.addWidget(etiqueta_seccion("Tux y tu equipo", TEXTO_SUAVE))
        term = boton("Vigilando tu terminal ✓" if terminal_activa else "Vigilar mi terminal", primario=terminal_activa, pequeno=True)
        term.setToolTip("Si un comando falla en bash, Tux te explica qué pasó. Solo guarda el último comando fallido.")
        term.clicked.connect(lambda: self.alternar_terminal.emit(not terminal_activa))
        ctx = boton("Qué sé de tu equipo", pequeno=True)
        ctx.clicked.connect(self.ver_contexto.emit)
        fila2 = QHBoxLayout()
        fila2.setSpacing(6)
        fila2.addWidget(term)
        fila2.addWidget(ctx)
        fila2.addStretch()
        self.lay.addLayout(fila2)
        pie = QLabel(f"Todo es local. Chats y progreso ocupan {kb:.1f} KB en ~/.config/tux-assistant")
        pie.setWordWrap(True)
        pie.setStyleSheet("color:#6E6E82; font-size:9pt; background:transparent;")
        self.lay.addWidget(pie)
        self.lay.addStretch()


COLORES_DIFICULTAD = {"basico": "#4FD1C5", "avanzado": "#63B3ED", "experto": "#B794F4", "maestro": "#F6C453"}


class TarjetaTema(QFrame):
    """Un tema: icono grande, nombre, anillo de avance y XP ganado."""

    def __init__(self, d, hechas, total, color, xp_mision):
        super().__init__()
        completo = hechas == total
        empezado = hechas > 0
        self.setObjectName("tema")
        self.setFixedSize(186, 108)
        borde = VERDE if completo else (color if empezado else "#262633")
        fondo = "#14201A" if completo else ("#1A1A26" if empezado else TARJETA)
        self.setStyleSheet(f"#tema {{ background:{fondo}; border:1px solid {borde}; border-radius:12px; }}")
        self.setToolTip(f"{d['nombre']}: {hechas}/{total} lecciones · {hechas * xp_mision}/{total * xp_mision} XP")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        col = QVBoxLayout()
        col.setSpacing(3)
        icono = QLabel(rich(d["icono"], 24))
        icono.setTextFormat(Qt.RichText)
        icono.setStyleSheet("background:transparent;")
        nombre = QLabel(html.escape(d["nombre"]))
        nombre.setWordWrap(True)
        nombre.setStyleSheet(f"color:{'#FFFFFF' if empezado or completo else TEXTO}; font-size:9.5pt; font-weight:700; background:transparent;")
        xp = QLabel(f"{hechas * xp_mision} / {total * xp_mision} XP")
        xp.setStyleSheet(f"color:{color if empezado else '#6E6E82'}; font-size:8.5pt; font-weight:600; background:transparent;")
        col.addWidget(icono)
        col.addWidget(nombre, 1)
        col.addWidget(xp)
        lay.addLayout(col, 1)
        anillo = AnilloNivel(38, 3.5)
        anillo.fijar(hechas / total, "✓" if completo else f"{hechas}/{total}")
        lay.addWidget(anillo, 0, Qt.AlignTop)


class EscaleraNiveles(QWidget):
    """Los 6 niveles como escalones; los alcanzados en naranja."""

    def __init__(self, niveles, actual):
        super().__init__()
        self.niveles, self.actual = niveles, actual
        self.setFixedHeight(58)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self.niveles)
        w = self.width() / n
        f = QFont()
        f.setPointSizeF(8)
        p.setFont(f)
        for i, (nombre, minimo, _) in enumerate(self.niveles):
            alto = 10 + i * 5
            x = i * w + 2
            r = QRectF(x, 36 - alto, w - 4, alto)
            if i < self.actual:
                color = QColor(NARANJA)
                color.setAlpha(150)
            elif i == self.actual:
                color = QColor(NARANJA)
            else:
                color = QColor("#262636")
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(r, 3, 3)
            p.setPen(QColor("#FFFFFF" if i == self.actual else TEXTO_SUAVE if i < self.actual else "#55556A"))
            f.setBold(i == self.actual)
            p.setFont(f)
            p.drawText(QRectF(i * w, 39, w, 11), Qt.AlignCenter, nombre.replace("Arquitecto Linux", "Arquitecto"))
            p.setPen(QColor("#55556A"))
            f.setBold(False)
            p.setFont(f)
            p.drawText(QRectF(i * w, 49, w, 10), Qt.AlignCenter, f"{minimo}")


class TarjetaEstilo(QFrame):
    """Estilo de explicación seleccionable, con un ejemplo de cómo sonaría."""

    def __init__(self, clave, titulo, descripcion, ejemplo, activo, al_elegir):
        super().__init__()
        self.setObjectName("estilo")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(186, 122)
        self.clave, self.al_elegir = clave, al_elegir
        borde = "#B794F4" if activo else "#2A2A3A"
        fondo = "#1F1A2E" if activo else TARJETA
        self.setStyleSheet(f"#estilo {{ background:{fondo}; border:1px solid {borde}; border-radius:10px; }}"
                           f"#estilo:hover {{ border-color:#B794F4; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 9)
        lay.setSpacing(3)
        t = QLabel(("● " if activo else "") + titulo)
        t.setStyleSheet(f"color:{'#D6BCFA' if activo else '#FFFFFF'}; font-size:10pt; font-weight:700; background:transparent;")
        d = QLabel(descripcion)
        d.setWordWrap(True)
        d.setStyleSheet(f"color:{TEXTO_SUAVE}; font-size:9pt; background:transparent;")
        e = QLabel(html.escape(ejemplo))
        e.setStyleSheet(f"color:#8A8A9E; font-family:{MONO}; font-size:8.5pt; background:#0A0A0F; border-radius:5px; padding:4px;")
        for w_ in (t, d):
            lay.addWidget(w_)
        lay.addStretch()
        lay.addWidget(e)

    def mousePressEvent(self, _):
        self.al_elegir(self.clave)


class BarraProgreso(QWidget):
    def __init__(self, fraccion):
        super().__init__()
        self.fraccion = fraccion
        self.setFixedSize(90, 6)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2A2A38"))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 3, 3)
        if self.fraccion > 0:
            p.setBrush(QColor(VERDE if self.fraccion >= 1 else NARANJA))
            p.drawRoundedRect(QRectF(0, 0, max(6, self.width() * self.fraccion), self.height()), 3, 3)


# ---------- Grafo dinámico de estudio (todos los planes) ----------

# Sin naranja (= lección actual) ni verde (= hecha) para no confundir
COLORES_PLAN = ["#4FD1C5", "#B794F4", "#63B3ED", "#F687B3", "#F6E05E", "#A3BFFA"]
NOMBRE_CORTO = {"terminal": "Terminal", "permisos": "Permisos", "paquetes": "Paquetes", "procesos": "Procesos",
                "redes": "Redes", "bash": "Bash", "texto": "Texto", "dev": "Dev", "seguridad": "Seguridad",
                "sistema": "systemd", "kernel": "Kernel", "contenedores": "Docker", "rendimiento": "Rendimiento",
                "personalizacion": "Estilo", "virtualizacion": "VMs", "ia": "IA"}


def _candado(p, x, y, tam, color):
    """Candadito dibujado a mano (cuerpo + arco)."""
    c = QColor(color)
    p.setPen(QPen(c, max(1.2, tam * 0.28)))
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(x - tam * 0.55, y - tam * 1.15, tam * 1.1, tam * 1.2), 0, 180 * 16)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(x - tam * 0.8, y - tam * 0.5, tam * 1.6, tam * 1.2), 1.5, 1.5)


class GrafoEstudio(QWidget):
    """Mapa vivo: tú en el centro → temas → lecciones. Las rutas de los planes fluyen animadas.

    Verde = hecha, naranja latiendo = lección actual, contorno de color = pendiente en un plan,
    gris = aún fuera de tus planes. Pasa el ratón por un nodo para ver qué es; clic en la
    lección actual para continuarla.
    """
    abrir_plan = pyqtSignal(str)

    def __init__(self, progreso, temas, lecciones, leccion_actual, plan_destacado=None, alto=360):
        super().__init__()
        from PyQt5.QtCore import QTimer
        self.progreso, self.temas, self.lecciones = progreso, temas, lecciones
        self.leccion_actual = leccion_actual
        self.destacado = plan_destacado
        self.modo = "normal"   # normal · armando (la IA está eligiendo) · revelando (la ruta se dibuja)
        from PyQt5.QtCore import QElapsedTimer
        self.reloj_anim = QElapsedTimer()
        self.fase = 0.0
        self.hover = None
        self.nodos = []  # (x, y, r, tipo, id)
        self.setMinimumHeight(alto)
        self.setMouseTracking(True)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tic)
        self.timer.start(50)

    def armar(self):
        self.modo = "armando"
        self.reloj_anim.start()

    def revelar(self):
        self.modo = "revelando"
        self.reloj_anim.start()

    def _tic(self):
        if self.isVisible():
            self.fase = (self.fase + 0.05) % 1000
            self.update()

    # --- datos ---
    def _estado(self):
        # Con un plan destacado se ve SU avance; si no, lo hecho en cualquier ruta
        planes = self.progreso["planes"]
        if self.destacado in planes:
            hechas = set(planes[self.destacado].get("completadas", []))
            saltadas = set(planes[self.destacado].get("saltadas", []))
        else:
            hechas = set(self.progreso["completadas"]).union(*[set(pl.get("completadas", [])) for pl in planes.values()])
            saltadas = set()
        actuales, en_plan = {}, {}
        for k, (pid, plan) in enumerate(self.progreso["planes"].items()):
            if self.destacado in planes and pid != self.destacado:
                continue  # solo la ruta que se está viendo: nada de otras rutas mezcladas
            color = COLORES_PLAN[k % len(COLORES_PLAN)]
            for lid in plan["lecciones"]:
                en_plan.setdefault(lid, []).append((pid, color, plan["nombre"]))
            lec, _, _ = self.leccion_actual(self.progreso, pid)
            if lec:
                actuales.setdefault(lec["id"], []).append(pid)
        return hechas, saltadas, actuales, en_plan

    def _posiciones(self):
        import math
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2 - 8
        base = min(w, h - 30)
        denso = len(self.temas) > 8
        r1, r2 = (base * 0.29, base * 0.45) if denso else (base * 0.24, base * 0.41)
        pos = {"centro": (cx, cy)}
        ids = list(self.temas)
        n = len(ids)
        for i, t in enumerate(ids):
            ang = -math.pi / 2 + i * 2 * math.pi / n
            pos[t] = (cx + r1 * math.cos(ang), cy + r1 * math.sin(ang))
            lecs = self.temas[t]["lecciones"]
            ancho = (2 * math.pi / n) * 0.72
            for j, l in enumerate(lecs):
                a = ang - ancho / 2 + (ancho * (j + 0.5) / len(lecs))
                pos[l["id"]] = (cx + r2 * math.cos(a), cy + r2 * math.sin(a))
        return pos

    # --- dibujo ---
    def paintEvent(self, _):
        import math
        from PyQt5.QtGui import QPainterPath, QPixmap
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pos = self._posiciones()
        hechas, saltadas, actuales, en_plan = self._estado()
        self.nodos = []
        cx, cy = pos["centro"]

        # --- Qué plan se mira y en qué fase de animación estamos ---
        planes = self.progreso["planes"]
        plan_vista = planes.get(self.destacado) if self.destacado else None
        ids_vista = set(plan_vista["lecciones"]) if plan_vista else set().union(*[set(pl["lecciones"]) for pl in planes.values()]) if planes else set()
        temas_vista = {self.lecciones[l]["tema"] for l in ids_vista if l in self.lecciones}
        armando = self.modo == "armando"
        rev = None
        if self.modo == "revelando":
            rev = min(1.0, self.reloj_anim.elapsed() / 2600.0)
            if rev >= 1.0:
                self.modo = "normal"
                rev = None
        orden_vista = plan_vista["lecciones"] if plan_vista else []
        alcance = (rev * len(orden_vista)) if rev is not None else len(orden_vista)  # lecciones ya «reveladas»
        indice = {lid: i for i, lid in enumerate(orden_vista)}
        temas_revelados = {self.lecciones[l]["tema"] for l in orden_vista[:int(alcance) + 1] if l in self.lecciones} \
            if rev is not None else temas_vista

        # Aristas centro → tema → lección (las de fuera del plan casi invisibles)
        for t, d in self.temas.items():
            tx, ty = pos[t]
            dentro = t in temas_vista and not armando
            p.setPen(QPen(QColor("#33334A" if dentro else "#1E1E2A"), 1.3 if dentro else 1))
            p.drawLine(int(cx), int(cy), int(tx), int(ty))
            for l in d["lecciones"]:
                lx, ly = pos[l["id"]]
                p.drawLine(int(tx), int(ty), int(lx), int(ly))

        # Modo «armando»: barrido tipo radar mientras la IA elige los temas
        if armando:
            seg = self.reloj_anim.elapsed() / 1000.0
            radio_max = max(math.hypot(pos[t][0] - cx, pos[t][1] - cy) for t in self.temas) + 40
            for i in range(14):
                ang = seg * 2.6 - i * 0.05
                c = QColor(NARANJA)
                c.setAlpha(max(0, 120 - i * 9))
                p.setPen(QPen(c, 2))
                p.drawLine(QPointF(cx, cy), QPointF(cx + radio_max * math.cos(ang), cy + radio_max * math.sin(ang)))
            for k in range(3):
                onda = (seg * 0.6 + k / 3) % 1
                c = QColor(NARANJA)
                c.setAlphaF(0.35 * (1 - onda))
                p.setPen(QPen(c, 1.5))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx, cy), radio_max * onda, radio_max * onda)

        # Rutas de los planes (línea discontinua que fluye en el orden del plan)
        for k, (pid, plan) in enumerate(planes.items()):
            if armando:
                break
            if self.destacado in planes and pid != self.destacado:
                continue  # las rutas de otros planes no se dibujan aquí
            color = QColor(COLORES_PLAN[k % len(COLORES_PLAN)])
            destacado = self.destacado in (None, pid)
            color.setAlpha(230 if destacado else 55)
            pen = QPen(color, 2.4 if destacado else 1.2)
            pen.setDashPattern([4, 4])
            pen.setDashOffset(-self.fase * 20)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            puntos = [pos[l] for l in plan["lecciones"] if l in pos]
            if len(puntos) < 2:
                continue
            if rev is not None and pid == self.destacado:
                # se dibuja solo hasta donde va la «cometa»
                tramo = rev * (len(puntos) - 1)
                n = int(tramo)
                puntos_vis = puntos[:n + 1]
                if n + 1 < len(puntos):
                    (x0, y0), (x1, y1) = puntos[n], puntos[n + 1]
                    f = tramo - n
                    puntos_vis.append((x0 + (x1 - x0) * f, y0 + (y1 - y0) * f))
            else:
                puntos_vis = puntos
            camino = QPainterPath()
            camino.moveTo(*puntos_vis[0])
            for (x0, y0), (x1, y1) in zip(puntos_vis, puntos_vis[1:]):
                mx, my = (x0 + x1) / 2, (y0 + y1) / 2
                camino.quadTo(mx + (cx - mx) * 0.18, my + (cy - my) * 0.18, x1, y1)
            p.drawPath(camino)
            if rev is not None and pid == self.destacado:
                hx, hy = puntos_vis[-1]
                brillo = QColor(NARANJA)
                brillo.setAlpha(90)
                p.setPen(Qt.NoPen)
                p.setBrush(brillo)
                p.drawEllipse(QPointF(hx, hy), 11, 11)
                p.setBrush(QColor("#FFD2B8"))
                p.drawEllipse(QPointF(hx, hy), 4, 4)

        # Nodos de lección
        pulso = (math.sin(self.fase * 2.2) + 1) / 2
        r_base = 4.5 if len(self.lecciones) > 30 else 6.5
        for t, d in self.temas.items():
            for l in d["lecciones"]:
                lid = l["id"]
                x, y = pos[lid]
                planes_l = en_plan.get(lid, [])
                r = r_base
                fuera = lid not in ids_vista
                oculta = rev is not None and lid in indice and indice[lid] > alcance
                if armando:
                    a = 0.25 + 0.35 * (math.sin(self.fase * 3 + x * 0.05 + y * 0.03) + 1) / 2
                    c = QColor("#8A8A9E")
                    c.setAlphaF(a)
                    p.setPen(Qt.NoPen)
                    p.setBrush(c)
                elif fuera or oculta:
                    p.setPen(QPen(QColor("#2A2A3A"), 1.2))
                    p.setBrush(QColor("#14141C"))
                elif lid in actuales:
                    halo = QColor(NARANJA)
                    halo.setAlpha(int(40 + 70 * pulso))
                    p.setPen(Qt.NoPen)
                    p.setBrush(halo)
                    rh = 10 + 5 * pulso
                    p.drawEllipse(QRectF(x - rh, y - rh, 2 * rh, 2 * rh))
                    p.setBrush(QColor(NARANJA))
                    r = 8
                elif lid in hechas:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(VERDE))
                elif lid in saltadas:
                    p.setPen(QPen(QColor("#6E6E82"), 1.5, Qt.DotLine))
                    p.setBrush(QColor(FONDO))
                elif planes_l:
                    p.setPen(QPen(QColor(planes_l[0][1]), 2))
                    p.setBrush(QColor(FONDO))
                else:
                    p.setPen(QPen(QColor("#2E2E40"), 1.5))
                    p.setBrush(QColor("#1A1A24"))
                if self.hover == lid:
                    r += 2.5
                p.drawEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))
                if fuera and not armando and self.hover == lid:
                    _candado(p, x, y - r - 7, 5, "#6E6E82")
                self.nodos.append((x, y, max(r, 9), "leccion", lid))

        # Nodos de tema: anillo de progreso + icono + nombre; candado si no es parte del plan
        f = QFont()
        f.setPointSizeF(7.5 if len(self.temas) > 8 else 8.5)
        f.setBold(True)
        p.setFont(f)
        for t, d in self.temas.items():
            x, y = pos[t]
            total = len(d["lecciones"])
            k = sum(1 for l in d["lecciones"] if l["id"] in hechas)
            r = (13 if self.hover == t else 11) if len(self.temas) > 8 else (16 if self.hover == t else 14)
            bloqueado = (t not in temas_vista) and not armando
            esperando = rev is not None and t in temas_vista and t not in temas_revelados
            apagado = bloqueado or esperando or armando
            p.setPen(QPen(QColor("#22222E" if apagado else "#2E2E40"), 3))
            p.setBrush(QColor("#111118" if apagado else "#16161F"))
            p.drawEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))
            if k and not apagado:
                pen = QPen(QColor(VERDE if k == total else NARANJA), 3)
                pen.setCapStyle(Qt.RoundCap)
                p.setPen(pen)
                p.drawArc(QRectF(x - r, y - r, 2 * r, 2 * r), 90 * 16, int(-360 * 16 * k / total))
            ruta = emoji.ruta_png(d["icono"])
            if ruta:
                pix = QPixmap(str(ruta))
                tam = 14 if len(self.temas) > 8 else 16
                p.setOpacity(0.28 if apagado else 1.0)
                p.drawPixmap(QRect(int(x - tam / 2), int(y - tam / 2), tam, tam), pix)
                p.setOpacity(1.0)
            if bloqueado:
                _candado(p, x + r * 0.7, y - r * 0.7, 5.5, "#8A8A9E")
            p.setPen(QColor("#55556A" if apagado else TEXTO_SUAVE))
            p.drawText(QRectF(x - 40, y + r + 1, 80, 14), Qt.AlignCenter, NOMBRE_CORTO.get(t, d["nombre"]))
            self.nodos.append((x, y, r + 2, "tema", t))

        # Centro: Tux (tú)
        p.setPen(QPen(QColor(NARANJA), 2))
        p.setBrush(QColor("#1E150F"))
        p.drawEllipse(QRectF(cx - 20, cy - 20, 40, 40))
        tux = QPixmap("assets/tux.png")
        if not tux.isNull():
            p.drawPixmap(QRect(int(cx - 13), int(cy - 14), 26, 26), tux)
        n = len(hechas)
        p.setPen(QColor(NARANJA if self.modo != "normal" else TEXTO))
        texto_centro = {"armando": "Armando…", "revelando": "Trazando ruta"}.get(self.modo, f"{n} hechas")
        p.drawText(QRectF(cx - 60, cy + 21, 120, 14), Qt.AlignCenter, texto_centro)

        # Leyenda
        f.setBold(False)
        f.setPointSizeF(8.5)
        p.setFont(f)
        x0, y0 = 6, self.height() - 14
        for color, texto, borde in ((VERDE, "Hecha", False), (NARANJA, "Actual", False),
                                    ("#8A8A9E", "En tu plan", True), ("#2A2A3A", "Bloqueado", False)):
            if borde:
                p.setPen(QPen(QColor(color), 1.5))
                p.setBrush(QColor(FONDO))
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(color))
            p.drawEllipse(QRectF(x0, y0 - 4, 8, 8))
            p.setPen(QColor(TEXTO_SUAVE))
            p.drawText(int(x0 + 12), int(y0 + 4), texto)
            x0 += 14 + p.fontMetrics().width(texto) + 10

    # --- interacción ---
    def _nodo_en(self, punto):
        for x, y, r, tipo, ident in reversed(self.nodos):
            if (punto.x() - x) ** 2 + (punto.y() - y) ** 2 <= (r + 3) ** 2:
                return tipo, ident
        return None

    def mouseMoveEvent(self, e):
        nodo = self._nodo_en(e.pos())
        nuevo = nodo[1] if nodo else None
        if nuevo != self.hover:
            self.hover = nuevo
            self.setCursor(Qt.PointingHandCursor if nodo else Qt.ArrowCursor)
            if nodo:
                QToolTip.showText(e.globalPos(), self._descripcion(*nodo), self)
            else:
                QToolTip.hideText()

    def _descripcion(self, tipo, ident):
        hechas, saltadas, actuales, en_plan = self._estado()
        if tipo == "tema":
            d = self.temas[ident]
            if self.destacado in self.progreso["planes"] and ident not in self.progreso["planes"][self.destacado]["temas"]:
                return f"🔒 {d['nombre']}\nNo es parte de este plan (créalo en otro plan para explorarlo)"
            k = sum(1 for l in d["lecciones"] if l["id"] in hechas)
            return f"{d['nombre']}: {k}/{len(d['lecciones'])} lecciones hechas"
        lec = self.lecciones[ident]
        if self.destacado and self.destacado in self.progreso["planes"] and \
                ident not in self.progreso["planes"][self.destacado]["lecciones"]:
            return f"🔒 {lec['titulo']}\nNo es parte de este plan"
        estado = ("✓ Hecha" if ident in hechas else "Saltada" if ident in saltadas
                  else "▶ Lección actual: haz clic para continuar" if ident in actuales
                  else "Pendiente" if ident in en_plan else "Aún no está en ningún plan")
        planes = ", ".join(n for _, _, n in en_plan.get(ident, []))
        return f"{lec['titulo']}\n{estado}" + (f"\nPlan: {planes}" if planes else "")

    def mousePressEvent(self, e):
        nodo = self._nodo_en(e.pos())
        if nodo and nodo[0] == "leccion":
            _, _, actuales, _ = self._estado()
            if nodo[1] in actuales:
                pid = self.destacado if self.destacado in actuales[nodo[1]] else actuales[nodo[1]][0]
                self.abrir_plan.emit(pid)

    def leaveEvent(self, e):
        self.hover = None
        super().leaveEvent(e)


class VentanaGrafo(QWidget):
    """El grafo en grande, en su propia ventana."""
    abrir_plan = pyqtSignal(str)

    def __init__(self, *args):
        super().__init__()
        self.setWindowTitle("Tux · Mapa de estudio")
        self.setStyleSheet(f"background:{FONDO}; color:{TEXTO};")
        self.resize(820, 820)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        titulo = QLabel("Tu mapa de estudio")
        titulo.setStyleSheet("color:#FFFFFF; font-size:14pt; font-weight:700;")
        sub = QLabel("La línea de color es tu ruta: fluye en el orden en que la estudias. Lo que no es parte de "
                     "ella sale con candado. Pasa el ratón por los nodos y haz clic en la lección actual (naranja).")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{TEXTO_SUAVE}; font-size:10.5pt;")
        self.grafo = GrafoEstudio(*args, alto=700)
        self.grafo.abrir_plan.connect(self.abrir_plan.emit)
        self.grafo.abrir_plan.connect(lambda _: self.close())
        lay.addWidget(titulo)
        lay.addWidget(sub)
        lay.addWidget(self.grafo, 1)


class ResumenTerminal(QFrame):
    """Cabecera de la sección Errores: lo que pasó esta semana en tu terminal y ajustes."""
    alternar_silencio = pyqtSignal(bool)
    alternar_vigilancia = pyqtSignal(bool)

    def __init__(self, resumen, nombres_tipo, silencioso, activa):
        super().__init__()
        self.setObjectName("resumenTerm")
        self.setStyleSheet(f"#resumenTerm {{ background:{TARJETA}; border:1px solid {BORDE}; border-radius:14px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        cab = QHBoxLayout()
        cab.addWidget(etiqueta_seccion("Tu terminal esta semana", "#FF5C5C"))
        cab.addStretch()
        estado = QLabel(f'<span style="color:{VERDE if activa else "#6E6E82"};">●</span>&nbsp;'
                        f'<span style="color:{TEXTO_SUAVE};">{"Vigilando" if activa else "Apagada"}</span>')
        estado.setTextFormat(Qt.RichText)
        estado.setStyleSheet("font-size:9pt; background:transparent;")
        cab.addWidget(estado)
        lay.addLayout(cab)

        total = resumen["total"]
        fila = QHBoxLayout()
        grande = QLabel(f'<span style="color:#FFFFFF; font-size:22pt; font-weight:800;">{total}</span>'
                        f'<span style="color:{TEXTO_SUAVE}; font-size:9.5pt;">&nbsp; errores · {resumen["hoy"]} hoy</span>')
        grande.setTextFormat(Qt.RichText)
        grande.setStyleSheet("background:transparent;")
        fila.addWidget(grande)
        fila.addStretch()
        if resumen["programa"]:
            prog, n = resumen["programa"]
            top = QLabel(f'<span style="color:{TEXTO_SUAVE};">Más fallos con</span><br>'
                         f'<span style="color:#FF9A66; font-family:{MONO}; font-weight:700;">{html.escape(prog)}</span>'
                         f'<span style="color:{TEXTO_SUAVE};"> ({n})</span>')
            top.setTextFormat(Qt.RichText)
            top.setAlignment(Qt.AlignRight)
            top.setStyleSheet("font-size:9.5pt; background:transparent;")
            fila.addWidget(top)
        lay.addLayout(fila)

        for tipo, n in resumen["por_tipo"][:4]:
            f2 = QHBoxLayout()
            nombre = QLabel(nombres_tipo.get(tipo, tipo))
            nombre.setStyleSheet(f"color:{TEXTO}; font-size:9.5pt; background:transparent;")
            f2.addWidget(nombre, 1)
            barra = BarraProgreso(n / max(total, 1))
            barra.setFixedSize(120, 6)
            f2.addWidget(barra)
            cuenta = QLabel(str(n))
            cuenta.setFixedWidth(22)
            cuenta.setAlignment(Qt.AlignRight)
            cuenta.setStyleSheet(f"color:{TEXTO_SUAVE}; font-size:9pt; background:transparent;")
            f2.addWidget(cuenta)
            lay.addLayout(f2)
        if not total:
            vacio = QLabel("Sin errores esta semana. Cuando algo falle en la terminal, aparecerá aquí.")
            vacio.setWordWrap(True)
            vacio.setStyleSheet(f"color:{TEXTO_SUAVE}; font-size:9.5pt; background:transparent;")
            lay.addWidget(vacio)

        botones = QHBoxLayout()
        botones.setSpacing(6)
        aviso = boton("Avisos con globo ✓" if not silencioso else "Modo silencioso", primario=not silencioso, pequeno=True)
        aviso.setToolTip("Silencioso: los errores se guardan aquí, pero Tux no te interrumpe con el globo")
        aviso.clicked.connect(lambda: self.alternar_silencio.emit(not silencioso))
        vig = boton("Apagar vigilancia" if activa else "Activar vigilancia", primario=not activa, pequeno=True)
        vig.clicked.connect(lambda: self.alternar_vigilancia.emit(not activa))
        botones.addWidget(aviso)
        botones.addWidget(vig)
        botones.addStretch()
        lay.addLayout(botones)


# ---------- Controles: cómo se maneja Tux ----------

class IconoRaton(QWidget):
    """Ratón dibujado con el botón que corresponde resaltado (izq, der, doble o arrastre)."""

    def __init__(self, gesto):
        super().__init__()
        self.gesto = gesto
        self.setFixedSize(46, 52)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cuerpo = QRectF(9, 4, 26, 40)
        p.setPen(QPen(QColor("#5A5A72"), 1.6))
        p.setBrush(QColor("#1A1A26"))
        p.drawRoundedRect(cuerpo, 13, 13)
        resalta = QColor(NARANJA)
        p.setPen(Qt.NoPen)
        p.setBrush(resalta)
        if self.gesto in ("izq", "doble", "arrastre"):
            path = __import__("PyQt5.QtGui", fromlist=["QPainterPath"]).QPainterPath()
            path.moveTo(22, 5)
            path.lineTo(22, 20)
            path.lineTo(10, 20)
            path.quadTo(10, 5, 22, 5)
            p.drawPath(path)
        elif self.gesto == "der":
            path = __import__("PyQt5.QtGui", fromlist=["QPainterPath"]).QPainterPath()
            path.moveTo(22, 5)
            path.lineTo(22, 20)
            path.lineTo(34, 20)
            path.quadTo(34, 5, 22, 5)
            p.drawPath(path)
        p.setPen(QPen(QColor("#5A5A72"), 1.2))
        p.drawLine(22, 5, 22, 20)
        p.drawLine(10, 20, 34, 20)
        if self.gesto == "doble":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(QRectF(28, 30, 17, 17))
            f = QFont()
            f.setPointSizeF(7.5)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#141418"))
            p.drawText(QRectF(28, 30, 17, 17), Qt.AlignCenter, "×2")
        elif self.gesto == "arrastre":
            p.setPen(QPen(QColor("#FFFFFF"), 1.8))
            for (x1, y1, x2, y2) in ((36, 36, 44, 36), (40, 32, 44, 36), (40, 40, 44, 36)):
                p.drawLine(x1, y1, x2, y2)


class PanelControles(QWidget):
    """Guía completa de cómo se maneja Tux (ratón y teclado)."""

    GESTOS = [
        ("izq", "Clic en Tux", "Pregunta rápida: escribe y la respuesta sale completa en su globo, compacta."),
        ("doble", "Doble clic en Tux", "Abre este cuaderno: explicaciones completas, planes de estudio y progreso."),
        ("arrastre", "Arrastrar a Tux", "Muévelo a cualquier parte de la pantalla; camina mientras lo llevas y el globo lo sigue."),
        ("der", "Clic derecho en Tux", "Tux se despide con una animación y se cierra TODO, incluido el modelo de IA en memoria."),
    ]
    TECLAS = [
        ("Enter", "Enviar lo que escribiste (en el cuaderno o en la pregunta rápida)."),
        ("Esc", "Cerrar la pregunta rápida."),
        ("✕", "Cerrar el cuaderno (arriba a la derecha). Solo se cierra con este botón."),
    ]
    EXTRAS = [
        ("💬", "Globo de Tux", "«Más detalle ›» abre la respuesta completa aquí; «Otra pregunta ›» abre otra pregunta rápida."),
        ("🚦", "Analizar comando", "Pega un comando con ese modo (abajo, junto al campo de texto) y te digo si es seguro."),
        ("💥", "Errores de la terminal", "Si activas la vigilancia, Tux aparece cuando un comando falla y te explica cómo arreglarlo."),
        ("😴", "Tux descansa", "Tras 1 minuto sin usarlo (y sin globo ni cuaderno abiertos) se entretiene con otras animaciones; mientras la IA te responde, pone cara de estar pensando."),
    ]

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(10)
        lay.addWidget(etiqueta_seccion("Cómo se maneja Tux"))
        for gesto, titulo, desc in self.GESTOS:
            lay.addWidget(self._fila(IconoRaton(gesto), titulo, desc, destacado=gesto in ("izq", "doble")))
        lay.addWidget(etiqueta_seccion("Teclado", TEXTO_SUAVE))
        for tecla, desc in self.TECLAS:
            kbd = QLabel(tecla)
            kbd.setAlignment(Qt.AlignCenter)
            kbd.setFixedSize(46, 30)
            kbd.setStyleSheet(f"color:#FFFFFF; font-family:{MONO}; font-size:9.5pt; font-weight:700; background:#22222F;"
                              f" border:1px solid #3A3A50; border-bottom:3px solid #3A3A50; border-radius:6px;")
            lay.addWidget(self._fila(kbd, "", desc))
        lay.addWidget(etiqueta_seccion("Más trucos", TEXTO_SUAVE))
        for icono, titulo, desc in self.EXTRAS:
            ic = QLabel(rich(icono, 26))
            ic.setTextFormat(Qt.RichText)
            ic.setFixedSize(46, 34)
            ic.setAlignment(Qt.AlignCenter)
            ic.setStyleSheet("background:transparent;")
            lay.addWidget(self._fila(ic, titulo, desc))
        lay.addStretch()

    def _fila(self, icono, titulo, desc, destacado=False):
        caja = QFrame()
        caja.setObjectName("control")
        caja.setStyleSheet(f"#control {{ background:{'#1E150F' if destacado else TARJETA}; "
                           f"border:1px solid {'#4A2A16' if destacado else BORDE}; border-radius:12px; }}")
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(10, 8, 12, 8)
        fila.setSpacing(12)
        fila.addWidget(icono, 0, Qt.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(2)
        if titulo:
            t = QLabel(html.escape(titulo))
            t.setStyleSheet(f"color:{'#FF9A66' if destacado else '#FFFFFF'}; font-size:10.5pt; font-weight:700; background:transparent;")
            col.addWidget(t)
        d = QLabel(html.escape(desc))
        d.setWordWrap(True)
        d.setStyleSheet(f"color:{TEXTO_SUAVE}; font-size:9.5pt; background:transparent;")
        col.addWidget(d)
        fila.addLayout(col, 1)
        return caja


class BarraSegmentos(QWidget):
    """Avance del plan en segmentos: verde = hecha, naranja = la lección actual, gris = pendiente."""

    def __init__(self):
        super().__init__()
        self.estados = []
        self.setFixedHeight(8)

    def fijar(self, estados):
        self.estados = estados
        self.setToolTip(f"{sum(1 for e in estados if e == 'hecha')} de {len(estados)} lecciones hechas")
        self.update()

    def paintEvent(self, _):
        if not self.estados:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self.estados)
        sep = 3 if n < 30 else 1.5
        ancho = (self.width() - sep * (n - 1)) / n
        colores = {"hecha": QColor(VERDE), "actual": QColor(NARANJA), "pendiente": QColor("#2E2A40")}
        p.setPen(Qt.NoPen)
        for i, e in enumerate(self.estados):
            p.setBrush(colores[e])
            p.drawRoundedRect(QRectF(i * (ancho + sep), 1, ancho, 6), 3, 3)
