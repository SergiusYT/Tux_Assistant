"""Intro animada de Tux Assistant (≈7 s, se salta con clic o Esc).

Secuencia: la pantalla se oscurece → un anillo naranja se dibuja → Tux aparece con
rebote y brillo → onda expansiva y partículas en órbita → el título se escribe
letra a letra → se «arranca» el sistema con datos reales del equipo → el logo
vuela hasta donde vivirá Tux en el escritorio.
"""
import math
import os
import platform
import random

from PyQt5.QtCore import Qt, QElapsedTimer, QPointF, QRectF, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QRadialGradient, QBrush
from PyQt5.QtWidgets import QApplication, QWidget

NARANJA = QColor("#FF7A3D")
DURACION = 7.0  # segundos (con pausa al final para leer todo)


def _ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def _ease_out_back(t, s=1.70158):
    t -= 1
    return t * t * ((s + 1) * t + s) + 1


def _ease_in_out(t):
    return 3 * t * t - 2 * t * t * t


def _tramo(t, ini, fin):
    """Progreso 0→1 de una fase que va de ini a fin (en segundos)."""
    if t <= ini:
        return 0.0
    if t >= fin:
        return 1.0
    return (t - ini) / (fin - ini)


def _datos_equipo():
    try:
        distro = platform.freedesktop_os_release().get("PRETTY_NAME", "Linux")
    except OSError:
        distro = "Linux"
    try:
        import psutil
        ram = f"{psutil.virtual_memory().total / 1024 ** 3:.0f} GB RAM"
    except Exception:
        ram = ""
    nucleos = f"{os.cpu_count()} núcleos"
    return distro, " · ".join(x for x in (nucleos, ram) if x)


