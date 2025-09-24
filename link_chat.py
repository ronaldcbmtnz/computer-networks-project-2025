import socket
import sys
import struct
import fcntl
import threading
import time
import os

LINK_CHAT_ETHERTYPE = 0x4C43

# --- Tipos de Mensaje para nuestro protocolo ---
MSG_TYPE_DISCOVERY = b'\x01'
MSG_TYPE_CHAT = b'\x02'
MSG_TYPE_FILE_START = b'\x03'
MSG_TYPE_FILE_DATA = b'\x04'
MSG_TYPE_FILE_END = b'\x05'
MSG_TYPE_FILE_ACK = b'\x06'
# Diccionario para guardar los hosts descubiertos {mac_bytes: "alias"}
# Usaremos un lock para evitar problemas de concurrencia entre hilos
known_hosts = {}
known_hosts_lock = threading.Lock()

# Estado de la transferencia de archivos
file_transfer_state = {}
file_transfer_lock = threading.Lock()

# Para guardar solicitudes de archivos pendientes
pending_file_requests = {}
pending_file_requests_lock = threading.Lock()

# Tamaño del payload de datos para archivos
FILE_CHUNK_SIZE = 1400

def get_mac_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    info = fcntl.ioctl(s.fileno(), 0x8927, struct.pack('256s', ifname[:15].encode('utf-8')))
    return info[18:24]

def format_mac(mac_bytes):
    return ':'.join(f'{b:02x}' for b in mac_bytes)

def parse_mac(mac_str):
    """Convierte una MAC en formato de cadena a bytes."""
    return bytes.fromhex(mac_str.replace(':', ''))

def receive_thread(sock, my_mac):
    while True:
        try:
            raw_data, addr = sock.recvfrom(1518)
            dest_mac, src_mac, eth_type = struct.unpack('!6s6sH', raw_data[:14])
            
            if src_mac == my_mac:
                continue # Ignorar nuestros propios paquetes

            payload = raw_data[14:]
            msg_type = payload[:1]
            msg_data = payload[1:]

            with known_hosts_lock:
                # Siempre que recibimos algo de alguien, lo añadimos/actualizamos en nuestra lista.
                # Esto es descubrimiento pasivo.
                if src_mac not in known_hosts:
                    host_alias = format_mac(src_mac)
                    known_hosts[src_mac] = host_alias
                    print(f"\r\n[+] Nuevo host descubierto: {host_alias}")
                    print("> ", end='', flush=True)

            if msg_type == MSG_TYPE_DISCOVERY:
                # Ya lo hemos añadido, no necesitamos hacer más con los mensajes de descubrimiento.
                pass
            elif msg_type == MSG_TYPE_CHAT:
                sender_alias = known_hosts.get(src_mac, format_mac(src_mac))
                print(f"\r\nMensaje de {sender_alias}: {msg_data.decode('utf-8', errors='ignore')}")
                print("> ", end='', flush=True)
                
             # --- Lógica de recepción de archivos ---
            elif msg_type == MSG_TYPE_FILE_START:
                # Formato: <tamaño_archivo (8 bytes)> <nombre_archivo (utf-8)>
                file_size = struct.unpack('!Q', msg_data[:8])[0]
                file_name = msg_data[8:].decode('utf-8')
                sender_alias = known_hosts.get(src_mac, format_mac(src_mac))
                
                with pending_file_requests_lock:
                    pending_file_requests[src_mac] = {"file_name": file_name, "file_size": file_size}
                
                print(f"\r\n[!] {sender_alias} quiere enviarte '{file_name}' ({file_size} bytes).")
                print(f"    Usa /accept {format_mac(src_mac)} para aceptar.")
                print("> ", end='', flush=True)

            elif msg_type == MSG_TYPE_FILE_ACK:
                # El receptor ha aceptado, podemos empezar a enviar
                with file_transfer_lock:
                    if src_mac in file_transfer_state and file_transfer_state[src_mac].get("status") == "waiting_ack":
                        file_transfer_state[src_mac]["status"] = "sending"
                        print(f"\r\n[*] {known_hosts.get(src_mac, format_mac(src_mac))} aceptó el archivo. Iniciando envío...")
                        print("> ", end='', flush=True)
                    
            elif msg_type == MSG_TYPE_FILE_DATA:
                 with file_transfer_lock:
                    if src_mac in file_transfer_state and file_transfer_state[src_mac].get("status") == "receiving":
                        state = file_transfer_state[src_mac]
                        seq_num = struct.unpack('!I', msg_data[:4])[0]
                        chunk_data = msg_data[4:]
                        
                        offset = seq_num * FILE_CHUNK_SIZE
                        state["file_handle"].seek(offset)
                        state["file_handle"].write(chunk_data)
                        
                        state["received_size"] += len(chunk_data)
                        progress = (state["received_size"] / state["file_size"]) * 100
                        print(f"\rRecibiendo '{state['file_name']}': {progress:.2f}% completado.", end="", flush=True)

            elif msg_type == MSG_TYPE_FILE_END:
                with file_transfer_lock:
                    if src_mac in file_transfer_state and file_transfer_state[src_mac].get("status") == "receiving":
                        state = file_transfer_state[src_mac]
                        state["file_handle"].close()
                        
                        print(f"\r\n[*] Transferencia de '{state['file_name']}' finalizada.")
                        print(f"[*] Archivo guardado como 'recibido_{state['file_name']}'.")
                        print("> ", end='', flush=True)
                        del file_transfer_state[src_mac]
            
        except Exception as e:
            print(f"\nError en el hilo de recepción: {e}")
            break
