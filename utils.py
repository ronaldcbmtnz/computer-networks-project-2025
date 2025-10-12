import socket
import fcntl
import struct

def obtener_direccion_mac(ifname):
    """
    Obtiene la dirección MAC en formato de bytes para una interfaz de red dada.
    Args:
        ifname (str): El nombre de la interfaz (ej: 'eth0', 'wlan0').
    Returns:
        bytes: La dirección MAC de 6 bytes.
    """
    # Creamos un socket temporal para poder hacer llamadas al sistema.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # fcntl.ioctl permite realizar operaciones de control en un dispositivo.
    # 0x8927 (SIOCGIFHWADDR) es la llamada para obtener la dirección de hardware.
    # Empaquetamos el nombre de la interfaz en una estructura de 256 bytes como espera el sistema.
    info = fcntl.ioctl(s.fileno(), 0x8927, struct.pack('256s', ifname[:15].encode('utf-8')))
    # La dirección MAC se encuentra en los bytes del 18 al 24 de la estructura devuelta.
    return info[18:24]

def mac_bits_cadena(mac_bytes):
    """
    Convierte una dirección MAC de formato de bytes a una cadena legible.
    Ejemplo: b'\x08\x00\x27...' -> "08:00:27:..."
    Args:
        mac_bytes (bytes): La dirección MAC de 6 bytes.
    Returns:
        str: La MAC formateada como cadena.
    """
    # Itera sobre cada byte, lo formatea como un número hexadecimal de 2 dígitos (con cero a la izquierda)
    # y los une con dos puntos.
    return ':'.join(f'{b:02x}' for b in mac_bytes)

def mac_cadena_bits(mac_str):
    """
    Convierte una dirección MAC en formato de cadena a su representación en bytes.
    Ejemplo: "08:00:27:..." -> b'\x08\x00\x27...'
    Args:
        mac_str (str): La MAC formateada como cadena.
    Returns:
        bytes: La dirección MAC de 6 bytes.
    """
    # Primero, elimina los dos puntos de la cadena.
    # Luego, convierte la cadena hexadecimal resultante en un objeto de bytes.
    return bytes.fromhex(mac_str.replace(':', ''))