import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

import pygame
from pygame import mixer

import sys
import signal
import requests
import subprocess
import time
import socket

from PyQt5.QtWidgets import QApplication, QLabel, QInputDialog, QLineEdit, QTextEdit, QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QScrollArea, QFrame
from PyQt5.QtCore import Qt, QPoint, QSize, QTimer, QThread, pyqtSignal, QRect, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QMovie, QGuiApplication, QCursor, QPainter, QBrush, QPen, QPolygon, QColor, QFont

import psutil
import platform
import datetime
import socket as sock
import json
from typing import Dict, List

import getpass
USERNAME = getpass.getuser()


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"
OLLAMA_PORT = 11434

TUX_SYSTEM_PROMPT = f"""
Eres TUX, la mascota oficial de Linux.
Hablas de forma amigable, clara y cercana.
Te gusta ayudar con Linux, comandos, programación y tecnología.
Usas ocasionalmente emojis como 🐧💻⚙️.
Tambien puedes ayudar en otras cosas y en cualquier tema, pero te especialas mas en Linux.
No mencionas que eres una IA ni un modelo de lenguaje.
Respondes como un asistente de escritorio clásico.
Si te preguntan por quien fuiste creado, dices que fue por Sergio Lozano, pero aclaras que fuiste creado como asistente virtual por Sergio. No como mascota TUX eso fue otra persona ahi si busca quien fue quien creo a TUX.
Y toda respuesta trata de hacerla concisa y corta, no extenderse mucho, solo lo puntual.
Este es el nombre del usuario: {USERNAME}, pero deducelo si dice un nombre de usuario como diferente dilo asi tal cual pero si dice un nombre comun o algo similar, dile con el nombre deducelo, y dirigete con el nombre del usuario cuando lo veas pertinente.
"""

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