def file_sender_thread(sock, my_mac, dest_mac_bytes, file_path):
    """ Hilo dedicado para enviar un archivo. """
    try:
        # Esperar a que el receptor acepte
        max_wait = 30
        while max_wait > 0:
            with file_transfer_lock:
                state = file_transfer_state.get(dest_mac_bytes)
                if state and state.get("status") == "sending":
                    break
            time.sleep(1)
            max_wait -= 1
        
        if max_wait == 0:
            print(f"\r\n[!] El receptor no aceptó el archivo a tiempo.")
            print("> ", end='', flush=True)
            with file_transfer_lock:
                if dest_mac_bytes in file_transfer_state:
                    del file_transfer_state[dest_mac_bytes]
            return
        
        # 2. Enviar datos del archivo
        header = struct.pack('!6s6sH', dest_mac_bytes, my_mac, LINK_CHAT_ETHERTYPE)
        with open(file_path, 'rb') as f:
            seq_num = 0
            while True:
                chunk = f.read(FILE_CHUNK_SIZE)
                if not chunk:
                    break
                data_payload = struct.pack('!I', seq_num) + chunk
                sock.send(header + MSG_TYPE_FILE_DATA + data_payload)
                seq_num += 1
                time.sleep(0.002) # Pausa un poco más grande para redes Wi-Fi
        
        # 3. Enviar paquete de fin
        sock.send(header + MSG_TYPE_FILE_END)
        print(f"\r\n[*] Envío de '{os.path.basename(file_path)}' completado.")
        print("> ", end='', flush=True)

    except Exception as e:
        print(f"\nError en el hilo de envío de archivo: {e}")
    finally:
        with file_transfer_lock:
            if dest_mac_bytes in file_transfer_state:
                del file_transfer_state[dest_mac_bytes]        

def discovery_thread(sock, my_mac, iface_name):
    """
    Hilo que envía un paquete de descubrimiento en broadcast cada 10 segundos.
    """
    broadcast_mac = b'\xff\xff\xff\xff\xff\xff'
    header = struct.pack('!6s6sH', broadcast_mac, my_mac, LINK_CHAT_ETHERTYPE)
    packet = header + MSG_TYPE_DISCOVERY

    while True:
        try:
            sock.send(packet)
            time.sleep(10)
        except Exception as e:
            print(f"Error en el hilo de descubrimiento: {e}")
            break

