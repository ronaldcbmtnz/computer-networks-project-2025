import sys
import os
import threading
import time
import socket
import struct
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem,
                             QTextEdit, QLineEdit, QFileDialog, QSplashScreen, 
                             QProgressBar, QMessageBox, QComboBox, QDialog)
from PyQt5.QtGui import QPixmap, QFont, QIcon, QColor, QPainter, QLinearGradient, QBrush, QPen, QFontDatabase
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSize, QRect, QPropertyAnimation, QEasingCurve, pyqtProperty

# Importamos los módulos del proyecto original
from config import *
from utils import obtener_direccion_mac, mac_bits_cadena, mac_cadena_bits
from network_threads import receive_thread, discovery_thread, file_sender_thread

class InterfaceSelectionDialog(QDialog):
    """Diálogo para seleccionar la interfaz de red"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar Interfaz de Red")
        self.setMinimumWidth(400)
        
        # Estilo oscuro
        self.setStyleSheet("""
            QDialog {
                background-color: #121212;
                color: #e0e0e0;
            }
            QLabel {
                color: #e0e0e0;
            }
            QComboBox {
                background-color: #1e1e1e;
                color: #e0e0e0;
                border: 1px solid #3d3d3d;
                padding: 5px;
                border-radius: 3px;
            }
            QComboBox::drop-down {
                border: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: #1e1e1e;
                color: #e0e0e0;
                selection-background-color: #2979ff;
            }
            QPushButton {
                background-color: #2979ff;
                color: white;
                border-radius: 4px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #448aff;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # Obtener interfaces disponibles
        self.interfaces = [iface[1] for iface in socket.if_nameindex()]
        
        # Mensaje explicativo
        label = QLabel("Selecciona la interfaz de red para comunicación:")
        label.setFont(QFont("Arial", 10))
        layout.addWidget(label)
        
        # Lista desplegable de interfaces
        self.combo = QComboBox()
        self.combo.addItems(self.interfaces)
        layout.addWidget(self.combo)
        
        # Botón de confirmación
        btn = QPushButton("Seleccionar")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)
    
    def get_selected_interface(self):
        """Devuelve la interfaz seleccionada"""
        return self.combo.currentText()

