"""
firewall_manager.py
Módulo para controlar el acceso a la red usando iptables.
"""
import subprocess

def bloquear_ip(ip):
    """Bloquea el acceso externo para la IP dada y redirige HTTP al portal cautivo."""
    # Bloquear tráfico externo
    cmd_block = [
        'sudo', 'iptables', '-A', 'FORWARD', '-s', ip, '-j', 'REJECT'
    ]
    subprocess.call(cmd_block)
    # Redirigir HTTP (puerto 80) al portal cautivo (puerto 8080)
    cmd_redirect = [
        'sudo', 'iptables', '-t', 'nat', '-A', 'PREROUTING', '-s', ip, '-p', 'tcp', '--dport', '80', '-j', 'REDIRECT', '--to-port', '8080'
    ]
    return subprocess.call(cmd_redirect)

def desbloquear_ip(ip):
    """Elimina todas las reglas de bloqueo y redirección HTTP para la IP dada."""
    # Eliminar reglas de bloqueo en FORWARD
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
    # Eliminar reglas de redirección HTTP en nat PREROUTING
    while True:
        result = subprocess.run(['sudo', 'iptables', '-t', 'nat', '-L', 'PREROUTING', '-n', '--line-numbers'], capture_output=True, text=True)
        lines = result.stdout.splitlines()
        num_to_delete = None
        for line in lines:
            if ip in line and 'tcp dpt:80' in line and 'REDIRECT' in line:
                parts = line.split()
                if parts:
                    num_to_delete = parts[0]
                    break
        if num_to_delete:
            subprocess.run(['sudo', 'iptables', '-t', 'nat', '-D', 'PREROUTING', num_to_delete], capture_output=True, text=True)
        else:
            break
    return True
