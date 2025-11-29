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
    """Elimina las reglas de bloqueo y redirección, y ACEPTA el tráfico para la IP dada."""
    # Eliminar todas las reglas REJECT para la IP
    while True:
        result = subprocess.run(['sudo', 'iptables-save'], capture_output=True, text=True)
        rule_to_delete = next((line for line in result.stdout.splitlines() if f'-s {ip}' in line and 'REJECT' in line), None)
        if rule_to_delete:
            delete_cmd = rule_to_delete.replace('-A', '-D')
            subprocess.run(f"sudo iptables {delete_cmd}", shell=True, check=True)
        else:
            break

    # Eliminar todas las reglas de REDIRECT para la IP
    while True:
        result = subprocess.run(['sudo', 'iptables-save', '-t', 'nat'], capture_output=True, text=True)
        rule_to_delete = next((line for line in result.stdout.splitlines() if f'-s {ip}' in line and 'REDIRECT' in line), None)
        if rule_to_delete:
            delete_cmd = rule_to_delete.replace('-A', '-D')
            subprocess.run(f"sudo iptables -t nat {delete_cmd}", shell=True, check=True)
        else:
            break

    # Añadir una regla para PERMITIR el tráfico de la IP autenticada
    print(f"Permitiendo tráfico para la IP: {ip}")
    subprocess.run(['sudo', 'iptables', '-I', 'FORWARD', '1', '-s', ip, '-j', 'ACCEPT'])
    
    return True
