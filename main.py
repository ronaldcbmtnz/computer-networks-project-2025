import socket
import sys
import struct
import threading
import os
import shutil
import queue
from config import *
from utils import obtener_direccion_mac, mac_bits_cadena, mac_cadena_bits
from network_threads import receive_thread, discovery_thread, file_sender_thread
from gui import ChatApplication

def main():
    """
    Función principal que inicializa y ejecuta la aplicación de chat.
    """
    # --- 1. Inicialización del Estado de la Aplicación ---
    # Este diccionario central contendrá todos los datos compartidos entre hilos.
    app_state = {
        # Diccionario para guardar los hosts descubiertos {mac_bytes: "alias"}
        "known_hosts": {},
        # Lock para acceder de forma segura a 'known_hosts'.
        "known_hosts_lock": threading.Lock(),
        # Diccionario para el estado de las transferencias de archivos.
        "file_transfer_state": {},
        # Lock para acceder de forma segura a 'file_transfer_state'.
        "file_transfer_lock": threading.Lock(),
        # Diccionario para guardar solicitudes de archivos pendientes.
        "pending_file_requests": {},
        # Lock para acceder de forma segura a 'pending_file_requests'.
        "pending_file_requests_lock": threading.Lock(),
        "gui_queue": queue.Queue(),
        "my_mac": None, # Añadimos para guardar nuestra MAC
        "socket": None, # Añadimos para guardar el socket
    }

    # --- 2. INICIAR LA INTERFAZ GRÁFICA ---
    # La GUI ahora se encargará de todo lo demás.
    try:
        # La aplicación solo necesita el diccionario de estado para empezar.
        app = ChatApplication(app_state)
        app.mainloop()
    except Exception as e:
        print(f"Ocurrió un error fatal en la aplicación: {e}")
    finally:
        # Asegura que el socket se cierre correctamente al salir.
        if app_state.get("socket"):
            app_state["socket"].close()
            print("Socket cerrado. Adiós.")
        sys.exit(0)

if __name__ == "__main__":
    main()