class AnimatedSplashScreen(QSplashScreen):
    def __init__(self):
        pixmap = QPixmap(800, 500)
        super().__init__(pixmap)
        
        # Crear un fondo degradado oscuro
        self.background = QLinearGradient(0, 0, 0, 500)
        self.background.setColorAt(0, QColor(25, 25, 35))
        self.background.setColorAt(1, QColor(10, 10, 15))
        
        # Configuración del título
        self.title = "MATCOMSHAP"
        self.subtitle = "Mensajería a Nivel de Enlace"
        self.font_size = 20
        self.opacity = 0
        
        # Configuración para animación
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.animation_step = 0
        self.max_steps = 100
        
        # Iniciar animación
        self.timer.start(30)
    
    def update_animation(self):
        """Actualiza la animación del splash"""
        self.animation_step += 1
        
        if self.animation_step < 30:
            # Fase 1: Aparecer título
            self.opacity = self.animation_step / 30
            self.font_size = 20 + (60 * self.opacity)
        elif self.animation_step < 60:
            # Fase 2: Mantener título
            self.opacity = 1.0
            self.font_size = 80
        elif self.animation_step < 90:
            # Fase 3: Aparecer subtítulo
            self.opacity = 1.0
            self.font_size = 80
        elif self.animation_step >= self.max_steps:
            # Detener la animación
            self.timer.stop()
            return
        
        # Actualizar la pantalla
        self.repaint()
    
    def drawContents(self, painter):
        """Dibuja el contenido del splash screen"""
        # Dibujar fondo
        painter.fillRect(self.rect(), QBrush(self.background))
        
        # Dibujar título con efecto de brillo
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Efecto de sombra para el título
        shadow_font = QFont("Impact", int(self.font_size))
        painter.setFont(shadow_font)
        painter.setPen(QPen(QColor(0, 0, 0, 180)))
        painter.drawText(QRect(5, 5, self.width(), int(self.height()/2)), 
                         Qt.AlignCenter, self.title)
        
        # Título principal
        glow_color = QColor(41, 121, 255)
        title_font = QFont("Impact", int(self.font_size))
        painter.setFont(title_font)
        painter.setPen(QPen(glow_color))
        painter.drawText(QRect(0, 0, self.width(), int(self.height()/2)), 
                         Qt.AlignCenter, self.title)
        
        # Subtítulo
        if self.animation_step >= 60:
            subtitle_opacity = min(1.0, (self.animation_step - 60) / 20)
            subtitle_font = QFont("Arial", 16)
            subtitle_font.setBold(True)
            painter.setFont(subtitle_font)
            
            subtitle_color = QColor(200, 200, 200, int(255 * subtitle_opacity))
            painter.setPen(QPen(subtitle_color))
            painter.drawText(QRect(0, int(self.height()/2), self.width(), 50), 
                             Qt.AlignCenter, self.subtitle)
        
        # Barra de progreso
        if self.animation_step >= 30:
            progress = min(100, (self.animation_step - 30) * 100 / (self.max_steps - 30))
            
            # Fondo de la barra
            bar_rect = QRect(int(self.width()/4), self.height() - 100, 
                            int(self.width()/2), 20)
            painter.fillRect(bar_rect, QColor(30, 30, 30))
            
            # Barra de progreso
            progress_width = int((self.width()/2) * (progress/100))
            progress_rect = QRect(int(self.width()/4), self.height() - 100, 
                                progress_width, 20)
            progress_gradient = QLinearGradient(0, 0, progress_width, 0)
            progress_gradient.setColorAt(0, QColor(41, 121, 255))
            progress_gradient.setColorAt(1, QColor(66, 165, 245))
            painter.fillRect(progress_rect, progress_gradient)
            
            # Texto de progreso
            painter.setPen(QPen(QColor(200, 200, 200)))
            painter.setFont(QFont("Arial", 10))
            painter.drawText(bar_rect, Qt.AlignCenter, f"{int(progress)}%")

