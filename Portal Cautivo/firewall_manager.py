"""
firewall_manager.py
Módulo para controlar el acceso a la red usando iptables.
"""
import subprocess

def bloquear_ip(ip):
    """Bloquea el acceso externo para la IP dada."""
    cmd = [
        'sudo', 'iptables', '-A', 'FORWARD', '-s', ip, '-j', 'REJECT'
    ]
    return subprocess.call(cmd)

def desbloquear_ip(ip):
    """Elimina todas las reglas de bloqueo para la IP dada en FORWARD, actualizando la lista tras cada borrado."""
    while True:
        result = subprocess.run(['sudo', 'iptables', '-L', 'FORWARD', '-n', '--line-numbers'], capture_output=True, text=True)
        lines = result.stdout.splitlines()
        num_to_delete = None
        for line in lines:
            if ip in line and 'REJECT' in line:
                parts = line.split()
                if parts:
                    num_to_delete = parts[0]
                    break
        if num_to_delete:
            subprocess.run(['sudo', 'iptables', '-D', 'FORWARD', num_to_delete], capture_output=True, text=True)
        else:
            break
    return True
