import socket
import struct
import time
import os
from config import *
from utils import mac_bits_cadena

def receive_thread(sock, my_mac, state):
    """
    Hilo que escucha continuamente paquetes entrantes y los procesa.
    Args:
        sock (socket): El socket RAW en el que escuchar.
        my_mac (bytes): La dirección MAC de este host para ignorar sus propios paquetes.
        state (dict): El diccionario de estado compartido de la aplicación.
    """
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
            if msg_type == MSG_TYPE_DISCOVERY:
                # No se necesita hacer nada más, el descubrimiento pasivo ya lo añadió.
                pass
            
            elif msg_type == MSG_TYPE_CHAT:
                # Obtiene el alias del emisor. Si no existe, usa la MAC formateada.
                sender_alias = state['known_hosts'].get(src_mac, mac_bits_cadena(src_mac))
                # Decodifica el mensaje a texto (UTF-8) e lo imprime.
                print(f"\r\nMensaje de {sender_alias}: {msg_data.decode('utf-8', errors='ignore')}")
                print("> ", end='', flush=True)
                
            elif msg_type == MSG_TYPE_FILE_START:
                # Desempaqueta el tamaño del archivo (8 bytes, long long) y el nombre.
                file_size = struct.unpack('!Q', msg_data[:8])[0]
                file_name = msg_data[8:].decode('utf-8')
                sender_alias = state['known_hosts'].get(src_mac, mac_bits_cadena(src_mac))
                
                # Guarda la solicitud en la lista de pendientes para que el usuario pueda aceptarla.
                with state['pending_file_requests_lock']:
                    state['pending_file_requests'][src_mac] = {"file_name": file_name, "file_size": file_size}
                
                # Notifica al usuario sobre la solicitud entrante.
                print(f"\r\n[!] {sender_alias} quiere enviarte '{file_name}' ({file_size} bytes).")
                print(f"    Usa /accept {mac_bits_cadena(src_mac)} para aceptar.")
                print("> ", end='', flush=True)

            elif msg_type == MSG_TYPE_FILE_ACK:
                # El receptor ha aceptado el archivo.
                with state['file_transfer_lock']:
                    # Comprueba si estábamos esperando esta confirmación.
                    if src_mac in state['file_transfer_state'] and state['file_transfer_state'][src_mac].get("status") == "waiting_ack":
                        # Cambia el estado a "enviando" para que el hilo emisor comience la transferencia.
                        state['file_transfer_state'][src_mac]["status"] = "sending"
                        print(f"\r\n[*] {state['known_hosts'].get(src_mac, mac_bits_cadena(src_mac))} aceptó el archivo. Iniciando envío...")
                        print("> ", end='', flush=True)
                    
            elif msg_type == MSG_TYPE_FILE_DATA:
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

            elif msg_type == MSG_TYPE_FILE_END:
                # El emisor nos notifica que ha terminado de enviar trozos.
                with state['file_transfer_lock']:
                    if src_mac in state['file_transfer_state'] and state['file_transfer_state'][src_mac].get("status") == "receiving":
                        transfer = state['file_transfer_state'][src_mac]
                        # Cierra el manejador del archivo.
                        transfer["file_handle"].close()
                        
                        print(f"\r\n[*] Transferencia de '{transfer['file_name']}' finalizada.")
                        print(f"[*] Archivo guardado como 'recibido_{transfer['file_name']}'.")
                        print("> ", end='', flush=True)
                        # Limpia el estado de esta transferencia.
                        del state['file_transfer_state'][src_mac]
            
        except Exception as e:
            # En caso de un error grave, se imprime y el hilo termina.
            print(f"\nError en el hilo de recepción: {e}")
            break

def file_sender_thread(sock, my_mac, dest_mac_bytes, file_path, state):
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
        print(f"\r\n[*] Envío de '{os.path.basename(file_path)}' completado.")
        print("> ", end='', flush=True)

    except Exception as e:
        print(f"\nError en el hilo de envío de archivo: {e}")
    finally:
        # Asegura que el estado de la transferencia se limpie, incluso si hay un error.
        with state['file_transfer_lock']:
            if dest_mac_bytes in state['file_transfer_state']:
                del state['file_transfer_state'][dest_mac_bytes]        

def discovery_thread(sock, my_mac):
    """
    Hilo que envía un paquete de descubrimiento en broadcast cada 10 segundos.
    """
    # La dirección MAC de broadcast es todo F's.
    broadcast_mac = b'\xff\xff\xff\xff\xff\xff'
    # Prepara la cabecera y el payload del paquete de descubrimiento.
    header = struct.pack('!6s6sH', broadcast_mac, my_mac, LINK_CHAT_ETHERTYPE)
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