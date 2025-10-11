# --- Configuración del Protocolo ---

# EtherType es un número de 16 bits en la cabecera Ethernet.
# Se usa para indicar qué protocolo está encapsulado en la trama.
# Hemos elegido 0x88B5 para identificar nuestro protocolo Link-Chat.
LINK_CHAT_ETHERTYPE = 0x88B5

# --- Tipos de Mensaje del Protocolo ---
# Usamos un solo byte al inicio de nuestro payload para definir el tipo de mensaje.

# Mensaje para descubrir a otros usuarios en la red (broadcast).
MSG_TYPE_DISCOVERY = 1
# Mensaje de respuesta al descubrimiento.
MSG_TYPE_DISCOVERY_RESP = 2
# Mensaje para una conversación de chat normal.
MSG_TYPE_CHAT = 3
# Mensaje para iniciar una solicitud de transferencia de archivo.
MSG_TYPE_FILE_START = 4
# Mensaje para confirmar que el receptor acepta la transferencia del archivo.
MSG_TYPE_FILE_ACK = 5
# Mensaje que contiene un trozo (chunk) de un archivo.
MSG_TYPE_FILE_DATA = 6
# Mensaje para indicar que la transferencia de un archivo ha finalizado.
MSG_TYPE_FILE_END = 7

# --- Configuración de Transferencia de Archivos ---

# Define el tamaño máximo en bytes de cada trozo de archivo que enviamos.
# El tamaño de trama Ethernet estándar es 1518 bytes. Restamos la cabecera (14),
# el tipo de mensaje (1), el número de secuencia (4) y un margen de seguridad.
FILE_CHUNK_SIZE = 1024

# Define el tiempo en segundos que el emisor esperará la aceptación del receptor
# antes de cancelar la solicitud de envío de archivo.
FILE_TRANSFER_TIMEOUT = 30