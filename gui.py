import tkinter as tk
# 1. Importar filedialog y os
from tkinter import scrolledtext, messagebox, Listbox, END, filedialog
import os
import socket
import sys
import threading
import struct
import shutil
# 2. Importar los nuevos tipos de mensaje y el file_sender_thread
from config import LINK_CHAT_ETHERTYPE, BROADCAST_MAC, MSG_TYPE_CHAT, MSG_TYPE_FILE_START, MSG_TYPE_FILE_ACK
from utils import obtener_direccion_mac, mac_bits_cadena, mac_cadena_bits
from network_threads import receive_thread, discovery_thread, file_sender_thread

class ChatApplication(tk.Tk):
    """
    Clase principal para la interfaz gráfica del chat.
    """
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        
        # Ocultamos la ventana principal hasta que se seleccione la interfaz
        self.withdraw() 
        
        # Mostramos la ventana de selección de interfaz
        self.show_interface_selection()

    def show_interface_selection(self):
        """Crea y muestra la ventana para seleccionar la interfaz de red."""
        self.selection_window = tk.Toplevel(self)
        self.selection_window.title("Seleccionar Interfaz")
        self.selection_window.geometry("300x200")
        
        # Evita que el usuario interactúe con otras ventanas
        self.selection_window.grab_set() 
        
        tk.Label(self.selection_window, text="Elige la interfaz de red:").pack(pady=10)

        try:
            interfaces = [iface[1] for iface in socket.if_nameindex()]
            self.iface_var = tk.StringVar(self.selection_window)
            if interfaces:
                self.iface_var.set(interfaces[0]) # Opción por defecto
            
            option_menu = tk.OptionMenu(self.selection_window, self.iface_var, *interfaces)
            option_menu.pack(pady=10, padx=20, fill=tk.X)
            
            connect_button = tk.Button(self.selection_window, text="Conectar", command=self.start_networking)
            connect_button.pack(pady=20)

        except Exception:
            messagebox.showerror("Error", "No se pudieron obtener las interfaces de red.\nAsegúrate de estar en Linux.")
            self.destroy()

    def start_networking(self):
        """Inicia la lógica de red después de seleccionar una interfaz."""
        iface_name = self.iface_var.get()
        if not iface_name:
            messagebox.showwarning("Advertencia", "Debes seleccionar una interfaz.")
            return

        try:
            my_mac = obtener_direccion_mac(iface_name)
            s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(LINK_CHAT_ETHERTYPE))
            s.bind((iface_name, 0))

            # Guardamos la información en el estado de la aplicación
            self.app_state['my_mac'] = my_mac
            self.app_state['socket'] = s

            # Iniciamos los hilos de red
            receiver = threading.Thread(target=receive_thread, args=(s, my_mac, self.app_state))
            receiver.daemon = True
            receiver.start()

            discoverer = threading.Thread(target=discovery_thread, args=(s, my_mac))
            discoverer.daemon = True
            discoverer.start()
            
            # Cerramos la ventana de selección y mostramos la principal
            self.selection_window.destroy()
            self.deiconify() # Muestra la ventana principal que estaba oculta
            self.setup_main_chat_window() # Construye la ventana de chat

        except PermissionError:
            messagebox.showerror("Error de Permisos", "Se necesitan privilegios de administrador.\nEjecuta la aplicación con 'sudo'.")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error de Red", f"No se pudo iniciar la red en {iface_name}:\n{e}")
            self.destroy()

    def setup_main_chat_window(self):
        """Construye la interfaz principal del chat."""
        self.title(f"Link-Layer Chat - {mac_bits_cadena(self.app_state['my_mac'])}")
        self.geometry("800x600")

        # --- Creación de Widgets ---
        main_frame = tk.Frame(self)
        main_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        # Dividimos el main_frame en dos: chat y estado
        chat_area_frame = tk.Frame(main_frame)
        chat_area_frame.pack(fill=tk.BOTH, expand=True)

        users_frame = tk.Frame(chat_area_frame)
        users_frame.pack(side=tk.LEFT, padx=(0, 10), fill=tk.Y)
        tk.Label(users_frame, text="Usuarios Descubiertos").pack()
        self.users_listbox = Listbox(users_frame)
        self.users_listbox.pack(fill=tk.Y, expand=True)

        # Añadimos un botón para limpiar la selección de usuario
        clear_selection_button = tk.Button(users_frame, text="Chat General", command=self.clear_user_selection)
        clear_selection_button.pack(fill=tk.X, pady=5)

        chat_frame = tk.Frame(chat_area_frame)
        chat_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.chat_area = scrolledtext.ScrolledText(chat_frame, wrap=tk.WORD, state='disabled')
        self.chat_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        self.message_entry = tk.Entry(chat_frame, font=("Helvetica", 12))
        self.message_entry.pack(padx=10, pady=(0, 10), fill=tk.X)
        
        # Frame para los botones de acción
        action_frame = tk.Frame(chat_frame)
        action_frame.pack(pady=(0, 10))

        self.send_button = tk.Button(action_frame, text="Enviar Mensaje", command=self.send_message)
        self.send_button.pack(side=tk.LEFT, padx=5)

        self.send_file_button = tk.Button(action_frame, text="Enviar Archivo", command=self.select_file_to_send)
        self.send_file_button.pack(side=tk.LEFT, padx=5)
        
        # 1. Añadir el botón de Enviar Carpeta
        self.send_folder_button = tk.Button(action_frame, text="Enviar Carpeta", command=self.select_folder_to_send)
        self.send_folder_button.pack(side=tk.LEFT, padx=5)
        
        # --- BARRA DE ESTADO ---
        self.status_label = tk.Label(main_frame, text="Listo", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Permitir enviar mensajes presionando la tecla 'Enter'
        self.message_entry.bind("<Return>", self.send_message_event)

        self.process_incoming()

    def _send_packet(self, dest_mac, msg_type, payload=b''):
        """
        Función auxiliar para construir y enviar un paquete Ethernet.
        """
        sock = self.app_state['socket']
        my_mac = self.app_state['my_mac']
        
        # Construye la cabecera Ethernet
        eth_header = struct.pack('!6s6sH', dest_mac, my_mac, LINK_CHAT_ETHERTYPE)
        
        # Construye el paquete completo
        packet = eth_header + msg_type + payload
        
        # Envía el paquete
        sock.send(packet)

    def process_incoming(self):
        """
        Revisa la cola de la GUI y actualiza la barra de estado.
        """
        # 1. Procesar eventos de la cola
        while not self.app_state['gui_queue'].empty():
            try:
                event = self.app_state['gui_queue'].get_nowait()
                event_type = event[0]
                
                if event_type == 'new_user':
                    mac_bytes = event[1]
                    self.update_user_list()
                    self.display_message(f"[Sistema] Nuevo usuario descubierto: {mac_bits_cadena(mac_bytes)}")
                
                elif event_type == 'chat_message':
                    # El mensaje ya viene formateado desde el hilo de red
                    formatted_message = event[1]
                    self.display_message(formatted_message)
                
                # 2. Añadir el manejo del evento de solicitud de archivo
                elif event_type == 'file_request':
                    sender_mac, file_name, file_size, is_folder = event[1], event[2], event[3], event[4]
                    self.handle_file_request(sender_mac, file_name, file_size, is_folder)

                # 3. Añadir el manejo del evento de recepción de archivo completada
                elif event_type == 'file_received':
                    file_name = event[1]
                    self.display_message(f"[Sistema] Archivo '{file_name}' recibido y guardado.")
                    messagebox.showinfo("Descarga Completada", f"El archivo '{file_name}' se ha descargado correctamente.")
                
                # Nuevo evento para carpetas
                elif event_type == 'folder_received':
                    folder_name = event[1]
                    self.display_message(f"[Sistema] Carpeta '{folder_name}' recibida y descomprimida.")
                    messagebox.showinfo("Descarga Completada", f"La carpeta '{folder_name}' se ha descargado y descomprimido correctamente.")

                elif event_type == 'error':
                    error_message = event[1]
                    self.display_message(f"[ERROR] {error_message}")

            except Exception:
                pass # Ignorar si la cola está vacía
        
        # 2. Actualizar la barra de estado con el progreso de la descarga
        self.update_status_bar()
        
        # 3. Volver a llamar a esta función
        self.after(250, self.process_incoming) # Aumentamos un poco el tiempo a 250ms

    # Nueva función para actualizar la barra de estado
    def update_status_bar(self):
        """
        Revisa si hay descargas activas y actualiza la etiqueta de estado.
        """
        active_downloads = []
        with self.app_state['pending_file_requests_lock']:
            # Buscamos todas las descargas activas
            for mac, request in self.app_state['pending_file_requests'].items():
                file_name = request['file_name']
                downloaded = request['downloaded_size']
                total = request['file_size']
                
                if total > 0:
                    percentage = (downloaded / total) * 100
                    active_downloads.append(f"Descargando '{file_name}': {percentage:.1f}%")

        if active_downloads:
            # Si hay descargas, las mostramos
            self.status_label.config(text=" | ".join(active_downloads))
        else:
            # Si no, mostramos "Listo"
            self.status_label.config(text="Listo")

    def update_user_list(self):
        """
        Limpia y vuelve a poblar la lista de usuarios con los datos de app_state.
        """
        self.users_listbox.delete(0, tk.END) # Limpia la lista actual
        
        with self.app_state['known_hosts_lock']:
            for mac_bytes in self.app_state['known_hosts']:
                mac_str = mac_bits_cadena(mac_bytes)
                self.users_listbox.insert(tk.END, mac_str)

    def clear_user_selection(self):
        """Deselecciona cualquier usuario en la lista."""
        self.users_listbox.selection_clear(0, tk.END)
        self.display_message("[Sistema] Escribiendo en el chat general.")

    def display_message(self, message):
        """
        Muestra un mensaje en el área de chat, asegurando que siempre
        se inserte en una nueva línea.
        """
        self.chat_area.config(state='normal')
        
        # Comprueba si el último carácter no es un salto de línea.
        # El '1.0' significa línea 1, caracter 0. 'end-2c' es "el final menos 2 caracteres".
        # Esto es necesario para ignorar el salto de línea final que Tkinter añade automáticamente.
        if self.chat_area.get('end-2c', 'end-1c') != '\n':
            self.chat_area.insert(tk.END, '\n')

        # Inserta el mensaje seguido de un salto de línea.
        self.chat_area.insert(tk.END, message + '\n')
        
        self.chat_area.config(state='disabled')
        self.chat_area.see(tk.END) # Auto-scroll hacia abajo

    def send_message_event(self, event):
        """Manejador para el evento de la tecla Enter."""
        self.send_message()

    def send_message(self):
        """
        Envía el contenido del campo de texto.
        Pone el mensaje en la cola de la GUI para ser mostrado, en lugar de mostrarlo directamente.
        """
        message = self.message_entry.get()
        if not message:
            return # No enviar mensajes vacíos

        dest_mac_bytes = BROADCAST_MAC
        is_private = False
        
        # Comprobar si hay un usuario seleccionado en la lista
        selection_indices = self.users_listbox.curselection()
        if selection_indices:
            selected_mac_str = self.users_listbox.get(selection_indices[0])
            try:
                dest_mac_bytes = mac_cadena_bits(selected_mac_str)
                is_private = True
            except Exception as e:
                messagebox.showerror("Error de MAC", f"La dirección MAC seleccionada no es válida: {e}")
                return

        try:
            # 1. Enviar el paquete a la red
            payload = message.encode('utf-8')
            self._send_packet(dest_mac_bytes, MSG_TYPE_CHAT, payload)

            # 2. PONER nuestro propio mensaje en la COLA para ser procesado
            #    en el orden correcto por process_incoming.
            if is_private:
                display_text = f"[Privado para {selected_mac_str}]: {message}"
            else:
                display_text = f"[Tú]: {message}"
            
            self.app_state['gui_queue'].put(('chat_message', display_text))

            # 3. Limpiar el campo de entrada
            self.message_entry.delete(0, tk.END)

        except Exception as e:
            messagebox.showerror("Error de Envío", f"No se pudo enviar el mensaje:\n{e}")

    # 4. Añadir la nueva función para seleccionar y enviar archivos
    def select_file_to_send(self):
        """
        Abre un diálogo para seleccionar un archivo y luego inicia el proceso de envío.
        """
        # Primero, comprobar que hay un destinatario seleccionado
        selection_indices = self.users_listbox.curselection()
        if not selection_indices:
            messagebox.showwarning("Destinatario Requerido", "Por favor, selecciona un usuario de la lista para enviarle un archivo.")
            return

        # Abrir el diálogo para seleccionar archivo
        file_path = filedialog.askopenfilename(title="Seleccionar archivo para enviar")
        if not file_path:
            return # El usuario canceló la selección

        try:
            # Obtener la MAC del destinatario
            selected_mac_str = self.users_listbox.get(selection_indices[0])
            dest_mac_bytes = mac_cadena_bits(selected_mac_str)

            # Obtener información del archivo
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)

            # Crear el payload del paquete FILE_START: tipo (1 byte, 0=file) + tamaño (8 bytes) + nombre (utf-8) + DELIMITADOR NULO
            is_folder_flag = b'\x00'
            payload = is_folder_flag + struct.pack('!Q', file_size) + file_name.encode('utf-8') + b'\x00'

            # Enviar la solicitud de transferencia
            self._send_packet(dest_mac_bytes, MSG_TYPE_FILE_START, payload)

            # 4. Registrar el estado de la transferencia como pendiente
            with self.app_state['file_transfer_lock']:
                self.app_state['file_transfer_state'][dest_mac_bytes] = {"status": "pending_ack"}

            # Iniciar el hilo que gestionará el envío real del archivo
            # Este hilo esperará el ACK antes de proceder
            sender_thread = threading.Thread(
                target=file_sender_thread,
                args=(self.app_state['socket'], self.app_state['my_mac'], dest_mac_bytes, file_path, self.app_state)
            )
            sender_thread.daemon = True
            sender_thread.start()

            # Notificar al usuario en la GUI
            self.display_message(f"[Sistema] Solicitud para enviar '{file_name}' a {selected_mac_str} enviada.")

        except Exception as e:
            messagebox.showerror("Error al Enviar Archivo", f"No se pudo iniciar la transferencia del archivo:\n{e}")

    # 3. Añadir la nueva función para gestionar la solicitud
    def handle_file_request(self, sender_mac, file_name, file_size, is_folder):
        """Muestra un pop-up para aceptar o rechazar un archivo."""
        sender_mac_str = mac_bits_cadena(sender_mac)
        
        # Formatear el tamaño para que sea legible
        if file_size < 1024:
            size_str = f"{file_size} B"
        elif file_size < 1024**2:
            size_str = f"{file_size/1024:.1f} KB"
        else:
            size_str = f"{file_size/1024**2:.1f} MB"

        # Preguntar al usuario
        answer = messagebox.askyesno(
            "Solicitud de Archivo Entrante",
            f"El usuario {sender_mac_str} quiere enviarte el archivo:\n\n"
            f"Nombre: {file_name}\n"
            f"Tamaño: {size_str}\n\n"
            "¿Aceptas la transferencia?"
        )

        if answer:
            # El usuario aceptó
            self.display_message(f"[Sistema] Aceptando '{file_name}' de {sender_mac_str}. Descargando...")
            
            # Guardar la información del archivo que vamos a recibir
            with self.app_state['pending_file_requests_lock']:
                self.app_state['pending_file_requests'][sender_mac] = {
                    "file_name": file_name,
                    "file_size": file_size,
                    "downloaded_size": 0,
                    "path": file_name,
                    "is_folder": is_folder
                }
            
            # Enviar el paquete de confirmación (ACK)
            self._send_packet(sender_mac, MSG_TYPE_FILE_ACK)
        else:
            # El usuario rechazó
            self.display_message(f"[Sistema] Rechazaste la transferencia de '{file_name}' de {sender_mac_str}.")
            # No se envía nada, el emisor entrará en timeout

    # 2. Añadir la nueva función para seleccionar y enviar carpetas
    def select_folder_to_send(self):
        """
        Abre un diálogo para seleccionar una carpeta, la comprime en un zip y la envía.
        """
        selection_indices = self.users_listbox.curselection()
        if not selection_indices:
            messagebox.showwarning("Destinatario Requerido", "Por favor, selecciona un usuario de la lista para enviarle una carpeta.")
            return

        folder_path = filedialog.askdirectory(title="Seleccionar carpeta para enviar")
        if not folder_path:
            return

        # Creamos un nombre para el archivo zip temporal
        zip_filename_base = f"temp_{os.path.basename(folder_path)}"
        zip_path = None
        
        try:
            # Comprimir la carpeta en un archivo zip
            self.display_message(f"[Sistema] Comprimiendo '{os.path.basename(folder_path)}'...")
            zip_path = shutil.make_archive(zip_filename_base, 'zip', folder_path)
            self.display_message(f"[Sistema] Compresión completada: {os.path.basename(zip_path)}")

            # Ahora, enviamos el archivo zip como si fuera un archivo normal
            selected_mac_str = self.users_listbox.get(selection_indices[0])
            dest_mac_bytes = mac_cadena_bits(selected_mac_str)
            file_name = os.path.basename(zip_path)
            file_size = os.path.getsize(zip_path)

            # Crear el payload del paquete FILE_START: tipo (1 byte, 1=folder) + tamaño (8 bytes) + nombre (utf-8) + DELIMITADOR NULO
            is_folder_flag = b'\x01'
            payload = is_folder_flag + struct.pack('!Q', file_size) + file_name.encode('utf-8') + b'\x00'
            
            self._send_packet(dest_mac_bytes, MSG_TYPE_FILE_START, payload)

            with self.app_state['file_transfer_lock']:
                self.app_state['file_transfer_state'][dest_mac_bytes] = {"status": "pending_ack"}

            # Iniciamos el hilo de envío, indicando que es un zip temporal
            sender_thread = threading.Thread(
                target=file_sender_thread,
                args=(self.app_state['socket'], self.app_state['my_mac'], dest_mac_bytes, zip_path, self.app_state, True) # is_temp_zip = True
            )
            sender_thread.daemon = True
            sender_thread.start()

            self.display_message(f"[Sistema] Solicitud para enviar '{file_name}' a {selected_mac_str} enviada.")

        except Exception as e:
            messagebox.showerror("Error al Enviar Carpeta", f"No se pudo iniciar la transferencia:\n{e}")
            # Si hubo un error pero el zip se creó, lo borramos
            if zip_path and os.path.exists(zip_path):
                os.remove(zip_path)