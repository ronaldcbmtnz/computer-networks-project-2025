"""
monitor_ips.py
Monitorea las IPs conectadas a la red y las bloquea automáticamente en iptables si no están autenticadas.
"""
import time
import subprocess
import os
from firewall_manager import bloquear_ip

# Lista de IPs autenticadas (debe actualizarse desde el backend)
autenticadas = set()

# Intervalo de escaneo en segundos
SCAN_INTERVAL = 2

def obtener_ips_conectadas():
    """Obtiene las IPs conectadas usando la tabla ARP del interfaz del portal.
    Filtra solo la subred del portal 192.168.100.0/24 para evitar vecinos de wlo1.
    """
    iface = os.environ.get('CAPTIVE_IFACE')
    cmd = ['arp', '-n'] if not iface else ['arp', '-n', '-i', iface]
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    ips = set()
    for line in resultado.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].count('.') == 3:
            ip = parts[0]
            if ip.startswith('192.168.100.') and ip != '192.168.100.1':
                ips.add(ip)
    return ips

def monitorear_y_bloquear():
    print("Monitor de IPs iniciado...")
    while True:
        ips = obtener_ips_conectadas()
        for ip in ips:
            if ip not in autenticadas:
                bloquear_ip(ip)
        time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    monitorear_y_bloquear()
