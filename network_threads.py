import socket
import struct
import time
import os
import shutil
from config import *  # <-- Esta línea ya importa todo, incluyendo la nueva constante
from utils import mac_bits_cadena

def receive_thread(sock, my_mac, state):
    """
    Hilo que escucha continuamente paquetes entrantes y los procesa.
    Args:
        sock (socket): El socket RAW en el que escuchar.
        my_mac (bytes): La dirección MAC de este host para ignorar sus propios paquetes.
        state (dict): El diccionario de estado compartido de la aplicación.
    """
    gui_queue = state['gui_queue'] # Obtenemos la cola de la GUI

    while True:
        try:
            raw_data, addr = sock.recvfrom(1518)
            
            dest_mac, src_mac, eth_type = struct.unpack('!6s6sH', raw_data[:14])
            
            if src_mac == my_mac:
                continue

            payload = raw_data[14:]
            msg_type = payload[:1]

            # --- Lógica de procesamiento de mensajes ---
            
            # Añadir host si es nuevo
            is_new_host = False
            with state['known_hosts_lock']:
                if src_mac not in state['known_hosts']:
                    state['known_hosts'][src_mac] = "Nuevo Usuario"
                    is_new_host = True
            
            if is_new_host:
                # Notificamos a la GUI que hay un nuevo usuario
                gui_queue.put(('new_user', src_mac))

            if msg_type == MSG_TYPE_DISCOVERY:
                pass

            elif msg_type == MSG_TYPE_CHAT:
                try:
                    # Decodificamos el mensaje y lo limpiamos con .strip()
                    message_text = payload[1:].decode('utf-8').strip()
                    
                    sender_mac_str = mac_bits_cadena(src_mac)
                    
                    # Determinar si es un mensaje privado o broadcast
                    if dest_mac == my_mac:
                        # Es un mensaje privado para nosotros
                        display_text = f"[Privado de {sender_mac_str}]: {message_text}"
                    else:
                        # Es un mensaje broadcast
                        display_text = f"[{sender_mac_str}]: {message_text}"
                    
                    # Ponemos el mensaje formateado en la cola
                    gui_queue.put(('chat_message', display_text))

                except UnicodeDecodeError:
                    sender_mac_str = mac_bits_cadena(src_mac)
                    gui_queue.put(('chat_message', f"[{sender_mac_str}]: [mensaje con formato inválido]"))
            
            # 5. Añadir lógica para manejar solicitudes de archivo
            elif msg_type == MSG_TYPE_FILE_START:
                try:
                    # Desempaquetar la bandera (1 byte) y el tamaño (8 bytes)
                    is_folder_flag = payload[1:2]
                    file_size = struct.unpack('!Q', payload[2:10])[0]
                    
                    # El resto del payload contiene el nombre del archivo y el delimitador
                    file_name_payload = payload[10:]
                    
                    # Encontrar la posición del delimitador nulo
                    null_terminator_pos = file_name_payload.find(b'\x00')
                    
                    if null_terminator_pos == -1:
                        raise ValueError("Paquete FILE_START malformado, sin delimitador de nombre.")

                    # Decodificar solo la parte del nombre del archivo
                    file_name = file_name_payload[:null_terminator_pos].decode('utf-8')
                    
                    # Poner el evento en la cola, incluyendo la bandera
                    gui_queue.put(('file_request', src_mac, file_name, file_size, is_folder_flag == b'\x01'))

                except Exception as e:
                    gui_queue.put(('error', f"Error al procesar solicitud de archivo: {e}"))
            
            # 5. Añadir lógica para manejar el ACK de archivo
            elif msg_type == MSG_TYPE_FILE_ACK:
                # El destinatario ha aceptado nuestro archivo.
                # Actualizamos el estado para que file_sender_thread pueda empezar a enviar.
                with state['file_transfer_lock']:
                    if src_mac in state['file_transfer_state']:
                        state['file_transfer_state'][src_mac]['status'] = 'sending'
            
            # 1. Añadir lógica para recibir trozos de archivo
            elif msg_type == MSG_TYPE_FILE_DATA:
                try:
                    with state['pending_file_requests_lock']:
                        if src_mac in state['pending_file_requests']:
                            request = state['pending_file_requests'][src_mac]
                            file_path = request['path']
                            
                            # El payload es el número de secuencia (4 bytes) + datos
                            chunk_data = payload[5:] # Ignoramos el seq_num por ahora
                            
                            # Abrir el archivo en modo 'append binary' y escribir el trozo
                            with open(file_path, 'ab') as f:
                                f.write(chunk_data)
                            
                            # Actualizar el tamaño descargado
                            request['downloaded_size'] += len(chunk_data)
                except Exception as e:
                    state['gui_queue'].put(('error', f"Error al recibir trozo de archivo: {e}"))

            # 2. Añadir lógica para finalizar la transferencia
            elif msg_type == MSG_TYPE_FILE_END:
                try:
                    with state['pending_file_requests_lock']:
                        if src_mac in state['pending_file_requests']:
                            request = state['pending_file_requests'][src_mac]
                            file_name = request['file_name']
                            file_path = request['path']
                            is_folder = request.get('is_folder', False) # Obtenemos la bandera

                            # Lógica de descompresión
                            if is_folder and os.path.exists(file_path):
                                try:
                                    # Descomprimir el archivo en el directorio actual
                                    shutil.unpack_archive(file_path, '.')
                                    # Borrar el archivo zip temporal
                                    os.remove(file_path)
                                    # Notificar a la GUI con el nombre original de la carpeta
                                    original_folder_name = file_name.replace('.zip', '')
                                    state['gui_queue'].put(('folder_received', original_folder_name))
                                except Exception as unpack_e:
                                    state['gui_queue'].put(('error', f"No se pudo descomprimir {file_name}: {unpack_e}"))
                            else:
                                # Notificar a la GUI que la descarga del archivo terminó
                                state['gui_queue'].put(('file_received', file_name))

                            # CAMBIAR EL PROPIETARIO DEL ARCHIVO
                            # Obtener el usuario que ejecutó sudo, si existe.
                            sudo_user = os.environ.get('SUDO_USER')
                            if sudo_user and os.path.exists(file_path):
                                try:
                                    # shutil.chown cambia el propietario (user:group)
                                    shutil.chown(file_path, user=sudo_user, group=sudo_user)
                                except Exception as chown_e:
                                    state['gui_queue'].put(('error', f"No se pudo cambiar el dueño de {file_name}: {chown_e}"))

                            # ENVIAR CONFIRMACIÓN DE VUELTA AL EMISOR
                            display_name = original_folder_name if is_folder else file_name
                            confirmation_message = f"[Sistema] El elemento '{display_name}' fue recibido correctamente.".encode('utf-8')
                            eth_header = struct.pack('!6s6sH', src_mac, my_mac, LINK_CHAT_ETHERTYPE)
                            packet = eth_header + MSG_TYPE_CHAT + confirmation_message
                            sock.send(packet)

                            # Limpiar la solicitud pendiente
                            del state['pending_file_requests'][src_mac]
                except Exception as e:
                    state['gui_queue'].put(('error', f"Error al finalizar archivo: {e}"))

        except Exception as e:
            gui_queue.put(('error', f"Error en el hilo receptor: {e}"))

