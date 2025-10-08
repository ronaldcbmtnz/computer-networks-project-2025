import socket
import sys
import struct
import threading
import os
from config import *
from utils import obtener_direccion_mac, mac_bits_cadena, mac_cadena_bits
from network_threads import receive_thread, discovery_thread, file_sender_thread

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
    }

    # --- 2. Selección de Interfaz de Red ---
    try:
        # Obtiene una lista de todas las interfaces de red disponibles en el sistema.
        interfaces = [iface[1] for iface in socket.if_nameindex()]
    except Exception:
        print("No se pudieron obtener las interfaces de red. Asegúrate de estar en Linux.")
        sys.exit(1)

    print("Interfaces de red disponibles:")
    for i, iface in enumerate(interfaces):
        print(f"  {i}: {iface}")
    
    try:
        # Pide al usuario que elija una interfaz por su número.
        choice = int(input("Elige la interfaz de red a utilizar: "))
        iface_name = interfaces[choice]
    except (ValueError, IndexError):
        print("Selección inválida.")
        sys.exit(1)

    print(f"Interfaz seleccionada: {iface_name}")

    # --- 3. Configuración del Socket y los Hilos ---
    s = None
    try:
        # Obtiene la dirección MAC de la interfaz seleccionada.
        my_mac = obtener_direccion_mac(iface_name)
        print(f"Tu dirección MAC es: {mac_bits_cadena(my_mac)}")

        # Crea un socket RAW (AF_PACKET) que opera a nivel de capa de enlace.
        # socket.htons(LINK_CHAT_ETHERTYPE) le dice al kernel que nos entregue solo
        # los paquetes que coincidan con nuestro EtherType personalizado.
        s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(LINK_CHAT_ETHERTYPE))
        # Vincula el socket a la interfaz de red elegida.
        s.bind((iface_name, 0))
        
        # Crea e inicia el hilo receptor.
        # Le pasamos el socket, nuestra MAC y el diccionario de estado.
        # 'daemon=True' significa que el hilo se cerrará automáticamente si el programa principal termina.
        receiver = threading.Thread(target=receive_thread, args=(s, my_mac, app_state))
        receiver.daemon = True
        receiver.start()

        # Crea e inicia el hilo de descubrimiento.
        discoverer = threading.Thread(target=discovery_thread, args=(s, my_mac))
        discoverer.daemon = True
        discoverer.start()

        # --- 4. Bucle Principal de Interacción con el Usuario ---
        print("\n¡Chat iniciado! Comandos disponibles:")
        print("  /list                - Muestra los usuarios descubiertos.")
        print("  /msg <id> <mensaje>  - Envía un mensaje privado.")
        print("  /send <id> <fpath>   - Envía un archivo a un usuario.")
        print("  /accept <mac>        - Acepta un archivo de un usuario.")
        print("  <mensaje>            - Envía un mensaje a todos (broadcast).")
        print("  quit                 - Salir del chat.")

        while True:
            # Espera la entrada del usuario.
            message = input("> ")
            if message.lower() == 'quit':
                break
            
            # Por defecto, los mensajes se envían a todos (broadcast).
            dest_mac_bytes = b'\xff\xff\xff\xff\xff\xff'
            payload = MSG_TYPE_CHAT + message.encode('utf-8')

            # --- Procesamiento de Comandos ---
            if message.startswith('/list'):
                with app_state['known_hosts_lock']:
                    if not app_state['known_hosts']:
                        print("No se han descubierto otros usuarios.")
                    else:
                        print("Usuarios descubiertos:")

        
                        # Muestra los usuarios con un ID numérico para facilitar su uso.
                        for i, mac_bytes in enumerate(app_state['known_hosts'].keys()):
                            print(f"  {i}: {mac_bits_cadena(mac_bytes)}")
                continue # Vuelve al inicio del bucle sin enviar ningún paquete.

            elif message.startswith('/msg'):
                parts = message.split(' ', 2)
                if len(parts) < 3:
                    print("Uso incorrecto. Ejemplo: /msg 00:1a:2b:3c:4d:5e Hola")
                    continue
                try:
                    # El segundo argumento ahora es la MAC, no el ID.
                    dest_mac_str = parts[1]
                    dest_mac_bytes = mac_cadena_bits(dest_mac_str)
                    
                    # Verificamos que conocemos esa MAC
                    with app_state['known_hosts_lock']:
                        if dest_mac_bytes not in app_state['known_hosts']:
                            print("Error: MAC de destino desconocida. Usa /list para ver los usuarios.")
                            continue
                    
                    # Prepara el payload con el mensaje.
                    payload = MSG_TYPE_CHAT + parts[2].encode('utf-8')
                except Exception:
                    print("Error: Formato de MAC inválido.")
                    continue
            
            elif message.startswith('/send'):
                parts = message.split(' ', 2)
                if len(parts) < 3:
                    print("Uso incorrecto. Ejemplo: /send 00:1a:2b:3c:4d:5e /ruta/a/archivo.txt")
                    continue
                try:
                    # El segundo argumento ahora es la MAC, no el ID.
                    dest_mac_str = parts[1]
                    dest_mac_bytes = mac_cadena_bits(dest_mac_str)
                    file_path = parts[2]
                    
                    if not os.path.exists(file_path):
                        print(f"Error: El archivo '{file_path}' no existe.")
                        continue

                    # Verificamos que conocemos esa MAC
                    with app_state['known_hosts_lock']:
                        if dest_mac_bytes not in app_state['known_hosts']:
                            print("Error: MAC de destino desconocida. Usa /list para ver los usuarios.")
                            continue
                    
                    # --- Envío de la solicitud FILE_START ---
                    file_size = os.path.getsize(file_path)

                    # --- Envío de la solicitud FILE_START ---
                    file_size = os.path.getsize(file_path)
                    file_name = os.path.basename(file_path)
                    start_payload = MSG_TYPE_FILE_START + struct.pack('!Q', file_size) + file_name.encode('utf-8')
                    header = struct.pack('!6s6sH', dest_mac_bytes, my_mac, LINK_CHAT_ETHERTYPE)
                    s.send(header + start_payload)
                    
                    # Registra el estado de la transferencia como "esperando ACK".
                    with app_state['file_transfer_lock']:
                        app_state['file_transfer_state'][dest_mac_bytes] = {"status": "waiting_ack"}
                    
                    # Inicia un hilo dedicado para manejar el envío de este archivo.
                    sender_thread = threading.Thread(target=file_sender_thread, args=(s, my_mac, dest_mac_bytes, file_path, app_state))
                    sender_thread.daemon = True
                    sender_thread.start()
                    print(f"Solicitud de envío de '{file_name}' enviada. Esperando aceptación del receptor...")

                except (ValueError, IndexError):
                    print("Comando /send inválido.")
                continue

            elif message.startswith('/accept'):
                parts = message.split(' ', 1)
                if len(parts) < 2:
                    print("Uso incorrecto. Ejemplo: /accept 00:11:22:33:44:55")
                    continue
                
                try:
                    mac_to_accept_bytes = mac_cadena_bits(parts[1])

                    with app_state['pending_file_requests_lock']:
                        if mac_to_accept_bytes not in app_state['pending_file_requests']:
                            print("No hay solicitud de archivo pendiente de esa MAC.")
                            continue
                        # Obtiene y elimina la solicitud de la lista de pendientes.
                        request = app_state['pending_file_requests'].pop(mac_to_accept_bytes)

                    # --- Preparación para recibir el archivo ---
                    with app_state['file_transfer_lock']:
                        file_path = f"recibido_{os.path.basename(request['file_name'])}"
                        # Abre el archivo en modo escritura binaria ('wb').
                        file_handle = open(file_path, "wb")
                        # Pre-asigna el espacio en disco para el archivo. Mejora el rendimiento.
                        file_handle.truncate(request['file_size'])
                        
                        # Registra el estado de la transferencia como "recibiendo".
                        app_state['file_transfer_state'][mac_to_accept_bytes] = {
                            "status": "receiving",
                            "file_name": request['file_name'],
                            "file_size": request['file_size'],
                            "file_handle": file_handle,
                            "received_size": 0
                        }
                    
                    # --- Envío del ACK al emisor ---
                    header = struct.pack('!6s6sH', mac_to_accept_bytes, my_mac, LINK_CHAT_ETHERTYPE)
                    s.send(header + MSG_TYPE_FILE_ACK)
                    print(f"Aceptado. Recibiendo '{request['file_name']}'...")

                except Exception as e:
                    print(f"Error al aceptar archivo: {e}")
                continue
            
            # --- Envío de Mensajes de Chat (Broadcast o Unicast) ---
            header = struct.pack('!6s6sH', dest_mac_bytes, my_mac, LINK_CHAT_ETHERTYPE)
            packet = header + payload
            s.send(packet)

    except PermissionError:
        print("Error: Se necesitan privilegios de administrador. Ejecuta con 'sudo'.")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCerrando el chat...")
    except Exception as e:
        print(f"Ocurrió un error principal: {e}")
    finally:
        # Asegura que el socket se cierre correctamente al salir.
        if s:
            s.close()
        print("Socket cerrado. Adiós.")
        sys.exit(0)

if __name__ == "__main__":
    main()
