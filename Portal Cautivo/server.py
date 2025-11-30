"""
server.py
Servidor HTTP básico implementado con sockets para el portal cautivo.
Maneja los endpoints principales: /, /login, /register y sirve archivos estáticos.
"""
import socket
import threading
import os
import urllib.parse
import time
import subprocess
import re
from user_manager import register_user, authenticate_user
from firewall_manager import desbloquear_ip, bloquear_ip
from monitor_ips import obtener_ips_conectadas

# --- Constantes y Globales ---
WEB_DIR = os.path.join(os.path.dirname(__file__), 'web')
PORT = 8080
autenticadas = {}

def get_mac_for_ip(ip: str) -> str | None:
    """Obtiene la MAC de una IP leyendo /proc/net/arp o usando arp -n.
    Devuelve None si no se encuentra.
    """
    try:
        with open('/proc/net/arp', 'r') as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if parts and parts[0] == ip:
                    mac = parts[3]
                    if mac and mac != '00:00:00:00:00:00':
                        return mac.lower()
    except Exception:
        pass
    try:
        out = subprocess.run(['arp', '-n', ip], capture_output=True, text=True).stdout
        m = re.search(r'((?:[0-9a-f]{2}:){5}[0-9a-f]{2})', out, re.I)
        if m:
            return m.group(1).lower()
    except Exception:
        pass
    return None

MIME_TYPES = {
    '.html': 'text/html',
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.ico': 'image/x-icon',
    'default': 'application/octet-stream'
}

# --- Hilo Monitor de IPs ---
def monitor_ips_thread():
    """Monitorea IPs conectadas y las bloquea si no están autenticadas."""
    print("Monitor de IPs iniciado...")
    while True:
        try:
            ips_conectadas = obtener_ips_conectadas()
            for ip in ips_conectadas:
                if ip not in autenticadas:
                    print(f"Monitor: Bloqueando IP no autenticada {ip}")
                    bloquear_ip(ip)
        except Exception as e:
            print(f"Error en el monitor de IPs: {e}")
        time.sleep(2)

# --- Manejadores de Peticiones ---
def handle_get_request(client_socket, path, client_ip):
    """Maneja peticiones GET."""
    detection_paths = [
        '/generate_204', '/ncsi.txt', '/hotspot-detect.html',
        '/library/test/success.html', '/success.txt', '/connecttest.txt',
        '/redirect'
    ]
    
    if path in detection_paths or path == '/':
        path = '/index.html'
        # Bloquear la IP al acceder al portal (solo si no está autenticada)
        if client_ip not in autenticadas:
            print(f"Bloqueando IP {client_ip} al acceder al portal.")
            bloquear_ip(client_ip)

    file_path = os.path.realpath(os.path.join(WEB_DIR, path.lstrip('/')))

    # Security check: Ensure the path is within the web directory
    if not file_path.startswith(WEB_DIR):
        send_response(client_socket, 404, "Not Found", "Recurso no encontrado.")
        return

    if os.path.isfile(file_path):
        _, ext = os.path.splitext(file_path)
        mime_type = MIME_TYPES.get(ext, MIME_TYPES['default'])
        
        with open(file_path, 'rb') as f:
            content = f.read()
        
        send_response(client_socket, 200, "OK", content, content_type=mime_type)
    else:
        send_response(client_socket, 404, "Not Found", f"Archivo no encontrado: {path}")

def handle_post_request(client_socket, path, body, client_ip):
    """Maneja peticiones POST."""
    params = urllib.parse.parse_qs(body)
    username = params.get('username', [''])[0]
    password = params.get('password', [''])[0]

    if path == '/login':
        if authenticate_user(username, password):
            mac = get_mac_for_ip(client_ip)
            print(f"Usuario '{username}' autenticado. Desbloqueando IP {client_ip}")
            if mac:
                desbloquear_ip(client_ip, mac)
                autenticadas[client_ip] = mac
            else:
                print(f"Advertencia: no se pudo obtener la MAC de {client_ip}. Se permite por IP.")
                desbloquear_ip(client_ip, None)
                autenticadas[client_ip] = None

            # Mostrar página de bienvenida bonita
            bienvenida_path = os.path.join(WEB_DIR, 'bienvenido.html')
            if os.path.isfile(bienvenida_path):
                with open(bienvenida_path, 'rb') as f:
                    content = f.read()
                send_response(client_socket, 200, "OK", content, content_type='text/html')
            else:
                send_response(client_socket, 200, "OK", "Login exitoso")
        else:
            print(f"Fallo de autenticación para usuario '{username}'")
            send_response(client_socket, 401, "Unauthorized", "Credenciales incorrectas")
    
    elif path == '/register':
        if register_user(username, password):
            print(f"Usuario '{username}' registrado exitosamente.")
            # Servir directamente index.html (mejor que 302 para algunos captives)
            index_path = os.path.join(WEB_DIR, 'index.html')
            if os.path.isfile(index_path):
                with open(index_path, 'rb') as f:
                    content = f.read()
                send_response(client_socket, 200, "OK", content, content_type='text/html')
            else:
                send_response(client_socket, 200, "OK", "Registro exitoso. Ahora puedes iniciar sesión.")
        else:
            print(f"Intento de registrar usuario existente '{username}'")
            send_response(client_socket, 409, "Conflict", "Usuario ya existe")
    else:
        send_response(client_socket, 404, "Not Found", "Endpoint no encontrado.")