def file_sender_thread(sock, my_mac, dest_mac_bytes, file_path, state, is_temp_zip=False):
    """
    Hilo dedicado para enviar un archivo, gestionando la espera del ACK y el envío por trozos.
    """
    try:
        # --- 1. Esperar la Aceptación (ACK) ---
        wait_time = FILE_TRANSFER_TIMEOUT
        while wait_time > 0:
            with state['file_transfer_lock']:
                transfer = state['file_transfer_state'].get(dest_mac_bytes)
                # Si el estado ha cambiado a "sending", el receptor aceptó.
                if transfer and transfer.get("status") == "sending":
                    break
            # Espera 1 segundo antes de volver a comprobar.
            time.sleep(1)
            wait_time -= 1
        
        # Si el tiempo se agota y no hay ACK, cancela la transferencia.
        if wait_time == 0:
            print(f"\r\n[!] El receptor no aceptó el archivo a tiempo.")
            print("> ", end='', flush=True)
            with state['file_transfer_lock']:
                if dest_mac_bytes in state['file_transfer_state']:
                    del state['file_transfer_state'][dest_mac_bytes]
            return
        
        # --- 2. Enviar Datos del Archivo ---
        # Prepara la cabecera Ethernet, que será la misma para todos los paquetes de esta transferencia.
        header = struct.pack('!6s6sH', dest_mac_bytes, my_mac, LINK_CHAT_ETHERTYPE)
        # Abre el archivo en modo lectura binaria ('rb').
        with open(file_path, 'rb') as f:
            seq_num = 0
            while True:
                # Lee un trozo del archivo del tamaño configurado.
                chunk = f.read(FILE_CHUNK_SIZE)
                # Si no hay más datos para leer, hemos terminado.
                if not chunk:
                    break
                # Construye el payload: tipo de mensaje, número de secuencia y los datos del trozo.
                data_payload = MSG_TYPE_FILE_DATA + struct.pack('!I', seq_num) + chunk
                # Envía el paquete completo.
                sock.send(header + data_payload)
                # Incrementa el número de secuencia para el siguiente paquete.
                seq_num += 1
                # Pequeña pausa para no saturar la red, especialmente en Wi-Fi.
                time.sleep(0.002)
        
        # --- 3. Enviar Paquete de Fin ---
        # Envía un último paquete para notificar que la transferencia ha terminado.
        sock.send(header + MSG_TYPE_FILE_END)
        
    except Exception as e:
        # Usamos la cola de la GUI para mostrar errores en el hilo de envío
        state['gui_queue'].put(('error', f"Error durante el envío de '{os.path.basename(file_path)}': {e}"))
    finally:
        # --- 4. LIMPIEZA ---
        # Si el archivo enviado era un zip temporal, lo borramos.
        if is_temp_zip and os.path.exists(file_path):
            try:
                os.remove(file_path)
                state['gui_queue'].put(('chat_message', f"[Sistema] Archivo temporal '{os.path.basename(file_path)}' eliminado."))
            except Exception as e:
                state['gui_queue'].put(('error', f"No se pudo eliminar el archivo temporal: {e}"))
        
        # Elimina la entrada de transferencia del estado de la aplicación.
        with state['file_transfer_lock']:
            if dest_mac_bytes in state['file_transfer_state']:
                del state['file_transfer_state'][dest_mac_bytes]

def discovery_thread(sock, my_mac):
    """
    Hilo que envía un paquete de descubrimiento en broadcast cada 10 segundos.
    """
    # La dirección MAC de broadcast ahora se importa desde config.py
    # Prepara la cabecera y el payload del paquete de descubrimiento.
    header = struct.pack('!6s6sH', BROADCAST_MAC, my_mac, LINK_CHAT_ETHERTYPE)
    packet = header + MSG_TYPE_DISCOVERY

    while True:
        try:
            # Envía el paquete de descubrimiento a toda la red local.
            sock.send(packet)
            # Duerme durante 10 segundos antes de enviar el siguiente.
            time.sleep(10)
        except Exception as e:
            print(f"Error en el hilo de descubrimiento: {e}")
            break