class Bubble(QLabel):
    def __init__(self, play_sound=True):
        super().__init__()
        self.play_sound = play_sound
        self.close_button_size = 20
        self.close_button_margin = 10
        self.tux_assistant = None
        self.current_screen = None
        
        # Tamaño de la flecha
        self.arrow_height = 12
        self.arrow_width = 20
        
        # Ajustar márgenes para dejar espacio para la flecha
        self.setContentsMargins(15, 15, 15, 25)  # Más espacio abajo para la flecha

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        
        # ✅ DISEÑO FUTURISTA TECNOLÓGICO CORREGIDO
        self.setStyleSheet("""
            QLabel {
                background-color: #0A0A0F;
                border: 1.2px solid #FF6C2C;
                border-radius: 20px;
                padding: 15px;
                font-size: 11pt;
                font-family: 'Segoe UI', 'Arial', 'Ubuntu Mono', monospace;
                color: #FFFFFF;
                max-width: 320px;
                min-width: 220px;
                font-weight: 500;
            }
        """)

        self.setWordWrap(True)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        
        # Margen para el texto
        self.setContentsMargins(15, 15, 15, 25)  # Más espacio abajo para la flecha

        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

        # ✅ BOTÓN DE CERRAR FUTURISTA
        self.close_button = QLabel(self)
        self.close_button.setFixedSize(self.close_button_size, self.close_button_size)
        self.close_button.setStyleSheet("""
            QLabel {
                background-color: #FF6C2C;
                border-radius: 10px;
                color: #0A0A0F;
                font-weight: bold;
                font-size: 12pt;
                qproperty-alignment: AlignCenter;
                border: 2px solid #FF8C4C;
            }
            QLabel:hover {
                background-color: #FF8C4C;
                border: 2px solid #FFAD6C;
            }
        """)
        self.close_button.setText("×")
        self.close_button.hide()
        
        # Cursor para el botón de cerrar
        self.close_button.setCursor(Qt.PointingHandCursor)
        
        self.close_button.mousePressEvent = self.close_bubble
        
        self.screen_check_timer = QTimer()
        self.screen_check_timer.timeout.connect(self.update_screen_if_needed)
        self.screen_check_timer.start(100)
        
        # Variables para calcular la posición de la flecha
        self.arrow_position_x = 0  # Posición X relativa de la flecha
        self.arrow_position = "top"  # Posición inicial de la flecha
        
        self.hide()
    
    def paintEvent(self, event):
        """Dibuja solo la flecha SOBRE el fondo existente sin sobrescribir bordes"""
        # Primero llama al paintEvent del padre para dibujar el fondo y estilo CSS
        super().paintEvent(event)
        
        # Solo si estamos en el proceso de dibujo principal
        if not self.isVisible():
            return
            
        # Solo dibuja la flecha
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Color y grosor de la flecha
        painter.setPen(QPen(QColor(255, 108, 44), 3))
        painter.setBrush(QBrush(QColor(255, 108, 44)))  # Relleno naranja
        
        # Calcular posición de la flecha
        width = self.width()
        height = self.height()
        
        # Calcular la posición X de la flecha basada en la posición del Tux
        # Si no hay Tux o no se ha calculado, centramos la flecha
        arrow_x = self.arrow_position_x if self.arrow_position_x > 0 else width // 2
        
        # Asegurar que la flecha no se salga de los bordes de la burbuja
        min_arrow_x = self.arrow_width // 2 + 5
        max_arrow_x = width - self.arrow_width // 2 - 5
        arrow_x = max(min_arrow_x, min(arrow_x, max_arrow_x))
        
        # La flecha apunta hacia el Tux
        if self.arrow_position == "top":
            # Flecha en la parte superior (apuntando hacia arriba)
            arrow_points = [
                QPoint(arrow_x, 0),  # Punta de la flecha en el borde superior
                QPoint(arrow_x - self.arrow_width // 2, self.arrow_height),
                QPoint(arrow_x + self.arrow_width // 2, self.arrow_height)
            ]
        else:
            # Flecha en la parte inferior (apuntando hacia abajo)
            arrow_points = [
                QPoint(arrow_x, height),  # Punta de la flecha en el borde inferior
                QPoint(arrow_x - self.arrow_width // 2, height - self.arrow_height),
                QPoint(arrow_x + self.arrow_width // 2, height - self.arrow_height)
            ]
        
        # Dibujar flecha rellena
        painter.drawPolygon(QPolygon(arrow_points))
        
        # Añadir borde a la flecha
        painter.setPen(QPen(QColor(200, 80, 30), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawPolygon(QPolygon(arrow_points))
        
        painter.end()

    def calculate_arrow_position(self, tux_center_x, bubble_x):
        """Calcula la posición de la flecha para que apunte al Tux"""
        # Calcular la posición X del Tux relativa a la burbuja
        # Convertir coordenadas de pantalla a coordenadas relativas de la burbuja
        
        # Primero obtener la posición global de la burbuja
        bubble_global_x = bubble_x
        
        # Calcular dónde está el Tux relativo a la burbuja
        tux_relative_x = tux_center_x - bubble_global_x
        
        # La flecha debe estar en la posición del Tux (centro del Tux)
        # Pero limitada para no salirse de los bordes de la burbuja
        return tux_relative_x


    def set_tux_assistant(self, tux_assistant):
        """Establece la referencia al asistente Tux"""
        self.tux_assistant = tux_assistant

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
                self.position_above_tux()

    def show_text(self, text, duration=None, play_sound=True):
        """Muestra texto en la burbuja"""
        self.hide_timer.stop()
        
        formatted_text = self.format_text(text)
        self.setText(formatted_text)
        self.adjustSize()
        
        self.current_screen = self.get_tux_screen()
        
        self.position_above_tux()
        
        if text != "..." and text != ".." and text != ".":
            self.close_button.show()
            self.position_close_button()
        else:
            self.close_button.hide()
        
        self.show()
        self.update()  # Forzar repintado para dibujar la flecha
        
        if play_sound and self.play_sound:
            play_bubble_sound()

        if duration:
            self.hide_timer.start(duration)

    def format_text(self, text):
        """Formatea el texto para mejor presentación con estilo tecnológico"""
        import re
        
        # Limpiar espacios extras
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        # Añadir emojis de terminal para dar estilo
        lines = text.split('\n')
        formatted_lines = []
        
        for i, line in enumerate(lines):
            if len(line) > 65:  # Límite un poco mayor para mejor legibilidad
                words = line.split(' ')
                current_line = ""
                for word in words:
                    if len(current_line) + len(word) + 1 <= 65:
                        current_line += " " + word if current_line else word
                    else:
                        formatted_lines.append(current_line)
                        current_line = word
                if current_line:
                    formatted_lines.append(current_line)
            else:
                # Añadir estilo de terminal a algunas líneas
                if i == 0 and any(keyword in text.lower() for keyword in ['proceso', 'memoria', 'cpu', 'disco', 'sistema', 'red']):
                    formatted_lines.append(f"⚡ {line}")
                elif "error" in line.lower() or "no se pudo" in line.lower():
                    formatted_lines.append(f"⚠️  {line}")
                elif "éxito" in line.lower() or "correcto" in line.lower():
                    formatted_lines.append(f"✅  {line}")
                else:
                    formatted_lines.append(line)
        
        return '\n'.join(formatted_lines)

    def position_close_button(self):
        """Posiciona el botón de cerrar en la esquina superior derecha"""
        self.close_button.move(
            self.width() - self.close_button_size - self.close_button_margin,
            self.close_button_margin + 5  # Un poco más abajo para no tocar el borde
        )

    def close_bubble(self, event=None):
        """Cierra la burbuja manualmente"""
        self.hide()
        self.hide_timer.stop()
        if self.tux_assistant:
            self.tux_assistant.bubble_closed_by_user = True

    def position_above_tux(self):
        """Posiciona la burbuja SIEMPRE encima del asistente Tux en su pantalla actual"""
        if not self.tux_assistant:
            screen = self.current_screen or QApplication.primaryScreen()
            screen_geometry = screen.availableGeometry()
            self.move(screen_geometry.width() - self.width() - 50, 50)
            return
        
        try:
            screen = self.current_screen or self.get_tux_screen()
            screen_geometry = screen.availableGeometry()
            
            tux_global_pos = self.tux_assistant.mapToGlobal(QPoint(0, 0))
            tux_x = tux_global_pos.x()
            tux_y = tux_global_pos.y()
            tux_width = self.tux_assistant.width()
            tux_height = self.tux_assistant.height()
            
            # Calcular el centro del Tux
            tux_center_x = tux_x + tux_width // 2
            
            screen_tux_x = tux_x - screen_geometry.x()
            screen_tux_y = tux_y - screen_geometry.y()
            
            # Calcular posición centrada horizontalmente
            bubble_x = screen_tux_x + (tux_width // 2) - (self.width() // 2)
            
            # Intentar poner encima del Tux primero
            bubble_y = screen_tux_y - self.height() - 5  # 5px de espacio (sin flecha)
            self.arrow_position = "bottom"  # Flecha apunta hacia abajo (hacia el Tux)
            
            absolute_x = screen_geometry.x() + bubble_x
            absolute_y = screen_geometry.y() + bubble_y
            
            # Guardar la posición X original antes de ajustar
            original_absolute_x = absolute_x
            
            # ✅ VERIFICAR SI HAY ESPACIO SUFICIENTE ARRIBA
            space_above = screen_tux_y - self.height()
            if space_above < 20:  # Menos de 20px de espacio arriba
                # No hay espacio suficiente arriba, mostrar debajo del Tux
                absolute_y = screen_geometry.y() + screen_tux_y + tux_height + 5
                self.arrow_position = "top"  # Flecha apunta hacia arriba (hacia el Tux)
            
            # ✅ AJUSTAR POSICIÓN HORIZONTAL PARA NO SALIRSE DE LA PANTALLA
            margin = 30  # Margen mínimo desde los bordes
            
            # Ajustar posición izquierda
            left_adjustment = 0
            if absolute_x < screen_geometry.x() + margin:
                left_adjustment = (screen_geometry.x() + margin) - absolute_x
                absolute_x = screen_geometry.x() + margin
            
            # Ajustar posición derecha
            elif absolute_x + self.width() > screen_geometry.x() + screen_geometry.width() - margin:
                right_adjustment = absolute_x + self.width() - (screen_geometry.x() + screen_geometry.width() - margin)
                absolute_x = screen_geometry.x() + screen_geometry.width() - self.width() - margin
            
            # ✅ Asegurar que la burbuja no sea más ancha que la pantalla
            max_width = screen_geometry.width() - 2 * margin
            if self.width() > max_width:
                self.setFixedWidth(max_width)
                self.adjustSize()
                # Recalcular posición centrada
                bubble_x = screen_tux_x + (tux_width // 2) - (self.width() // 2)
                absolute_x = screen_geometry.x() + bubble_x
                # Ajustar nuevamente si se sale
                if absolute_x < screen_geometry.x() + margin:
                    absolute_x = screen_geometry.x() + margin
            
            # ✅ CALCULAR LA POSICIÓN DE LA FLECHA PARA APUNTAR AL TUX
            # Si la burbuja se movió para ajustarse a los bordes, la flecha debe ajustarse
            bubble_center_x = absolute_x + self.width() // 2
            tux_center_global_x = tux_x + tux_width // 2
            
            # Calcular dónde debería estar la flecha para apuntar al Tux
            # En coordenadas relativas a la burbuja
            self.arrow_position_x = tux_center_global_x - absolute_x
            
            # Limitar la flecha para que no se salga de los bordes de la burbuja
            min_arrow_x = self.arrow_width + 10
            max_arrow_x = self.width() - self.arrow_width - 10
            self.arrow_position_x = max(min_arrow_x, min(self.arrow_position_x, max_arrow_x))
            
            self.move(int(absolute_x), int(absolute_y))
            self.position_close_button()
            
            # Forzar redibujado de la flecha
            self.update()
            
        except Exception as e:
            screen = self.current_screen or QApplication.primaryScreen()
            screen_geometry = screen.availableGeometry()
            self.move(screen_geometry.width() - self.width() - 50, 50)

    def resizeEvent(self, event):
        """Reajusta la posición al cambiar tamaño"""
        super().resizeEvent(event)
        if self.isVisible():
            self.position_above_tux()
            self.position_close_button()

    def mousePressEvent(self, event):
        """Permite cerrar la burbuja haciendo clic en cualquier parte"""
        if event.button() == Qt.LeftButton:
            if not self.close_button.geometry().contains(event.pos()):
                self.close_bubble()
        
        super().mousePressEvent(event)


class ChatWindow(QWidget):
    def __init__(self, tux_assistant):
        super().__init__()
        self.tux_assistant = tux_assistant
        self.current_screen = None
        self.init_ui()
        self.setup_animations()
        
        # Timer para verificar cambios de pantalla
        self.screen_check_timer = QTimer()
        self.screen_check_timer.timeout.connect(self.update_screen_if_needed)
        self.screen_check_timer.start(100)
        
    def init_ui(self):
        """Inicializa la interfaz de usuario del chat"""
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Configurar tamaño y posición
        self.setFixedSize(400, 500)
        
        # Crear widget principal con layout
        main_widget = QWidget()
        main_widget.setObjectName("mainWidget")
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        # Título del chat
        title_label = QLabel("🐧💬 Chat con Tux")
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignCenter)
        
        # Botón para cerrar
        close_button = QPushButton("✕")
        close_button.setObjectName("closeButton")
        close_button.setFixedSize(30, 30)
        close_button.clicked.connect(self.hide)
        
        # Layout del título
        title_layout = QHBoxLayout()
        title_layout.addStretch()
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(close_button)
        
        # Área de chat (scrollable)
        self.chat_area = QScrollArea()
        self.chat_area.setWidgetResizable(True)
        self.chat_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setSpacing(8)
        self.chat_layout.setContentsMargins(5, 5, 5, 5)
        self.chat_layout.addStretch()
        
        self.chat_area.setWidget(self.chat_container)
        
        # Área de entrada
        input_widget = QWidget()
        input_widget.setObjectName("inputWidget")
        input_layout = QHBoxLayout(input_widget)
        input_layout.setContentsMargins(5, 5, 5, 5)
        
        self.input_field = QLineEdit()
        self.input_field.setObjectName("inputField")
        self.input_field.setPlaceholderText("Escribe tu pregunta aquí...")
        self.input_field.returnPressed.connect(self.send_message)
        
        send_button = QPushButton("➤")
        send_button.setObjectName("sendButton")
        send_button.setFixedSize(40, 35)
        send_button.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(send_button)
        
        # Agregar todos los widgets al layout principal
        main_layout.addLayout(title_layout)
        main_layout.addWidget(self.chat_area)
        main_layout.addWidget(input_widget)
        
        # Configurar el layout principal en el widget ChatWindow
        layout = QVBoxLayout(self)
        layout.addWidget(main_widget)
        
        # Aplicar estilos
        self.apply_styles()
        
        # Historial de mensajes
        self.message_history = []
    
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
    
    def position_near_tux(self):
        """Posiciona la ventana de chat arriba o abajo del Tux"""
        if not self.tux_assistant:
            return
        
        try:
            screen = self.current_screen or self.get_tux_screen()
            screen_geometry = screen.availableGeometry()
            
            tux_global_pos = self.tux_assistant.mapToGlobal(QPoint(0, 0))
            tux_x = tux_global_pos.x()
            tux_y = tux_global_pos.y()
            tux_width = self.tux_assistant.width()
            tux_height = self.tux_assistant.height()
            
            # Calcular posición centrada horizontalmente
            chat_x = tux_x + (tux_width // 2) - (self.width() // 2)
            
            # Primero intentar posicionar ARRIBA del Tux
            chat_y = tux_y - self.height() - 10  # 10px de espacio
            
            # Verificar si hay espacio suficiente arriba
            space_above = tux_y - screen_geometry.y()
            if space_above < self.height() + 20:  # Menos de espacio necesario arriba
                # No hay espacio arriba, posicionar ABAJO del Tux
                chat_y = tux_y + tux_height + 10
            
            # Ajustar horizontalmente para no salirse de la pantalla
            margin = 20  # Margen mínimo desde los bordes
            
            if chat_x < screen_geometry.x() + margin:
                chat_x = screen_geometry.x() + margin
            elif chat_x + self.width() > screen_geometry.x() + screen_geometry.width() - margin:
                chat_x = screen_geometry.x() + screen_geometry.width() - self.width() - margin
            
            # Asegurar que no se salga verticalmente
            if chat_y < screen_geometry.y() + margin:
                chat_y = screen_geometry.y() + margin
            elif chat_y + self.height() > screen_geometry.y() + screen_geometry.height() - margin:
                chat_y = screen_geometry.y() + screen_geometry.height() - self.height() - margin
            
            # Si la burbuja está visible, verificar que no se superpongan
            if self.tux_assistant.bubble and self.tux_assistant.bubble.isVisible():
                bubble_pos = self.tux_assistant.bubble.pos()
                bubble_size = self.tux_assistant.bubble.size()
                
                # Crear rectángulos para verificar colisión
                chat_rect = QRect(chat_x, chat_y, self.width(), self.height())
                bubble_rect = QRect(bubble_pos.x(), bubble_pos.y(), 
                                  bubble_size.width(), bubble_size.height())
                
                # Si se superponen, mover el chat a la posición opuesta
                if chat_rect.intersects(bubble_rect):
                    if chat_y < tux_y:  # Si el chat estaba arriba
                        # Mover abajo
                        chat_y = tux_y + tux_height + 10
                    else:  # Si el chat estaba abajo
                        # Mover arriba si hay espacio
                        if space_above >= self.height() + 20:
                            chat_y = tux_y - self.height() - 10
            
            self.move(int(chat_x), int(chat_y))
            
        except Exception as e:
            # En caso de error, posicionar en la esquina
            screen = QGuiApplication.primaryScreen().availableGeometry()
            self.move(screen.width() - self.width() - 50, 50)


    def position_near_tux_smooth(self):
        """Posiciona la ventana de chat cerca del Tux con animación suave"""
        if not self.tux_assistant:
            return
        
        try:
            screen = self.current_screen or self.get_tux_screen()
            screen_geometry = screen.availableGeometry()
            
            tux_global_pos = self.tux_assistant.mapToGlobal(QPoint(0, 0))
            tux_x = tux_global_pos.x()
            tux_y = tux_global_pos.y()
            tux_width = self.tux_assistant.width()
            tux_height = self.tux_assistant.height()
            
            # Calcular posición centrada horizontalmente
            target_x = tux_x + (tux_width // 2) - (self.width() // 2)
            
            # Primero intentar posicionar ARRIBA del Tux
            target_y = tux_y - self.height() - 10  # 10px de espacio
            
            # Verificar si hay espacio suficiente arriba
            space_above = tux_y - screen_geometry.y()
            if space_above < self.height() + 20:  # Menos de espacio necesario arriba
                # No hay espacio arriba, posicionar ABAJO del Tux
                target_y = tux_y + tux_height + 10
            
            # Ajustar horizontalmente para no salirse de la pantalla
            margin = 20  # Margen mínimo desde los bordes
            
            if target_x < screen_geometry.x() + margin:
                target_x = screen_geometry.x() + margin
            elif target_x + self.width() > screen_geometry.x() + screen_geometry.width() - margin:
                target_x = screen_geometry.x() + screen_geometry.width() - self.width() - margin
            
            # Asegurar que no se salga verticalmente
            if target_y < screen_geometry.y() + margin:
                target_y = screen_geometry.y() + margin
            elif target_y + self.height() > screen_geometry.y() + screen_geometry.height() - margin:
                target_y = screen_geometry.y() + screen_geometry.height() - self.height() - margin
            
            # Si la burbuja está visible, verificar que no se superpongan
            if self.tux_assistant.bubble and self.tux_assistant.bubble.isVisible():
                bubble_pos = self.tux_assistant.bubble.pos()
                bubble_size = self.tux_assistant.bubble.size()
                
                # Crear rectángulos para verificar colisión
                chat_rect = QRect(target_x, target_y, self.width(), self.height())
                bubble_rect = QRect(bubble_pos.x(), bubble_pos.y(), 
                                  bubble_size.width(), bubble_size.height())
                
                # Si se superponen, mover el chat a la posición opuesta
                if chat_rect.intersects(bubble_rect):
                    if target_y < tux_y:  # Si el chat estaba arriba
                        # Mover abajo
                        target_y = tux_y + tux_height + 10
                    else:  # Si el chat estaba abajo
                        # Mover arriba si hay espacio
                        if space_above >= self.height() + 20:
                            target_y = tux_y - self.height() - 10
            
            # Crear animación para movimiento suave
            animation = QPropertyAnimation(self, b"pos")
            animation.setDuration(200)
            animation.setStartValue(self.pos())
            animation.setEndValue(QPoint(int(target_x), int(target_y)))
            animation.setEasingCurve(QEasingCurve.OutCubic)
            animation.start()
            
        except Exception as e:
            # En caso de error, posicionar sin animación
            self.position_near_tux()

    def position_above_tux(self):
        """Posiciona el chat arriba del Tux"""
        if not self.tux_assistant:
            return
        
        try:
            screen = self.current_screen or self.get_tux_screen()
            screen_geometry = screen.availableGeometry()
            
            tux_global_pos = self.tux_assistant.mapToGlobal(QPoint(0, 0))
            tux_x = tux_global_pos.x()
            tux_y = tux_global_pos.y()
            tux_width = self.tux_assistant.width()
            
            # Calcular posición centrada horizontalmente
            chat_x = tux_x + (tux_width // 2) - (self.width() // 2)
            chat_y = tux_y - self.height() - 10  # 10px de espacio
            
            # Ajustar para no salirse de la pantalla
            margin = 20
            if chat_x < screen_geometry.x() + margin:
                chat_x = screen_geometry.x() + margin
            elif chat_x + self.width() > screen_geometry.x() + screen_geometry.width() - margin:
                chat_x = screen_geometry.x() + screen_geometry.width() - self.width() - margin
            
            if chat_y < screen_geometry.y() + margin:
                chat_y = screen_geometry.y() + margin
            
            self.move(int(chat_x), int(chat_y))
            
        except Exception as e:
            screen = QGuiApplication.primaryScreen().availableGeometry()
            self.move(screen.width() - self.width() - 50, 50)

    def position_below_tux(self):
        """Posiciona el chat abajo del Tux"""
        if not self.tux_assistant:
            return
        
        try:
            screen = self.current_screen or self.get_tux_screen()
            screen_geometry = screen.availableGeometry()
            
            tux_global_pos = self.tux_assistant.mapToGlobal(QPoint(0, 0))
            tux_x = tux_global_pos.x()
            tux_y = tux_global_pos.y()
            tux_width = self.tux_assistant.width()
            tux_height = self.tux_assistant.height()
            
            # Calcular posición centrada horizontalmente
            chat_x = tux_x + (tux_width // 2) - (self.width() // 2)
            chat_y = tux_y + tux_height + 10  # 10px de espacio
            
            # Ajustar para no salirse de la pantalla
            margin = 20
            if chat_x < screen_geometry.x() + margin:
                chat_x = screen_geometry.x() + margin
            elif chat_x + self.width() > screen_geometry.x() + screen_geometry.width() - margin:
                chat_x = screen_geometry.x() + screen_geometry.width() - self.width() - margin
            
            if chat_y + self.height() > screen_geometry.y() + screen_geometry.height() - margin:
                chat_y = screen_geometry.y() + screen_geometry.height() - self.height() - margin
            
            self.move(int(chat_x), int(chat_y))
            
        except Exception as e:
            screen = QGuiApplication.primaryScreen().availableGeometry()
            self.move(screen.width() - self.width() - 50, screen.height() - self.height() - 50)
 
 
    def apply_styles(self):
        """Aplica estilos CSS a la ventana de chat"""
        self.setStyleSheet("""
            QWidget {
                background-color: transparent;
            }
            
            #mainWidget {
                background-color: rgba(10, 10, 15, 0.95);
                border: 2px solid #FF6C2C;
                border-radius: 15px;
            }
            
            #titleLabel {
                color: #FF6C2C;
                font-size: 16pt;
                font-weight: bold;
                font-family: 'Segoe UI', 'Arial', 'Ubuntu Mono';
                padding: 10px;
            }
            
            #closeButton {
                background-color: #FF6C2C;
                border: 2px solid #FF8C4C;
                border-radius: 15px;
                color: #0A0A0F;
                font-weight: bold;
                font-size: 12pt;
            }
            
            #closeButton:hover {
                background-color: #FF8C4C;
                border: 2px solid #FFAD6C;
            }
            
            #closeButton:pressed {
                background-color: #FF4C0C;
            }
            
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            
            QScrollBar:vertical {
                background: #1A1A2E;
                width: 10px;
                border-radius: 5px;
            }
            
            QScrollBar::handle:vertical {
                background: #FF6C2C;
                border-radius: 5px;
                min-height: 20px;
            }
            
            QScrollBar::handle:vertical:hover {
                background: #FF8C4C;
            }
            
            #inputWidget {
                background-color: rgba(26, 26, 46, 0.8);
                border: 1px solid #FF6C2C;
                border-radius: 10px;
                padding: 5px;
            }
            
            #inputField {
                background-color: transparent;
                border: none;
                color: #FFFFFF;
                font-size: 11pt;
                font-family: 'Segoe UI', 'Arial', 'Ubuntu Mono';
                padding: 8px;
                selection-background-color: #FF6C2C;
            }
            
            #inputField:focus {
                outline: none;
            }
            
            #sendButton {
                background-color: #FF6C2C;
                border: 2px solid #FF8C4C;
                border-radius: 10px;
                color: #0A0A0F;
                font-weight: bold;
                font-size: 12pt;
            }
            
            #sendButton:hover {
                background-color: #FF8C4C;
                border: 2px solid #FFAD6C;
            }
            
            #sendButton:pressed {
                background-color: #FF4C0C;
            }
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
        """Muestra la ventana de chat con animación"""
        self.current_screen = self.get_tux_screen()
        
        # Primero posicionar sin mostrar
        self.position_near_tux()
        
        # Asegurarse de que no esté superpuesto con la burbuja
        if self.tux_assistant.bubble and self.tux_assistant.bubble.isVisible():
            # Si hay burbuja visible, intentar posicionar en el lado opuesto
            bubble_pos = self.tux_assistant.bubble.pos()
            tux_global_pos = self.tux_assistant.mapToGlobal(QPoint(0, 0))
            
            # Determinar dónde está la burbuja (arriba o abajo del Tux)
            if bubble_pos.y() < tux_global_pos.y():
                # Burbuja arriba, poner chat abajo
                self.position_below_tux()
            else:
                # Burbuja abajo, poner chat arriba
                self.position_above_tux()
        
        self.show()
        self.show_animation.start()
        self.input_field.setFocus()
        
    def hide_completely(self):
        """Oculta completamente la ventana después de la animación"""
        super().hide()
        
    def add_message(self, text, is_user=True):
        """Añade un mensaje al chat"""
        message_widget = QWidget()
        message_widget.setObjectName("userMessage" if is_user else "tuxMessage")
        
        message_layout = QHBoxLayout(message_widget)
        message_layout.setContentsMargins(10, 8, 10, 8)
        
        message_label = QLabel(text)
        message_label.setObjectName("messageText")
        message_label.setWordWrap(True)
        message_label.setMaximumWidth(300)
        message_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        
        if is_user:
            message_label.setStyleSheet("""
                #messageText {
                    background-color: #FF6C2C;
                    color: #0A0A0F;
                    border-radius: 15px;
                    padding: 12px;
                    font-family: 'Segoe UI', 'Arial';
                    font-size: 11pt;
                    font-weight: 500;
                }
            """)
            message_layout.addStretch()
            message_layout.addWidget(message_label)
        else:
            message_label.setStyleSheet("""
                #messageText {
                    background-color: rgba(255, 108, 44, 0.2);
                    color: #FFFFFF;
                    border: 1px solid #FF6C2C;
                    border-radius: 15px;
                    padding: 12px;
                    font-family: 'Segoe UI', 'Arial';
                    font-size: 11pt;
                    font-weight: 500;
                }
            """)
            message_layout.addWidget(message_label)
            message_layout.addStretch()
        
        # Insertar al principio (arriba del stretch)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, message_widget)
        
        # Guardar en historial
        self.message_history.append({
            'text': text,
            'is_user': is_user,
            'time': time.time()
        })
        
        # Scroll al final
        QTimer.singleShot(50, self.scroll_to_bottom)
        
    def scroll_to_bottom(self):
        """Desplaza el chat hasta el final"""
        scrollbar = self.chat_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def send_message(self):
        """Envía el mensaje del usuario"""
        text = self.input_field.text().strip()
        if text:
            # Añadir mensaje del usuario
            self.add_message(text, is_user=True)
            
            # Limpiar campo de entrada
            self.input_field.clear()
            
            # Ocultar ventana de chat
            self.hide_animation.start()
            
            # Procesar la pregunta a través del Tux
            self.process_user_question(text)
            
    def process_user_question(self, text):
        """Procesa la pregunta del usuario usando el Tux"""
        # Mostrar animación de pensamiento en el Tux
        self.tux_assistant.start_thinking_animation()
        self.tux_assistant.thinking.start()
        
        # Verificar si es pregunta del sistema
        system_keywords = ['proceso', 'memoria', 'cpu', 'disco', 'almacenamiento', 
                          'sistema', 'consumiendo', 'ram', 'red', 'redes']
        is_system_question = any(keyword in text.lower() for keyword in system_keywords)
        
        if is_system_question:
            detailed_answer = get_detailed_system_answer(text)
            if detailed_answer:
                self.tux_assistant.thinking.stop()
                self.tux_assistant.stop_thinking_animation()
                self.tux_assistant.say(detailed_answer, play_sound=True)
                # También añadir al chat
                self.add_message(detailed_answer, is_user=False)
                return
        
        # Usar IA para otras preguntas
        if self.tux_assistant.ai_worker and self.tux_assistant.ai_worker.isRunning():
            self.tux_assistant.ai_worker.stop()
            self.tux_assistant.ai_worker.wait(1000)
        
        self.tux_assistant.ai_worker = AIWorker(text, include_system_info=True)
        self.tux_assistant.ai_worker.finished.connect(self.on_ai_response)
        self.tux_assistant.ai_worker.error.connect(self.on_ai_error)
        self.tux_assistant.ai_worker.start()
        
    def on_ai_response(self, answer):
        """Maneja la respuesta de la IA"""
        self.tux_assistant.thinking.stop()
        self.tux_assistant.stop_thinking_animation()
        
        # Mostrar en burbuja
        self.tux_assistant.say(answer, play_sound=True)
        
        # Añadir al chat
        self.add_message(answer, is_user=False)
        
        # Limpiar worker
        if self.tux_assistant.ai_worker:
            try:
                self.tux_assistant.ai_worker.finished.disconnect()
                self.tux_assistant.ai_worker.error.disconnect()
            except:
                pass
            self.tux_assistant.ai_worker = None
            
    def on_ai_error(self, error_msg):
        """Maneja errores de la IA"""
        self.tux_assistant.thinking.stop()
        self.tux_assistant.stop_thinking_animation()
        
        # Mostrar error en burbuja
        self.tux_assistant.say(error_msg, play_sound=True)
        
        # Añadir al chat
        self.add_message(error_msg, is_user=False)
        
        # Limpiar worker
        if self.tux_assistant.ai_worker:
            try:
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

    def start(self):
        self.active = True
        self.step = 0
        self.timer.start(500)

    def stop(self):
        self.active = False
        self.timer.stop()

    def animate(self):
        if not self.active:
            return
        dots = "." * ((self.step % 3) + 1)
        self.bubble.show_text(f"{dots}", play_sound=False)
        self.step += 1

class AIWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, prompt, include_system_info=True):
        super().__init__()
        self.prompt = prompt
        self.include_system_info = include_system_info
        self.is_running = True
        
    def run(self):
        try:
            system_context = ""
            if self.include_system_info:
                try:
                    system_info = get_system_info()
                    system_context = format_system_info_for_prompt(system_info)
                except Exception as e:
                    system_context = "[Información del sistema no disponible]"
            
            full_prompt = f"{TUX_SYSTEM_PROMPT}\n\n"
            
            if system_context:
                full_prompt += f"INFORMACIÓN ACTUAL DEL SISTEMA:\n{system_context}\n\n"
            
            full_prompt += f"Usuario: {self.prompt}\nTux:"
            
            session = requests.Session()
            session.timeout = (5, 30)
            
            response = session.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "prompt": full_prompt,
                    "stream": False
                }
            )
            
            if not self.is_running:
                return
                
            data = response.json()
            text = data.get("response", "").strip()
            
            if not text:
                self.finished.emit("🤔 Mmm… no supe qué decir.\nIntenta preguntarme de otra forma.")
            else:
                self.finished.emit(text)
                
        except requests.exceptions.Timeout:
            if self.is_running:
                self.error.emit("⏳ La respuesta tardó demasiado.\nIntenta con una pregunta más corta.")
        except Exception as e:
            if self.is_running:
                self.error.emit("No puedo conectarme con Ollama 😢")
    
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
        
        elif "sistema" in question_type.lower() or "información" in question_type.lower():
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
                    public_ip = urllib.request.urlopen('https://api.ipify.org').read().decode('utf8')
                    respuesta += f"• IP Pública: {public_ip}\n"
                except:
                    respuesta += "• IP Pública: No se pudo obtener\n"

                return respuesta
        
        return ""
        
    except Exception as e:
        return ""

class TuxAssistant(QLabel):
    def __init__(self):
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
        self.inactivity_timer.start(10000)
        
        self.movie = self.animations.get('sentado', self.create_default_animation())
        self.movie.setScaledSize(self.tux_size)
        self.movie.start()
        self.setMovie(self.movie)

        self.bubble = Bubble(play_sound=True)
        self.bubble.set_tux_assistant(self)
        self.thinking = ThinkingIndicator(self)

        # Inicializar ventana de chat
        self.chat_window = ChatWindow(self)
        
        self.drag_offset = None
        self.initial_press_pos = None
        self.ai_worker = None

        self.bubble_closed_by_user = False

        self.position_at_bottom_right()
        self.show()

        QTimer.singleShot(
            800,
            lambda: self.say("Hola, soy Tux 🐧\nPregúntame lo que quieras", play_sound=True)
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
    
    def start_thinking_animation(self):
        """Inicia animación de búsqueda"""
        self.is_thinking = True
        
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
        if current_time - self.last_mouse_move_time > 0.3:
            self.walking_timer.stop()
            self.stop_walking_animation()
    
    def check_inactivity(self):
        """Verifica inactividad con estados más controlados"""
        if self.is_thinking or self.is_moving or self.is_dragging:
            return
            
        current_time = time.time()
        inactive_time = current_time - self.last_activity_time
        
        relaxed_animations = ['relajado', 'relajado2', 'relajado3', 'relajado4', 'relajado5']
        
        if inactive_time < 60:
            if self.inactivity_state != 'active':
                self.inactivity_state = 'active'
                self.idle_start_time = None
                self.relaxed_start_time = None
                if self.current_animation != 'sentado':
                    self.set_animation('sentado')
        
        elif 60 <= inactive_time < 120:
            if self.inactivity_state != 'idle':
                self.inactivity_state = 'idle'
                self.idle_start_time = current_time
                self.relaxed_start_time = None
                if self.current_animation != 'sentado':
                    self.set_animation('sentado')
        
        elif inactive_time >= 300:
            if self.inactivity_state != 'relaxed':
                self.inactivity_state = 'relaxed'
                self.relaxed_start_time = current_time
                
                import random
                self.current_relaxed_animation = random.choice(relaxed_animations)
                self.set_animation(self.current_relaxed_animation)
            
            elif current_time - self.relaxed_start_time > 150:
                self.relaxed_start_time = current_time
                
                available_animations = [anim for anim in relaxed_animations 
                                      if anim != self.current_relaxed_animation]
                
                if available_animations:
                    import random
                    self.current_relaxed_animation = random.choice(available_animations)
                    self.set_animation(self.current_relaxed_animation)
                else:
                    import random
                    self.current_relaxed_animation = random.choice(relaxed_animations)
                    self.set_animation(self.current_relaxed_animation)
    
    def update_activity_time(self):
        """Actualiza el tiempo de última actividad"""
        self.last_activity_time = time.time()
        
        if self.inactivity_state == 'relaxed':
            self.inactivity_state = 'active'
            self.relaxed_start_time = None
            if not self.is_thinking and not self.is_moving:
                self.set_animation('sentado')

    def cleanup_threads(self):
        """Limpiar hilos antes de cerrar"""
        if self.ai_worker and self.ai_worker.isRunning():
            self.ai_worker.stop()
        
        self.inactivity_timer.stop()
        self.walking_timer.stop()
        
        try:
            mixer.stop()
        except:
            pass

    def say(self, text, play_sound=True):
        """Muestra un mensaje en la burbuja"""
        if self.bubble_closed_by_user and not play_sound:
            self.bubble_closed_by_user = False
            return
            
        base_time = 6000
        extra_time = len(text) * 80
        total_time = min(base_time + extra_time, 60000)

        self.bubble.show_text(text, total_time, play_sound=play_sound)
        self.update_bubble_position()
        
        self.update_activity_time()
        
        self.bubble_closed_by_user = False

    def update_bubble_position(self):
        """Actualiza la posición de la burbuja"""
        if self.bubble and self.bubble.isVisible():
            self.bubble.position_above_tux()

    def moveEvent(self, event):
        """Se ejecuta cuando el Tux se mueve"""
        super().moveEvent(event)
        
        # Actualizar posición de la burbuja
        if self.bubble and self.bubble.isVisible():
            QTimer.singleShot(20, self.update_bubble_position)
        
        # Actualizar posición del chat
        if self.chat_window and self.chat_window.isVisible():
            QTimer.singleShot(20, self.update_chat_position)

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
            self.cleanup_threads()
            QTimer.singleShot(100, lambda: QApplication.quit())
        
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
                self.move(new_pos)
                
                # Actualizar posiciones de burbuja y chat inmediatamente
                if self.bubble and self.bubble.isVisible():
                    self.bubble.position_above_tux()
                
                if self.chat_window and self.chat_window.isVisible():
                    self.chat_window.position_near_tux_smooth()  # Usar versión suave
                
                self.last_mouse_move_time = time.time()
        
        self.update_activity_time()

    def mouseReleaseEvent(self, event):
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
        """Muestra la ventana de chat al hacer doble clic"""
        if event.button() == Qt.LeftButton:
            self.chat_window.show_chat()
        
        self.update_activity_time()

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

def close_app(sig=None, frame=None):
    app = QApplication.instance()
    if app:
        for widget in app.topLevelWidgets():
            if isinstance(widget, TuxAssistant):
                widget.cleanup_threads()
        time.sleep(0.5)
        app.quit()

signal.signal(signal.SIGINT, close_app)
signal.signal(signal.SIGTERM, close_app)

if __name__ == "__main__":
    ollama_process = None
    try:
        audio_initialized = init_audio()
        ollama_process = start_ollama()
        
        app = QApplication(sys.argv)
        tux = TuxAssistant()
        
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