class ChatApp(QMainWindow):
    # Señales para actualizar la interfaz desde hilos
    message_received = pyqtSignal(str, str)  # (remitente, mensaje)
    user_discovered = pyqtSignal(bytes, str)  # (mac_bytes, mac_str)
    file_progress = pyqtSignal(str, int)  # (archivo, porcentaje)
    file_request_received = pyqtSignal(bytes, str, str, int)  # (mac_bytes, mac_str, filename, filesize)
    
    def __init__(self):
        super().__init__()
        
        # Configuración de la ventana principal
        self.setWindowTitle("LinkChat - Mensajería a Nivel de Enlace")
        self.setMinimumSize(900, 600)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121212;
                color: #e0e0e0;
            }
            QWidget {
                background-color: #121212;
                color: #e0e0e0;
            }
            QPushButton {
                background-color: #2979ff;
                color: white;
                border-radius: 4px;
                padding: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #448aff;
            }
            QListWidget {
                background-color: #1e1e1e;
                color: #e0e0e0;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: #e0e0e0;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
            }
            QLineEdit {
                background-color: #1e1e1e;
                color: #e0e0e0;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 5px;
            }
            QLabel {
                color: #e0e0e0;
            }
        """)
        
        # Estado de la aplicación (similar al original)
        self.app_state = {
            "known_hosts": {},
            "known_hosts_lock": threading.Lock(),
            "file_transfer_state": {},
            "file_transfer_lock": threading.Lock(),
            "pending_file_requests": {},
            "pending_file_requests_lock": threading.Lock(),
        }
        
        # Variable para almacenar el socket y la MAC
        self.socket = None
        self.my_mac = None
        self.current_chat_mac = None  # Para saber con quién estamos chateando
        
        # Configuración de la interfaz
        self.setup_ui()
        
        # Conectar señales
        self.message_received.connect(self.display_message)
        self.user_discovered.connect(self.add_discovered_user)
        self.file_progress.connect(self.update_file_progress)
        self.file_request_received.connect(self.show_file_request)
        
        # Timer para actualizar periódicamente la lista de usuarios
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_users)
        # Actualizar cada 30 segundos
        self.refresh_timer.start(30000)
        
    def setup_network(self):
        """Configura la red y los hilos de comunicación"""
        # Obtener interfaces disponibles
        interfaces = socket.if_nameindex()
        
        if not interfaces:
            QMessageBox.critical(self, "Error", "No se encontraron interfaces de red.")
            return False
        
        # Diálogo para seleccionar interfaz
        dialog = InterfaceSelectionDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            QMessageBox.warning(self, "Aviso", "No se seleccionó ninguna interfaz de red.")
            return False
        
        iface_name = dialog.get_selected_interface()
        
        # Verificar que la interfaz sigue existiendo
        try:
            if iface_name not in [iface[1] for iface in socket.if_nameindex()]:
                QMessageBox.critical(self, "Error", f"La interfaz {iface_name} ya no está disponible.")
                return False
        except:
            QMessageBox.critical(self, "Error", "Error al verificar las interfaces disponibles.")
            return False
        
        try:
            # Crear el socket RAW
            self.socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(LINK_CHAT_ETHERTYPE))
            self.socket.bind((iface_name, 0))
            
            # Obtener la dirección MAC de la interfaz
            self.my_mac = obtener_direccion_mac(iface_name)
            
            # Verificar que se obtuvo una MAC válida
            if not self.my_mac or len(self.my_mac) != 6:
                QMessageBox.critical(self, "Error", f"No se pudo obtener una dirección MAC válida para {iface_name}")
                return False
            
            self.setWindowTitle(f"LinkChat - {mac_bits_cadena(self.my_mac)}")
            
            # Iniciar los hilos
            receiver = threading.Thread(target=self.receive_thread_wrapper)
            receiver.daemon = True
            receiver.start()
            
            discoverer = threading.Thread(target=discovery_thread, args=(self.socket, self.my_mac))
            discoverer.daemon = True
            discoverer.start()
            
            return True
        except PermissionError:
            QMessageBox.critical(self, "Error", "Se necesitan privilegios de administrador. Ejecuta con 'sudo'.")
            return False
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al configurar la red: {e}")
            return False
    
    def receive_thread_wrapper(self):
        """Wrapper para el hilo receptor que emite señales a la interfaz"""
        def custom_handler(src_mac, msg_type, payload):
            """Manejador personalizado para mensajes recibidos"""
            # Convertir msg_type de bytes a int si es necesario
            if isinstance(msg_type, bytes) and len(msg_type) == 1:
                msg_type = msg_type[0]
                
            if msg_type == MSG_TYPE_CHAT:
                # Mensaje de chat
                message = payload.decode('utf-8', errors='replace')
                self.message_received.emit(mac_bits_cadena(src_mac), message)
            elif msg_type == MSG_TYPE_FILE_START:
                # Solicitud de archivo
                file_size = struct.unpack('!Q', payload[:8])[0]
                file_name = payload[8:].decode('utf-8', errors='replace')
                self.file_request_received.emit(src_mac, mac_bits_cadena(src_mac), file_name, file_size)
            elif msg_type == MSG_TYPE_FILE_DATA:
                # Actualizar el progreso
                pass
            elif msg_type == MSG_TYPE_FILE_END:
                # Archivo recibido completamente
                with self.app_state['file_transfer_lock']:
                    if src_mac in self.app_state['file_transfer_state']:
                        transfer = self.app_state['file_transfer_state'][src_mac]
                        file_name = transfer['file_name']
                        # Actualizar la interfaz con 100% completado
                        self.file_progress.emit(file_name, 100)
    
        try:
            receive_thread(self.socket, self.my_mac, self.app_state, custom_handler)
        except Exception as e:
            print(f"Error en receive_thread: {e}")
    
    def setup_ui(self):
        """Configura los elementos de la interfaz"""
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QHBoxLayout(central_widget)
        
        # Panel de usuarios (izquierda)
        self.create_user_panel(main_layout)
        
        # Panel de chat (centro-derecha)
        self.create_chat_panel(main_layout)
        
        # Área de transferencias de archivo
        self.create_file_transfer_panel(main_layout)
    
    def create_user_panel(self, parent_layout):
        """Crea el panel de usuarios descubiertos"""
        user_panel = QWidget()
        user_layout = QVBoxLayout(user_panel)
        
        # Título
        user_title = QLabel("Usuarios Descubiertos")
        user_title.setFont(QFont("Arial", 14, QFont.Bold))
        user_layout.addWidget(user_title)
        
        # Lista de usuarios
        self.user_list = QListWidget()
        self.user_list.setMinimumWidth(200)
        self.user_list.itemClicked.connect(self.user_selected)
        user_layout.addWidget(self.user_list)
        
        # Botones
        refresh_btn = QPushButton("Actualizar")
        refresh_btn.clicked.connect(self.refresh_users)
        user_layout.addWidget(refresh_btn)
        
        # Botón para iniciar la red
        start_network_btn = QPushButton("Iniciar Red")
        start_network_btn.clicked.connect(self.setup_network)
        user_layout.addWidget(start_network_btn)
        
        parent_layout.addWidget(user_panel)
    
    def create_chat_panel(self, parent_layout):
        """Crea el panel de chat con mensajes y entrada"""
        chat_panel = QWidget()
        chat_layout = QVBoxLayout(chat_panel)
        
        # Título del chat
        self.chat_title = QLabel("Chat Global (Broadcast)")
        self.chat_title.setFont(QFont("Arial", 14, QFont.Bold))
        chat_layout.addWidget(self.chat_title)
        
        # Área de mensajes
        self.messages_area = QTextEdit()
        self.messages_area.setReadOnly(True)
        chat_layout.addWidget(self.messages_area, 3)
        
        # Panel de entrada
        input_panel = QWidget()
        input_layout = QHBoxLayout(input_panel)
        
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Escribe un mensaje...")
        self.message_input.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.message_input, 4)
        
        send_btn = QPushButton("Enviar")
        send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(send_btn)
        
        file_btn = QPushButton("Archivo")
        file_btn.clicked.connect(self.send_file)
        input_layout.addWidget(file_btn)
        
        chat_layout.addWidget(input_panel)
        
        parent_layout.addWidget(chat_panel, 2)
    
    def create_file_transfer_panel(self, parent_layout):
        """Crea el panel para las transferencias de archivos"""
        file_panel = QWidget()
        file_layout = QVBoxLayout(file_panel)
        
        # Título
        file_title = QLabel("Transferencias")
        file_title.setFont(QFont("Arial", 14, QFont.Bold))
        file_layout.addWidget(file_title)
        
        # Lista de transferencias (implementación básica)
        self.transfers_list = QListWidget()
        file_layout.addWidget(self.transfers_list)
        
        # Botón para limpiar transferencias
        clear_btn = QPushButton("Limpiar")
        clear_btn.clicked.connect(self.transfers_list.clear)
        file_layout.addWidget(clear_btn)
        
        parent_layout.addWidget(file_panel)
    
    def user_selected(self, item):
        """Maneja la selección de un usuario de la lista"""
        mac_str = item.text().split(" - ")[0].strip()
        
        # Cambiar el título del chat
        self.chat_title.setText(f"Chat con {mac_str}")
        
        # Almacenar la MAC del usuario seleccionado
        self.current_chat_mac = mac_cadena_bits(mac_str)
        
        # Limpiar el área de mensajes para este nuevo chat
        self.messages_area.clear()

    def refresh_users(self):
        """Actualiza la lista de usuarios manualmente"""
        if not self.socket:
            QMessageBox.warning(self, "Error", "Primero debes iniciar la red.")
            return
            
        # Limpiar la lista
        self.user_list.clear()
        
        # Actualizar con los usuarios conocidos
        with self.app_state['known_hosts_lock']:
            for mac_bytes in self.app_state['known_hosts'].keys():
                mac_str = mac_bits_cadena(mac_bytes)
                self.user_list.addItem(f"{mac_str} - Usuario")
    
    def display_message(self, sender, message):
        """Muestra un mensaje en el área de chat"""
        timestamp = time.strftime("%H:%M:%S")
        
        # Aplicar colores según el remitente
        if sender == "Tú":
            style = "color: #4fc3f7; font-weight: bold;"
        else:
            style = "color: #ff8a65; font-weight: bold;"
            
        self.messages_area.append(f"<span style='color:#9e9e9e'>[{timestamp}]</span> <span style='{style}'>{sender}:</span> {message}")
    
    def send_message(self):
        """Envía un mensaje al usuario seleccionado o broadcast"""
        if not self.socket:
            QMessageBox.warning(self, "Error", "Primero debes iniciar la red.")
            return
            
        message = self.message_input.text().strip()
        if not message:
            return
            
        try:
            # Verificar que el socket está activo
            if not self.socket or getattr(self.socket, '_closed', False):
                QMessageBox.warning(self, "Error", "La conexión de red no está activa.")
                return
            
            # Preparar el mensaje
            payload = message.encode('utf-8')
            
            if self.current_chat_mac:
                # Enviar a un usuario específico
                dst_mac = self.current_chat_mac
                broadcast = False
            else:
                # Enviar a todos (broadcast)
                dst_mac = b'\xff\xff\xff\xff\xff\xff'
                broadcast = True
                
            # Construir y enviar el paquete
            eth_header = dst_mac + self.my_mac + struct.pack('!H', LINK_CHAT_ETHERTYPE)
            msg_header = struct.pack('!B', MSG_TYPE_CHAT)
            packet = eth_header + msg_header + payload
            self.socket.send(packet)
            
            # Mostrar el mensaje en la interfaz
            self.display_message("Tú", message)
            
            # Limpiar el campo de entrada
            self.message_input.clear()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al enviar el mensaje: {e}")
    
    def send_file(self):
        """Inicia el proceso para enviar un archivo"""
        if not self.socket:
            QMessageBox.warning(self, "Error", "Primero debes iniciar la red.")
            return
            
        if not self.current_chat_mac:
            QMessageBox.warning(self, "Error", "Debes seleccionar un usuario para enviar archivos.")
            return
            
        # Diálogo para seleccionar archivo
        file_path, _ = QFileDialog.getOpenFileName(self, "Seleccionar archivo", "", "Todos los archivos (*)")
        
        if not file_path:
            return
            
        # Verificar que el archivo exista y sea accesible
        if not os.path.isfile(file_path) or not os.access(file_path, os.R_OK):
            QMessageBox.critical(self, "Error", f"El archivo {file_path} no existe o no es accesible")
            return
            
        try:
            # Obtener información del archivo
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            # Crear una entrada en la lista de transferencias
            from PyQt5.QtWidgets import QListWidgetItem
            item = QListWidgetItem(f"Enviando: {file_name} (0%)")
            self.transfers_list.addItem(item)
            
            # Iniciar hilo para enviar el archivo
            file_thread = threading.Thread(
                target=file_sender_thread,
                args=(self.socket, self.my_mac, self.current_chat_mac, file_path, file_name, self.app_state)
            )
            file_thread.daemon = True
            file_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al iniciar transferencia: {e}")
    
    def update_file_progress(self, file_name, progress):
        """Actualiza el progreso de transferencia de un archivo"""
        # Buscar en la lista de transferencias
        for i in range(self.transfers_list.count()):
            item = self.transfers_list.item(i)
            if file_name in item.text():
                if progress >= 100:
                    item.setText(f"Completado: {file_name}")
                else:
                    item.setText(f"Enviando: {file_name} ({progress}%)")
                break
    
    def add_discovered_user(self, mac_bytes, mac_str):
        """Añade un usuario descubierto a la lista"""
        # Verificar si ya existe en la lista
        for i in range(self.user_list.count()):
            if mac_str in self.user_list.item(i).text():
                return
                
        # Añadir a la lista si no existe
        self.user_list.addItem(f"{mac_str} - Usuario")
    
    def show_file_request(self, src_mac, mac_str, file_name, file_size):
        """Muestra una solicitud de recepción de archivo"""
        # Convertir tamaño a formato legible
        size_str = self.format_size(file_size)
        
        # Preguntar al usuario si acepta el archivo
        reply = QMessageBox.question(self, 
                                    "Recepción de archivo",
                                    f"{mac_str} quiere enviarte el archivo:\n{file_name} ({size_str})",
                                    QMessageBox.Yes | QMessageBox.No)
                                    
        if reply == QMessageBox.Yes:
            # Seleccionar ubicación para guardar
            save_path, _ = QFileDialog.getSaveFileName(self, "Guardar archivo", file_name, "Todos los archivos (*)")
            
            if save_path:
                # Preparar el archivo para recepción
                try:
                    file_handle = open(save_path, 'wb')
                    
                    # Aceptar el archivo y configurar el estado
                    with self.app_state['file_transfer_lock']:
                        self.app_state['file_transfer_state'][src_mac] = {
                            'file_name': file_name,
                            'file_size': file_size,
                            'file_handle': file_handle,
                            'status': 'receiving',
                            'received_size': 0,
                            'save_path': save_path
                        }
                    
                    # Crear entrada en la lista de transferencias
                    item = QListWidgetItem(f"Recibiendo: {file_name} (0%)")
                    self.transfers_list.addItem(item)
                    
                    # Enviar ACK
                    if self.socket:
                        eth_header = src_mac + self.my_mac + struct.pack('!H', LINK_CHAT_ETHERTYPE)
                        msg_header = struct.pack('!B', MSG_TYPE_FILE_ACK)  # Corrección: empaquetar como byte
                        packet = eth_header + msg_header
                        self.socket.send(packet)
                        
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"No se pudo preparar el archivo para recepción: {e}")
    
    @staticmethod
    def format_size(size_bytes):
        """Formatea un tamaño en bytes a formato legible"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} TB"

    def closeEvent(self, event):
        """Maneja el cierre de la aplicación"""
        # Cerrar socket si está abierto
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        
        # Aceptar el evento de cierre
        event.accept()

