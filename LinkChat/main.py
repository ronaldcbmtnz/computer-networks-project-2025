import socket
import sys
import threading
import os
import queue
import netifaces
from config import LINK_CHAT_ETHERTYPE
from utils import obtener_direccion_mac
from network_threads import receive_thread, discovery_thread
from gui import ChatApplication
from cli import start_cli_mode # Importamos la nueva función

def setup_network(interface):
    """Abre el socket y obtiene la MAC."""
    try:
        # Crear el socket RAW
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(LINK_CHAT_ETHERTYPE))
        sock.bind((interface, 0))
        
        # Obtener la dirección MAC
        my_mac = obtener_direccion_mac(interface)
        return sock, my_mac
    except PermissionError:
        print("[ERROR] Permiso denegado. Ejecuta el script con 'sudo'.")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] No se pudo inicializar la red en '{interface}': {e}")
        sys.exit(1)

def main():
    """
    Función principal que inicializa y ejecuta la aplicación.
    Decide si lanzar la GUI o el modo CLI.
    """
    app_state = {
        "known_hosts": {},
        "known_hosts_lock": threading.Lock(),
        "file_transfer_state": {},
        "file_transfer_lock": threading.Lock(),
        "pending_file_requests": {},
        "pending_file_requests_lock": threading.Lock(),
        "gui_queue": queue.Queue(),
        "my_mac": None,
        "socket": None,
    }

    # Decidir el modo de ejecución
    run_mode = os.environ.get('RUN_MODE', 'GUI').upper()

    if run_mode == 'CLI':
        # --- MODO LÍNEA DE COMANDOS (PARA DOCKER) ---
        print("Iniciando en modo Línea de Comandos (CLI)...")
        # En Docker, la interfaz suele ser 'eth0'
        interface = 'eth0' 
        sock, my_mac = setup_network(interface)
        app_state["socket"] = sock
        app_state["my_mac"] = my_mac
        
        # Iniciar hilos de red
        recv_thread = threading.Thread(target=receive_thread, args=(sock, my_mac, app_state), daemon=True)
        recv_thread.start()
        
        disc_thread = threading.Thread(target=discovery_thread, args=(sock, my_mac), daemon=True)
        disc_thread.start()

        start_cli_mode(app_state)

    else:
        # --- MODO GRÁFICO (POR DEFECTO) ---
        try:
            app = ChatApplication(app_state)
            app.mainloop()
        except Exception as e:
            print(f"Ocurrió un error fatal en la aplicación: {e}")

    # Asegura que el socket se cierre correctamente al salir.
    if app_state.get("socket"):
        app_state["socket"].close()
        print("\nSocket cerrado. Adiós.")
    sys.exit(0)

if __name__ == "__main__":
    # Necesitamos netifaces para la GUI, pero no para el CLI.
    # Lo importamos aquí para que el CLI no tenga dependencias extra.
    try:
        import netifaces
    except ImportError:
        if os.environ.get('RUN_MODE', 'GUI').upper() != 'CLI':
            print("Error: El paquete 'netifaces' es necesario para el modo GUI. Instálalo con 'pip install netifaces'")
            sys.exit(1)
    main()