class IntroTux(QWidget):
    terminada = pyqtSignal()

    def __init__(self, destino=None):
        """destino: QPoint global donde aparecerá Tux (el logo vuela hasta ahí al final)."""
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        pantalla = QApplication.primaryScreen().geometry()
        self.setGeometry(pantalla)
        self.destino = destino
        self.logo = QPixmap("assets/tux.png")
        distro, hw = _datos_equipo()
        self.lineas = [
            ("Leyendo tu equipo", f"{distro} · {hw}"),
            ("Conectando con la IA local", "100% en tu PC, nada sale a internet"),
            ("Preparando tu cuaderno", "listo para aprender"),
        ]
        rnd = random.Random(7)
        # partículas: (radio, ángulo inicial, velocidad, tamaño, color)
        colores = [QColor("#FF7A3D"), QColor("#FFB27A"), QColor("#4FD1C5"), QColor("#B794F4")]
        self.particulas = [(rnd.uniform(120, 260), rnd.uniform(0, 2 * math.pi), rnd.uniform(0.25, 0.9) * rnd.choice((1, -1)),
                            rnd.uniform(1.5, 3.6), rnd.choice(colores)) for _ in range(46)]
        self.reloj = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self._cerrando = False

    def empezar(self):
        self.show()
        self.raise_()
        self.reloj.start()
        self.timer.start(16)

    def _terminar(self):
        if self._cerrando:
            return
        self._cerrando = True
        self.timer.stop()
        self.terminada.emit()
        self.close()

    def mousePressEvent(self, _):
        self._terminar()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Escape, Qt.Key_Space, Qt.Key_Return):
            self._terminar()

    # ---------- dibujo ----------
    def paintEvent(self, _):
        t = self.reloj.elapsed() / 1000.0 if self.reloj.isValid() else 0.0
        if t >= DURACION:
            QTimer.singleShot(0, self._terminar)
            t = DURACION
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        centro = QPointF(w / 2, h / 2 - 40)

        salida = _ease_in_out(_tramo(t, 6.2, DURACION))  # fase final: todo se va

        # 1) Fondo: oscurece con viñeta
        fondo = _tramo(t, 0.0, 0.45) * (1 - salida)
        grad = QRadialGradient(centro, max(w, h) * 0.75)
        grad.setColorAt(0.0, QColor(22, 14, 10, int(235 * fondo)))
        grad.setColorAt(0.5, QColor(10, 10, 14, int(240 * fondo)))
        grad.setColorAt(1.0, QColor(0, 0, 0, int(250 * fondo)))
        p.fillRect(self.rect(), QBrush(grad))

        alfa_general = 1 - salida

        # 2) Partículas en órbita
        aparicion = _tramo(t, 0.5, 1.4) * alfa_general
        if aparicion > 0:
            for radio, ang, vel, tam, color in self.particulas:
                a = ang + vel * t
                r = radio * (0.6 + 0.4 * _ease_out_cubic(_tramo(t, 0.5, 1.6)))
                x = centro.x() + r * math.cos(a)
                y = centro.y() + r * math.sin(a) * 0.55  # órbita elíptica
                c = QColor(color)
                c.setAlphaF(0.75 * aparicion * (0.5 + 0.5 * math.sin(t * 3 + radio)))
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawEllipse(QPointF(x, y), tam, tam)

        # 3) Anillo naranja que se dibuja + brillo
        anillo = _ease_out_cubic(_tramo(t, 0.25, 1.15))
        r_anillo = 96
        if anillo > 0:
            for grosor, alfa in ((16, 25), (9, 50), (3.5, 255)):
                c = QColor(NARANJA)
                c.setAlpha(int(alfa * alfa_general))
                pen = QPen(c, grosor)
                pen.setCapStyle(Qt.RoundCap)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawArc(QRectF(centro.x() - r_anillo, centro.y() - r_anillo, 2 * r_anillo, 2 * r_anillo),
                          90 * 16, int(-360 * 16 * anillo))
            # segundo anillo fino girando
            c = QColor(255, 178, 122, int(120 * alfa_general * _tramo(t, 0.9, 1.4)))
            pen = QPen(c, 1.5)
            pen.setDashPattern([2, 6])
            p.setPen(pen)
            r2 = r_anillo + 16
            p.save()
            p.translate(centro)
            p.rotate(t * 40)
            p.drawEllipse(QPointF(0, 0), r2, r2)
            p.restore()

        # 4) Onda expansiva cuando aparece Tux
        onda = _tramo(t, 1.0, 1.9)
        if 0 < onda < 1:
            c = QColor(NARANJA)
            c.setAlphaF(0.55 * (1 - onda) * alfa_general)
            p.setPen(QPen(c, 2.5))
            p.setBrush(Qt.NoBrush)
            r = r_anillo + 260 * _ease_out_cubic(onda)
            p.drawEllipse(centro, r, r)

        # 5) Tux: rebote + brillo pulsante; al final vuela a su sitio en el escritorio
        tux_t = _tramo(t, 0.6, 1.35)
        if tux_t > 0 and not self.logo.isNull():
            escala = max(0.0, _ease_out_back(tux_t)) * (1 + 0.03 * math.sin(t * 4) * (1 - salida))
            tam = 130 * escala
            pos = QPointF(centro)
            if salida > 0 and self.destino is not None:
                dest = QPointF(self.mapFromGlobal(self.destino))
                pos = QPointF(centro.x() + (dest.x() - centro.x()) * salida, centro.y() + (dest.y() - centro.y()) * salida)
                tam = tam * (1 - 0.35 * salida)
            brillo = QRadialGradient(pos, tam * 1.1)
            brillo.setColorAt(0, QColor(255, 122, 61, int(110 * (0.7 + 0.3 * math.sin(t * 5)) * tux_t)))
            brillo.setColorAt(1, QColor(255, 122, 61, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(brillo))
            p.drawEllipse(pos, tam * 1.1, tam * 1.1)
            p.setOpacity(min(1.0, tux_t * 1.6))
            p.drawPixmap(QRectF(pos.x() - tam / 2, pos.y() - tam / 2, tam, tam), self.logo, QRectF(self.logo.rect()))
            p.setOpacity(1.0)

        # 6) Título que se escribe letra a letra con cursor
        titulo = "Tux Assistant"
        escrito = int(len(titulo) * _tramo(t, 1.3, 2.3))
        if escrito > 0:
            f = QFont("Inter")
            f.setPointSize(34)
            f.setWeight(QFont.Black)
            f.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
            p.setFont(f)
            y_titulo = centro.y() + r_anillo + 70
            texto = titulo[:escrito]
            ancho_total = p.fontMetrics().width(titulo)
            x0 = w / 2 - ancho_total / 2
            p.setPen(QColor(255, 255, 255, int(255 * alfa_general)))
            p.drawText(QPointF(x0, y_titulo), texto[:3])
            if len(texto) > 3:
                p.setPen(QColor(255, 122, 61, int(255 * alfa_general)))
                p.drawText(QPointF(x0 + p.fontMetrics().width("Tux"), y_titulo), texto[3:])
            if escrito < len(titulo) or int(t * 3) % 2 == 0:
                p.fillRect(QRectF(x0 + p.fontMetrics().width(texto) + 4, y_titulo - 32, 4, 36),
                           QColor(255, 122, 61, int(230 * alfa_general)))

        # 7) Subtítulo
        sub = _ease_out_cubic(_tramo(t, 2.2, 2.9))
        if sub > 0:
            f = QFont("Inter")
            f.setPointSize(13)
            p.setFont(f)
            p.setPen(QColor(200, 200, 215, int(255 * sub * alfa_general)))
            y = centro.y() + r_anillo + 108 + 10 * (1 - sub)
            p.drawText(QRectF(0, y - 20, w, 30), Qt.AlignCenter, "Aprende Linux con tu propio pingüino · IA 100% local")

        # 8) «Arranque» con datos reales del equipo
        base_y = centro.y() + r_anillo + 160
        f = QFont("JetBrains Mono")
        f.setStyleHint(QFont.Monospace)
        f.setPointSize(10)
        p.setFont(f)
        for i, (accion, detalle) in enumerate(self.lineas):
            ini = 2.9 + i * 0.8
            a = _tramo(t, ini, ini + 0.3) * alfa_general
            if a <= 0:
                continue
            listo = t > ini + 0.65
            y = base_y + i * 24
            x = w / 2 - 250
            p.setPen(QColor(74, 222, 128, int(255 * a)) if listo else QColor(255, 122, 61, int(255 * a)))
            p.drawText(QPointF(x, y), "✓" if listo else "❯")
            p.setPen(QColor(236, 236, 241, int(255 * a)))
            p.drawText(QPointF(x + 22, y), accion)
            p.setPen(QColor(138, 138, 158, int(255 * a)))
            p.drawText(QPointF(x + 22 + p.fontMetrics().width(accion) + 12, y), detalle)

        # 9) Barra de progreso
        barra = _ease_in_out(_tramo(t, 2.9, 5.4))
        if barra > 0:
            ancho = 500
            x = w / 2 - ancho / 2
            y = base_y + 3 * 24 + 6
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(40, 40, 54, int(255 * alfa_general)))
            p.drawRoundedRect(QRectF(x, y, ancho, 4), 2, 2)
            p.setBrush(QColor(255, 122, 61, int(255 * alfa_general)))
            p.drawRoundedRect(QRectF(x, y, ancho * barra, 4), 2, 2)

        # pista para saltar
        if t > 0.8 and salida == 0:
            f = QFont("Inter")
            f.setPointSize(9)
            p.setFont(f)
            p.setPen(QColor(120, 120, 140, 160))
            p.drawText(QRectF(0, max(h - 50, base_y + 3 * 24 + 30), w, 20), Qt.AlignCenter, "Clic para saltar")


