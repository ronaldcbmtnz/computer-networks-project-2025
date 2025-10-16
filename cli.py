import struct
import threading
import time
import os  # Necesitamos os para el manejo de archivos
from config import *
from utils import mac_bits_cadena, mac_cadena_bits
from network_threads import file_sender_thread  # Importamos el hilo emisor

def handle_user_input(sock, my_mac, state):
    """
    Maneja la entrada del usuario desde la terminal.
    """
    while True:
        try:
            user_input = input("> ").strip()
            if not user_input:
                continue

            if user_input.lower() == '/list':
                print("--- Hosts Descubiertos ---")
                with state['known_hosts_lock']:
                    if not state['known_hosts']:
                        print("No se han descubierto otros usuarios.")
                    else:
                        for i, mac_bytes in enumerate(state['known_hosts']):
                            print(f"  {i}: {mac_bits_cadena(mac_bytes)}")
                print("------------------------")

            elif user_input.lower().startswith('/msg '):
                parts = user_input.split(' ', 2)
                if len(parts) < 3:
                    print("[!] Uso: /msg <user_id> <mensaje>")
                    continue
                
                user_id, message = parts[1], parts[2]
                try:
                    user_id = int(user_id)
                    with state['known_hosts_lock']:
                        hosts_list = list(state['known_hosts'].keys())
                        if 0 <= user_id < len(hosts_list):
                            dest_mac = hosts_list[user_id]
                            header = struct.pack('!6s6sH', dest_mac, my_mac, LINK_CHAT_ETHERTYPE)
                            packet = header + MSG_TYPE_CHAT + message.encode('utf-8')
                            sock.send(packet)
                        else:
                            print(f"[!] ID de usuario '{user_id}' no válido.")
                except (ValueError, IndexError):
                    print(f"[!] ID de usuario '{user_id}' no válido.")

            elif user_input.lower().startswith('/send '):
                parts = user_input.split(' ', 2)
                if len(parts) < 3:
                    print("[!] Uso: /send <user_id> <ruta_del_archivo>")
                    continue
                
                user_id_str, file_path = parts[1], parts[2]

                # Validar que el archivo exista DENTRO del contenedor
                if not os.path.exists(file_path):
                    print(f"[!] Error: El archivo '{file_path}' no existe dentro del contenedor.")
                    continue

                try:
                    user_id = int(user_id_str)
                    with state['known_hosts_lock']:
                        hosts_list = list(state['known_hosts'].keys())
                        if not (0 <= user_id < len(hosts_list)):
                            print(f"[!] ID de usuario '{user_id}' no válido.")
                            continue
                        dest_mac = hosts_list[user_id]

                    # Iniciar la lógica de envío de archivo
                    file_name = os.path.basename(file_path)
                    file_size = os.path.getsize(file_path)

                    # Payload: bandera (no es carpeta), tamaño y nombre
                    payload = b'\x00' + struct.pack('!Q', file_size) + file_name.encode('utf-8') + b'\x00'
                    header = struct.pack('!6s6sH', dest_mac, my_mac, LINK_CHAT_ETHERTYPE)
                    # Enviamos el paquete de inicio
                    sock.send(header + MSG_TYPE_FILE_START + payload)

                   
                    sender_thread = threading.Thread(
                        target=file_sender_thread,
                        args=(sock, my_mac, dest_mac, file_path, state)
                    )
                    sender_thread.daemon = True
                    sender_thread.start()
                    print(f"Solicitud para enviar '{file_name}' a {mac_bits_cadena(dest_mac)} enviada.")

                except (ValueError, IndexError):
                    print(f"[!] ID de usuario '{user_id_str}' no válido.")
                except Exception as e:
                    print(f"[!] Error al iniciar envío de archivo: {e}")

            else: # Mensaje broadcast
                header = struct.pack('!6s6sH', BROADCAST_MAC, my_mac, LINK_CHAT_ETHERTYPE)
                packet = header + MSG_TYPE_CHAT + user_input.encode('utf-8')
                sock.send(packet)

        except (KeyboardInterrupt, EOFError):
            print("\nSaliendo...")
            break
        except Exception as e:
            print(f"\n[!] Error en la entrada de usuario: {e}")
            break

def process_incoming_cli(state):
    """
    Procesa eventos de la cola para la versión de terminal.
    """
    gui_queue = state['gui_queue']
    while True:
        try:
            event = gui_queue.get()
            event_type = event[0]

            if event_type == 'new_user':
                mac_str = mac_bits_cadena(event[1])
                print(f"\r[+] Nuevo host descubierto: {mac_str}\n> ", end='', flush=True)
            
            elif event_type == 'chat_message':
                print(f"\r{event[1]}\n> ", end='', flush=True)
            
            elif event_type == 'file_download_started':
                file_name = event[1]
                print(f"\r[+] Descarga iniciada: '{file_name}'.\n> ", end='', flush=True)

            elif event_type == 'file_received':
                file_name = event[1]
                print(f"\r[+] Archivo '{file_name}' recibido correctamente.\n> ", end='', flush=True)

            elif event_type == 'error':
                 print(f"\r[ERROR] {event[1]}\n> ", end='', flush=True)

            gui_queue.task_done()
        except Exception as e:
            print(f"Error procesando cola: {e}")


def start_cli_mode(app_state):
    """
    Función principal para el modo de línea de comandos.
    """
    sock = app_state['socket']
    my_mac = app_state['my_mac']

    # Hilo para procesar la cola de la GUI (ahora CLI)
    cli_processor_thread = threading.Thread(target=process_incoming_cli, args=(app_state,), daemon=True)
    cli_processor_thread.start()

    print("Modo terminal iniciado. Escribe un mensaje o usa /list, /msg.")
    # El bucle de entrada de usuario se ejecuta en el hilo principal
    handle_user_input(sock, my_mac, app_state)