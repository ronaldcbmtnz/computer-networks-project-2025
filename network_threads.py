import socket
import struct
import time
import os
import shutil  # <-- AÑADE ESTA IMPORTACIÓN
from config import *
from utils import mac_bits_cadena

def receive_thread(sock, my_mac, state, custom_handler=None):
    """
    Hilo que escucha continuamente paquetes entrantes y los procesa.
    Args:
        sock (socket): El socket RAW en el que escuchar.
        my_mac (bytes): La dirección MAC de este host para ignorar sus propios paquetes.
        state (dict): El diccionario de estado compartido de la aplicación.
        custom_handler (callable, optional): Función personalizada para manejar mensajes.
    """
    # Convertir las constantes de tipo de mensaje a bytes para comparación
    MSG_TYPE_DISCOVERY_B = struct.pack('!B', MSG_TYPE_DISCOVERY)
    MSG_TYPE_CHAT_B = struct.pack('!B', MSG_TYPE_CHAT)
    MSG_TYPE_FILE_START_B = struct.pack('!B', MSG_TYPE_FILE_START)
    MSG_TYPE_FILE_ACK_B = struct.pack('!B', MSG_TYPE_FILE_ACK)
    MSG_TYPE_FILE_DATA_B = struct.pack('!B', MSG_TYPE_FILE_DATA)
    MSG_TYPE_FILE_END_B = struct.pack('!B', MSG_TYPE_FILE_END)

    # Verificación recomendada al inicio de receive_thread
    required_keys = ['known_hosts', 'known_hosts_lock', 'file_transfer_state', 
                     'file_transfer_lock', 'pending_file_requests', 'pending_file_requests_lock']
    for key in required_keys:
        if key not in state:
            print(f"Error: Falta la clave '{key}' en el diccionario de estado")
            return

    try:
        while True:
            try:
                # Espera y recibe datos del socket. 1518 es el tamaño máximo de una trama Ethernet.
                raw_data, addr = sock.recvfrom(1518)
                
                # Desempaqueta la cabecera Ethernet (14 bytes): MAC destino, MAC origen, EtherType.
                dest_mac, src_mac, eth_type = struct.unpack('!6s6sH', raw_data[:14])
                
                # Ignora los paquetes que nosotros mismos hemos enviado.
                if src_mac == my_mac:
                    continue

                # El payload son los datos que vienen después de la cabecera Ethernet.
                payload = raw_data[14:]
                # El primer byte del payload es nuestro tipo de mensaje.
                msg_type = payload[:1]
                # El resto son los datos del mensaje.
                msg_data = payload[1:]

                # Si hay un manejador personalizado, delega el procesamiento.
                if custom_handler:
                    try:
                        custom_handler(src_mac, msg_type, msg_data)
                    except Exception as handler_error:
                        print(f"Error en custom_handler: {handler_error}")
                    continue

                # --- Lógica de Descubrimiento Pasivo ---
                # Usamos un lock para acceder de forma segura al diccionario compartido 'known_hosts'.
                with state['known_hosts_lock']:
                    # Si la MAC de origen no está en nuestra lista de hosts conocidos...
                    if src_mac not in state['known_hosts']:
                        # La añadimos usando su MAC formateada como alias inicial.
                        state['known_hosts'][src_mac] = mac_bits_cadena(src_mac)
                        # Imprimimos una notificación en la consola del usuario.
                        print(f"\r\n[+] Nuevo host descubierto: {mac_bits_cadena(src_mac)}")
                        print("> ", end='', flush=True)

                # --- Procesamiento de Mensajes según su Tipo ---
                if msg_type == MSG_TYPE_DISCOVERY_B:
                    # No se necesita hacer nada más, el descubrimiento pasivo ya lo añadió.
                    pass
                
                elif msg_type == MSG_TYPE_CHAT_B:
                    # Obtiene el alias del emisor. Si no existe, usa la MAC formateada.
                    sender_alias = state['known_hosts'].get(src_mac, mac_bits_cadena(src_mac))
                    # Decodifica el mensaje a texto (UTF-8) e lo imprime.
                    print(f"\r\nMensaje de {sender_alias}: {msg_data.decode('utf-8', errors='ignore')}")
                    print("> ", end='', flush=True)
                    
                elif msg_type == MSG_TYPE_FILE_START_B:
                    # Desempaqueta el tamaño del archivo (8 bytes, long long) y el nombre.
                    file_size = struct.unpack('!Q', msg_data[:8])[0]
                    
                    # Decodifica el nombre del archivo y elimina cualquier byte nulo al final.
                    file_name_bytes = msg_data[8:].strip(b'\x00')
                    file_name = file_name_bytes.decode('utf-8')
                    
                    # Código recomendado para sanitizar nombres de archivo
                    import os.path
                    file_name = os.path.basename(file_name)  # Elimina cualquier ruta
                    file_name = file_name.replace('/', '_').replace('\\', '_')  # Reemplaza caracteres peligrosos
                    
                    sender_alias = state['known_hosts'].get(src_mac, mac_bits_cadena(src_mac))
                    
                    # Guarda la solicitud en la lista de pendientes para que el usuario pueda aceptarla.
                    with state['pending_file_requests_lock']:
                        state['pending_file_requests'][src_mac] = {"file_name": file_name, "file_size": file_size}
                    
                    # Notifica al usuario sobre la solicitud entrante.
                    print(f"\r\n[!] {sender_alias} quiere enviarte '{file_name}' ({file_size} bytes).")
                    print(f"    Usa /accept {mac_bits_cadena(src_mac)} para aceptar.")
                    print("> ", end='', flush=True)

                elif msg_type == MSG_TYPE_FILE_ACK_B:
                    # El receptor ha aceptado el archivo.
                    with state['file_transfer_lock']:
                        # Comprueba si estábamos esperando esta confirmación.
                        if src_mac in state['file_transfer_state'] and state['file_transfer_state'][src_mac].get("status") == "waiting_ack":
                            # Cambia el estado a "enviando" para que el hilo emisor comience la transferencia.
                            state['file_transfer_state'][src_mac]["status"] = "sending"
                            print(f"\r\n[*] {state['known_hosts'].get(src_mac, mac_bits_cadena(src_mac))} aceptó el archivo. Iniciando envío...")
                            print("> ", end='', flush=True)
                        
                elif msg_type == MSG_TYPE_FILE_DATA_B:
                    # Estamos recibiendo un trozo de archivo.
                    with state['file_transfer_lock']:
                        # Comprueba si estamos en modo "recibiendo" desde esta MAC.
                        if src_mac in state['file_transfer_state'] and state['file_transfer_state'][src_mac].get("status") == "receiving":
                            transfer = state['file_transfer_state'][src_mac]
                            # Desempaqueta el número de secuencia (4 bytes, integer).
                            seq_num = struct.unpack('!I', msg_data[:4])[0]
                            # El resto son los datos del trozo.
                            chunk_data = msg_data[4:]
                            
                            # Calcula la posición en el archivo donde escribir este trozo.
                            offset = seq_num * FILE_CHUNK_SIZE
                            transfer["file_handle"].seek(offset)
                            transfer["file_handle"].write(chunk_data)
                            
                            # Actualiza el progreso de la descarga.
                            transfer["received_size"] += len(chunk_data)
                            progress = (transfer["received_size"] / transfer["file_size"]) * 100
                            # Imprime el progreso en la misma línea para no saturar la consola.
                            print(f"\rRecibiendo '{transfer['file_name']}': {progress:.2f}% completado.", end="", flush=True)

                elif msg_type == MSG_TYPE_FILE_END_B:
                    with state['file_transfer_lock']:
                        if src_mac in state['file_transfer_state']:
                            transfer = state['file_transfer_state'][src_mac]
                            # Cierra el manejador del archivo.
                            transfer['file_handle'].close()
                            
                            # Usar la ruta guardada por la interfaz, si está disponible
                            final_file_path = transfer.get('save_path', f"recibido_{transfer['file_name']}")
                            print(f"\r\n[+] Transferencia de '{transfer['file_name']}' completada.")
                            
                            # --- LÓGICA PARA DESCOMPRIMIR ---
                            # Solo descomprimir si no es un archivo seleccionado por el usuario
                            if 'save_path' not in transfer and final_file_path.endswith('.zip'):
                                print(f"El archivo es un zip. Descomprimiendo...")
                                try:
                                    # Extrae el contenido en una carpeta con el mismo nombre (sin .zip).
                                    extract_dir = final_file_path[:-4]
                                    shutil.unpack_archive(final_file_path, extract_dir)
                                    print(f"Carpeta extraída en: '{extract_dir}'")
                                    # Borra el archivo zip después de extraerlo.
                                    os.remove(final_file_path)
                                except Exception as e:
                                    print(f"Error al descomprimir: {e}")

                            del state['file_transfer_state'][src_mac]
                    print("> ", end='', flush=True)
                
            except Exception as e:
                print(f"Error en recepción de paquete: {e}")
                # Pequeña pausa para evitar consumir CPU al 100% en caso de error repetido
                time.sleep(0.1)
    except Exception as e:
        print(f"Error fatal en receive_thread: {e}")

