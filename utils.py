import socket
import fcntl
import struct

def obtener_direccion_mac(interfaz):
    """Obtiene la dirección MAC de una interfaz de red como bytes"""
    try:
        with open(f'/sys/class/net/{interfaz}/address', 'r') as f:
            mac_str = f.read().strip()
        
        # Validar formato de MAC
        if not all(c in '0123456789abcdefABCDEF:' for c in mac_str) or mac_str.count(':') != 5:
            raise ValueError(f"Formato de MAC inválido: {mac_str}")
            
        return mac_cadena_bits(mac_str)
    except Exception as e:
        print(f"Error al obtener MAC de {interfaz}: {e}")
        return None

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