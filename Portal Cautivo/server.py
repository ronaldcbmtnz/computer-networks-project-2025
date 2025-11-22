"""
server.py
Servidor HTTP básico para el portal cautivo.
Maneja los endpoints principales: /, /login, /register
"""


import http.server
import socketserver
import threading
import os
import urllib.parse
from user_manager import register_user, authenticate_user
from firewall_manager import desbloquear_ip, bloquear_ip
import subprocess
from monitor_ips import obtener_ips_conectadas, bloquear_ip

WEB_DIR = os.path.join(os.path.dirname(__file__), 'web')
PORT = 8080

# Lista global de IPs autenticadas
autenticadas = set()

class CaptivePortalHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        client_ip = self.client_address[0]
        # Bloquear la IP al acceder al portal (solo si no está autenticada)
        # Para simplificar, bloqueamos siempre que acceda a '/'
        if self.path == '/':
            bloquear_ip(client_ip)
            self.path = '/index.html'
        return super().do_GET()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        params = urllib.parse.parse_qs(post_data)

        if self.path == '/login':
            self.handle_login(params)
        elif self.path == '/register':
            self.handle_register(params)
        else:
            self.send_error(404, 'Not Found')

    def handle_login(self, params):
        username = params.get('username', [''])[0]
        password = params.get('password', [''])[0]
        client_ip = self.client_address[0]
        if authenticate_user(username, password):
            desbloquear_ip(client_ip)
            autenticadas.add(client_ip)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'Login exitoso')
        else:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'Credenciales incorrectas')

    def handle_register(self, params):
        username = params.get('username', [''])[0]
        password = params.get('password', [''])[0]
        if register_user(username, password):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'Registro exitoso')
        else:
            self.send_response(409)
            self.end_headers()
            self.wfile.write(b'Usuario ya existe')

if __name__ == '__main__':
    # Ejecutar el script de configuración de iptables usando ruta absoluta
    script_path = os.path.join(os.path.dirname(__file__), 'setup_iptables_captive_portal.sh')
    subprocess.run(['sudo', 'bash', script_path])

    def monitor_ips_thread():
        import time
        while True:
            ips = obtener_ips_conectadas()
            for ip in ips:
                if ip not in autenticadas:
                    bloquear_ip(ip)
            time.sleep(10)

    t = threading.Thread(target=monitor_ips_thread, daemon=True)
    t.start()

    try:
        with socketserver.ThreadingTCPServer(("", PORT), CaptivePortalHandler) as httpd:
            print(f"Servidor Captive Portal corriendo en el puerto {PORT}")
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando servidor y limpiando reglas iptables...")
        subprocess.run(['sudo', 'iptables', '-F'])
        print("Reglas iptables eliminadas.")
