import os
# Las rutas de los recursos (assets/...) son relativas: se trabaja siempre desde la carpeta de la app
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
# Fuerza XWayland: en Wayland nativo Qt no puede mover la ventana ni dejarla siempre encima
os.environ['QT_QPA_PLATFORM'] = 'xcb'

try:  # el sonido es opcional: sin pygame Tux funciona igual, solo que en silencio
    import pygame
    from pygame import mixer
except ImportError:
    pygame = mixer = None

import sys
import re
import signal
import requests
import subprocess
import time
import socket

from PyQt5.QtWidgets import QApplication, QStackedWidget, QToolTip, QLabel, QInputDialog, QLineEdit, QTextEdit, QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QScrollArea, QFrame
from PyQt5.QtCore import Qt, QPoint, QRectF, QSize, QTimer, QThread, pyqtSignal, QRect, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QPainterPath, QPixmap, QMovie, QGuiApplication, QCursor, QPainter, QBrush, QPen, QPolygon, QColor, QFont

import psutil
import platform
import datetime
import socket as sock
import json
from typing import Dict, List

import getpass
USERNAME = getpass.getuser()

# Capa pedagógica y contexto mínimo (archivo pedagogia.py, en esta misma carpeta)
from pedagogia import (
    cargar_nivel,
    guardar_nivel,
    detectar_cambio_nivel,
    construir_system_prompt,
    obtener_contexto_minimo,
    pide_mas_detalle,
    max_tokens,
    respuesta_identidad,
)
import contexto_sistema
import herramientas
import riesgo
import terminal
import aprendizaje
import cuaderno
import emoji
import html
from formato import md_a_html, extraer_comandos, resumen, NARANJA, TEXTO, TEXTO_SUAVE


OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
OLLAMA_PORT = 11434
# Modelo deja de descargarse de la GPU tras 5 min por defecto; así se mantiene cargado
OLLAMA_KEEP_ALIVE = "30m"

# Preferencia de modelos: los de ~3B caben enteros en una GPU de 4 GB y responden mucho más rápido.
# Se puede forzar uno con la variable de entorno TUX_MODEL (ej. TUX_MODEL=mistral ./run.sh)
MODELOS_PREFERIDOS = ["qwen3:4b-instruct-2507-q4_K_M", "qwen2.5:3b", "llama3.2:3b", "qwen2.5:1.5b", "mistral"]
_modelo_elegido = None


def elegir_modelo():
    """Devuelve TUX_MODEL o el primer modelo preferido que esté instalado en Ollama."""
    global _modelo_elegido
    if _modelo_elegido:
        return _modelo_elegido
    forzado = os.environ.get("TUX_MODEL")
    if not forzado:  # el instalador guarda aquí el modelo elegido si no es el de por defecto
        try:
            with open(os.path.expanduser("~/.config/tux-assistant/modelo"), encoding="utf-8") as f:
                forzado = f.read().strip() or None
        except OSError:
            forzado = None
    if forzado:
        _modelo_elegido = forzado
        return forzado
    try:
        instalados = [m["name"] for m in requests.get(OLLAMA_TAGS_URL, timeout=3).json().get("models", [])]
    except Exception:
        return MODELOS_PREFERIDOS[-1]  # Ollama aún no responde: no se cachea, se reintenta luego
    for preferido in MODELOS_PREFERIDOS:
        for nombre in instalados:
            if nombre == preferido or nombre == preferido + ":latest":
                _modelo_elegido = nombre
                return nombre
    _modelo_elegido = instalados[0] if instalados else MODELOS_PREFERIDOS[-1]
    return _modelo_elegido


def precalentar_modelo():
    """Carga el modelo en memoria al arrancar para que la primera respuesta no espere la carga."""
    for _ in range(10):
        if ollama_running():
            break
        time.sleep(1)
    try:
        requests.post(
            OLLAMA_CHAT_URL,
            json={"model": elegir_modelo(), "messages": [], "keep_alive": OLLAMA_KEEP_ALIVE},
            timeout=120,
        )
    except Exception:
        pass


# 📁 RUTAS DE ANIMACIONES
TUX_ANIMATIONS = {
    'sentado': 'assets/tux_sentado.gif',
    'busqueda': 'assets/tux_busqueda.gif',
    'busqueda2': 'assets/tux_busqueda2.gif',
    'relajado': 'assets/tux_relajado.gif',
    'relajado2': 'assets/tux_relajado2.gif',
    'relajado3': 'assets/tux_relajado3.gif',
    'relajado4': 'assets/tux_relajado4.gif',
    'relajado5': 'assets/tux_relajado5.gif',
    'caminando': 'assets/tux_caminando.gif'
}

def verify_animations():
    """Verifica que existan todas las animaciones"""
    missing = []
    for name, path in TUX_ANIMATIONS.items():
        if not os.path.exists(path):
            missing.append(name)
    
    if missing:
        # print(f"Animaciones faltantes: {', '.join(missing)}")
        return False
    return True

# 🔍 Verificar si Ollama está corriendo
def ollama_running():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", OLLAMA_PORT)) == 0

# 🚀 Iniciar Ollama
def start_ollama():
    if not ollama_running():
        # print("Iniciando Ollama...")
        process = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(3)
        return process
    return None