def send_response(client_socket, status_code, status_text, body, content_type='text/plain', headers=None):
    """Envía una respuesta HTTP al cliente."""
    if isinstance(body, str):
        body = body.encode('utf-8')
    extra_headers = ''
    if headers:
        for k, v in headers.items():
            extra_headers += f"{k}: {v}\r\n"

    # Ensure no-cache headers by default (helps captive portals)
    if headers is None:
        headers = {}
    headers.setdefault('Cache-Control', 'no-cache, no-store, must-revalidate')
    headers.setdefault('Pragma', 'no-cache')
    headers.setdefault('Expires', '0')

    response_header = (
        f"HTTP/1.1 {status_code} {status_text}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"{extra_headers}\r\n"
    )
    client_socket.sendall(response_header.encode('utf-8') + body)

# --- Manejador de Conexiones ---
def handle_connection(client_socket, client_address):
    """Parsea la petición y la delega al manejador correspondiente."""
    try:
        request_data = client_socket.recv(4096).decode('utf-8', errors='ignore')
        if not request_data:
            return

        lines = request_data.split('\r\n')
        request_line = lines[0]
        method, path, _ = request_line.split(' ')
        
        print(f"Petición recibida: {method} {path} desde {client_address[0]}")

        if method == 'GET':
            handle_get_request(client_socket, path, client_address[0])
        elif method == 'POST':
            # Extraer cuerpo de la petición
            body_start = request_data.find('\r\n\r\n') + 4
            body = request_data[body_start:]
            handle_post_request(client_socket, path, body, client_address[0])
        else:
            send_response(client_socket, 405, "Method Not Allowed", "Método no permitido.")

    except Exception as e:
        # Ignorar errores de conexión reseteada, son comunes en portales cautivos
        if isinstance(e, ConnectionResetError):
            print(f"Conexión reseteada por el cliente: {client_address[0]}")
        else:
            print(f"Error manejando la petición desde {client_address}: {e}")
    finally:
        client_socket.close()

# --- Bucle Principal del Servidor ---
def run_server():
    """Inicia el servidor de sockets."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('', PORT))
    server_socket.listen(5)
    print(f"Servidor de socket escuchando en el puerto {PORT}")

    while True:
        client_socket, client_address = server_socket.accept()
        thread = threading.Thread(target=handle_connection, args=(client_socket, client_address))
        thread.daemon = True
        thread.start()

if __name__ == '__main__':
    # Ejecutar el script de configuración de iptables
    script_path = os.path.join(os.path.dirname(__file__), 'setup_iptables_captive_portal.sh')
    try:
        subprocess.run(['sudo', 'bash', script_path], check=True)
        print("Script de iptables ejecutado correctamente.")
    except subprocess.CalledProcessError as e:
        print(f"Error ejecutando el script de iptables: {e}")
        exit(1)

    # Iniciar el monitor de IPs en un hilo
    monitor_thread = threading.Thread(target=monitor_ips_thread, daemon=True)
    monitor_thread.start()

    # Iniciar el servidor
    try:
        run_server()
    except KeyboardInterrupt:
        print("\nCerrando servidor y limpiando reglas iptables...")
        subprocess.run(['sudo', 'iptables', '-F'])
        subprocess.run(['sudo', 'iptables', '-t', 'nat', '-F'])
        print("Reglas de iptables limpiadas.")
    except Exception as e:
        print(f"Error al iniciar el servidor: {e}")