def main():
    try:
        interfaces = [iface[1] for iface in socket.if_nameindex()]
    except Exception:
        print("No se pudieron obtener las interfaces de red. Asegúrate de estar en Linux.")
        sys.exit(1)

    print("Interfaces de red disponibles:")
    for i, iface in enumerate(interfaces):
        print(f"  {i}: {iface}")
    
    try:
        choice = int(input("Elige la interfaz de red a utilizar: "))
        iface_name = interfaces[choice]
    except (ValueError, IndexError):
        print("Selección inválida.")
        sys.exit(1)

    print(f"Interfaz seleccionada: {iface_name}")

    s = None
    try:
        my_mac = get_mac_address(iface_name)
        print(f"Tu dirección MAC es: {format_mac(my_mac)}")

        s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(LINK_CHAT_ETHERTYPE))
        s.bind((iface_name, 0))
        
        # Iniciar hilo de recepción
        receiver = threading.Thread(target=receive_thread, args=(s, my_mac))
        receiver.daemon = True
        receiver.start()

        # Iniciar hilo de descubrimiento
        discoverer = threading.Thread(target=discovery_thread, args=(s, my_mac, iface_name))
        discoverer.daemon = True
        discoverer.start()

        print("\n¡Chat iniciado! Comandos disponibles:")
        print("  /list                - Muestra los usuarios descubiertos.")
        print("  /msg <id> <mensaje>  - Envía un mensaje privado.")
        print("  /send <id> <fpath>   - Envía un archivo a un usuario.")
        print("  /accept <mac>        - Acepta un archivo de un usuario.")
        print("  <mensaje>            - Envía un mensaje a todos (broadcast).")
        print("  quit                 - Salir del chat.")

        while True:
            message = input("> ")
            if message.lower() == 'quit':
                break
            
            dest_mac_bytes = b'\xff\xff\xff\xff\xff\xff' # Broadcast por defecto
            playload = MSG_TYPE_CHAT + message.encode('utf-8')

            if message.startswith('/list'):
                with known_hosts_lock:
                    if not known_hosts:
                        print("No se han descubierto otros usuarios.")
                        continue
                    print("Usuarios descubiertos:")
                    for i, mac_bytes in enumerate(known_hosts.keys()):
                        print(f"  {i}: {format_mac(mac_bytes)}")
                continue

            elif message.startswith('/msg'):
                parts = message.split(' ', 2)
                if len(parts) < 3:
                    print("Uso incorrecto. Ejemplo: /msg 0 Hola que tal")
                    continue
                try:
                    user_id = int(parts[1])
                    with known_hosts_lock:
                        hosts_list = list(known_hosts.keys())
                        if 0 <= user_id < len(hosts_list):
                            dest_mac_bytes = hosts_list[user_id]
                            playload = MSG_TYPE_CHAT + parts[2].encode('utf-8')
                        else:
                            print("ID de usuario inválido.")
                            continue
                except ValueError:
                    print("ID de usuario debe ser un número.")
                    continue
            
            elif message.startswith('/send'):
                parts = message.split(' ', 2)
                if len(parts) < 3:
                    print("Uso incorrecto. Ejemplo: /send 0 /ruta/a/mi/archivo.txt")
                    continue
                try:
                    user_id = int(parts[1])
                    file_path = parts[2]
                    
                    if not os.path.exists(file_path):
                        print(f"Error: El archivo '{file_path}' no existe.")
                        continue

                    with known_hosts_lock:
                        hosts_list = list(known_hosts.keys())
                        if not (0 <= user_id < len(hosts_list)):
                            print("ID de usuario inválido.")
                            continue
                        dest_mac_bytes = hosts_list[user_id]
                     # 1. Enviar paquete de inicio
                    file_size = os.path.getsize(file_path)
                    file_name = os.path.basename(file_path)
                    start_payload = struct.pack('!Q', file_size) + file_name.encode('utf-8')
                    header = struct.pack('!6s6sH', dest_mac_bytes, my_mac, LINK_CHAT_ETHERTYPE)
                    s.send(header + MSG_TYPE_FILE_START + start_payload)
                    
                    with file_transfer_lock:
                        file_transfer_state[dest_mac_bytes] = {"status": "waiting_ack"}
                    
                    # Iniciar hilo de envío que esperará el ACK
                    sender_thread = threading.Thread(target=file_sender_thread, args=(s, my_mac, dest_mac_bytes, file_path))
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
                    mac_to_accept_str = parts[1]
                    mac_to_accept_bytes = parse_mac(mac_to_accept_str)

                    with pending_file_requests_lock:
                        if mac_to_accept_bytes not in pending_file_requests:
                            print("No hay solicitud de archivo pendiente de esa MAC.")
                            continue
                        request = pending_file_requests.pop(mac_to_accept_bytes)

                    # Preparar para recibir
                    with file_transfer_lock:
                        file_path = f"recibido_{os.path.basename(request['file_name'])}"
                        file_handle = open(file_path, "wb")
                        file_handle.truncate(request['file_size'])
                        
                        file_transfer_state[mac_to_accept_bytes] = {
                            "status": "receiving",
                            "file_name": request['file_name'],
                            "file_size": request['file_size'],
                            "file_handle": file_handle,
                            "received_size": 0
                        }
                    
                    # Enviar ACK al emisor
                    header = struct.pack('!6s6sH', mac_to_accept_bytes, my_mac, LINK_CHAT_ETHERTYPE)
                    s.send(header + MSG_TYPE_FILE_ACK)
                    print(f"Aceptado. Recibiendo '{request['file_name']}'...")

                except Exception as e:
                    print(f"Error al aceptar archivo: {e}")
                continue
            
            header = struct.pack('!6s6sH', dest_mac_bytes, my_mac, LINK_CHAT_ETHERTYPE)
            packet = header + playload
            s.send(packet)


    except PermissionError:
        print("Error: Se necesitan privilegios de administrador. Ejecuta con 'sudo'.")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCerrando el chat...")
    except Exception as e:
        print(f"Ocurrió un error principal: {e}")
    finally:
        if s:
            s.close()
        print("Socket cerrado. Adiós.")
        sys.exit(0)

if __name__ == "__main__":
    main()