def show_splash_screen():
    """Muestra una pantalla de bienvenida estilo videojuego"""
    splash = AnimatedSplashScreen()
    splash.show()
    
    # Usar un enfoque más seguro para no bloquear la UI
    start_time = time.time()
    while splash.timer.isActive() and time.time() - start_time < 5:  # Timeout de 5 segundos
        QApplication.processEvents()
        time.sleep(0.01)  # Pequeña pausa para no consumir CPU
    
    # Tiempo adicional para apreciar la pantalla completada
    time.sleep(0.5)
    
    return splash

def main():
    # Configurar variables de entorno si no están presentes
    if 'XDG_RUNTIME_DIR' not in os.environ:
        os.environ['XDG_RUNTIME_DIR'] = '/tmp/runtime-' + os.environ.get('USER', 'root')
        try:
            os.makedirs(os.environ['XDG_RUNTIME_DIR'], exist_ok=True)
            os.chmod(os.environ['XDG_RUNTIME_DIR'], 0o700)
        except:
            pass
    
    app = QApplication(sys.argv)
    
    # Configurar el manejo de señales para una terminación más limpia
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    # Mostrar pantalla de bienvenida
    splash = show_splash_screen()
    
    # Iniciar la aplicación principal
    window = ChatApp()
    window.show()
    
    # Cerrar la pantalla de bienvenida
    splash.finish(window)
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()