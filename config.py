# --- Configuración del Protocolo ---

# EtherType es un número de 16 bits en la cabecera Ethernet.
# Se usa para indicar qué protocolo está encapsulado en la trama.
# Hemos elegido 0x4C43 (las letras 'LC' en ASCII) para identificar nuestro protocolo Link-Chat.
LINK_CHAT_ETHERTYPE = 0x4C43

# --- Tipos de Mensaje del Protocolo ---
# Usamos un solo byte al inicio de nuestro payload para definir el tipo de mensaje.

# Mensaje para descubrir a otros usuarios en la red (broadcast).
MSG_TYPE_DISCOVERY = b'\x01'
# Mensaje para una conversación de chat normal.
MSG_TYPE_CHAT = b'\x02'
# Mensaje para iniciar una solicitud de transferencia de archivo.
MSG_TYPE_FILE_START = b'\x03'
# Mensaje que contiene un trozo (chunk) de un archivo.
MSG_TYPE_FILE_DATA = b'\x04'
# Mensaje para indicar que la transferencia de un archivo ha finalizado.
MSG_TYPE_FILE_END = b'\x05'
# Mensaje para confirmar que el receptor acepta la transferencia del archivo.
MSG_TYPE_FILE_ACK = b'\x06'

# --- Configuración de Transferencia de Archivos ---

# Define el tamaño máximo en bytes de cada trozo de archivo que enviamos.
# El tamaño de trama Ethernet estándar es 1518 bytes. Restamos la cabecera (14),
# el tipo de mensaje (1), el número de secuencia (4) y un margen de seguridad.
FILE_CHUNK_SIZE = 1400

# Define el tiempo en segundos que el emisor esperará la aceptación del receptor
# antes de cancelar la solicitud de envío de archivo.
FILE_TRANSFER_TIMEOUT = 30