def file_sender_thread(sock, src_mac, dst_mac, file_path, file_name, state):
    """Thread para enviar un archivo a un host"""
    try:
        # Verificar que el archivo existe
        if not os.path.exists(file_path):
            print(f"El archivo {file_path} no existe")
            return
            
        # Obtener tamaño del archivo
        file_size = os.path.getsize(file_path)
        
        # Registrar en estado
        with state['file_transfer_lock']:
            state['file_transfer_state'][dst_mac] = {
                "file_path": file_path,
                "file_name": file_name,
                "file_size": file_size,
                "status": "waiting_ack",
                "sent_size": 0
            }
        
        # Enviar solicitud de archivo
        eth_header = dst_mac + src_mac + struct.pack('!H', LINK_CHAT_ETHERTYPE)
        msg_header = struct.pack('!B', MSG_TYPE_FILE_START)  # Empaquetar como byte
        file_info = struct.pack('!Q', file_size) + file_name.encode('utf-8')
        packet = eth_header + msg_header + file_info
        sock.send(packet)
        
        # Esperar confirmación (esto debería tener un timeout)
        start_time = time.time()
        while time.time() - start_time < 60:  # 1 minuto de timeout
            with state['file_transfer_lock']:
                if dst_mac in state['file_transfer_state']:
                    if state['file_transfer_state'][dst_mac]["status"] == "sending":
                        break
            time.sleep(0.1)
        else:
            # Si pasa 1 minuto sin respuesta, cancelar
            with state['file_transfer_lock']:
                if dst_mac in state['file_transfer_state']:
                    del state['file_transfer_state'][dst_mac]
            print(f"Timeout esperando confirmación para enviar {file_name}")
            return
        
        # Enviar el archivo en trozos
        with open(file_path, 'rb') as f:
            seq_num = 0
            while True:
                chunk = f.read(FILE_CHUNK_SIZE)
                if not chunk:
                    break
                    
                # Enviar trozo
                eth_header = dst_mac + src_mac + struct.pack('!H', LINK_CHAT_ETHERTYPE)
                msg_header = struct.pack('!B', MSG_TYPE_FILE_DATA)  # Empaquetar como byte
                chunk_info = struct.pack('!I', seq_num) + chunk
                packet = eth_header + msg_header + chunk_info
                sock.send(packet)
                
                # Actualizar progreso
                with state['file_transfer_lock']:
                    if dst_mac in state['file_transfer_state']:
                        state['file_transfer_state'][dst_mac]["sent_size"] += len(chunk)
                        progress = (state['file_transfer_state'][dst_mac]["sent_size"] / file_size) * 100
                        print(f"\rEnviando '{file_name}': {progress:.2f}% completado.", end="", flush=True)
                
                seq_num += 1
                time.sleep(0.001)  # Pequeña pausa para no saturar la red
                
        # Enviar fin de transferencia
        eth_header = dst_mac + src_mac + struct.pack('!H', LINK_CHAT_ETHERTYPE)
        msg_header = struct.pack('!B', MSG_TYPE_FILE_END)  # Empaquetar como byte
        packet = eth_header + msg_header
        sock.send(packet)
        
        print(f"\nTransferencia de '{file_name}' completada.")
        
        # Actualizar estado
        with state['file_transfer_lock']:
            if dst_mac in state['file_transfer_state']:
                del state['file_transfer_state'][dst_mac]
                
    except Exception as e:
        print(f"Error en file_sender_thread: {e}")
        # Limpiar estado en caso de error
        with state['file_transfer_lock']:
            if dst_mac in state['file_transfer_state']:
                del state['file_transfer_state'][dst_mac]

def discovery_thread(sock, my_mac):
    """
    Hilo que envía un paquete de descubrimiento en broadcast cada 10 segundos.
    """
    # La dirección MAC de broadcast es todo F's.
    broadcast_mac = b'\xff\xff\xff\xff\xff\xff'
    # Prepara la cabecera y el payload del paquete de descubrimiento.
    header = struct.pack('!6s6sH', broadcast_mac, my_mac, LINK_CHAT_ETHERTYPE)
    packet = header + struct.pack('!B', MSG_TYPE_DISCOVERY)  # Empaquetar como byte

    while True:
        try:
            # Envía el paquete de descubrimiento a toda la red local.
            sock.send(packet)
            # Duerme durante 10 segundos antes de enviar el siguiente.
            time.sleep(10)
        except Exception as e:
            print(f"Error en el hilo de descubrimiento: {e}")
            break