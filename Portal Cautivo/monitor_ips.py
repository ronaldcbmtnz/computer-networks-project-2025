"""
monitor_ips.py
Monitorea las IPs conectadas a la red y las bloquea automáticamente en iptables si no están autenticadas.
"""
import time
import subprocess
from firewall_manager import bloquear_ip

# Lista de IPs autenticadas (debe actualizarse desde el backend)
autenticadas = set()

# Intervalo de escaneo en segundos
SCAN_INTERVAL = 10

def obtener_ips_conectadas():
    """Obtiene las IPs conectadas usando la tabla ARP."""
    resultado = subprocess.run(['arp', '-n'], capture_output=True, text=True)
    ips = set()
    for line in resultado.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].count('.') == 3:
            ips.add(parts[0])
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