class DespedidaTux(QWidget):
    """Animación de cierre (≈3,8 s, clic o Esc para saltar).

    Tux sale de su sitio y vuela al centro → un anillo se dibuja → saluda (se balancea) mientras se
    escribe «¡Hasta pronto!» con el resumen de la sesión → todo se contrae en un destello y se apaga.
    """
    terminada = pyqtSignal()
    DURACION = 3.8

    def __init__(self, origen, resumen=""):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setGeometry(QApplication.primaryScreen().geometry())
        self.origen = origen
        self.resumen = resumen
        self.logo = QPixmap("assets/tux.png")
        rnd = random.Random(11)
        colores = [QColor("#FF7A3D"), QColor("#FFB27A"), QColor("#4FD1C5"), QColor("#B794F4")]
        self.particulas = [(rnd.uniform(140, 300), rnd.uniform(0, 2 * math.pi), rnd.uniform(0.3, 1.0) * rnd.choice((1, -1)),
                            rnd.uniform(1.5, 3.4), rnd.choice(colores)) for _ in range(50)]
        self.reloj = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self._cerrando = False

    def empezar(self):
        self.show()
        self.raise_()
        self.reloj.start()
        self.timer.start(16)

    def _terminar(self):
        if self._cerrando:
            return
        self._cerrando = True
        self.timer.stop()
        self.hide()
        self.terminada.emit()
        self.close()

    def mousePressEvent(self, _):
        self._terminar()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Escape, Qt.Key_Space, Qt.Key_Return):
            self._terminar()

    def paintEvent(self, _):
        t = self.reloj.elapsed() / 1000.0 if self.reloj.isValid() else 0.0
        if t >= self.DURACION:
            QTimer.singleShot(0, self._terminar)
            t = self.DURACION
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        centro = QPointF(w / 2, h / 2 - 40)
        colapso = _ease_in_out(_tramo(t, 2.75, 3.35))   # todo se contrae al centro
        apagado = _tramo(t, 3.3, self.DURACION)          # el fondo se desvanece
        alfa = 1 - colapso

        # Fondo
        fondo = _tramo(t, 0.0, 0.4) * (1 - apagado)
        grad = QRadialGradient(centro, max(w, h) * 0.75)
        grad.setColorAt(0.0, QColor(22, 14, 10, int(230 * fondo)))
        grad.setColorAt(0.6, QColor(10, 10, 14, int(240 * fondo)))
        grad.setColorAt(1.0, QColor(0, 0, 0, int(250 * fondo)))
        p.fillRect(self.rect(), QBrush(grad))

        # Partículas que orbitan y al final se tragan hacia el centro
        aparicion = _tramo(t, 0.3, 1.0)
        for radio, ang, vel, tam, color in self.particulas:
            a = ang + vel * t * (1 + 3 * colapso)
            r = radio * (1 - colapso) * (0.7 + 0.3 * aparicion)
            c = QColor(color)
            c.setAlphaF(0.7 * aparicion * (1 - apagado))
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawEllipse(QPointF(centro.x() + r * math.cos(a), centro.y() + r * math.sin(a) * 0.55), tam, tam)

        # Anillo
        anillo = _ease_out_cubic(_tramo(t, 0.45, 1.1))
        r_anillo = 96 * (1 - colapso)
        if anillo > 0 and r_anillo > 1:
            for grosor, a_ in ((16, 25), (9, 50), (3.5, 255)):
                c = QColor(NARANJA)
                c.setAlpha(int(a_ * alfa))
                pen = QPen(c, grosor)
                pen.setCapStyle(Qt.RoundCap)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawArc(QRectF(centro.x() - r_anillo, centro.y() - r_anillo, 2 * r_anillo, 2 * r_anillo),
                          90 * 16, int(360 * 16 * anillo))

        # Tux: vuela desde su sitio al centro, saluda balanceándose y se encoge en el colapso
        if not self.logo.isNull() and colapso < 1:
            vuelo = _ease_out_cubic(_tramo(t, 0.0, 0.8))
            origen = QPointF(self.mapFromGlobal(self.origen)) if self.origen is not None else centro
            pos = QPointF(origen.x() + (centro.x() - origen.x()) * vuelo, origen.y() + (centro.y() - origen.y()) * vuelo)
            tam = (90 + 40 * vuelo) * (1 - colapso)
            brillo = QRadialGradient(pos, max(tam, 1) * 1.1)
            brillo.setColorAt(0, QColor(255, 122, 61, int(110 * vuelo * alfa)))
            brillo.setColorAt(1, QColor(255, 122, 61, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(brillo))
            p.drawEllipse(pos, tam * 1.1, tam * 1.1)
            saludo = _tramo(t, 0.9, 2.6)
            angulo = 9 * math.sin(saludo * math.pi * 5) * (1 - _tramo(t, 2.3, 2.6)) if saludo > 0 else 0
            p.save()
            p.translate(pos)
            p.rotate(angulo)
            p.drawPixmap(QRectF(-tam / 2, -tam / 2, tam, tam), self.logo, QRectF(self.logo.rect()))
            p.restore()

        # Destello final
        destello = _tramo(t, 3.2, self.DURACION)
        if 0 < destello < 1:
            c = QColor(255, 210, 184)
            c.setAlphaF(0.9 * (1 - destello))
            p.setPen(QPen(c, 3))
            p.setBrush(Qt.NoBrush)
            r = 6 + 420 * _ease_out_cubic(destello)
            p.drawEllipse(centro, r, r)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawEllipse(centro, 10 * (1 - destello), 10 * (1 - destello))

        # Texto: «¡Hasta pronto!» letra a letra + mensaje + resumen de la sesión
        titulo = "¡Hasta pronto!"
        escrito = int(len(titulo) * _tramo(t, 0.9, 1.5))
        if escrito > 0 and alfa > 0:
            f = QFont("Inter")
            f.setPointSize(34)
            f.setWeight(QFont.Black)
            p.setFont(f)
            y = centro.y() + 96 + 70
            ancho = p.fontMetrics().width(titulo)
            x0 = w / 2 - ancho / 2
            p.setPen(QColor(255, 255, 255, int(255 * alfa)))
            p.drawText(QPointF(x0, y), titulo[:escrito])
            if escrito < len(titulo) or int(t * 3) % 2 == 0:
                p.fillRect(QRectF(x0 + p.fontMetrics().width(titulo[:escrito]) + 4, y - 32, 4, 36),
                           QColor(255, 122, 61, int(230 * alfa)))
        sub = _ease_out_cubic(_tramo(t, 1.4, 1.9)) * alfa
        if sub > 0:
            f = QFont("Inter")
            f.setPointSize(13)
            p.setFont(f)
            p.setPen(QColor(200, 200, 215, int(255 * sub)))
            p.drawText(QRectF(0, centro.y() + 96 + 92, w, 30), Qt.AlignCenter,
                       "Sigue practicando: Linux se aprende usándolo 🐧".replace(" 🐧", ""))
        res = _ease_out_cubic(_tramo(t, 1.7, 2.2)) * alfa
        if res > 0 and self.resumen:
            f = QFont("JetBrains Mono")
            f.setStyleHint(QFont.Monospace)
            f.setPointSize(10)
            p.setFont(f)
            p.setPen(QColor(74, 222, 128, int(255 * res)))
            p.drawText(QRectF(0, centro.y() + 96 + 128, w, 24), Qt.AlignCenter, "✓ " + self.resumen)