# 🔧 FUNCIONES PARA RECOPILAR INFORMACIÓN DEL SISTEMA
def get_system_info() -> Dict:
    """Obtiene información completa del sistema"""
    info = {}
    
    try:
        # Información básica del sistema
        info['sistema'] = {
            'sistema_operativo': platform.system(),
            'distribucion': platform.freedesktop_os_release().get('PRETTY_NAME', 'Desconocida') 
                if os.path.exists('/etc/os-release') else platform.platform(),
            'version_kernel': platform.release(),
            'arquitectura': platform.machine(),
            'hostname': sock.gethostname(),
            'usuario': USERNAME,
            'fecha_hora': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'zona_horaria': time.tzname[0] if time.daylight else time.tzname[1]
        }
        
        # Información de CPU
        cpu_info = {
            'nucleos_fisicos': psutil.cpu_count(logical=False),
            'nucleos_logicos': psutil.cpu_count(logical=True),
            'uso_actual': f"{psutil.cpu_percent(interval=0.1)}%",
            'frecuencia_actual': f"{psutil.cpu_freq().current:.2f} MHz" if psutil.cpu_freq() else "N/A"
        }
        info['cpu'] = cpu_info
        
        # Información de memoria
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        info['memoria'] = {
            'total_ram': f"{mem.total / (1024**3):.2f} GB",
            'ram_disponible': f"{mem.available / (1024**3):.2f} GB",
            'ram_usada': f"{mem.used / (1024**3):.2f} GB",
            'porcentaje_ram_usada': f"{mem.percent}%",
            'total_swap': f"{swap.total / (1024**3):.2f} GB" if swap.total > 0 else "0 GB",
            'swap_usada': f"{swap.used / (1024**3):.2f} GB" if swap.total > 0 else "0 GB"
        }
        
        # Información de disco
        disk_info = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_info.append({
                    'dispositivo': partition.device,
                    'punto_montaje': partition.mountpoint,
                    'sistema_archivos': partition.fstype,
                    'total': f"{usage.total / (1024**3):.2f} GB",
                    'usado': f"{usage.used / (1024**3):.2f} GB",
                    'libre': f"{usage.free / (1024**3):.2f} GB",
                    'porcentaje_usado': f"{usage.percent}%"
                })
            except:
                continue
        info['discos'] = disk_info
        
        # Procesos en ejecución
        procesos = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    pinfo = proc.info
                    if pinfo['cpu_percent'] is not None and pinfo['cpu_percent'] > 0.1:
                        procesos.append({
                            'pid': pinfo['pid'],
                            'nombre': pinfo['name'],
                            'cpu': f"{pinfo['cpu_percent']:.1f}%",
                            'memoria': f"{pinfo['memory_percent']:.1f}%"
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # Ordenar por uso de CPU
            procesos.sort(key=lambda x: float(x['cpu'].replace('%', '')), reverse=True)
            info['procesos_top'] = procesos[:10]
        except:
            info['procesos_top'] = []
        
        # Información de red
        net_info = []
        try:
            for interface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == sock.AF_INET:
                        net_info.append({
                            'interfaz': interface,
                            'ip': addr.address,
                            'mascara': addr.netmask
                        })
        except:
            pass
        info['red'] = net_info
        
        # Información de carga del sistema
        load = os.getloadavg()
        info['carga_sistema'] = {
            '1_minuto': load[0],
            '5_minutos': load[1],
            '15_minutos': load[2]
        }
        
        # Tiempo de actividad
        uptime = datetime.datetime.now() - datetime.datetime.fromtimestamp(psutil.boot_time())
        info['uptime'] = str(uptime).split('.')[0]
        
        # Espacio en directorio home del usuario
        home_path = os.path.expanduser("~")
        try:
            home_usage = psutil.disk_usage(home_path)
            info['home_usuario'] = {
                'ruta': home_path,
                'total': f"{home_usage.total / (1024**3):.2f} GB",
                'usado': f"{home_usage.used / (1024**3):.2f} GB",
                'libre': f"{home_usage.free / (1024**3):.2f} GB",
                'porcentaje_usado': f"{home_usage.percent}%"
            }
        except:
            info['home_usuario'] = {'ruta': home_path, 'error': 'No se pudo leer'}
        
    except Exception as e:
        info['error'] = f"No se pudo obtener información del sistema: {str(e)}"
    
    return info

def format_system_info_for_prompt(system_info: Dict) -> str:
    """Formatea la información del sistema para incluir en el prompt"""
    prompt_sections = []
    
    if 'sistema' in system_info:
        sys_info = system_info['sistema']
        prompt_sections.append(f"SISTEMA: {sys_info['distribucion']} | Kernel: {sys_info['version_kernel']} | Usuario: {sys_info['usuario']}")
        prompt_sections.append(f"HOST: {sys_info['hostname']} | Hora: {sys_info['fecha_hora']} | Uptime: {system_info.get('uptime', 'N/A')}")
    
    if 'cpu' in system_info:
        cpu = system_info['cpu']
        prompt_sections.append(f"CPU: {cpu['nucleos_fisicos']} núcleos físicos, {cpu['nucleos_logicos']} lógicos | Uso: {cpu['uso_actual']} | Frecuencia: {cpu.get('frecuencia_actual', 'N/A')}")
    
    if 'memoria' in system_info:
        mem = system_info['memoria']
        prompt_sections.append(f"RAM: {mem['total_ram']} total | {mem['ram_disponible']} libre | {mem['porcentaje_ram_usada']} usado | Swap: {mem['total_swap']}")
    
    if 'discos' in system_info and system_info['discos']:
        disk_summary = []
        for disk in system_info['discos'][:3]:
            disk_summary.append(f"{disk['punto_montaje']}: {disk['porcentaje_usado']} usado ({disk['usado']}/{disk['total']})")
        if disk_summary:
            prompt_sections.append(f"DISCOS: {' | '.join(disk_summary)}")
    
    if 'home_usuario' in system_info and 'error' not in system_info['home_usuario']:
        home = system_info['home_usuario']
        prompt_sections.append(f"HOME ({USERNAME}): {home['porcentaje_usado']} usado ({home['usado']}/{home['total']}) libre: {home['libre']}")
    
    if 'procesos_top' in system_info and system_info['procesos_top']:
        top_procs = []
        for i, proc in enumerate(system_info['procesos_top'][:3], 1):
            top_procs.append(f"{i}. {proc['nombre']} (CPU: {proc['cpu']}, Mem: {proc['memoria']})")
        if top_procs:
            prompt_sections.append(f"PROCESOS TOP: {' | '.join(top_procs)}")
    
    if 'carga_sistema' in system_info:
        load = system_info['carga_sistema']
        prompt_sections.append(f"CARGA: 1min:{load['1_minuto']:.2f} | 5min:{load['5_minutos']:.2f} | 15min:{load['15_minutos']:.2f}")

    if 'red' in system_info and system_info['red']:
        net_summary = []
        for net in system_info['red']:
            if net['interfaz'] != 'lo':
                net_summary.append(f"{net['interfaz']}: {net['ip']}")
        if net_summary:
            prompt_sections.append(f"RED: {' | '.join(net_summary)}")

    return "\n".join(prompt_sections)

def init_audio():
    """Inicializa el sistema de audio"""
    try:
        pygame.init()
        mixer.init()
        mixer.music.set_volume(0.7)
        return True
    except Exception as e:
        # print(f"Error inicializando audio: {e}")
        return False

def play_bubble_sound():
    """Reproduce el sonido de burbuja"""
    try:
        sound_path = "assets/bubble_sound.mp3"
        
        if os.path.exists(sound_path):
            sound = mixer.Sound(sound_path)
            sound.set_volume(0.8)
            sound.play()
        else:
            import numpy as np
            
            sample_rate = 44100
            duration = 0.1
            frequency = 440
            
            samples = []
            for i in range(int(duration * sample_rate)):
                value = np.sin(2 * np.pi * frequency * i / sample_rate)
                samples.append(value * 0.5)
            
            samples = (np.array(samples) * 32767).astype(np.int16)
            sound = pygame.mixer.Sound(buffer=samples.tobytes())
            sound.set_volume(0.6)
            sound.play()
            
    except Exception as e:
        pass  # Silenciar error de sonido

class Bubble(QWidget):
    """Globo de Tux: tarjeta compacta con resumen, primer comando y enlace al chat.

    La respuesta completa (con todo el formato) vive en el chat; aquí solo se
    muestra lo esencial para no tapar la pantalla.
    """
    ANCHO = 300
    SOMBRA = 12        # margen transparente donde se dibuja la sombra
    COLA_ALTO = 9      # alto de la colita que apunta a Tux
    COLA_ANCHO = 18
    RADIO = 14

    def __init__(self, play_sound=True):
        super().__init__()
        self.play_sound = play_sound
        self.tux_assistant = None
        self.current_screen = None
        self.arrow_position = "bottom"
        self.arrow_position_x = 0
        self.arrow_position_y = 0
        self._lado = None
        self.comandos = []
        self.compacto = False
        self.rapido = False   # modo rápido: muestra la respuesta COMPLETA, compacta, sin abrir el cuaderno

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.layout_principal = QVBoxLayout(self)
        self.layout_principal.setSpacing(6)

        # Cabecera: punto naranja + "Tux" + botón cerrar discreto
        cabecera = QHBoxLayout()
        cabecera.setSpacing(6)
        self.titulo = QLabel(f'<span style="color:{NARANJA};">●</span>&nbsp;'
                             f'<span style="color:{TEXTO_SUAVE};">Tux</span>')
        self.titulo.setStyleSheet("font-family:'Inter','Segoe UI','Ubuntu',sans-serif; font-size:10pt; font-weight:600;")
        self.boton_cerrar = QPushButton("✕")
        self.boton_cerrar.setFixedSize(20, 20)
        self.boton_cerrar.setCursor(Qt.PointingHandCursor)
        self.boton_cerrar.setStyleSheet(f"""
            QPushButton {{ background:transparent; border:none; color:{TEXTO_SUAVE}; font-size:10pt; border-radius:10px; }}
            QPushButton:hover {{ background:rgba(255,255,255,0.08); color:#FFFFFF; }}
        """)
        self.boton_cerrar.clicked.connect(self.close_bubble)
        cabecera.addWidget(self.titulo)
        cabecera.addStretch()
        cabecera.addWidget(self.boton_cerrar)
        self.cabecera = QWidget()
        self.cabecera.setLayout(cabecera)
        cabecera.setContentsMargins(0, 0, 0, 0)

        self.cuerpo = QLabel()
        self.cuerpo.setTextFormat(Qt.RichText)
        self.cuerpo.setWordWrap(True)
        self.cuerpo.setOpenExternalLinks(False)
        self.cuerpo.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.cuerpo.setStyleSheet(f"color:{TEXTO}; font-family:'Inter','Segoe UI','Ubuntu',sans-serif; font-size:10.5pt;")
        self.cuerpo.linkActivated.connect(self._enlace)

        self.layout_principal.addWidget(self.cabecera)
        self.layout_principal.addWidget(self.cuerpo)

        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)
        self._duracion = None

        self.fade = QPropertyAnimation(self, b"windowOpacity")
        self.fade.setDuration(160)

        self.screen_check_timer = QTimer()
        self.screen_check_timer.timeout.connect(self.update_screen_if_needed)
        self.screen_check_timer.start(150)
        self.hide()

    # ---------- contenido ----------

    def _margenes(self):
        s, c, cola = self.SOMBRA, self.COLA_ALTO, self.arrow_position
        pad_v, pad_h = 10, (12 if self.compacto else 14)
        self.layout_principal.setContentsMargins(
            s + pad_h + (c if cola == "left" else 0),
            s + pad_v + (c if cola == "top" else 0),
            s + pad_h + (c if cola == "right" else 0),
            s + pad_v + (c if cola == "bottom" else 0),
        )

    def _ancho_tarjeta(self):
        return 74 if self.compacto else (350 if self.rapido else self.ANCHO)

    def _alto_tarjeta(self):
        """Alto de la tarjeta (sin sombra ni cola) para el contenido actual."""
        anterior = self.arrow_position
        self.arrow_position = "bottom"
        self._margenes()
        w = self._ancho_tarjeta() + 2 * self.SOMBRA
        h = self.layout_principal.totalHeightForWidth(w)
        if h <= 0:
            h = self.layout_principal.totalSizeHint().height()
        self.arrow_position = anterior
        self._margenes()
        return h - 2 * self.SOMBRA - self.COLA_ALTO

    def show_text(self, text, duration=None, play_sound=True, accion=None, rapido=False):
        """accion: (href, etiqueta) opcional, se muestra como enlace en lugar de 'Ver respuesta completa'.
        rapido: respuesta del modo rápido (se muestra completa y compacta; el ancho se mantiene al recolocar)."""
        self.hide_timer.stop()
        self.rapido = bool(rapido)
        estaba_oculta = not self.isVisible()
        es_pensando = text.strip() in (".", "..", "...")
        self.compacto = es_pensando

        if es_pensando:
            n = len(text.strip())
            puntos = "".join(
                f'<span style="color:{NARANJA if i < n else "#4A4A58"};">●</span>&nbsp;'
                for i in range(3)
            )
            self.cabecera.hide()
            self.cuerpo.setText(f'<span style="font-size:11pt;">{puntos}</span>')
            self.comandos = []
            texto_visible = ""
        elif self.rapido and not accion:
            # Respuesta rápida: entera, con su comando para copiar, en letra un poco más pequeña
            self.cabecera.show()
            lineas = [l for l in text.split("\n") if not l.strip().startswith(("📊", "🔎", "(Dime «explícame más»"))]
            while lineas and (not lineas[-1].strip() or lineas[-1].strip().endswith("?")):
                lineas.pop()  # en modo rápido no hace falta la pregunta final
            limpio = "\n".join(lineas)
            cuerpo, self.comandos = md_a_html(limpio.strip())
            enlaces = (f'<p style="margin:6px 0 0 0;"><a href="chat:detalle" style="color:{NARANJA}; '
                       f'text-decoration:none; font-weight:600;">Más detalle&nbsp;›</a>'
                       f'&nbsp;&nbsp;&nbsp;&nbsp;<a href="rapida:abrir" style="color:{TEXTO_SUAVE}; '
                       f'text-decoration:none;">Otra pregunta&nbsp;›</a></p>')
            aviso = emoji.a_html("🖱️", 14) + "&nbsp;<b>Doble clic en Tux</b> para el cuaderno completo"
            enlaces += (f'<table width="100%" cellspacing="0" cellpadding="5" style="margin-top:6px;">'
                        f'<tr><td style="background-color:#2A1A12; color:#FFB089; font-size:9pt;">{aviso}</td></tr></table>')
            self.cuerpo.setText(f'<div style="font-size:9.5pt;">{cuerpo}</div>' + enlaces)
            texto_visible = limpio
        else:
            self.cabecera.show()
            frase, recortada = resumen(text)
            self.comandos = extraer_comandos(text)
            partes = []
            if frase:
                partes.append(md_a_html(frase, con_copiar=False)[0])
            if self.comandos:
                partes.append(md_a_html(f"`{self.comandos[0]}`")[0])
            hay_mas = recortada or len(self.comandos) > 1 or len(text) > len(frase) + 40 + sum(map(len, self.comandos[:1]))
            if accion:
                partes.append(
                    f'<p style="margin:4px 0 0 0;"><a href="{accion[0]}" style="color:{NARANJA}; '
                    f'text-decoration:none; font-weight:600;">{accion[1]}&nbsp;›</a></p>'
                )
            else:
                enlaces = []
                if hay_mas:
                    enlaces.append(f'<a href="chat:abrir" style="color:{NARANJA}; text-decoration:none; '
                                   f'font-weight:600;">Ver completa&nbsp;›</a>')
                enlaces.append(f'<a href="rapida:abrir" style="color:{TEXTO_SUAVE}; text-decoration:none;">'
                               f'Otra pregunta&nbsp;›</a>')
                partes.append('<p style="margin:6px 0 0 0;">' + "&nbsp;&nbsp;&nbsp;&nbsp;".join(enlaces) + "</p>")
            if not partes:
                partes.append(md_a_html(text)[0])
            self.cuerpo.setText("".join(partes))
            texto_visible = frase

        self.current_screen = self.get_tux_screen()
        self.position_above_tux()

        if estaba_oculta:
            self.setWindowOpacity(0.0)
            self.show()
            self.fade.stop()
            self.fade.setStartValue(0.0)
            self.fade.setEndValue(1.0)
            self.fade.start()
        self.update()

        if play_sound and self.play_sound:
            play_bubble_sound()

        if duration:
            # El tiempo depende de lo que se ve en el globo, no de la respuesta completa
            tope = 40000 if self.rapido else 20000
            self._duracion = min(5000 + len(texto_visible) * 55 + (4000 if self.comandos else 0), tope)
            self.hide_timer.start(self._duracion)

    def _enlace(self, href):
        from formato import texto_de_enlace
        if texto_de_enlace(href):
            QApplication.clipboard().setText(texto_de_enlace(href))
            QToolTip.showText(QCursor.pos(), "Copiado ✓", self)
        elif href.startswith("copiar:"):
            i = int(href.split(":", 1)[1])
            if i < len(self.comandos):
                QApplication.clipboard().setText(self.comandos[i])
                QToolTip.showText(QCursor.pos(), "Copiado ✓", self)
        elif href == "chat:abrir" and self.tux_assistant:
            self.close_bubble()
            self.tux_assistant.chat_window.show_chat()
        elif href == "chat:detalle" and self.tux_assistant:
            # De la respuesta rápida al cuaderno, pidiendo la explicación completa
            self.close_bubble()
            chat = self.tux_assistant.chat_window
            chat.show_chat()
            chat._ir_a(chat.TAB_PREGUNTAS)
            chat._enviar_texto("Explícame más a fondo")
        elif href == "rapida:abrir" and self.tux_assistant:
            self.close_bubble()
            self.tux_assistant.abrir_pregunta_rapida()
        elif href == "tux:explicar" and self.tux_assistant:
            self.close_bubble()
            self.tux_assistant.explicar_error_terminal()

    # El globo no se esconde mientras el ratón está encima
    def enterEvent(self, event):
        self.hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._duracion and self.isVisible() and not self.compacto:
            self.hide_timer.start(3500)
        super().leaveEvent(event)

    # ---------- dibujo ----------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s, c, cola_lado = self.SOMBRA, self.COLA_ALTO, self.arrow_position
        caja = QRectF(s, s, self.width() - 2 * s, self.height() - 2 * s)
        if cola_lado == "top":
            caja.setTop(caja.top() + c)
        elif cola_lado == "bottom":
            caja.setBottom(caja.bottom() - c)
        elif cola_lado == "left":
            caja.setLeft(caja.left() + c)
        else:
            caja.setRight(caja.right() - c)

        forma = QPainterPath()
        forma.addRoundedRect(caja, self.RADIO, self.RADIO)
        if not self.compacto:
            m = self.RADIO + self.COLA_ANCHO / 2
            a = self.COLA_ANCHO / 2
            cola = QPainterPath()
            if cola_lado in ("top", "bottom"):
                x = max(caja.left() + m, min(self.arrow_position_x, caja.right() - m))
                borde = caja.top() if cola_lado == "top" else caja.bottom()
                dentro = 1 if cola_lado == "top" else -1
                punta = borde - c if cola_lado == "top" else borde + c
                cola.moveTo(x - a, borde + dentro)
                cola.lineTo(x, punta)
                cola.lineTo(x + a, borde + dentro)
            else:
                y = max(caja.top() + m, min(self.arrow_position_y, caja.bottom() - m))
                borde = caja.left() if cola_lado == "left" else caja.right()
                dentro = 1 if cola_lado == "left" else -1
                punta = borde - c if cola_lado == "left" else borde + c
                cola.moveTo(borde + dentro, y - a)
                cola.lineTo(punta, y)
                cola.lineTo(borde + dentro, y + a)
            cola.closeSubpath()
            forma = forma.united(cola)

        # Sombra suave: capas translúcidas cada vez más grandes
        p.setPen(Qt.NoPen)
        for i in range(s, 0, -2):
            p.setBrush(QColor(0, 0, 0, int(28 * (1 - i / s)) + 4))
            p.drawRoundedRect(caja.adjusted(-i / 2, -i / 2 + 3, i / 2, i / 2 + 3), self.RADIO + i / 2, self.RADIO + i / 2)

        p.setBrush(QColor(20, 20, 28, 246))
        p.setPen(QPen(QColor(255, 122, 61, 120), 1))
        p.drawPath(forma)

        # Línea de acento naranja arriba
        if not self.compacto:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 122, 61, 200))
            p.drawRoundedRect(QRectF(caja.left() + 18, caja.top(), 34, 2.5), 1.2, 1.2)
        p.end()

    # ---------- posición ----------

    def set_tux_assistant(self, tux_assistant):
        self.tux_assistant = tux_assistant

    def get_tux_screen(self):
        if not self.tux_assistant:
            return QApplication.primaryScreen()
        for screen in QGuiApplication.screens():
            if screen.geometry().contains(self.tux_assistant.pos()):
                return screen
        return QApplication.primaryScreen()

    def update_screen_if_needed(self):
        if not self.tux_assistant or not self.isVisible():
            return
        nueva = self.get_tux_screen()
        if nueva != self.current_screen:
            self.current_screen = nueva
            self.position_above_tux()

    # Lado del globo respecto a Tux -> lado donde va la cola
    _COLA_POR_LADO = {"arriba": "bottom", "abajo": "top", "derecha": "left", "izquierda": "right"}

    def position_above_tux(self):
        """Coloca el globo junto a Tux sin taparlo nunca.

        Prueba arriba, abajo, derecha e izquierda; usa el primero que quepa entero en
        pantalla sin tocar a Tux ni al chat. Mientras se arrastra, conserva el lado
        actual si sigue cabiendo, para que no salte de un lado a otro.
        """
        pantalla = (self.current_screen or self.get_tux_screen() or QApplication.primaryScreen()).availableGeometry()
        s, c, gap, borde = self.SOMBRA, self.COLA_ALTO, 4, 8
        card_w, card_h = self._ancho_tarjeta(), self._alto_tarjeta()

        if not self.tux_assistant:
            self._aplicar_lado("bottom", card_w, card_h)
            self.move(pantalla.right() - self.width() - 40, pantalla.top() + 40)
            return

        tux = self.tux_assistant.frameGeometry()
        obstaculos = []
        chat = getattr(self.tux_assistant, "chat_window", None)
        if chat is not None and chat.isVisible():
            obstaculos.append(chat.frameGeometry())

        izq, der = pantalla.left() + borde, pantalla.right() - borde
        arr, aba = pantalla.top() + borde, pantalla.bottom() - borde

        def limitar(v, minimo, maximo):
            return max(minimo, min(v, maximo)) if maximo >= minimo else minimo

        def candidato(lado):
            """Rectángulo ocupado (tarjeta + cola) o None si no cabe en ese lado."""
            if lado in ("arriba", "abajo"):
                x = limitar(tux.center().x() - card_w // 2, izq, der - card_w)
                if lado == "arriba":
                    y = tux.top() - gap - c - card_h
                    ocupado = QRect(x, y, card_w, card_h + c)
                else:
                    y = tux.bottom() + gap + c
                    ocupado = QRect(x, y - c, card_w, card_h + c)
            else:
                y = limitar(tux.center().y() - card_h // 2, arr, aba - card_h)
                if lado == "derecha":
                    x = tux.right() + gap + c
                    ocupado = QRect(x - c, y, card_w + c, card_h)
                else:
                    x = tux.left() - gap - c - card_w
                    ocupado = QRect(x, y, card_w + c, card_h)
            tarjeta = QRect(x, y, card_w, card_h)
            if tarjeta.left() < izq or tarjeta.right() > der or tarjeta.top() < arr or tarjeta.bottom() > aba:
                return None
            if ocupado.intersects(tux):
                return None
            return tarjeta, ocupado

        orden = ["arriba", "abajo", "derecha", "izquierda"]
        previo = getattr(self, "_lado", None)
        if previo in orden:  # histéresis: primero intenta quedarse donde está
            orden.remove(previo)
            orden.insert(0, previo)

        elegido = None
        validos = [(lado, candidato(lado)) for lado in orden]
        validos = [(lado, r) for lado, r in validos if r]
        for lado, (tarjeta, ocupado) in validos:
            if not any(ocupado.intersects(o) for o in obstaculos):
                elegido = (lado, tarjeta)
                break
        if elegido is None and validos:
            elegido = (validos[0][0], validos[0][1][0])
        if elegido is None:
            # Pantalla muy justa: el lado con más espacio libre, ajustado a la pantalla
            espacio = {
                "arriba": tux.top() - arr, "abajo": aba - tux.bottom(),
                "derecha": der - tux.right(), "izquierda": tux.left() - izq,
            }
            lado = max(espacio, key=espacio.get)
            if lado in ("arriba", "abajo"):
                x = limitar(tux.center().x() - card_w // 2, izq, der - card_w)
                y = arr if lado == "arriba" else limitar(tux.bottom() + gap + c, arr, aba - card_h)
            else:
                y = limitar(tux.center().y() - card_h // 2, arr, aba - card_h)
                x = limitar(tux.right() + gap + c, izq, der - card_w) if lado == "derecha" else izq
            elegido = (lado, QRect(x, y, card_w, card_h))

        lado, tarjeta = elegido
        self._lado = lado
        cola = self._COLA_POR_LADO[lado]
        self._aplicar_lado(cola, card_w, card_h)

        x = tarjeta.left() - s - (c if cola == "left" else 0)
        y = tarjeta.top() - s - (c if cola == "top" else 0)
        self.arrow_position_x = tux.center().x() - x
        self.arrow_position_y = tux.center().y() - y
        self.move(int(x), int(y))
        self.raise_()  # siempre por delante de Tux
        self.update()

    def _aplicar_lado(self, cola, card_w, card_h):
        s, c = self.SOMBRA, self.COLA_ALTO
        self.arrow_position = cola
        self._margenes()
        horizontal = cola in ("left", "right")
        self.setFixedSize(card_w + 2 * s + (c if horizontal else 0),
                          card_h + 2 * s + (0 if horizontal else c))

    def close_bubble(self, event=None):
        self.hide()
        self.hide_timer.stop()
        if self.tux_assistant:
            self.tux_assistant.bubble_closed_by_user = True


class PreguntaRapida(QWidget):
    """Modo rápido: un globito con un campo para preguntar. La respuesta sale en el globo de Tux."""
    enviada = pyqtSignal(str)
    ANCHO, ALTO, COLA = 390, 150, 14

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.ANCHO, self.ALTO + self.COLA)
        self.cola_abajo = True
        self.objetivo_x = self.ANCHO // 2
        self.lay = QVBoxLayout(self)
        self.lay.setSpacing(8)
        cab = QHBoxLayout()
        titulo = QLabel('<span style="color:#FF7A3D; font-size:9.5pt; font-weight:800;">PREGUNTA RÁPIDA</span>'
                        '<span style="color:#8A8A9E; font-size:9pt;">&nbsp;&nbsp;respuesta corta en el globo</span>')
        cab.addWidget(titulo)
        cab.addStretch()
        pista = QLabel(emoji.a_html("🖱️", 15) + '&nbsp;<span style="color:#FFB089; font-size:9.5pt;">'
                       '<b>¿Quieres más detalle?</b> Haz <b>doble clic en Tux</b> para abrir el cuaderno completo</span>')
        pista.setTextFormat(Qt.RichText)
        pista.setWordWrap(True)
        pista.setStyleSheet("background:#2A1A12; border:1px solid #4A2A16; border-radius:8px; padding:5px 8px;")
        fila = QHBoxLayout()
        fila.setSpacing(6)
        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("Pregúntale algo corto a Tux…")
        self.entrada.setStyleSheet("QLineEdit { background:#0A0A0F; color:#FFFFFF; border:1px solid #34344A; border-radius:10px;"
                                   " padding:8px 10px; font-size:10.5pt; } QLineEdit:focus { border-color:#FF7A3D; }")
        self.entrada.returnPressed.connect(self._enviar)
        boton = QPushButton("➤")
        boton.setFixedSize(38, 36)
        boton.setCursor(Qt.PointingHandCursor)
        boton.setStyleSheet("QPushButton { background:#FF7A3D; border:none; border-radius:10px; color:#141418;"
                            " font-weight:bold; font-size:11pt; } QPushButton:hover { background:#FF9461; }")
        boton.clicked.connect(self._enviar)
        fila.addWidget(self.entrada)
        fila.addWidget(boton)
        self.lay.addLayout(cab)
        self.lay.addLayout(fila)
        self.lay.addWidget(pista)
        self._margenes()

    def _margenes(self):
        c = self.COLA
        self.lay.setContentsMargins(16, 12 + (0 if self.cola_abajo else c), 16, 12 + (c if self.cola_abajo else 0))

    def _enviar(self):
        texto = self.entrada.text().strip()
        if texto:
            self.entrada.clear()
            self.hide()
            self.enviada.emit(texto)

    def mostrar(self, tux_rect, pantalla):
        """Arriba de Tux si cabe; si no, abajo. La colita apunta al pingüino."""
        dibujo = tux_rect.adjusted(18, 10, -18, -4)
        self.cola_abajo = dibujo.top() - pantalla.top() > self.height() + 8
        self._margenes()
        x = max(pantalla.left() + 8, min(dibujo.center().x() - self.width() // 2, pantalla.right() - 8 - self.width()))
        y = dibujo.top() - self.height() if self.cola_abajo else dibujo.bottom()
        self.objetivo_x = dibujo.center().x() - x
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.entrada.setFocus()
        self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c, base = self.COLA, 13
        cuerpo = QRectF(2, 2 + (0 if self.cola_abajo else c), self.width() - 4, self.ALTO - 4)
        path = QPainterPath()
        path.addRoundedRect(cuerpo, 18, 18)
        x = max(cuerpo.left() + 30, min(self.objetivo_x, cuerpo.right() - 30))
        y0 = cuerpo.bottom() if self.cola_abajo else cuerpo.top()
        y1 = y0 + (c if self.cola_abajo else -c)
        punta = QPainterPath()
        punta.moveTo(x - base, y0 - (1 if self.cola_abajo else -1))
        punta.quadTo(x - 2, y0, x, y1)
        punta.quadTo(x + 2, y0, x + base, y0 - (1 if self.cola_abajo else -1))
        punta.closeSubpath()
        globo = path.united(punta)
        p.setBrush(QColor(14, 14, 20, 247))
        p.setPen(QPen(QColor("#FF7A3D"), 1.4))
        p.drawPath(globo)


GUIA_TUX = """**Así funciona Tux** 🐧
- **Dos modos**: un **clic** en Tux abre la pregunta rápida (la respuesta sale en su globo y se guarda en «Preguntas rápidas»); **doble clic** abre este cuaderno completo.
- **Preguntas**: es tu cuaderno general. Pregunta cualquier duda de Linux o de tu PC; Tux mide datos reales de tu equipo (RAM, disco, red…) y te lo explica. Cada respuesta trae el comando desarmado parte por parte y un botón para copiarlo. Clic en cualquier `código` del texto también lo copia.
- **🚦 Semáforo**: antes de ejecutar algo que encontraste en internet, pégalo con el modo «Analizar comando». Tux lo revisa con reglas fijas (no con la IA): 🟢 seguro, 🟡 cuidado (sudo, borrar, sobrescribir), 🔴 peligroso (borrar el sistema, formatear un disco, ejecutar código de internet).
- **💥 Errores de la terminal**: actívalo en Progreso → «Vigilar mi terminal» y abre una terminal nueva. Si un comando falla, Tux aparece y te explica qué pasó; si escribiste mal algo (`apd` en vez de `apt`) te da el comando corregido. Cada error trae la lección que enseña a evitarlo, avisa si se repite y la pestaña Errores muestra tu semana (con modo silencioso).
- **Mi ruta**: crea un plan de estudio según lo que quieras aprender. Cada plan tiene su propio cuaderno, lecciones y misiones que Tux comprueba en tu equipo. El grafo muestra todos tus planes a la vez.
- **Progreso**: cada misión comprobada da XP según su dificultad (Básico 10 · Avanzado 25 · Experto 40 · Maestro 60). Con XP subes de nivel: Principiante → Intermedio → Avanzado → Experto → Maestro → Arquitecto Linux. Aparte eliges **cómo te explica Tux**: paso a paso, explicado, al grano o técnico a fondo."""


class ChatWindow(QWidget):
    def __init__(self, tux_assistant):
        super().__init__()
        self.tux_assistant = tux_assistant
        self.current_screen = None
        self.nivel = cargar_nivel()  # principiante / intermedio / avanzado
        self.progreso = aprendizaje.cargar_progreso()
        self.chat_id = aprendizaje.CHAT_LIBRE
        self.esperando_meta = False     # tras «＋ Nuevo plan», el próximo mensaje es la meta
        self.mision_pendiente = None    # lección cuya misión se muestra al terminar la explicación
        self.plan_worker = None
        self.preguntas_sesion = 0
        self.xp_inicio = aprendizaje.xp_total(self.progreso)
        self.init_ui()
        self._poblar_selector()
        self._cargar_chat_actual()
        self.setup_animations()
        
        # Timer para verificar cambios de pantalla
        self.screen_check_timer = QTimer()
        self.screen_check_timer.timeout.connect(self.update_screen_if_needed)
        self.screen_check_timer.start(100)
        
    def init_ui(self):
        """Cuaderno de Tux: cabecera con nivel, pestañas (Cuaderno · Mi ruta · Progreso) y barra de entrada"""
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(450, 630)

        main_widget = QWidget()
        main_widget.setObjectName("mainWidget")
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        # --- Cabecera: Tux + nivel con anillo de progreso + cerrar ---
        cab = QHBoxLayout()
        cab.setSpacing(10)
        avatar = QLabel()
        pix = QPixmap("assets/tux.png")
        if not pix.isNull():
            avatar.setPixmap(pix.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        avatar.setFixedSize(30, 30)
        self.lbl_titulo = QLabel()
        self.lbl_titulo.setTextFormat(Qt.RichText)
        self.anillo = cuaderno.AnilloNivel(30, 3)
        close_button = QPushButton("✕")
        close_button.setObjectName("closeButton")
        close_button.setFixedSize(28, 28)
        close_button.setCursor(Qt.PointingHandCursor)
        close_button.clicked.connect(self.hide)
        ayuda = QPushButton("?")
        ayuda.setObjectName("closeButton")
        ayuda.setFixedSize(28, 28)
        ayuda.setCursor(Qt.PointingHandCursor)
        ayuda.setToolTip("Cómo se maneja Tux (ratón y teclado)")
        ayuda.clicked.connect(self._ver_controles)
        cab.addWidget(avatar)
        cab.addWidget(self.lbl_titulo, 1)
        cab.addWidget(self.anillo)
        cab.addWidget(ayuda)
        cab.addWidget(close_button)

        # --- Pestañas ---
        pestanas = QHBoxLayout()
        pestanas.setSpacing(4)
        self.botones_pestana = []
        for i, nombre in enumerate(("Preguntas", "Errores", "Mi ruta", "Progreso")):
            b = QPushButton(nombre)
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(30)
            b.clicked.connect(lambda _, k=i: self._ir_a(k))
            pestanas.addWidget(b)
            self.botones_pestana.append(b)
        contenedor_tabs = QFrame()
        contenedor_tabs.setObjectName("tabs")
        contenedor_tabs.setLayout(pestanas)
        pestanas.setContentsMargins(3, 3, 3, 3)

        self.paginas = QStackedWidget()

        # --- Página 1: cuaderno ---
        pag_cuaderno = QWidget()
        lc = QVBoxLayout(pag_cuaderno)
        lc.setContentsMargins(0, 0, 0, 0)
        lc.setSpacing(8)

        self.banner_plan = QFrame()
        self.banner_plan.setObjectName("bannerPlan")
        lb = QHBoxLayout(self.banner_plan)
        lb.setContentsMargins(10, 6, 6, 6)
        self.lbl_progreso = QLabel()
        self.lbl_progreso.setTextFormat(Qt.RichText)
        self.lbl_progreso.setWordWrap(True)
        # En el cuaderno general lleva a «Mi ruta»; dentro de un plan vuelve al general
        self.boton_banner = QPushButton()
        self.boton_banner.setObjectName("linkButton")
        self.boton_banner.setCursor(Qt.PointingHandCursor)
        self.boton_banner.clicked.connect(
            lambda: self._accion_banner())
        self.boton_nuevo = QPushButton("+ Nuevo")
        self.boton_nuevo.setObjectName("linkButton")
        self.boton_nuevo.setCursor(Qt.PointingHandCursor)
        self.boton_nuevo.setToolTip("Nuevo cuaderno de preguntas")
        self.boton_nuevo.clicked.connect(self._nuevo_cuaderno)
        lb.addWidget(self.lbl_progreso, 1)
        lb.addWidget(self.boton_banner)
        lb.addWidget(self.boton_nuevo)


        self.chat_area = QScrollArea()
        self.chat_area.setWidgetResizable(True)
        self.chat_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chat_container = QWidget()
        self.chat_container.setObjectName("chatContainer")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setSpacing(10)
        self.chat_layout.setContentsMargins(2, 2, 8, 2)
        self.chat_layout.addStretch()
        self.chat_area.setWidget(self.chat_container)

        # Botón flotante para bajar al final (aparece cuando no estás viendo lo último)
        self.boton_abajo = QPushButton("↓", self.chat_area)
        self.boton_abajo.setObjectName("botonAbajo")
        self.boton_abajo.setFixedSize(38, 38)
        self.boton_abajo.setCursor(Qt.PointingHandCursor)
        self.boton_abajo.setToolTip("Ir al final")
        self.boton_abajo.clicked.connect(self._bajar_suave)
        self.boton_abajo.hide()
        barra = self.chat_area.verticalScrollBar()
        barra.valueChanged.connect(self._actualizar_boton_abajo)
        barra.rangeChanged.connect(lambda *_: self._actualizar_boton_abajo())

        # Modos de la barra de entrada (se ocultan en modo estudio)
        self.modos_widget = QWidget()
        modos = QHBoxLayout(self.modos_widget)
        modos.setContentsMargins(0, 0, 0, 0)
        modos.setSpacing(4)
        self.botones_modo = {}
        for clave, nombre in (("preguntar", "Preguntar"), ("analizar", "Analizar comando"), ("error", "Explicar error")):
            b = QPushButton(nombre)
            b.setObjectName("modo")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(24)
            b.clicked.connect(lambda _, c=clave: self._fijar_modo(c))
            modos.addWidget(b)
            self.botones_modo[clave] = b
        modos.addStretch()

        input_widget = QWidget()
        input_widget.setObjectName("inputWidget")
        input_layout = QHBoxLayout(input_widget)
        input_layout.setContentsMargins(6, 4, 4, 4)
        self.input_field = QLineEdit()
        self.input_field.setObjectName("inputField")
        self.input_field.returnPressed.connect(self.send_message)
        send_button = QPushButton("➤")
        send_button.setObjectName("sendButton")
        send_button.setFixedSize(36, 32)
        send_button.setCursor(Qt.PointingHandCursor)
        send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(send_button)

        # Cabecera del cuaderno de preguntas: el nombre del cuaderno actual, bien visible, y acceso al listado
        self.cab_cuaderno = QFrame()
        self.cab_cuaderno.setObjectName("cabCuaderno")
        self.cab_cuaderno.setCursor(Qt.PointingHandCursor)
        lcc = QHBoxLayout(self.cab_cuaderno)
        lcc.setContentsMargins(12, 6, 8, 6)
        lcc.setSpacing(8)
        self.lbl_cuaderno = QLabel()
        self.lbl_cuaderno.setTextFormat(Qt.RichText)
        self.boton_lista = QPushButton("Mis cuadernos ▾")
        self.boton_lista.setObjectName("linkButton")
        self.boton_lista.setCursor(Qt.PointingHandCursor)
        self.boton_lista.clicked.connect(self._alternar_lista)
        self.cab_cuaderno.mousePressEvent = lambda _e: self._alternar_lista()
        lcc.addWidget(self.lbl_cuaderno, 1)
        lcc.addWidget(self.boton_lista)
        self.cab_cuaderno.hide()

        # Listado de cuadernos (ocupa el área del cuaderno mientras está abierto)
        self.lista_scroll = QScrollArea()
        self.lista_scroll.setWidgetResizable(True)
        self.lista_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lista_widget = QWidget()
        self.lay_lista = QVBoxLayout(self.lista_widget)
        self.lay_lista.setContentsMargins(0, 0, 6, 0)
        self.lay_lista.setSpacing(6)
        self.lista_scroll.setWidget(self.lista_widget)
        self.vista_cuaderno = QStackedWidget()

        self.vista_cuaderno.addWidget(self.chat_area)
        self.vista_cuaderno.addWidget(self.lista_scroll)
        # Cabecera del MODO ESTUDIO (cuando estás dentro de una lección de un plan)
        self.cab_estudio = QFrame()
        self.cab_estudio.setObjectName("cabEstudio")
        le = QVBoxLayout(self.cab_estudio)
        le.setContentsMargins(12, 10, 10, 10)
        le.setSpacing(7)
        fe = QHBoxLayout()
        fe.setSpacing(10)
        self.icono_estudio = QLabel()
        self.icono_estudio.setTextFormat(Qt.RichText)
        self.lbl_estudio = QLabel()
        self.lbl_estudio.setTextFormat(Qt.RichText)
        self.lbl_estudio.setWordWrap(True)
        volver_mapa = QPushButton("‹  Volver al mapa")
        volver_mapa.setObjectName("botonMapa")
        volver_mapa.setFixedHeight(30)
        volver_mapa.setCursor(Qt.PointingHandCursor)
        volver_mapa.setToolTip("Volver al mapa de tu ruta")
        volver_mapa.clicked.connect(lambda: self._ir_a(self.TAB_RUTA))
        # Vista compacta (por defecto): una línea con la lección y botones pequeños; clic para desplegar
        self.lbl_compacto = QLabel()
        self.lbl_compacto.setTextFormat(Qt.RichText)
        self.lbl_compacto.setCursor(Qt.PointingHandCursor)
        self.mini_mapa = QPushButton("‹ Mapa")
        self.mini_mapa.setObjectName("miniBoton")
        self.mini_mapa.setCursor(Qt.PointingHandCursor)
        self.mini_mapa.setFixedHeight(26)
        self.mini_mapa.setToolTip("Volver al mapa de tu ruta")
        self.mini_mapa.clicked.connect(lambda: self._ir_a(self.TAB_RUTA))
        self.mini_mision = QPushButton()
        self.mini_mision.setObjectName("miniMision")
        self.mini_mision.setIcon(emoji.icono("🎯"))
        self.mini_mision.setCursor(Qt.PointingHandCursor)
        self.mini_mision.setFixedHeight(26)
        self.mini_mision.setToolTip("Ver la misión de esta lección")
        self.mini_mision.clicked.connect(lambda: (self.panel_mision.setVisible(not self.panel_mision.isVisible()),
                                                  self._pintar_panel_mision()))
        fe.addWidget(self.icono_estudio, 0, Qt.AlignTop)
        fe.addWidget(self.lbl_estudio, 1)
        fe.addWidget(self.lbl_compacto, 1)
        fe.addWidget(self.mini_mapa, 0, Qt.AlignVCenter)
        fe.addWidget(self.mini_mision, 0, Qt.AlignVCenter)
        le.addLayout(fe)
        self._estudio_expandido = False
        for w in (self.lbl_compacto, self.lbl_estudio, self.icono_estudio):
            w.mousePressEvent = lambda _e: self._alternar_cabecera_estudio()
        self.segmentos = cuaderno.BarraSegmentos()
        le.addWidget(self.segmentos)
        self.fila_mapa_w = QWidget()
        fila_mapa = QHBoxLayout(self.fila_mapa_w)
        fila_mapa.setContentsMargins(0, 0, 0, 0)
        fila_mapa.setSpacing(8)
        fila_mapa.addWidget(volver_mapa)
        # La misión siempre a mano: aunque la conversación siga, se consulta aquí
        self.boton_mision = QPushButton("Misión")
        self.boton_mision.setObjectName("botonMision")
        self.boton_mision.setIcon(emoji.icono("🎯"))
        self.boton_mision.setFixedHeight(30)
        self.boton_mision.setCursor(Qt.PointingHandCursor)
        self.boton_mision.setToolTip("Ver la misión de esta lección y lo que te falta")
        self.boton_mision.clicked.connect(lambda: (self.panel_mision.setVisible(not self.panel_mision.isVisible()),
                                                   self._pintar_panel_mision()))
        self.boton_mision.hide()
        fila_mapa.addWidget(self.boton_mision)
        fila_mapa.addStretch()
        le.addWidget(self.fila_mapa_w)
        self.panel_mision = QFrame()
        self.panel_mision.setObjectName("panelMision")
        self.lay_mision = QVBoxLayout(self.panel_mision)
        self.lay_mision.setContentsMargins(12, 10, 12, 10)
        self.lay_mision.setSpacing(6)
        self.panel_mision.hide()
        le.addWidget(self.panel_mision)
        self.cab_estudio.hide()

        lc.addWidget(self.banner_plan)
        lc.addWidget(self.cab_estudio)
        lc.addWidget(self.cab_cuaderno)
        lc.addWidget(self.vista_cuaderno, 1)
        lc.addWidget(self.modos_widget)
        lc.addWidget(input_widget)

        # --- Página 2: ruta ---
        self.panel_ruta = cuaderno.PanelRuta()
        self.panel_ruta.abrir_plan.connect(self._continuar_plan)
        self.panel_ruta.crear_plan.connect(self._crear_plan)
        self.panel_ruta.borrar_plan.connect(self._borrar_plan)
        # --- Página 3: progreso ---
        self.panel_progreso = cuaderno.PanelProgreso()
        self.panel_progreso.cambiar_nivel.connect(self._cambiar_nivel)
        self.panel_progreso.alternar_terminal.connect(self._configurar_terminal)
        self.panel_progreso.ver_contexto.connect(lambda: (self._ir_a(self.TAB_PREGUNTAS), self._enviar_texto("¿Qué sabes de mi pc?")))
        self.panel_controles = cuaderno.PanelControles()
        for panel in (pag_cuaderno, self.panel_ruta, self.panel_progreso, self.panel_controles):
            if panel is pag_cuaderno:
                self.paginas.addWidget(panel)
                continue
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            panel.setObjectName("panel")
            scroll.setWidget(panel)
            self.paginas.addWidget(scroll)

        main_layout.addLayout(cab)
        main_layout.addWidget(contenedor_tabs)
        main_layout.addWidget(self.paginas, 1)

        # El cuaderno es un GLOBO DE DIÁLOGO de Tux: se dibuja a mano (paintEvent) con una colita que le apunta
        self.lay_externo = QVBoxLayout(self)
        self.lay_externo.addWidget(main_widget)
        self._lado = "arriba"
        self._aplicar_cola()

        self.apply_styles()

        self.message_history = []
        self.respuesta_en_vivo = None  # tarjeta de la respuesta que llega en streaming
        self.modo = "preguntar"
        self._fijar_modo("preguntar")
        self._ir_a(0)

    TAB_PREGUNTAS, TAB_ERRORES, TAB_RUTA, TAB_PROGRESO = range(4)

    def _ir_a(self, k):
        """Pestañas: Preguntas y Errores usan el cuaderno; Mi ruta y Progreso son paneles."""
        for i, b in enumerate(self.botones_pestana):
            b.setChecked(i == k)
        self._cerrar_lista()
        if k == self.TAB_ERRORES:
            self.paginas.setCurrentIndex(0)
            if self.chat_id != aprendizaje.CHAT_ERRORES:
                self._cambiar_chat(aprendizaje.CHAT_ERRORES)
            self.errores_nuevos = 0
            self._pintar_pestana_errores()
        elif k == self.TAB_PREGUNTAS:
            self.paginas.setCurrentIndex(0)
            # Desde errores o desde una lección se vuelve al último cuaderno de PREGUNTAS (no a la lección)
            if self.chat_id == aprendizaje.CHAT_ERRORES or self._en_plan():
                self._cambiar_chat(getattr(self, "ultimo_cuaderno_preguntas", aprendizaje.CHAT_LIBRE))
        else:
            self.paginas.setCurrentIndex(1 if k == self.TAB_RUTA else 2)
            self._refrescar_paneles()

    def _abrir_estudio(self):
        """Modo estudio: el cuaderno del plan, con la pestaña «Mi ruta» marcada (no «Preguntas»)."""
        self._cerrar_lista()
        self.paginas.setCurrentIndex(0)
        for i, b in enumerate(self.botones_pestana):
            b.setChecked(i == self.TAB_RUTA)

    def _ver_controles(self):
        """Guía de controles (botón «?»). Cualquier pestaña vuelve a lo normal."""
        if self.paginas.currentIndex() == 3:
            self._ir_a(self.TAB_PREGUNTAS)
            return
        for b in self.botones_pestana:
            b.setChecked(False)
        self.paginas.setCurrentIndex(3)

    def _pintar_pestana_errores(self):
        n = getattr(self, "errores_nuevos", 0)
        self.botones_pestana[self.TAB_ERRORES].setText(f"Errores · {n}" if n else "Errores")

    def _accion_banner(self):
        if self.chat_id == aprendizaje.CHAT_ERRORES:
            self._configurar_terminal(not terminal.instalado())
        elif self._en_plan():
            self._cambiar_chat(getattr(self, "ultimo_cuaderno_preguntas", aprendizaje.CHAT_LIBRE))
            self._ir_a(self.TAB_PREGUNTAS)
        else:
            self._alternar_lista()

    def _pintar_cabecera_cuaderno(self):
        datos = self.progreso["cuadernos"].get(self.chat_id, {"nombre": "General"})
        n = len(self.progreso["cuadernos"])
        self.lbl_cuaderno.setText(
            '<span style="color:#FF7A3D; font-size:8.5pt; font-weight:700;">CUADERNO</span><br>'
            f'<span style="color:#FFFFFF; font-size:10.5pt; font-weight:700;">{cuaderno.rich(datos["nombre"], 14)}</span>')
        self.boton_lista.setText(f"Mis cuadernos ({n}) ▾" if self.vista_cuaderno.currentIndex() == 0 else "Cerrar ▴")
        self.cab_cuaderno.show()

    def _cerrar_lista(self):
        if hasattr(self, "vista_cuaderno") and self.vista_cuaderno.currentIndex() == 1:
            self.vista_cuaderno.setCurrentIndex(0)
            if self.chat_id in self.progreso["cuadernos"]:
                self._pintar_cabecera_cuaderno()

    def _alternar_lista(self):
        if self.vista_cuaderno.currentIndex() == 1:
            self._cerrar_lista()
            return
        self._pintar_lista()
        self.vista_cuaderno.setCurrentIndex(1)
        self._pintar_cabecera_cuaderno()

    def _pintar_lista(self):
        """Listado de cuadernos: nombre, última pregunta y número de preguntas; el actual resaltado."""
        cuaderno._borrar_layout(self.lay_lista)
        nuevo = cuaderno.boton("+  Nuevo cuaderno", primario=True)
        nuevo.clicked.connect(self._nuevo_cuaderno)
        self.lay_lista.addWidget(nuevo)
        for cid, datos in reversed(list(self.progreso["cuadernos"].items())):
            mensajes = aprendizaje.cargar_chat(cid)
            preguntas = [m["text"] for m in mensajes if m["is_user"]]
            ultima = preguntas[-1] if preguntas else "Vacío: escribe tu primera pregunta"
            activo = cid == self.chat_id
            fila = QFrame()
            fila.setObjectName("filaActiva" if activo else "fila")
            fila.setCursor(Qt.PointingHandCursor)
            fl = QHBoxLayout(fila)
            fl.setContentsMargins(12, 9, 8, 9)
            fl.setSpacing(8)
            icono = QLabel(cuaderno.rich({aprendizaje.CHAT_LIBRE: "💬", aprendizaje.CHAT_RAPIDAS: "⚡"}.get(cid, "📒"), 18))
            icono.setTextFormat(Qt.RichText)
            icono.setFixedWidth(22)
            fl.addWidget(icono, 0, Qt.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(2)
            titulo = QLabel(cuaderno.rich(datos["nombre"], 13))
            titulo.setTextFormat(Qt.RichText)
            titulo.setObjectName("filaTitulo")
            vista = ultima if len(ultima) <= 44 else ultima[:43] + "…"
            sub = QLabel(f"{html.escape(vista)}  ·  {len(preguntas)} {'pregunta' if len(preguntas) == 1 else 'preguntas'}")
            sub.setObjectName("filaSub")
            col.addWidget(titulo)
            col.addWidget(sub)
            fl.addLayout(col, 1)
            borrar = QPushButton("Vaciar" if cid == aprendizaje.CHAT_LIBRE else "Borrar")
            borrar.setObjectName("borrarCuaderno")
            borrar.setCursor(Qt.PointingHandCursor)

            def confirmar(_, c=cid, b=borrar):
                if b.text() in ("Borrar", "Vaciar"):
                    b.setText("¿Seguro?")
                    return
                aprendizaje.borrar_cuaderno(self.progreso, c)
                if c == self.chat_id:
                    self.chat_id = aprendizaje.CHAT_LIBRE
                    self._cargar_chat_actual()
                self._pintar_lista()
                self.vista_cuaderno.setCurrentIndex(1)
                self._pintar_cabecera_cuaderno()
            borrar.clicked.connect(confirmar)
            fl.addWidget(borrar, 0, Qt.AlignVCenter)
            fila.mousePressEvent = lambda _e, c=cid: self._abrir_cuaderno(c)
            self.lay_lista.addWidget(fila)
        self.lay_lista.addStretch()

    def _abrir_cuaderno(self, cid):
        self.vista_cuaderno.setCurrentIndex(0)
        if cid != self.chat_id:
            self._cambiar_chat(cid)
        else:
            self._pintar_cabecera_cuaderno()

    def _nuevo_cuaderno(self):
        cid = aprendizaje.crear_cuaderno(self.progreso)
        self.vista_cuaderno.setCurrentIndex(0)
        self._cambiar_chat(cid)
        self._ir_a(self.TAB_PREGUNTAS)
        self.input_field.setFocus()

    def _fijar_modo(self, modo):
        self.modo = modo
        for c, b in self.botones_modo.items():
            b.setChecked(c == modo)
        self.input_field.setPlaceholderText({
            "preguntar": "Pregúntale a Tux…",
            "analizar": "Pega un comando y te digo si es seguro…",
            "error": "Pega el mensaje de error…",
        }[modo])
        self.input_field.setFocus()

    def _cambiar_nivel(self, nivel):
        self.nivel = nivel
        guardar_nivel(nivel)
        self._refrescar_paneles()

    def get_tux_screen(self):
        """Obtiene la pantalla donde está el Tux"""
        if not self.tux_assistant:
            return QApplication.primaryScreen()
        
        screens = QGuiApplication.screens()
        tux_pos = self.tux_assistant.pos()
        
        for screen in screens:
            screen_geometry = screen.geometry()
            if screen_geometry.contains(tux_pos):
                return screen
        
        return QApplication.primaryScreen()
    
    def update_screen_if_needed(self):
        """Actualiza la pantalla si el Tux cambió de monitor"""
        if not self.tux_assistant or not self.isVisible():
            return
        
        new_screen = self.get_tux_screen()
        if new_screen != self.current_screen:
            self.current_screen = new_screen
            if self.isVisible():
                self.position_near_tux()
    
    ALTO_MAX, ALTO_MIN = 630, 380

    def position_near_tux(self):
        """El globo va SIEMPRE arriba o abajo de Tux (con la colita apuntándole) y nunca lo tapa.

        Si no cabe completo, se encoge al espacio libre (mínimo 380 px). Se queda del mismo lado
        mientras quepa, para no saltar al arrastrar.
        """
        if not self.tux_assistant:
            return
        screen = (self.current_screen or self.get_tux_screen()).availableGeometry()
        # Caja del DIBUJO del pingüino (el GIF tiene bordes transparentes)
        tux = self.tux_assistant.frameGeometry().adjusted(18, 10, -18, -4)
        margen = 8
        arriba = tux.top() - screen.top() - margen
        abajo = screen.bottom() - margen - tux.bottom()
        previo = getattr(self, "_lado", "arriba")
        if previo not in ("arriba", "abajo"):
            previo = "arriba"
        espacio_previo = arriba if previo == "arriba" else abajo
        if espacio_previo >= self.ALTO_MIN:
            lado = previo
        else:
            lado = "arriba" if arriba >= abajo else "abajo"
        espacio = arriba if lado == "arriba" else abajo
        alto = max(200, min(self.ALTO_MAX, espacio)) // 10 * 10  # en pasos de 10 px: menos re-dibujos al arrastrar
        if alto != self.height():
            self.setFixedSize(self.width(), alto)
        if lado != self._lado:
            self._lado = lado
            self._aplicar_cola()
        x = tux.center().x() - self.width() // 2
        x = max(screen.left() + margen, min(x, screen.right() - margen - self.width()))
        y = tux.top() - alto if lado == "arriba" else tux.bottom()
        if self.pos() != QPoint(x, y):
            self.move(x, y)
        self.update()  # la colita sigue a Tux

    # ---------- globo de diálogo ----------
    COLA = 22          # largo de la colita
    SOMBRA = 6
    # Lado del cuaderno respecto a Tux → lado del globo donde sale la colita
    _COLA_DE = {"arriba": "abajo", "abajo": "arriba", "izquierda": "derecha", "derecha": "izquierda"}

    def _aplicar_cola(self):
        cola = self._COLA_DE.get(self._lado, "abajo")
        m, c = self.SOMBRA, self.COLA
        self.lay_externo.setContentsMargins(
            m + (c if cola == "izquierda" else 0), m + (c if cola == "arriba" else 0),
            m + (c if cola == "derecha" else 0), m + (c if cola == "abajo" else 0))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cola = self._COLA_DE.get(self._lado, "abajo")
        m, c, radio, base = self.SOMBRA, self.COLA, 20, 17
        cuerpo = QRectF(self.rect()).adjusted(m + (c if cola == "izquierda" else 0), m + (c if cola == "arriba" else 0),
                                              -(m + (c if cola == "derecha" else 0)), -(m + (c if cola == "abajo" else 0)))
        # Punto de Tux en coordenadas del globo: la colita apunta a él
        objetivo = self.mapFromGlobal(self.tux_assistant.frameGeometry().center()) if self.tux_assistant else cuerpo.center().toPoint()
        path = QPainterPath()
        path.addRoundedRect(cuerpo, radio, radio)
        punta = QPainterPath()
        if cola in ("abajo", "arriba"):
            x = max(cuerpo.left() + radio + base, min(objetivo.x(), cuerpo.right() - radio - base))
            y0 = cuerpo.bottom() if cola == "abajo" else cuerpo.top()
            y1 = y0 + (c if cola == "abajo" else -c)
            xt = max(x - 18, min(objetivo.x(), x + 18))
            punta.moveTo(x - base, y0 - (2 if cola == "abajo" else -2))
            punta.quadTo(x - 2, y0, xt, y1)
            punta.quadTo(x + 4, y0, x + base, y0 - (2 if cola == "abajo" else -2))
        else:
            y = max(cuerpo.top() + radio + base, min(objetivo.y(), cuerpo.bottom() - radio - base))
            x0 = cuerpo.right() if cola == "derecha" else cuerpo.left()
            x1 = x0 + (c if cola == "derecha" else -c)
            yt = max(y - 18, min(objetivo.y(), y + 18))
            punta.moveTo(x0 - (2 if cola == "derecha" else -2), y - base)
            punta.quadTo(x0, y - 2, x1, yt)
            punta.quadTo(x0, y + 4, x0 - (2 if cola == "derecha" else -2), y + base)
        punta.closeSubpath()
        globo = path.united(punta)
        for i, alfa in ((4, 18), (2, 30)):  # sombra suave
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, alfa))
            p.drawPath(globo.translated(0, i))
        p.setBrush(QColor(14, 14, 20, 247))
        p.setPen(QPen(QColor("#3A3A50"), 1.2))
        p.drawPath(globo)

    def position_near_tux_smooth(self):
        """(Compatibilidad) Al arrastrar se recoloca directo: animar cada movimiento lo volvía lento."""
        self.position_near_tux()

    def apply_styles(self):
        """Estilos del cuaderno (oscuro, acento naranja, texto siempre legible)"""
        self.setStyleSheet("""
            QWidget { background-color: transparent; color: #ECECF1; font-family: 'Inter', 'Ubuntu', 'Noto Sans', sans-serif; }
            #mainWidget { background: transparent; border: none; }
            #tabs { background-color: #16161F; border-radius: 10px; }
            #tab { background: transparent; border: none; border-radius: 8px; color: #8A8A9E; font-size:10.5pt; font-weight: 600; }
            #tab:hover { color: #ECECF1; }
            #tab:checked { background: #26263A; color: #FFFFFF; }
            #bannerPlan { background-color: #1E150F; border: 1px solid #4A2A16; border-radius: 10px; }
            #linkButton { background: transparent; border: none; color: #FF7A3D; font-size:9.5pt; font-weight: 600; }
            #linkButton:hover { color: #FFA070; }
            #modo { background: transparent; border: 1px solid #2E2E3E; border-radius: 12px; color: #8A8A9E;
                    font-size:9.5pt; padding: 0 10px; }
            #modo:hover { color: #ECECF1; }
            #modo:checked { border-color: #FF7A3D; color: #FF7A3D; background: #1E150F; }
            #closeButton { background: transparent; border: none; border-radius: 14px; color: #8A8A9E; font-size:11pt; }
            #closeButton:hover { background: rgba(255,255,255,0.08); color: #FFFFFF; }
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: transparent; width: 6px; margin: 2px; }
            QScrollBar::handle:vertical { background: #34344A; border-radius: 3px; min-height: 24px; }
            QScrollBar::handle:vertical:hover { background: #FF7A3D; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            #inputWidget { background-color: #16161F; border: 1px solid #2E2E3E; border-radius: 12px; }
            #inputField { background: transparent; border: none; color: #FFFFFF; font-size:10.5pt; padding: 6px;
                          selection-background-color: #FF7A3D; }
            #sendButton { background-color: #FF7A3D; border: none; border-radius: 9px; color: #141418;
                          font-weight: bold; font-size:11pt; }
            #sendButton:hover { background-color: #FF9461; }
            #cabEstudio { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #241A3A, stop:1 #1A1426);
                          border: 1px solid #4B3A78; border-radius: 12px; }
            #botonAbajo { background: #FF7A3D; border: 2px solid #0E0E14; border-radius: 19px; color: #141418;
                          font-size: 15pt; font-weight: 900; }
            #botonAbajo:hover { background: #FF9461; }
            #botonMision { background: #2A1A12; border: 1px solid #FF7A3D; border-radius: 15px; color: #FFB089;
                           font-size: 10pt; font-weight: 700; padding: 0 14px; }
            #botonMision:hover { background: #3A2416; }
            #panelMision { background: #1A1426; border: 1px solid #4B3A78; border-radius: 10px; }
            #miniBoton { background: #2E2448; border: 1px solid #6B55A8; border-radius: 13px; color: #FFFFFF;
                         font-size: 9.5pt; font-weight: 700; padding: 0 10px; }
            #miniBoton:hover { border-color: #B794F4; }
            #miniMision { background: #2A1A12; border: 1px solid #FF7A3D; border-radius: 13px; color: #FFB089;
                          font-size: 9.5pt; font-weight: 700; padding: 0 10px; }
            #miniMision:hover { background: #3A2416; }
            #botonMapa { background: #2E2448; border: 1px solid #6B55A8; border-radius: 15px; color: #FFFFFF;
                         font-size: 10pt; font-weight: 700; padding: 0 16px; }
            #botonMapa:hover { background: #3B2E5C; border-color: #B794F4; }
            #cabCuaderno { background-color: #16161F; border: 1px solid #2E2E3E; border-radius: 10px; }
            #cabCuaderno:hover { border-color: #4A2A16; }
            #fila { background-color: #16161F; border: 1px solid #262633; border-radius: 10px; }
            #fila:hover { border-color: #FF7A3D; }
            #filaActiva { background-color: #21160F; border: 1px solid #FF7A3D; border-radius: 10px; }
            #filaTitulo { color: #FFFFFF; font-size:10pt; font-weight: 700; }
            #filaSub { color: #8A8A9E; font-size:9.5pt; }
            #listaCuadernos { background-color: #16161F; border: 1px solid #2E2E3E; border-radius: 10px; }
            #filaCuaderno { background: transparent; border: none; border-radius: 7px; color: #ECECF1;
                            font-size:10.5pt; text-align: left; padding: 6px 8px; }
            #filaCuaderno:hover { background: #22222F; }
            #filaCuaderno[activo="true"] { color: #FF7A3D; font-weight: 600; }
            #borrarCuaderno { background: transparent; border: none; color: #6E6E82; font-size:9.5pt; padding: 0 6px; }
            #borrarCuaderno:hover { color: #FF5C5C; }
            QToolTip { background-color: #1D1D29; color: #ECECF1; border: 1px solid #34344A; padding: 4px; }
        """)
        
    def setup_animations(self):
        """Configura animaciones para mostrar/ocultar la ventana"""
        self.show_animation = QPropertyAnimation(self, b"windowOpacity")
        self.show_animation.setDuration(300)
        self.show_animation.setStartValue(0)
        self.show_animation.setEndValue(1)
        self.show_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        self.hide_animation = QPropertyAnimation(self, b"windowOpacity")
        self.hide_animation.setDuration(200)
        self.hide_animation.setStartValue(1)
        self.hide_animation.setEndValue(0)
        self.hide_animation.setEasingCurve(QEasingCurve.InCubic)
        self.hide_animation.finished.connect(self.hide_completely)
        
    def show_chat(self):
        """Muestra el cuaderno; el globo se cierra (solo se ve uno de los dos)"""
        self.tux_assistant.bubble.hide()
        self.tux_assistant.pregunta.hide()
        if not self.tux_assistant.is_moving and self.tux_assistant.current_animation != 'sentado':
            self.tux_assistant.set_animation('sentado')  # con el cuaderno abierto, Tux quieto
        self.current_screen = self.get_tux_screen()
        
        self.position_near_tux()
        
        self.show()
        self.show_animation.start()
        self.input_field.setFocus()
        
    def hide_completely(self):
        """Oculta completamente la ventana después de la animación"""
        super().hide()
        
    def add_message(self, text, is_user=True, registrar=True):
        """Añade una entrada al cuaderno: pregunta (título) o tarjeta de Tux"""
        self._quitar_bienvenida()
        if is_user:
            widget = cuaderno.PreguntaUsuario(text)
        else:
            widget = cuaderno.Tarjeta(text)
            widget.accion.connect(self._accion_tarjeta)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, widget)

        if registrar:
            self.message_history.append({
                'text': text,
                'is_user': is_user,
                'time': time.time()
            })
            self._guardar_chat()

        QTimer.singleShot(60, self.scroll_to_bottom)
        return widget

    def _pintar_respuesta(self, tarjeta, texto, final=True):
        tarjeta.actualizar(texto, final)

    def _accion_tarjeta(self, accion):
        """Botones de las tarjetas: comprobar misión, pista, responder, explícame…"""
        if accion == "responder":
            self._fijar_modo("preguntar")
            self._esperando = "comprension"  # responde a la pregunta de Tux (la corrige la IA, no es la misión)
            self.input_field.setPlaceholderText("Escribe tu respuesta a la pregunta de Tux…")
            self.input_field.setFocus()
        elif accion == "explicame":
            self._enviar_texto("Explícame más a fondo")
        elif accion == "continuar":
            self._enviar_texto("sigue")  # pide_mas_detalle reconoce «sigue»
        elif accion == "comprobar":
            leccion, _, _ = aprendizaje.leccion_actual(self.progreso, self.chat_id) if self._en_plan() else (None, 0, 0)
            if leccion and not leccion.get("pasos") and aprendizaje.es_mision_de_respuesta(leccion):
                self._fijar_modo("preguntar")
                self._esperando = "mision"
                self.input_field.setPlaceholderText("Escribe aquí tu respuesta a la misión…")
                self.input_field.setFocus()
            else:
                self._enviar_texto("listo")
        elif accion.startswith("aprender:"):
            self._aprender_leccion(accion.split(":", 1)[1])
        elif accion == "explicar_error":
            self.tux_assistant.explicar_error_terminal()
        elif accion in ("pista", "saltar", "siguiente"):
            self._enviar_texto(accion)

    # Lo que se ve en el cuaderno cuando la acción viene de un botón
    _ETIQUETAS_ACCION = {"listo": "Comprobar misión", "pista": "Pídele una pista", "saltar": "Saltar misión",
                         "siguiente": "Siguiente lección", "empezar": "Empezar lección", "sigue": "Continúa"}

    def _quizas_titular(self, respuesta):
        """Tras la PRIMERA conversación de un cuaderno, la IA le pone un título corto (en segundo plano)."""
        cid = self.chat_id
        datos = self.progreso["cuadernos"].get(cid)
        if not datos or cid in (aprendizaje.CHAT_LIBRE, aprendizaje.CHAT_RAPIDAS) or datos.get("titulo_ia"):
            return
        preguntas = [m["text"] for m in self.message_history if m["is_user"]]
        if len(preguntas) != 1:
            return
        trabajador = TituloWorker(cid, preguntas[0], respuesta)
        trabajador.listo.connect(self._titulo_listo)
        self._titulos = getattr(self, "_titulos", []) + [trabajador]  # que no lo borre el recolector
        trabajador.start()

    def _titulo_listo(self, cid, titulo):
        if titulo:
            aprendizaje.titular_cuaderno(self.progreso, cid, titulo)
            if cid == self.chat_id:
                self._actualizar_progreso()
            if self.vista_cuaderno.currentIndex() == 1:
                self._pintar_lista()

    def _enviar_texto(self, texto):
        self.preguntas_sesion += 1
        if hasattr(self, "panel_mision"):
            self._cerrar_panel_mision()
        if not self.message_history and self.chat_id in self.progreso["cuadernos"]:
            aprendizaje.nombrar_cuaderno(self.progreso, self.chat_id, texto)
            self._actualizar_progreso()
        self.add_message(self._ETIQUETAS_ACCION.get(texto, texto), is_user=True)
        self.process_user_question(texto)

    def pregunta_rapida(self, texto):
        """Modo rápido: se guarda en «Preguntas rápidas» y la respuesta sale en el globo de Tux."""
        cid = aprendizaje.asegurar_rapidas(self.progreso)
        if self.chat_id != cid:
            self._cambiar_chat(cid)
        self._rapida = True
        self._enviar_texto(texto)

    def _mostrar_bienvenida_errores(self):
        caja = QFrame()
        caja.setObjectName("bienvenida")
        caja.setStyleSheet("#bienvenida { background: #16161F; border: 1px solid #262633; border-radius: 14px; }")
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(10)
        lay.addWidget(cuaderno.etiqueta_seccion("Errores de tu terminal", "#FF5C5C"))
        lay.addWidget(cuaderno.etiqueta_rich(
            "Cuando un comando falle en bash, aparecerá aquí con lo que pasó y el comando corregido para copiar. "
            "Funciona en las terminales que abras <b>después</b> de activarlo. Solo se guarda el último comando "
            "que falló; nada más de lo que escribes.", 10))
        if not terminal.instalado():
            b = cuaderno.boton("Activar vigilancia", primario=True)
            b.clicked.connect(lambda: self._configurar_terminal(True))
            fila = QHBoxLayout()
            fila.addWidget(b)
            fila.addStretch()
            lay.addLayout(fila)
        self.bienvenida = caja
        self.chat_layout.insertWidget(0, caja)

    def _mostrar_resumen_terminal(self):
        datos = terminal.cargar_estadisticas()
        resumen = cuaderno.ResumenTerminal(terminal.resumen_semana(datos), terminal.TIPOS,
                                           datos["silencioso"], terminal.instalado())
        resumen.alternar_silencio.connect(self._alternar_silencio)
        resumen.alternar_vigilancia.connect(self._configurar_terminal)
        self.chat_layout.insertWidget(0, resumen)

    def _alternar_silencio(self, silencioso):
        datos = terminal.cargar_estadisticas()
        datos["silencioso"] = silencioso
        terminal.guardar_estadisticas(datos)
        self._cargar_chat_actual()

    def _aprender_leccion(self, carga):
        """Desde un error: se ARMA (con la animación del grafo) un repaso con el CONTEXTO del error.

        carga = «lid|tipo|comando» (o «título|comando» en tarjetas antiguas). El repaso junta 2-4 lecciones
        útiles para ese tipo de error y su meta menciona los comandos que fallaron, así la IA crea misiones y
        explicaciones que tienen que ver con lo que pasó.
        """
        partes = carga.split("|")
        if partes[0] in aprendizaje.LECCIONES:
            lid = partes[0]
            tipo = partes[1] if len(partes) > 2 else "otro"
            cmd = partes[-1] if len(partes) > 1 else ""
        else:
            lid = next((k for k, l in aprendizaje.LECCIONES.items() if l["titulo"] == partes[0]), None)
            tipo, cmd = "otro", partes[-1] if len(partes) > 1 else ""
        if not lid:
            return
        if not self.isVisible():
            self.show_chat()
        nombre = f"Evitar: {terminal.TIPOS.get(tipo, 'errores de la terminal')}"[:40]
        # Si ya hay un repaso de este tipo sin terminar, se muestra ese (no se duplica)
        for pid, plan in self.progreso["planes"].items():
            if plan["nombre"] == nombre and aprendizaje.leccion_actual(self.progreso, pid)[0]:
                self._mostrar_ruta_animada(pid)
                return
        recientes = []
        for m in reversed(aprendizaje.cargar_chat(aprendizaje.CHAT_ERRORES)):
            r = re.search(r"Falló `([^`]+)`", m["text"])
            if r and r.group(1) not in recientes and r.group(1) != cmd:
                recientes.append(r.group(1))
            if len(recientes) >= 3:
                break
        meta = (f"No volver a cometer en la terminal errores como `{cmd}` ({terminal.TIPOS.get(tipo, 'error').lower()})"
                if cmd else f"Evitar {terminal.TIPOS.get(tipo, 'errores').lower()} en la terminal")
        if recientes:
            meta += ". Otros errores recientes: " + ", ".join(f"`{c}`" for c in recientes)
        lecciones = terminal.ruta_recomendada(lid, tipo, aprendizaje.LECCIONES, aprendizaje.TEMAS)
        temas = list(dict.fromkeys(aprendizaje.LECCIONES[l]["tema"] for l in lecciones))
        self._ir_a(self.TAB_RUTA)
        self.panel_ruta.mostrar_armando(self.progreso, aprendizaje.TEMAS, aprendizaje.LECCIONES,
                                        aprendizaje.leccion_actual, meta)
        self._armando = True
        self.tux_assistant.start_thinking_animation()

        def crear():
            pid = aprendizaje.crear_plan(self.progreso, nombre, meta, temas, lecciones)
            self._armando = False
            self.tux_assistant.stop_thinking_animation()
            self._mostrar_ruta_animada(pid)
        QTimer.singleShot(3400, crear)  # tiempo para ver cómo se arma

    def _mostrar_ruta_animada(self, pid):
        """Muestra una ruta en Mi ruta, en vista Grafo, con su recorrido animado (luego se puede explorar todo)."""
        self.panel_ruta.mostrando_rutas = False
        self.panel_ruta.vista = "grafo"
        self.panel_ruta.plan_visible = pid
        self.panel_ruta.revelar_pid = pid
        QTimer.singleShot(3000, lambda: setattr(self.panel_ruta, "revelar_pid", None))
        self._ir_a(self.TAB_RUTA)

    def registrar_error(self, texto):
        """Los errores de terminal van a su propia sección (no se mezclan con las preguntas)."""
        if self.chat_id == aprendizaje.CHAT_ERRORES:
            self.add_message(texto, is_user=False)
            self._cargar_chat_actual()  # refresca el resumen de la semana
            QTimer.singleShot(80, self.scroll_to_bottom)
        else:
            aprendizaje.agregar_a_chat(aprendizaje.CHAT_ERRORES, texto)
            self.errores_nuevos = getattr(self, "errores_nuevos", 0) + 1
            self._pintar_pestana_errores()

    def _mostrar_pensando(self, consulta, paso, texto_propio=None):
        if getattr(self, "pensando", None) is None:
            self.pensando = QLabel()
            self.pensando.setTextFormat(Qt.RichText)
            self.pensando.setStyleSheet("background: transparent; padding: 4px 6px;")
            self.chat_layout.insertWidget(self.chat_layout.count() - 1, self.pensando)
            QTimer.singleShot(60, self.scroll_to_bottom)
        puntos = "".join(f'<span style="color:{"#FF7A3D" if i == paso % 3 else "#3A3A4C"}; font-size:12pt;">●</span>&nbsp;'
                         for i in range(3))
        texto = (f'Revisando en tu equipo <span style="font-family:monospace; color:#FF7A3D;">{html.escape(consulta)}</span>'
                 if consulta else (texto_propio or "Tux está pensando"))
        self.pensando.setText(f'{puntos}&nbsp;<span style="color:#8A8A9E; font-size:10pt;">{texto}</span>')

    def _quitar_pensando(self):
        if getattr(self, "pensando", None) is not None:
            self.pensando.deleteLater()
            self.pensando = None

    def _quitar_bienvenida(self):
        if getattr(self, "bienvenida", None) is not None:
            self.bienvenida.deleteLater()
            self.bienvenida = None

    def _mostrar_bienvenida(self):
        """Cuaderno vacío: qué puede hacer Tux, con atajos de un clic."""
        caja = QFrame()
        caja.setObjectName("bienvenida")
        caja.setStyleSheet("#bienvenida { background: #16161F; border: 1px solid #262633; border-radius: 14px; }")
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(10)
        lay.addWidget(cuaderno.etiqueta_seccion("Tu cuaderno de Linux"))
        lay.addWidget(cuaderno.etiqueta_rich(
            "Pregúntame lo que quieras de Linux o de tu equipo. Te explico <b>antes</b> de que ejecutes nada, "
            "con datos reales de tu PC y sin hacer cambios por ti.", 10))
        for texto, accion in (("¿Cuánta RAM estoy usando?", lambda: self._enviar_texto("¿Cuánta RAM estoy usando?")),
                              ("¿Es seguro  rm -rf ~ ?", lambda: self._enviar_texto("analiza rm -rf ~")),
                              ("Armar mi plan de estudio", lambda: self._ir_a(self.TAB_RUTA)),
                              ("¿Cómo funciona Tux?", lambda: self.add_message(GUIA_TUX, is_user=False)),
                              ("Cómo se maneja Tux con el ratón", self._ver_controles)):
            b = cuaderno.boton(texto)
            b.setStyleSheet(b.styleSheet() + "QPushButton { text-align: left; padding-left: 12px; }")
            b.clicked.connect(accion)
            lay.addWidget(b)
        self.bienvenida = caja
        self.chat_layout.insertWidget(0, caja)

    def _actualizar_boton_abajo(self, *_):
        barra = self.chat_area.verticalScrollBar()
        lejos = barra.maximum() - barra.value() > 140
        self.boton_abajo.move(self.chat_area.width() - self.boton_abajo.width() - 16,
                              self.chat_area.height() - self.boton_abajo.height() - 10)
        self.boton_abajo.setVisible(lejos)
        if lejos:
            self.boton_abajo.raise_()

    def _bajar_suave(self):
        barra = self.chat_area.verticalScrollBar()
        self._anim_abajo = QPropertyAnimation(barra, b"value")
        self._anim_abajo.setDuration(350)
        self._anim_abajo.setStartValue(barra.value())
        self._anim_abajo.setEndValue(barra.maximum())
        self._anim_abajo.setEasingCurve(QEasingCurve.OutCubic)
        self._anim_abajo.start()

    def scroll_to_bottom(self):
        """Desplaza el chat hasta el final"""
        scrollbar = self.chat_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def send_message(self):
        """Envía lo escrito según el modo: preguntar, analizar comando o explicar error"""
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        if self.modo == "analizar" and not riesgo.peticion_analisis(text):
            text = "analiza " + text
        elif self.modo == "error":
            text = f"Tengo este error: «{text}». ¿Qué significa y cómo lo arreglo?"
        if getattr(self, "_esperando", None) == "comprension":
            self._esperando = None
            text = f"Mi respuesta a tu pregunta de comprobación: {text}"
        self._fijar_modo("preguntar")
        self._enviar_texto(text)
            
    def process_user_question(self, text):
        """Procesa la pregunta del usuario usando el Tux"""
        # Tras «＋ Nuevo plan»: este mensaje es la meta del estudiante
        if self.esperando_meta:
            self.esperando_meta = False
            self._crear_plan(text)
            return

        # Cambio de nivel: "nivel principiante / intermedio / avanzado"
        nuevo_nivel = detectar_cambio_nivel(text)
        if nuevo_nivel:
            self.nivel = nuevo_nivel
            guardar_nivel(nuevo_nivel)
            self._responder(f"Listo, desde ahora te explico en nivel {nuevo_nivel} 🐧")
            return

        # Vigilancia de terminal (se activa/desactiva solo si el usuario lo pide)
        m = re.search(r"\b(activa|activar|enciende|desactiva|desactivar|apaga|quita)\b.*\b(terminal|consola)\b|^/terminal\s+(on|off)", text, re.IGNORECASE)
        if m:
            self._configurar_terminal(not re.search(r"desactiv|apaga|quita|off", text, re.IGNORECASE))
            return

        # Semáforo de riesgo: «analiza rm -rf …», «¿es seguro …?», «$ comando»
        comando = riesgo.peticion_analisis(text)
        if comando:
            r = riesgo.analizar(comando)
            if not self.isVisible():
                self.tux_assistant.say(f"{riesgo.ETIQUETA[r['nivel']]} · `{comando}`", play_sound=True)
            self.add_message(riesgo.a_markdown(comando, r), is_user=False)
            return

        # Transparencia: mostrar exactamente qué sabe Tux del equipo
        if re.search(r"qu[eé] sabes de mi (pc|equipo|sistema|computador\w*)|/contexto", text, re.IGNORECASE):
            info = contexto_sistema.contexto_completo()
            kb = aprendizaje.espacio_usado() / 1024
            msg = ("Esto es lo que sé de tu equipo (solo lectura, no sale de tu PC):\n\n```texto\n" + info + "\n```\n"
                   f"Lo que guardo en disco (chats y progreso) ocupa {kb:.1f} KB.")
            self.tux_assistant.say("Te muestro en el chat todo lo que sé de tu equipo 🐧", play_sound=True)
            self.add_message(msg, is_user=False)
            return

        # Preguntas de identidad: respuesta fija e instantánea
        fija = respuesta_identidad(text)
        if fija:
            self._responder(fija)
            return

        # Dentro de un plan de estudio: empezar / siguiente / listo / pista / saltar / respuesta
        if self._en_plan():
            if self._flujo_plan(text):
                return
        elif re.search(r"\b(plan de estudios?|quiero (aprender|estudiar)|ens[eé][ñn]ame linux)\b", text, re.IGNORECASE):
            self._crear_plan(text)
            return

        self._preguntar_ia()

    # ---------- helpers de respuesta ----------

    def _responder(self, msg, sonido=True):
        """Respuesta fija (sin IA): al chat y, si el chat está cerrado, al globo."""
        if not self.isVisible():
            self.tux_assistant.say(msg, play_sound=sonido)
        self.add_message(msg, is_user=False)

    def _preguntar_ia(self, extra="", pregunta=None):
        """Lanza la IA con el historial del chat actual (+ contexto de lección si hay).

        pregunta: reemplaza (solo para la IA) el último mensaje del usuario, p. ej. «empezar» → «Enséñame …».
        """
        if not extra and self._en_plan():
            extra = self._contexto_plan()
        tokens = None
        if getattr(self, "_rapida", False):
            extra += ("\n\nMODO RÁPIDO (manda sobre el FORMATO de arriba): responde en 1 a 3 frases cortas y directas. "
                      "Si hace falta un comando, ponlo solo en su propia línea, sin viñetas que expliquen sus partes. "
                      "Sin títulos, sin advertencias largas y sin pregunta final.")
            tokens = 130
        historial = [dict(m) for m in self.message_history]
        if pregunta and historial and historial[-1]["is_user"]:
            historial[-1]["text"] = pregunta
        self.tux_assistant.start_thinking_animation()
        self.tux_assistant.thinking.start()

        if self.tux_assistant.ai_worker and self.tux_assistant.ai_worker.isRunning():
            try:
                self.tux_assistant.ai_worker.parcial.disconnect()
                self.tux_assistant.ai_worker.finished.disconnect()
                self.tux_assistant.ai_worker.error.disconnect()
            except TypeError:
                pass
            self.tux_assistant.ai_worker.stop()
            self.tux_assistant.ai_worker.wait(1000)

        self.respuesta_en_vivo = None
        self.tux_assistant.ai_worker = AIWorker(historial, self.nivel, extra, en_vivo=pregunta is None, tokens=tokens)
        self.tux_assistant.ai_worker.parcial.connect(self.on_ai_parcial)
        self.tux_assistant.ai_worker.consultando.connect(self.on_ai_consultando)
        self.tux_assistant.ai_worker.finished.connect(self.on_ai_response)
        self.tux_assistant.ai_worker.error.connect(self.on_ai_error)
        self.tux_assistant.ai_worker.start()

    # ---------- chats guardados ----------

    def _en_plan(self):
        return self.chat_id in self.progreso["planes"]

    def _plan(self):
        return self.progreso["planes"].get(self.chat_id)

    def _guardar_chat(self):
        try:
            aprendizaje.guardar_chat(self.chat_id, self.message_history)
        except OSError:
            pass

    def _poblar_selector(self):
        """(Compatibilidad) refresca cabecera, ruta y progreso."""
        self._refrescar_paneles()

    def _refrescar_paneles(self):
        # Cabecera: nivel de CONOCIMIENTO (se gana con XP); el estilo de explicación va aparte
        xp = aprendizaje.xp_total(self.progreso)
        info = aprendizaje.nivel_conocimiento(xp)
        idx, nombre, _, minimo, siguiente = info
        if siguiente:
            self.anillo.fijar((xp - minimo) / (siguiente - minimo))
            sub = f"{xp} XP · {siguiente - xp} para {aprendizaje.NIVELES_CONOCIMIENTO[idx + 1][0]}"
        else:
            self.anillo.fijar(1.0)
            sub = f"{xp} XP · nivel máximo"
        self.anillo.setToolTip(sub)
        self.lbl_titulo.setText(
            f'<span style="color:#FFFFFF; font-size:11.5pt; font-weight:700;">Tux</span>'
            f'<span style="color:#FF7A3D; font-size:10pt; font-weight:600;">&nbsp;&nbsp;{html.escape(nombre)}</span><br>'
            f'<span style="color:#8A8A9E; font-size:9.5pt;">{sub}</span>')
        if (self.paginas.currentIndex() == 1 or not hasattr(self, "_ruta_lista")) and not getattr(self, "_armando", False):
            self.panel_ruta.refrescar(self.progreso, aprendizaje.TEMAS, aprendizaje.LECCIONES,
                                      aprendizaje.leccion_actual, self.chat_id if self._en_plan() else None)
            self._ruta_lista = True
        if self.paginas.currentIndex() == 2:
            self.panel_progreso.refrescar(self.progreso, aprendizaje.TEMAS, self.nivel, info, xp,
                                          aprendizaje.NIVELES_CONOCIMIENTO, terminal.instalado(),
                                          aprendizaje.espacio_usado() / 1024, aprendizaje.XP_POR_DIFICULTAD)

    def _cambiar_chat(self, cid):
        self._guardar_chat()
        self.esperando_meta = False
        self.chat_id = cid
        if cid != aprendizaje.CHAT_ERRORES:
            self.ultimo_cuaderno = cid
            if cid in self.progreso["cuadernos"]:
                self.ultimo_cuaderno_preguntas = cid
        self._cargar_chat_actual()
        self._refrescar_paneles()

    def _limpiar_widgets(self):
        self.bienvenida = None
        self.pensando = None
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _cargar_chat_actual(self):
        self._limpiar_widgets()
        self.respuesta_en_vivo = None
        self.message_history = aprendizaje.cargar_chat(self.chat_id)
        for m in self.message_history[-40:]:   # solo se pintan los últimos, el resto queda guardado
            self.add_message(m["text"], m["is_user"], registrar=False)
        if self._en_plan() and not self.message_history:
            plan = self._plan()
            self.add_message(
                f"📘 **Plan «{plan['nombre']}»**\n{aprendizaje.resumen_plan(plan, self.progreso)}\n\n"
                f"**Meta:** {plan['meta']}\n\nCada lección se adapta a esta meta y termina con una misión de varios pasos "
                "que compruebo en tu equipo. Pregúntame lo que quieras en cualquier momento.",
                is_user=False)
        if self.chat_id == aprendizaje.CHAT_ERRORES:
            self._mostrar_resumen_terminal()
        elif not self.message_history and not self._en_plan():
            self._mostrar_bienvenida()
        self._actualizar_progreso()

    def _actualizar_progreso(self):
        """Banner superior: dice siempre en qué cuaderno estás (general o el de un plan)."""
        self.boton_nuevo.setVisible(not self._en_plan() and self.chat_id != aprendizaje.CHAT_ERRORES)
        estudio = self._en_plan()
        self.cab_estudio.setVisible(estudio)
        self.modos_widget.setVisible(not estudio)
        self.chat_container.setStyleSheet("#chatContainer { background:#110F1A; border-radius:12px; }" if estudio else "")
        if estudio:
            self.input_field.setPlaceholderText("Pregúntale a Tux sobre esta lección…")
        elif self.modo == "preguntar":
            self.input_field.setPlaceholderText("Pregúntale a Tux…")
        if self.chat_id == aprendizaje.CHAT_ERRORES:
            self._cerrar_lista()
            self.cab_cuaderno.hide()
            activa = terminal.instalado()
            self.lbl_progreso.setText(
                '<span style="color:#FF5C5C; font-size:8.5pt; font-weight:700;">ERRORES DE TU TERMINAL</span><br>'
                f'<span style="color:#ECECF1; font-size:10pt;">{"Vigilancia activa" if activa else "Vigilancia apagada"}</span>')
            self.boton_banner.setText("Apagar" if activa else "Activar")
            self.banner_plan.show()
            return
        if not self._en_plan():
            self.banner_plan.hide()
            self._pintar_cabecera_cuaderno()
            return
        self._cerrar_lista()
        self.cab_cuaderno.hide()
        self.banner_plan.hide()
        plan = self._plan()
        leccion, i, total = aprendizaje.leccion_actual(self.progreso, self.chat_id)
        nombre = html.escape(plan["nombre"])
        if leccion:
            tema = aprendizaje.TEMAS[leccion["tema"]]
            self._icono_estudio = tema["icono"]
            self.lbl_compacto.setText(
                f'<span style="color:#FFFFFF; font-size:10.5pt; font-weight:800;">{html.escape(leccion["titulo"])}</span>'
                f'<span style="color:#A0A0B0; font-size:9.5pt;">&nbsp; · {i}/{total}</span>'
                f'<span style="color:#B794F4; font-size:10pt;">&nbsp; ▾</span>')
            self.icono_estudio.setText(cuaderno.rich(tema["icono"], 30))
            self.lbl_estudio.setText(
                f'<span style="color:#B794F4; font-size:8.5pt; font-weight:800;">MODO ESTUDIO · {nombre.upper()}</span><br>'
                f'<span style="color:#FFFFFF; font-size:12pt; font-weight:800;">{html.escape(leccion["titulo"])}</span><br>'
                f'<span style="color:#A0A0B0; font-size:9.5pt;">Lección {i} de {total} · {html.escape(tema["nombre"])} · '
                f'<span style="color:#4ADE80;">misión +{aprendizaje.xp_leccion(leccion["id"])} XP</span></span>')
        else:
            self._icono_estudio = "🏆"
            self.lbl_compacto.setText('<span style="color:#4ADE80; font-size:10.5pt; font-weight:800;">¡Plan completado!</span>'
                                      '<span style="color:#B794F4; font-size:10pt;">&nbsp; ▾</span>')
            self.icono_estudio.setText(cuaderno.rich("🏆", 30))
            self.lbl_estudio.setText(
                f'<span style="color:#B794F4; font-size:8.5pt; font-weight:800;">MODO ESTUDIO · {nombre.upper()}</span><br>'
                f'<span style="color:#4ADE80; font-size:12pt; font-weight:800;">¡Plan completado!</span>')
        hechas = set(plan.get("completadas", [])) | set(plan.get("saltadas", []))
        self.segmentos.fijar([("hecha" if l in hechas else "actual" if leccion and l == leccion["id"] else "pendiente")
                              for l in plan["lecciones"]])
        self._pintar_panel_mision()
        self._aplicar_cabecera_estudio()

    def _cerrar_panel_mision(self):
        if self.panel_mision.isVisible():
            self.panel_mision.hide()
            self._pintar_panel_mision()  # actualiza las flechas de los botones

    def _alternar_cabecera_estudio(self):
        self._estudio_expandido = not self._estudio_expandido
        self._aplicar_cabecera_estudio()

    def _aplicar_cabecera_estudio(self):
        """Compacta: una línea (lección · n/total) + «‹ Mapa» y «🎯 x/y». Desplegada: todo el detalle."""
        exp = self._estudio_expandido
        self.lbl_estudio.setVisible(exp)
        self.fila_mapa_w.setVisible(exp)
        self.lbl_compacto.setVisible(not exp)
        self.mini_mapa.setVisible(not exp)
        self.mini_mision.setVisible(not exp and getattr(self, "_mision_disponible", False))
        self.cab_estudio.layout().setContentsMargins(12, 8 if not exp else 10, 10, 8 if not exp else 10)
        self.icono_estudio.setText(cuaderno.rich(getattr(self, "_icono_estudio", "📘"), 18 if not exp else 30))

    def _pintar_panel_mision(self):
        """Panel de la misión actual (en la cabecera de estudio): texto, pasos con ✓/○ y botones."""
        plan = self._plan()
        leccion = aprendizaje.leccion_actual(self.progreso, self.chat_id)[0] if plan else None
        if (not leccion or leccion["id"] not in plan.get("vistas", [])
                or getattr(self, "_generando_mision", None) == leccion["id"]):
            self.boton_mision.hide()
            self.panel_mision.hide()
            self._mision_disponible = False
            self.mini_mision.hide()
            return
        pasos = leccion.get("pasos")
        hechos = aprendizaje.pasos_hechos(plan, leccion["id"]) if pasos else set()
        abierto = self.panel_mision.isVisible()
        etiqueta = f"Misión · {len(hechos)}/{len(pasos)} pasos" if pasos else "Misión"
        self.boton_mision.setText(f"{etiqueta}  {'▴' if abierto else '▾'}")
        self.boton_mision.show()
        self._mision_disponible = True
        self.mini_mision.setText(f"{len(hechos)}/{len(pasos)}" if pasos else "Misión")
        self.mini_mision.setVisible(not self._estudio_expandido)
        if not abierto:
            return
        cuaderno._borrar_layout(self.lay_mision)
        cab = QHBoxLayout()
        cab.addWidget(cuaderno.etiqueta_seccion("Misión de esta lección"))
        cab.addStretch()
        cerrar = QPushButton("✕")
        cerrar.setObjectName("closeButton")
        cerrar.setFixedSize(26, 26)
        cerrar.setCursor(Qt.PointingHandCursor)
        cerrar.setToolTip("Cerrar la misión")
        cerrar.clicked.connect(self._cerrar_panel_mision)
        cab.addWidget(cerrar)
        self.lay_mision.addLayout(cab)
        self.lay_mision.addWidget(cuaderno.etiqueta_rich(md_a_html(leccion["mision"], con_copiar=False)[0], 10.5, "#FFFFFF"))
        for i, paso in enumerate(pasos or []):
            hecho = i in hechos
            fila = QHBoxLayout()
            fila.setSpacing(8)
            marca = QLabel("✓" if hecho else str(i + 1))
            marca.setFixedSize(22, 22)
            marca.setAlignment(Qt.AlignCenter)
            marca.setStyleSheet(f"background:{'#16301F' if hecho else '#2A1A12'}; color:{'#4ADE80' if hecho else '#FF7A3D'};"
                                f" border:1px solid {'#4ADE80' if hecho else '#FF7A3D'}; border-radius:11px;"
                                " font-size:9pt; font-weight:800;")
            fila.addWidget(marca, 0, Qt.AlignTop)
            texto = md_a_html(paso["texto"], con_copiar=False)[0]
            fila.addWidget(cuaderno.etiqueta_rich(texto, 9.5, "#8A8A9E" if hecho else "#ECECF1"), 1)
            self.lay_mision.addLayout(fila)
        botones = QHBoxLayout()
        botones.setSpacing(6)
        for nombre, accion, primario in (("Comprobar", "comprobar", True), ("Pista", "pista", False)):
            b = cuaderno.boton(nombre, primario=primario, pequeno=True)
            b.clicked.connect(lambda _, a=accion: self._accion_tarjeta(a))
            botones.addWidget(b)
        botones.addStretch()
        self.lay_mision.addLayout(botones)

    def _continuar_plan(self, pid):
        """Desde Mi ruta: abre el cuaderno del plan y da la lección actual (si no está ya en curso)."""
        self._cambiar_chat(pid)
        self._abrir_estudio()
        leccion, _, _ = aprendizaje.leccion_actual(self.progreso, pid)
        if not leccion:
            return
        if leccion["id"] in self._plan().get("vistas", []):
            QTimer.singleShot(80, self.scroll_to_bottom)  # ya la explicó: se retoma donde iba, sin repetir
            return
        self._enviar_texto("empezar")

    def _borrar_plan(self, pid):
        aprendizaje.borrar_plan(self.progreso, pid)
        if self.chat_id == pid:
            self.chat_id = aprendizaje.CHAT_LIBRE
            self._cargar_chat_actual()
        self._refrescar_paneles()

    # ---------- planes de estudio ----------

    def _crear_plan(self, meta):
        """La IA elige temas del catálogo fijo según la meta (con respaldo por palabras clave)."""
        self.tux_assistant.start_thinking_animation()
        if not self.isVisible():
            self.show_chat()
        # Se ve cómo se arma: grafo en modo radar y pasos en Mi ruta
        self._ir_a(self.TAB_RUTA)
        self.panel_ruta.mostrar_armando(self.progreso, aprendizaje.TEMAS, aprendizaje.LECCIONES,
                                        aprendizaje.leccion_actual, meta)
        self._armando = True
        self.plan_worker = PlanWorker(meta, self.nivel)
        self.plan_worker.listo.connect(lambda nombre, temas, m=meta: self._plan_creado(m, nombre, temas))
        self.plan_worker.start()

    def _plan_creado(self, meta, nombre, temas):
        self.tux_assistant.thinking.stop()
        self.tux_assistant.stop_thinking_animation()
        if not nombre:
            nombre = aprendizaje.TEMAS[temas[0]]["nombre"] if temas else "Mi plan"
        pid = aprendizaje.crear_plan(self.progreso, nombre, meta, temas)
        self._armando = False
        self.panel_ruta.revelar_pid = pid      # la ruta del plan nuevo se dibuja animada
        self.panel_ruta.vista = "grafo"
        self.panel_ruta.mostrando_rutas = False
        QTimer.singleShot(3000, lambda: setattr(self.panel_ruta, "revelar_pid", None))
        self.panel_ruta.plan_visible = pid
        self._cambiar_chat(pid)
        if not self.isVisible():
            self.show_chat()
        self._ir_a(self.TAB_RUTA)  # se muestra el mapa del plan recién creado
        self.tux_assistant.say(f"📘 Te armé el plan «{nombre}». Pulsa «Continuar lección» cuando quieras.", play_sound=True)

    def _contexto_plan(self):
        leccion, i, total = aprendizaje.leccion_actual(self.progreso, self.chat_id)
        if not leccion:
            return ""
        return aprendizaje.contexto_leccion(self._plan(), leccion, i, total)

    def _flujo_plan(self, text):
        """Comandos del plan. Devuelve True si el mensaje ya quedó atendido."""
        t = text.strip().lower()
        leccion, i, total = aprendizaje.leccion_actual(self.progreso, self.chat_id)

        if leccion is None:
            if re.fullmatch(r"(empezar|siguiente|continuar|listo|ya)\W*", t):
                self._responder("🏆 Ya terminaste este plan. Crea otro con «＋ Nuevo plan de estudio» o pregúntame lo que quieras.")
                return True
            return False

        if re.fullmatch(r"(empe[zc]ar|empecemos|comenzar|siguiente( lecci[oó]n)?|continuar|sigamos|vamos|dale)\W*", t):
            self.mision_pendiente = leccion
            self._preguntar_ia(pregunta=f"Enséñame la lección «{leccion['titulo']}»: {leccion['objetivo']}.")
            return True

        if re.fullmatch(r"(listo|ya|hecho|termin[eé]|ya est[aá]|ya lo hice|comprueba|verifica|revisa)\W*", t):
            if not leccion.get("pasos") and aprendizaje.es_mision_de_respuesta(leccion):
                self._esperando = "mision"
                self._responder("Escríbeme la respuesta que encontraste y la comparo con tu equipo 🐧")
            else:
                self._verificar(leccion, "")
            return True

        if re.fullmatch(r"(pista|ayuda|no s[eé]( c[oó]mo)?|ay[uú]dame)\W*", t):
            self._preguntar_ia(self._contexto_plan(),
                               pregunta=f"Dame una pista corta para esta misión, sin darme la solución completa: «{leccion['mision']}»")
            return True

        if re.fullmatch(r"(saltar|s[aá]ltala|omitir|siguiente misi[oó]n)\W*", t):
            aprendizaje.marcar(self.progreso, leccion["id"], saltada=True, pid=self.chat_id)
            self._poblar_selector()
            self._actualizar_progreso()
            siguiente, i, total = aprendizaje.leccion_actual(self.progreso, self.chat_id)
            self._responder("✅ La salté ⏭️ (no cuenta para subir de nivel)." +
                            (f"\n\nSiguiente lección ({i}/{total}): **{siguiente['titulo']}**." if siguiente else ""))
            return True

        # Respuesta a una misión: SOLO si Tux la está esperando, o si es un dato corto (no una pregunta ni una petición)
        espera = getattr(self, "_esperando", None) == "mision"
        dato_corto = (len(t.split()) <= 3 and "?" not in t and not pide_mas_detalle(t)
                      and not re.match(r"(c[oó]mo|qu[eé]|por ?qu[eé]|expl[ií]c|dime|ayuda|no entiendo|hola|gracias)", t))
        if (espera or dato_corto) and self._mision_espera_respuesta(leccion):
            self._esperando = None
            self._verificar(leccion, text)
            return True
        return False

    def _mision_espera_respuesta(self, leccion):
        if leccion.get("pasos"):
            hechos = aprendizaje.pasos_hechos(self._plan(), leccion["id"])
            return any(p["check"][0] in ("respuesta", "respuesta_fija") for i, p in enumerate(leccion["pasos"]) if i not in hechos)
        return aprendizaje.es_mision_de_respuesta(leccion)

    def _verificar(self, leccion, respuesta):
        if leccion.get("pasos"):
            self._verificar_pasos(leccion, respuesta)
            return
        ok, detalle = aprendizaje.verificar(leccion["check"], respuesta)
        if not ok:
            self._responder(f"❌ Aún no. {detalle}\nCorrígelo y vuelve a comprobar, o pide una pista.")
            return
        self._mision_cumplida(leccion)

    def _verificar_pasos(self, leccion, respuesta):
        """Misión de varios pasos: se revisa cada uno en el equipo; se completa cuando TODOS están hechos."""
        pid, lid, plan = self.chat_id, leccion["id"], self._plan()
        detalles, respuesta_usada, pide_dato = {}, False, None
        for i, paso in enumerate(leccion["pasos"]):
            if i in aprendizaje.pasos_hechos(plan, lid):
                continue
            es_respuesta = paso["check"][0] in ("respuesta", "respuesta_fija")
            if es_respuesta and not (respuesta and not respuesta_usada):
                pide_dato = pide_dato if pide_dato is not None else i
                continue
            ok, det = aprendizaje.verificar(paso["check"], respuesta if es_respuesta else "")
            respuesta_usada = respuesta_usada or es_respuesta
            if ok:
                aprendizaje.marcar_paso(self.progreso, pid, lid, i)
            else:
                detalles[i] = det
        hechos = aprendizaje.pasos_hechos(plan, lid)
        if len(hechos) == len(leccion["pasos"]):
            self._mision_cumplida(leccion)
            return
        lineas = [f"❌ **Vas {len(hechos)} de {len(leccion['pasos'])} pasos.** Esto es lo que vi en tu equipo:"]
        for i, paso in enumerate(leccion["pasos"]):
            if i in hechos:
                lineas.append(f"- ✓ Paso {i + 1}: hecho")
            elif i in detalles:
                lineas.append(f"- ○ Paso {i + 1}: {detalles[i]}")
            else:
                lineas.append(f"- ○ Paso {i + 1}: escríbeme el dato que encontraste")
        if pide_dato is not None and not detalles:
            self._esperando = "mision"
            lineas.append(f"\nEscribe aquí la respuesta del paso {pide_dato + 1} y la comparo con tu equipo.")
        else:
            lineas.append("\nTermina lo que falta y vuelve a comprobar, o pide una pista.")
        self._responder("\n".join(lineas))
        self._pintar_panel_mision()

    def _mision_cumplida(self, leccion):
        antes = aprendizaje.nivel_conocimiento(aprendizaje.xp_total(self.progreso))[0]
        aprendizaje.marcar(self.progreso, leccion["id"], pid=self.chat_id)
        ganado = aprendizaje.xp_leccion(leccion["id"])
        xp = aprendizaje.xp_total(self.progreso)
        idx, nombre, desc, _, _ = aprendizaje.nivel_conocimiento(xp)
        partes = [f"✅ **¡Misión cumplida! +{ganado} XP** Lo comprobé en tu equipo. Llevas {xp} XP."]
        nuevo = None
        if idx > antes:
            partes.append(f"🎓 **Subiste a {nombre}**: {desc.lower()}.")
            nuevo = aprendizaje.estilo_sugerido(self.progreso, self.nivel)
            if nuevo:
                self.nivel = nuevo
                guardar_nivel(nuevo)
                partes[-1] += (f" Desde ahora te explico en modo «{aprendizaje.NOMBRE_ESTILO[nuevo]}» "
                               "(cámbialo en Progreso cuando quieras).")
        siguiente, i, total = aprendizaje.leccion_actual(self.progreso, self.chat_id)
        if siguiente:
            partes.append(f"Siguiente lección ({i}/{total}): **{siguiente['titulo']}**.")
        else:
            partes.append(f"🏆 ¡Terminaste el plan «{self._plan()['nombre']}»!")
        self.tux_assistant.say(partes[1] if len(partes) > 2 else partes[0], play_sound=True)
        self.add_message("\n\n".join(partes), is_user=False)
        self._poblar_selector()
        self._actualizar_progreso()

    # ---------- vigilancia de terminal ----------

    def _configurar_terminal(self, activar):
        if activar:
            ok = terminal.instalar()
            msg = ("🖥️ Listo: desde ahora, cuando un comando falle en la terminal te explico qué pasó.\n"
                   "Funciona en las terminales que abras desde ahora. Solo guardo el ÚLTIMO comando que falló "
                   "(nada más) y lo quitas con «desactivar terminal»."
                   if ok else "No pude modificar tu `~/.bashrc` 😢")
        else:
            terminal.desinstalar()
            msg = "Quité la vigilancia de la terminal de tu `~/.bashrc`. Afecta a las terminales nuevas."
        if self.chat_id == aprendizaje.CHAT_ERRORES:
            self._cargar_chat_actual()
            self.add_message(msg, is_user=False)
        else:
            self._responder(msg)
        self._refrescar_paneles()

    def on_ai_consultando(self, comando):
        """La IA pidió un comando de solo lectura: se muestra en el globo mientras se ejecuta"""
        thinking = self.tux_assistant.thinking
        if not thinking.active:
            thinking.start()
            self.tux_assistant.start_thinking_animation()
        thinking.consulta = comando
        thinking.animate()

    def on_ai_parcial(self, texto):
        """Muestra la respuesta mientras se va generando (streaming)"""
        rapida = getattr(self, "_rapida", False)
        if self.respuesta_en_vivo is None:
            # Primer trozo: se quita el indicador «pensando», pero Tux sigue con su animación de «crear la
            # respuesta» hasta que termine de escribir (on_ai_response la devuelve a la normal)
            self.tux_assistant.thinking.stop()
            self.respuesta_en_vivo = self.add_message(texto, is_user=False)
            self.respuesta_en_vivo.actualizar(texto, final=False)
            if not self.isVisible():
                self.tux_assistant.bubble.show_text(texto, play_sound=True, rapido=rapida)
            else:
                self.tux_assistant.bubble.hide()
        else:
            self._pintar_respuesta(self.respuesta_en_vivo, texto, final=False)
            self.message_history[-1]['text'] = texto
            if not self.isVisible():
                self.tux_assistant.bubble.show_text(texto, play_sound=False, rapido=rapida)
        self.tux_assistant.update_bubble_position()
        self.scroll_to_bottom()

    def on_ai_response(self, answer):
        """Maneja la respuesta final de la IA"""
        rapida = getattr(self, "_rapida", False)
        self._rapida = False
        self._quizas_titular(answer)
        self.tux_assistant.thinking.stop()
        self.tux_assistant.stop_thinking_animation()

        if self.respuesta_en_vivo is not None:
            # Ya se mostró en vivo: solo se fija el texto final y el tiempo de la burbuja
            self._pintar_respuesta(self.respuesta_en_vivo, answer)
            self.message_history[-1]['text'] = answer
            if not self.isVisible():
                self.tux_assistant.say(answer, play_sound=False, rapido=rapida)
            self.respuesta_en_vivo = None
            self._guardar_chat()
        else:
            if not self.isVisible():
                self.tux_assistant.say(answer, play_sound=True, rapido=rapida)
            self.add_message(answer, is_user=False)
        self._mostrar_mision()
        
        # Limpiar worker
        if self.tux_assistant.ai_worker:
            try:
                self.tux_assistant.ai_worker.parcial.disconnect()
                self.tux_assistant.ai_worker.finished.disconnect()
                self.tux_assistant.ai_worker.error.disconnect()
            except:
                pass
            self.tux_assistant.ai_worker = None
            
    def _mostrar_mision(self):
        """Tras explicar una lección, la misión se muestra aparte.

        Cada ruta tiene SU misión: si aún no existe, la IA la crea (adaptada a la meta de la ruta y distinta de
        las de otras rutas) y el código la valida; si no sirve, se usa la del catálogo.
        """
        if not self.mision_pendiente:
            return
        leccion, self.mision_pendiente = self.mision_pendiente, None
        pid = self.chat_id
        plan = self.progreso["planes"].get(pid)
        if plan is None:
            self.add_message(aprendizaje.tarjeta_mision(leccion), is_user=False)
            return
        aprendizaje.marcar_vista(self.progreso, pid, leccion["id"])
        if leccion.get("mision_propia"):
            self.add_message(aprendizaje.tarjeta_mision(leccion), is_user=False)
            return
        self._generando_mision = leccion["id"]
        self._mostrar_pensando(None, 0, "Tux está creando una misión para esta ruta")
        trabajador = MisionWorker(pid, aprendizaje.prompt_mision(
            plan, leccion, aprendizaje.misiones_usadas(self.progreso, leccion["id"], excepto=pid)), leccion["id"])
        trabajador.listo.connect(self._mision_lista)
        self._misiones_en_curso = getattr(self, "_misiones_en_curso", []) + [trabajador]
        trabajador.start()

    def _mision_lista(self, pid, lid, resultado):
        self._generando_mision = None
        self._quitar_pensando()
        plan = self.progreso["planes"].get(pid)
        if plan is None:
            return
        if resultado:
            aprendizaje.guardar_mision(self.progreso, pid, lid, *resultado)
        tarjeta = aprendizaje.tarjeta_mision(aprendizaje.leccion_de_plan(plan, lid))
        if self.chat_id == pid:
            self.add_message(tarjeta, is_user=False)
            self._pintar_panel_mision()
        else:
            aprendizaje.agregar_a_chat(pid, tarjeta)

    def on_ai_error(self, error_msg):
        """Maneja errores de la IA"""
        self._rapida = False
        self.tux_assistant.thinking.stop()
        self.tux_assistant.stop_thinking_animation()
        self.respuesta_en_vivo = None
        
        # Mostrar error en burbuja
        self.tux_assistant.say(error_msg, play_sound=True)
        
        # Añadir al chat
        self.add_message(error_msg, is_user=False)
        self._mostrar_mision()
        
        # Limpiar worker
        if self.tux_assistant.ai_worker:
            try:
                self.tux_assistant.ai_worker.parcial.disconnect()
                self.tux_assistant.ai_worker.finished.disconnect()
                self.tux_assistant.ai_worker.error.disconnect()
            except:
                pass
            self.tux_assistant.ai_worker = None




class ThinkingIndicator:
    def __init__(self, tux_assistant):
        self.tux = tux_assistant
        self.bubble = tux_assistant.bubble
        self.timer = QTimer()
        self.timer.timeout.connect(self.animate)
        self.step = 0
        self.active = False
        self.consulta = None  # comando que la IA está revisando ahora

    def start(self):
        self.active = True
        self.step = 0
        self.timer.start(500)
        QTimer.singleShot(0, self.animate)

    def stop(self):
        self.active = False
        self.timer.stop()
        self.consulta = None
        self.tux.chat_window._quitar_pensando()

    def animate(self):
        if not self.active:
            return
        dots = "." * ((self.step % 3) + 1)
        chat = self.tux.chat_window
        if chat.isVisible():
            # Con el cuaderno abierto, el «pensando» va dentro de él y no en un globo encima
            self.bubble.hide()
            chat._mostrar_pensando(self.consulta, self.step)
            self.step += 1
            return
        if self.consulta:
            self.bubble.show_text(f"🔎 Revisando en tu equipo `{self.consulta}`{dots}", play_sound=False)
        else:
            self.bubble.show_text(f"{dots}", play_sound=False)
        self.step += 1

class MisionWorker(QThread):
    """Pide a la IA una misión para una lección de UNA ruta (JSON validado por aprendizaje.parsear_mision)."""
    listo = pyqtSignal(str, str, object)

    def __init__(self, pid, prompt, lid):
        super().__init__()
        self.pid, self.prompt, self.lid = pid, prompt, lid

    def run(self):
        resultado = None
        try:
            cuerpo = {
                "model": elegir_modelo(),
                "messages": [{"role": "user", "content": self.prompt}],
                "stream": False, "format": "json", "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": {"temperature": 0.5, "num_predict": 450},
            }
            if elegir_modelo().startswith(("qwen3", "deepseek-r1")):
                cuerpo["think"] = False
            for _ in range(2):  # un reintento si la IA no da algo comprobable
                r = requests.post(OLLAMA_CHAT_URL, json=cuerpo, timeout=60)
                resultado = aprendizaje.parsear_mision(r.json().get("message", {}).get("content", ""))
                if resultado:
                    resultado = (resultado[0], aprendizaje.asegurar_pasos_posibles(resultado[1]))
                    break
        except Exception:
            pass
        self.listo.emit(self.pid, self.lid, resultado)


class TituloWorker(QThread):
    """Pide a la IA un título de 2-4 palabras para un cuaderno, según su primera conversación."""
    listo = pyqtSignal(str, str)

    def __init__(self, cid, pregunta, respuesta):
        super().__init__()
        self.cid, self.pregunta, self.respuesta = cid, pregunta, respuesta

    def run(self):
        titulo = ""
        try:
            cuerpo = {
                "model": elegir_modelo(),
                "messages": [{"role": "user", "content":
                              "Escribe SOLO un título en español de 2 a 4 palabras para un cuaderno de estudio sobre esta "
                              "conversación. Sin comillas, sin punto final, sin emojis.\n\n"
                              f"Pregunta: {self.pregunta[:300]}\nRespuesta: {self.respuesta[:400]}"}],
                "stream": False, "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": {"temperature": 0.2, "num_predict": 16},
            }
            if elegir_modelo().startswith(("qwen3", "deepseek-r1")):
                cuerpo["think"] = False
            r = requests.post(OLLAMA_CHAT_URL, json=cuerpo, timeout=40)
            titulo = r.json().get("message", {}).get("content", "")
        except Exception:
            pass
        titulo = re.sub(r"<think>.*?</think>", "", titulo, flags=re.DOTALL)
        titulo = titulo.strip().split("\n")[0].strip(" \"'«»*.#:").strip()
        if not (2 <= len(titulo) <= 40):
            titulo = ""
        self.listo.emit(self.cid, titulo[:1].upper() + titulo[1:] if titulo else "")


class TerminalWorker(QThread):
    """Arma la explicación rápida de un comando fallido sin congelar la interfaz."""
    listo = pyqtSignal(dict, str, str)

    def __init__(self, err):
        super().__init__()
        self.err = err

    def run(self):
        try:
            explicacion, real = terminal.explicacion_rapida(self.err)
        except Exception:
            explicacion, real = f"El comando terminó con error (código {self.err['codigo']}).", ""
        self.listo.emit(self.err, explicacion, real)


class PlanWorker(QThread):
    """Pide a la IA qué temas del catálogo encajan con la meta (respuesta JSON corta)."""
    listo = pyqtSignal(str, list)

    def __init__(self, meta, nivel):
        super().__init__()
        self.meta, self.nivel = meta, nivel

    def run(self):
        nombre, temas = "", []
        try:
            cuerpo = {
                "model": elegir_modelo(),
                "messages": [{"role": "user", "content": aprendizaje.prompt_seleccion(self.meta, self.nivel)}],
                "stream": False, "format": "json",
                "keep_alive": OLLAMA_KEEP_ALIVE, "options": {"temperature": 0.2, "num_predict": 120},
            }
            if elegir_modelo().startswith(("qwen3", "deepseek-r1")):
                cuerpo["think"] = False
            r = requests.post(OLLAMA_CHAT_URL, json=cuerpo, timeout=60)
            nombre, temas = aprendizaje.parsear_seleccion(r.json().get("message", {}).get("content", ""))
        except Exception:
            pass
        if not temas:  # respaldo sin IA
            temas = aprendizaje.seleccion_por_palabras(self.meta, self.nivel)
        temas = aprendizaje.ajustar_seleccion(self.meta, temas)
        self.listo.emit(nombre, temas)


class AIWorker(QThread):
    parcial = pyqtSignal(str)   # texto acumulado mientras llega (streaming)
    consultando = pyqtSignal(str)  # comando de solo lectura que la IA está consultando
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, historial, nivel, extra="", en_vivo=True, tokens=None):
        super().__init__()
        self.tokens = tokens  # tope propio (modo rápido)
        self.historial = historial
        self.nivel = nivel
        self.en_vivo = en_vivo  # False en lecciones: no se pegan datos del equipo a la pregunta
        self.extra = extra  # contexto de la lección cuando se está en un plan de estudio
        self.is_running = True

    def run(self):
        try:
            ultima = self.historial[-1]["text"] if self.historial else ""
            detalle = pide_mas_detalle(ultima)

            # Contexto completo del equipo (estático en caché + estado actual) + capa pedagógica
            try:
                contexto = contexto_sistema.contexto_completo()
            except Exception:
                contexto = obtener_contexto_minimo()
            system_prompt = construir_system_prompt(self.nivel, contexto, USERNAME, detalle=detalle) + self.extra

            # Historial corto: menos tokens que procesar = respuesta más rápida
            mensajes = [{"role": "system", "content": system_prompt}]
            # Si hay alertas reales relacionadas con la pregunta, se pegan a la pregunta
            # (los modelos pequeños atienden mucho más al mensaje del usuario)
            try:
                pistas = contexto_sistema.alertas_relevantes(ultima) if self.en_vivo else []
                en_vivo = contexto_sistema.datos_en_vivo(ultima) if self.en_vivo else ""
            except Exception:
                pistas, en_vivo = [], ""
            for i, m in enumerate(self.historial[-6:]):
                texto = m["text"]
                if i == len(self.historial[-6:]) - 1 and m["is_user"]:
                    if en_vivo:
                        if self.tokens:  # modo rápido
                            texto += ("\n\n[DATOS REALES DE MI EQUIPO, medidos ahora mismo. Respóndeme en 1 o 2 frases "
                                      "con el dato exacto, sin explicar de más.]\n" + en_vivo)
                        else:
                            texto += ("\n\n[DATOS REALES DE MI EQUIPO, medidos ahora mismo. Respóndeme con estos números "
                                  "exactos y explícame qué significan; no me pidas ejecutar comandos para verlos.]\n" + en_vivo)
                    if pistas:
                        texto += "\n[Alerta real ahora: " + "; ".join(pistas) + "]"
                if not m["is_user"] and len(texto) > 600:
                    texto = texto[:600] + "…"
                mensajes.append({
                    "role": "user" if m["is_user"] else "assistant",
                    "content": texto,
                })

            # Bucle de herramienta: la IA puede pedir hasta 3 rondas de comandos de solo lectura
            self.consultas = []
            text, cortada = "", False
            for ronda in range(4):
                usar_herramienta = ronda < 3
                text, cortada, llamadas = self._pedir(mensajes, detalle, usar_herramienta)
                if not self.is_running:
                    return
                if not llamadas:
                    break
                mensajes.append({"role": "assistant", "content": text, "tool_calls": llamadas})
                for llamada in llamadas:
                    comando = (llamada.get("function", {}).get("arguments") or {}).get("comando", "")
                    self.consultando.emit(comando)
                    resultado = herramientas.ejecutar(comando)
                    self.consultas.append(comando)
                    mensajes.append({"role": "tool", "tool_name": "consultar_sistema",
                                     "content": f"$ {comando}\n{resultado}"})

            text = text.strip()
            medidos = re.findall(r"^\[(.+?)\]", en_vivo, re.MULTILINE)
            if medidos and text:
                # Transparencia: qué datos reales del equipo se midieron para responder
                text += "\n\n📊 Medí ahora en tu equipo: " + ", ".join(m.lower() for m in medidos)
            if self.consultas and text:
                # Transparencia: qué consultó Tux para responder
                text += ("\n" if medidos else "\n\n") + "🔎 Revisé en tu equipo: " + ", ".join(f"`{c}`" for c in self.consultas)
            if cortada:
                text += "…\n\n(Dime «explícame más» y sigo 🐧)"

            if not self.is_running:
                return
            if not text:
                self.finished.emit("🤔 Mmm… no supe qué decir.\nIntenta preguntarme de otra forma.")
            else:
                self.finished.emit(text)

        except requests.exceptions.Timeout:
            if self.is_running:
                self.error.emit("⏳ La respuesta tardó demasiado.\nIntenta con una pregunta más corta.")
        except Exception:
            if self.is_running:
                self.error.emit("No puedo conectarme con Ollama 😢")

    def _pedir(self, mensajes, detalle, usar_herramienta):
        """Una llamada en streaming. Devuelve (texto, cortada, llamadas_a_herramienta)."""
        cuerpo = {
            "model": elegir_modelo(),
            "messages": mensajes,
            "stream": True,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": {
                "num_predict": self.tokens or max_tokens(self.nivel, detalle),
                "num_ctx": 8192,
                "temperature": 0.3,
                "repeat_penalty": 1.15,
            },
        }
        if usar_herramienta:
            cuerpo["tools"] = [herramientas.HERRAMIENTA_OLLAMA]
        if cuerpo["model"].startswith(("qwen3", "deepseek-r1")):
            cuerpo["think"] = False  # sin "razonamiento" previo: responde mucho más rápido
        response = requests.post(OLLAMA_CHAT_URL, json=cuerpo, stream=True, timeout=(5, 120))
        response.raise_for_status()
        text, cortada, llamadas = "", False, []
        for linea in response.iter_lines():
            if not self.is_running:
                response.close()
                return text, cortada, []
            if not linea:
                continue
            trozo = json.loads(linea)
            mensaje = trozo.get("message", {})
            llamadas += mensaje.get("tool_calls") or []
            text += mensaje.get("content", "")
            if "<think>" in text:  # por si el modelo razona en voz alta: no se muestra
                text = re.sub(r"<think>.*?(</think>|$)", "", text, flags=re.DOTALL)
            if trozo.get("done"):
                cortada = trozo.get("done_reason") == "length"
                break
            if text.strip() and not llamadas and "consultar_sistema" not in text:
                self.parcial.emit(text.strip())
        # Algunos modelos escriben la llamada como texto: se detecta y se ejecuta igual
        if usar_herramienta and not llamadas:
            m = re.search(r'consultar_sistema\W*\{\s*"comando"\s*:\s*"([^"]+)"', text)
            if m:
                llamadas = [{"function": {"name": "consultar_sistema", "arguments": {"comando": m.group(1)}}}]
                text = ""
        return text, cortada, llamadas

    def stop(self):
        """Método para detener el hilo de forma segura"""
        self.is_running = False
        self.terminate()
        self.wait(2000)

def get_detailed_system_answer(question_type: str) -> str:
    """Obtiene respuestas detalladas para preguntas específicas del sistema"""
    try:
        system_info = get_system_info()
        
        if "proceso" in question_type.lower() or "consumiendo" in question_type.lower():
            if 'procesos_top' in system_info and system_info['procesos_top']:
                respuesta = "🎯 Procesos que más consumen:\n"
                for i, proc in enumerate(system_info['procesos_top'][:5], 1):
                    respuesta += f"{i}. {proc['nombre']} (PID: {proc['pid']})\n"
                    respuesta += f"   CPU: {proc['cpu']} | Memoria: {proc['memoria']}\n"
                return respuesta
            else:
                return "No pude obtener información de procesos en este momento."
        
        elif "memoria" in question_type.lower() or "ram" in question_type.lower():
            if 'memoria' in system_info:
                mem = system_info['memoria']
                respuesta = "🧠 Estado de la memoria:\n"
                respuesta += f"• Total RAM: {mem['total_ram']}\n"
                respuesta += f"• En uso: {mem['ram_usada']} ({mem['porcentaje_ram_usada']})\n"
                respuesta += f"• Disponible: {mem['ram_disponible']}\n"
                respuesta += f"• Swap total: {mem['total_swap']}\n"
                respuesta += f"• Swap usado: {mem['swap_usada']}\n"
                return respuesta
        
        elif "disco" in question_type.lower() or "almacenamiento" in question_type.lower():
            if 'discos' in system_info and system_info['discos']:
                respuesta = "💾 Estado de los discos:\n"
                for disk in system_info['discos']:
                    respuesta += f"• {disk['punto_montaje']} ({disk['dispositivo']}):\n"
                    respuesta += f"  Total: {disk['total']} | Usado: {disk['usado']} ({disk['porcentaje_usado']})\n"
                    respuesta += f"  Libre: {disk['libre']} | FS: {disk['sistema_archivos']}\n"
                return respuesta
        
        elif "cpu" in question_type.lower() or "procesador" in question_type.lower():
            if 'cpu' in system_info:
                cpu = system_info['cpu']
                respuesta = "⚡ Estado del CPU:\n"
                respuesta += f"• Núcleos físicos: {cpu['nucleos_fisicos']}\n"
                respuesta += f"• Núcleos lógicos: {cpu['nucleos_logicos']}\n"
                respuesta += f"• Uso actual: {cpu['uso_actual']}\n"
                if 'frecuencia_actual' in cpu:
                    respuesta += f"• Frecuencia: {cpu['frecuencia_actual']}\n"
                return respuesta
        
        elif "sistema" in question_type.lower() or "información" in question_type.lower() or "informacion" in question_type.lower():
            respuesta = "📊 Información completa del sistema:\n"
            if 'sistema' in system_info:
                sys_info = system_info['sistema']
                respuesta += f"• SO: {sys_info['distribucion']}\n"
                respuesta += f"• Kernel: {sys_info['version_kernel']}\n"
                respuesta += f"• Hostname: {sys_info['hostname']}\n"
                respuesta += f"• Usuario: {sys_info['usuario']}\n"
                respuesta += f"• Hora: {sys_info['fecha_hora']}\n"
                respuesta += f"• Uptime: {system_info.get('uptime', 'N/A')}\n"
            
            if 'carga_sistema' in system_info:
                load = system_info['carga_sistema']
                respuesta += f"• Carga sistema: 1min:{load['1_minuto']:.2f} | 5min:{load['5_minutos']:.2f} | 15min:{load['15_minutos']:.2f}\n"
            return respuesta

        elif "red" in question_type.lower() or "ip" in question_type.lower() or "conexión" in question_type.lower() or "internet" in question_type.lower():
            if 'red' in system_info and system_info['red']:
                respuesta = "🌐 Información de red:\n"
                for net in system_info['red']:
                    if net['interfaz'] != 'lo':
                        respuesta += f"• Interfaz {net['interfaz']}:\n"
                        respuesta += f"  IP: {net['ip']}\n"
                        respuesta += f"  Máscara: {net['mascara']}\n"
                
                try:
                    import urllib.request
                    public_ip = urllib.request.urlopen('https://api.ipify.org', timeout=3).read().decode('utf8')
                    respuesta += f"• IP Pública: {public_ip}\n"
                except:
                    respuesta += "• IP Pública: No se pudo obtener\n"

                return respuesta
        
        return ""
        
    except Exception as e:
        return ""

class TuxAssistant(QLabel):
    def __init__(self, mostrar=True):
        super().__init__()

        self.tux_size = QSize(130, 130)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.tux_size)

        self.animations = {}
        self.load_animations()
        
        self.current_animation = 'sentado'
        self.is_thinking = False
        self.is_moving = False
        self.is_dragging = False
        self.was_thinking_before_drag = False
        
        self.last_mouse_move_time = time.time()
        self.mouse_press_time = 0
        self.walking_timer = QTimer()
        self.walking_timer.timeout.connect(self.check_walking)
        self.drag_distance_threshold = 5
        
        self.last_activity_time = time.time()
        self.inactivity_state = 'active'
        self.idle_start_time = None
        self.relaxed_start_time = None
        self.current_relaxed_animation = None
        
        self.inactivity_timer = QTimer()
        self.inactivity_timer.timeout.connect(self.check_inactivity)
        self.inactivity_timer.start(5000)
        
        self.movie = self.animations.get('sentado', self.create_default_animation())
        self.movie.setScaledSize(self.tux_size)
        self.movie.start()
        self.setMovie(self.movie)

        self.bubble = Bubble(play_sound=True)
        self.bubble.set_tux_assistant(self)
        # Modo rápido (clic) y modo detallado (doble clic)
        self.pregunta = PreguntaRapida()
        self.pregunta.enviada.connect(lambda t: self.chat_window.pregunta_rapida(t))
        self._timer_clic = QTimer(self)
        self._timer_clic.setSingleShot(True)
        self._timer_clic.timeout.connect(self._clic_simple)
        self.thinking = ThinkingIndicator(self)

        # Inicializar ventana de chat
        self.chat_window = ChatWindow(self)
        
        self.drag_offset = None
        self.initial_press_pos = None
        self.ai_worker = None

        self.bubble_closed_by_user = False

        # Vigilancia de terminal: revisa cada segundo si cambió el archivo del último error (barato: solo stat)
        self.error_terminal = None
        self.terminal_worker = None
        self._marca_terminal = terminal.marca()
        self.terminal_timer = QTimer()
        self.terminal_timer.timeout.connect(self.revisar_terminal)
        self.terminal_timer.start(1000)

        self.position_at_bottom_right()
        if mostrar:
            self.aparecer()

    def aparecer(self):
        """Tux entra en escena (tras la intro) con un fundido y saluda explicando los dos modos."""
        self.setWindowOpacity(0.0)
        self.show()
        self._fundido = QPropertyAnimation(self, b"windowOpacity")
        self._fundido.setDuration(350)
        self._fundido.setStartValue(0.0)
        self._fundido.setEndValue(1.0)
        self._fundido.start()
        QTimer.singleShot(
            500,
            lambda: (self.bubble.show_text("¡Hola! Soy Tux 🐧, tu compañero para aprender Linux. "
                                           "Hazme clic y pregúntame lo que quieras.", 12000, play_sound=True,
                                           accion=("rapida:abrir", "Preguntar algo")),
                     self.update_bubble_position())
        )

    def position_at_bottom_right(self):
        """Posiciona el asistente en la esquina inferior derecha de la pantalla PRINCIPAL"""
        try:
            screen = QApplication.primaryScreen()
            screen_geometry = screen.availableGeometry()
            
            margin_right = 30
            margin_bottom = 100
            
            x_pos = screen_geometry.width() - self.tux_size.width() - margin_right
            y_pos = screen_geometry.height() - self.tux_size.height() - margin_bottom
            
            self.move(x_pos, y_pos)
            
        except Exception as e:
            self.move(100, 100)

    def load_animations(self):
        """Carga todas las animaciones disponibles"""
        for name, path in TUX_ANIMATIONS.items():
            if os.path.exists(path):
                movie = QMovie(path)
                movie.setScaledSize(self.tux_size)
                self.animations[name] = movie

    def create_default_animation(self):
        """Crea una animación por defecto si no hay archivos"""
        movie = QMovie()
        movie.setScaledSize(self.tux_size)
        return movie
    
    def set_animation(self, animation_name):
        """Cambia la animación actual"""
        if animation_name == self.current_animation:
            return
        
        if animation_name in self.animations:
            self.current_animation = animation_name
            self.movie.stop()
            self.movie = self.animations[animation_name]
            self.movie.setScaledSize(self.tux_size)
            self.movie.start()
            self.setMovie(self.movie)
    
    def _ventana_abierta(self):
        return ((self.chat_window and self.chat_window.isVisible()) or (self.bubble and self.bubble.isVisible())
                or (hasattr(self, "pregunta") and self.pregunta.isVisible()))

    def start_thinking_animation(self):
        """Animación de búsqueda mientras la IA crea la respuesta (también con el cuaderno abierto)"""
        self.is_thinking = True
        self.inactivity_state = 'active'
        if self.is_moving:
            return  # al soltarlo, mouseReleaseEvent vuelve a poner la de pensar
        
        import random
        chosen_animation = random.choice(['busqueda', 'busqueda2'])
        self.set_animation(chosen_animation)
    
    def stop_thinking_animation(self):
        """Detiene animación de búsqueda y vuelve a sentado"""
        self.is_thinking = False
        self.set_animation('sentado')
    
    def start_walking_animation(self):
        """Inicia animación de caminar"""
        if not self.is_moving:
            self.is_moving = True
            
            if self.is_thinking:
                self.was_thinking_before_drag = True
            else:
                self.was_thinking_before_drag = False
            
            self.set_animation('caminando')
    
    def stop_walking_animation(self):
        """Detiene animación de caminar"""
        if self.is_moving:
            self.is_moving = False
            
            if self.was_thinking_before_drag:
                self.start_thinking_animation()
                self.was_thinking_before_drag = False
            else:
                if not self.is_thinking:
                    self.set_animation('sentado')
    
    def check_walking(self):
        """Verifica si el usuario todavía está moviendo el mouse"""
        current_time = time.time()
        if current_time - self.last_mouse_move_time > 0.25:
            self.walking_timer.stop()
            self.stop_walking_animation()
    
    INACTIVIDAD_RELAX = 60      # segundos sin interacción (y sin globo ni cuaderno) para entretenerse
    CAMBIO_RELAX = 40           # cada cuánto cambia de animación de entretenimiento

    def check_inactivity(self):
        """Estados: sentado (normal) · pensando (la IA escribe) · caminando (lo arrastras) ·
        relajado (1 min sin interacción y sin globo, pregunta rápida ni cuaderno abiertos)."""
        if self.is_thinking or self.is_moving or self.is_dragging:
            return
        ahora = time.time()
        if self._ventana_abierta():
            # Con algo abierto, Tux atiende: animación normal y el reloj de inactividad se reinicia
            self.last_activity_time = ahora
            if self.inactivity_state != 'active' or self.current_animation != 'sentado':
                self.inactivity_state = 'active'
                self.set_animation('sentado')
            return
        relajadas = [a for a in ('relajado', 'relajado2', 'relajado3', 'relajado4', 'relajado5') if a in self.animations]
        if ahora - self.last_activity_time < self.INACTIVIDAD_RELAX or not relajadas:
            if self.inactivity_state != 'active':
                self.inactivity_state = 'active'
                self.set_animation('sentado')
            return
        import random
        if self.inactivity_state != 'relaxed':
            self.inactivity_state = 'relaxed'
            self.relaxed_start_time = ahora
            self.current_relaxed_animation = random.choice(relajadas)
            self.set_animation(self.current_relaxed_animation)
        elif ahora - self.relaxed_start_time > self.CAMBIO_RELAX:
            self.relaxed_start_time = ahora
            otras = [a for a in relajadas if a != self.current_relaxed_animation] or relajadas
            self.current_relaxed_animation = random.choice(otras)
            self.set_animation(self.current_relaxed_animation)

    def update_activity_time(self):
        """Actualiza el tiempo de última actividad"""
        self.last_activity_time = time.time()
        
        if self.inactivity_state == 'relaxed':
            self.inactivity_state = 'active'
            self.relaxed_start_time = None
            if not self.is_thinking and not self.is_moving:
                self.set_animation('sentado')

    def despedirse(self):
        """Clic derecho: animación de despedida y después se apaga TODO (ventanas, hilos y el modelo de IA)."""
        if getattr(self, "_despidiendo", False):
            return
        self._despidiendo = True
        chat = self.chat_window
        n = chat.preguntas_sesion
        xp = aprendizaje.xp_total(chat.progreso) - chat.xp_inicio
        nivel = aprendizaje.nivel_conocimiento(aprendizaje.xp_total(chat.progreso))[1]
        partes = [f"Hoy: {n} {'pregunta' if n == 1 else 'preguntas'}"]
        if xp > 0:
            partes.append(f"+{xp} XP")
        partes.append(f"nivel {nivel}")
        origen = self.frameGeometry().center()
        for ventana in (chat, self.bubble, self.pregunta, getattr(chat.panel_ruta, "ventana_grafo", None)):
            if ventana is not None:
                ventana.hide()
        self.hide()
        from intro import DespedidaTux
        self._despedida = DespedidaTux(origen, " · ".join(partes))
        self._despedida.terminada.connect(self.apagar_todo)
        self._despedida.empezar()

    def apagar_todo(self):
        self.cleanup_threads()
        descargar_modelo()  # libera la VRAM: el modelo no se queda cargado en Ollama
        QApplication.quit()

    def cleanup_threads(self):
        """Detiene TODO lo de Tux antes de cerrar: hilos, temporizadores, ventanas y sonido."""
        if getattr(self, "_limpio", False):
            return
        self._limpio = True
        if self.ai_worker and self.ai_worker.isRunning():
            self.ai_worker.stop()
            self.ai_worker.wait(1500)
        chat = self.chat_window
        hilos = [chat.plan_worker, self.terminal_worker] + getattr(chat, "_misiones_en_curso", []) + getattr(chat, "_titulos", [])
        for hilo in hilos:
            if hilo is not None and hilo.isRunning():
                hilo.wait(1500)
        for timer in (self.inactivity_timer, self.walking_timer, self.terminal_timer, self._timer_clic,
                      self.bubble.hide_timer, self.bubble.screen_check_timer, chat.screen_check_timer,
                      getattr(self, "_timer_seguir", None)):
            if timer is not None:
                timer.stop()
        self.thinking.timer.stop()
        try:
            chat._guardar_chat()
        except Exception:
            pass
        for ventana in QApplication.topLevelWidgets():
            if ventana is not getattr(self, "_despedida", None):
                ventana.hide()
        
        try:
            mixer.stop()
        except:
            pass

    def say(self, text, play_sound=True, rapido=False):
        """Muestra un mensaje en la burbuja (nunca a la vez que el cuaderno: uno u otro)"""
        if self.chat_window and self.chat_window.isVisible():
            self.bubble.hide()
            return
        if self.bubble_closed_by_user and not play_sound:
            self.bubble_closed_by_user = False
            return
            
        base_time = 6000
        extra_time = len(text) * 80
        total_time = min(base_time + extra_time, 60000)

        self.bubble.show_text(text, total_time, play_sound=play_sound, rapido=rapido)
        self.update_bubble_position()
        
        self.update_activity_time()
        
        self.bubble_closed_by_user = False

    def revisar_terminal(self):
        marca = terminal.marca()
        if marca is None or marca == self._marca_terminal:
            return
        self._marca_terminal = marca
        err = terminal.leer_error()
        if not terminal.vale_la_pena(err) or (self.terminal_worker and self.terminal_worker.isRunning()):
            return
        # La explicación rápida puede volver a correr un comando de solo lectura: en otro hilo
        self.terminal_worker = TerminalWorker(err)
        self.terminal_worker.listo.connect(self.mostrar_error_terminal)
        self.terminal_worker.start()

    def mostrar_error_terminal(self, err, explicacion, real):
        self.error_terminal = (err, real)
        comando = err["comando"] if len(err["comando"]) <= 60 else err["comando"][:57] + "…"
        # Primer párrafo = lo que se ve en el globo; el mensaje real va a la IA si pide «Explícame más»
        texto = f"💥 Falló `{comando}`. {explicacion}"
        # Sacarle provecho: tipo de error, repeticiones y la lección que enseña a evitarlo
        tipo = terminal.clasificar(err, explicacion, real)
        veces = terminal.registrar(err, tipo)
        if veces >= 2:
            texto += f"\n🔁 Es la {veces}.ª vez seguida que falla igual: pulsa «Explícame más» y lo vemos con calma."
        lid = terminal.leccion_recomendada(err, tipo)
        if lid in aprendizaje.LECCIONES:
            lec = aprendizaje.LECCIONES[lid]
            texto += f"\n🎓 Aprende a evitarlo: «{lec['titulo']}» (+{aprendizaje.xp_leccion(lid)} XP) ⟦{lid}|{tipo}⟧"
        self.chat_window.registrar_error(texto)
        if self.chat_window.isVisible():
            self.chat_window._ir_a(self.chat_window.TAB_ERRORES)  # se va directo a mostrar el error
            QTimer.singleShot(120, self.chat_window.scroll_to_bottom)
            play_bubble_sound()
            return
        if terminal.cargar_estadisticas()["silencioso"]:
            return  # modo silencioso: queda guardado en «Errores» sin interrumpir
        self.bubble.show_text(texto, 25000, play_sound=True, accion=("tux:explicar", "Explícame más"))
        self.update_bubble_position()

    def explicar_error_terminal(self):
        """El usuario pidió más detalle del error de terminal: va al chat libre y pregunta a la IA."""
        if not self.error_terminal:
            return
        err, real = self.error_terminal
        chat = self.chat_window
        if not chat.isVisible():
            chat.show_chat()
        chat._ir_a(chat.TAB_ERRORES)
        chat.add_message(terminal.pregunta_para_ia(err, real), is_user=True)
        chat.process_user_question(chat.message_history[-1]["text"])

    def update_bubble_position(self):
        """Actualiza la posición de la burbuja"""
        if self.bubble and self.bubble.isVisible():
            self.bubble.position_above_tux()

    def moveEvent(self, event):
        """Se ejecuta cuando el Tux se mueve"""
        super().moveEvent(event)
        
        # Un solo temporizador agrupa todos los movimientos (antes se creaban decenas por segundo)
        if not hasattr(self, "_timer_seguir"):
            self._timer_seguir = QTimer(self)
            self._timer_seguir.setSingleShot(True)
            self._timer_seguir.timeout.connect(self._seguir_a_tux)
        if not self._timer_seguir.isActive():
            self._timer_seguir.start(16)

    def _seguir_a_tux(self):
        if self.pregunta.isVisible():
            self.pregunta.mostrar(self.frameGeometry(), self.bubble.get_tux_screen().availableGeometry())
        if self.bubble and self.bubble.isVisible():
            self.update_bubble_position()
        if self.chat_window and self.chat_window.isVisible():
            self.update_chat_position()

    def update_chat_position(self):
        """Actualiza la posición del chat"""
        if self.chat_window and self.chat_window.isVisible():
            self.chat_window.position_near_tux()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_offset = event.pos()
            self.initial_press_pos = event.pos()
            self.mouse_press_time = time.time()
            self.is_dragging = False
            
        elif event.button() == Qt.RightButton:
            self.despedirse()
        
        self.update_activity_time()

    def mouseMoveEvent(self, event):
        if self.drag_offset and self.initial_press_pos:
            current_pos = event.pos()
            distance = ((current_pos.x() - self.initial_press_pos.x()) ** 2 + 
                    (current_pos.y() - self.initial_press_pos.y()) ** 2) ** 0.5
            
            if not self.is_dragging and distance > self.drag_distance_threshold:
                self.is_dragging = True
                
                if not self.is_thinking:
                    self.start_walking_animation()
                
                self.walking_timer.start(100)
            
            if self.is_dragging:
                new_pos = event.globalPos() - self.drag_offset
                self.move(new_pos)  # moveEvent recoloca globo y cuaderno (agrupado con un temporizador)
                self.last_mouse_move_time = time.time()
                # Si se detuvo un momento y volvió a moverse, retoma la caminata
                if not self.is_moving and not self.is_thinking:
                    self.start_walking_animation()
                if not self.walking_timer.isActive():
                    self.walking_timer.start(100)
        
        self.update_activity_time()

    def mouseReleaseEvent(self, event):
        if self.drag_offset and not self.is_dragging and event.button() == Qt.LeftButton:
            # Clic sin arrastrar: se espera por si es doble clic
            self._timer_clic.start(QApplication.doubleClickInterval())
        if self.drag_offset:
            self.drag_offset = None
            self.initial_press_pos = None
            self.is_dragging = False
            
            if self.walking_timer.isActive():
                self.walking_timer.stop()
            
            if self.is_moving:
                self.stop_walking_animation()
            
            if self.is_thinking and not self.is_moving:
                self.start_thinking_animation()
        
        self.update_activity_time()
    
    def mouseDoubleClickEvent(self, event):
        """Doble clic: modo detallado (el cuaderno completo)"""
        if event.button() == Qt.LeftButton:
            self._timer_clic.stop()
            self.pregunta.hide()
            self.chat_window.show_chat()
        
        self.update_activity_time()

    def _clic_simple(self):
        """Clic: modo rápido (o cerrarlo si ya está abierto)."""
        if self.chat_window.isVisible():
            self.chat_window.raise_()
            return
        if self.pregunta.isVisible():
            self.pregunta.hide()
        else:
            self.abrir_pregunta_rapida()

    def abrir_pregunta_rapida(self):
        if self.chat_window.isVisible():
            return
        self.bubble.hide()
        pantalla = self.bubble.get_tux_screen().availableGeometry()
        self.pregunta.mostrar(self.frameGeometry(), pantalla)

    def on_ai_response(self, answer):
        self.thinking.stop()
        self.stop_thinking_animation()
        self.say(f"{answer}", play_sound=True)

        if self.ai_worker:
            try:
                self.ai_worker.finished.disconnect()
                self.ai_worker.error.disconnect()
            except:
                pass
            self.ai_worker = None

    def on_ai_error(self, error_msg):
        self.thinking.stop()
        self.stop_thinking_animation()
        self.say(error_msg, play_sound=True)
        
        if self.ai_worker:
            try:
                self.ai_worker.finished.disconnect()
                self.ai_worker.error.disconnect()
            except:
                pass
            self.ai_worker = None

def descargar_modelo():
    """Pide a Ollama que suelte el modelo de Tux de la memoria (keep_alive=0)."""
    try:
        requests.post(OLLAMA_CHAT_URL.replace("/api/chat", "/api/generate"),
                      json={"model": elegir_modelo(), "keep_alive": 0}, timeout=4)
    except Exception:
        pass


def close_app(sig=None, frame=None):
    app = QApplication.instance()
    if app:
        for widget in app.topLevelWidgets():
            if isinstance(widget, TuxAssistant):
                widget.cleanup_threads()
        descargar_modelo()
        app.quit()

signal.signal(signal.SIGINT, close_app)
signal.signal(signal.SIGTERM, close_app)

if __name__ == "__main__":
    ollama_process = None
    try:
        audio_initialized = init_audio()
        ollama_process = start_ollama()
        import threading
        threading.Thread(target=precalentar_modelo, daemon=True).start()
        contexto_sistema.precalentar()
        
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)  # cerrar el mapa grande no debe cerrar a Tux
        if os.environ.get("TUX_SIN_INTRO"):
            tux = TuxAssistant()
        else:
            # Intro animada; al terminar, el logo «vuela» hasta donde aparece Tux
            from intro import IntroTux
            tux = TuxAssistant(mostrar=False)
            intro = IntroTux(destino=tux.frameGeometry().center())
            intro.terminada.connect(tux.aparecer)
            intro.empezar()
        
        app.aboutToQuit.connect(lambda: tux.cleanup_threads())
        
        exit_code = app.exec_()
        
    except KeyboardInterrupt:
        exit_code = 0
    except Exception as e:
        exit_code = 1
        
    finally:
        if ollama_process:
            ollama_process.terminate()
            try:
                ollama_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                ollama_process.kill()

        try:
            pygame.quit()
        except:
            pass
    
    sys.exit(exit_code)