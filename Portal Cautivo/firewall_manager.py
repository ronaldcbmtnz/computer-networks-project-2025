"""
firewall_manager.py
Módulo para controlar el acceso a la red usando iptables.
"""
import subprocess

def _iptables_save(table=None):
    args = ['sudo', 'iptables-save'] if not table else ['sudo', 'iptables-save', '-t', table]
    return subprocess.run(args, capture_output=True, text=True).stdout.splitlines()

def _delete_matching_rules(lines, table_prefix):
    for line in list(lines):
        delete_cmd = line.replace('-A', '-D')
        # Build full iptables invocation
        if table_prefix:
            subprocess.run(f"sudo iptables -t {table_prefix} {delete_cmd}", shell=True, check=False)
        else:
            subprocess.run(f"sudo iptables {delete_cmd}", shell=True, check=False)

def bloquear_ip(ip):
    """Bloquea el acceso externo para la IP dada y redirige HTTP al portal cautivo."""
    # Bloquear tráfico externo si la regla no existe todavía
    cmd_check_block = ['sudo', 'iptables', '-C', 'FORWARD', '-s', ip, '-j', 'REJECT']
    if subprocess.call(cmd_check_block, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        subprocess.call(['sudo', 'iptables', '-A', 'FORWARD', '-s', ip, '-j', 'REJECT'])

    # Redirigir HTTP (puerto 80) al portal cautivo (puerto 8080) evitando duplicados
    cmd_check_redirect = [
        'sudo', 'iptables', '-t', 'nat', '-C', 'PREROUTING', '-s', ip, '-p', 'tcp', '--dport', '80', '-j', 'REDIRECT', '--to-port', '8080'
    ]
    if subprocess.call(cmd_check_redirect, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        return subprocess.call([
            'sudo', 'iptables', '-t', 'nat', '-A', 'PREROUTING', '-s', ip, '-p', 'tcp', '--dport', '80', '-j', 'REDIRECT', '--to-port', '8080'
        ])
    return 0

def desbloquear_ip(ip, mac=None):
    """Elimina reglas de bloqueo/redirección y permite tráfico sólo si coincide IP(+MAC)."""
    # Eliminar REJECT para la IP
    reject_lines = [l for l in _iptables_save() if f'-s {ip}' in l and 'REJECT' in l]
    _delete_matching_rules(reject_lines, table_prefix=None)

    # Eliminar REDIRECT para la IP en NAT
    redirect_lines = [l for l in _iptables_save('nat') if f'-s {ip}' in l and 'REDIRECT' in l]
    _delete_matching_rules(redirect_lines, table_prefix='nat')

    # Eliminar ACCEPTs previos para esa IP (con o sin MAC) para evitar reglas huérfanas
    accept_lines = [l for l in _iptables_save() if ' -A FORWARD ' in l and f'-s {ip}' in l and ' -j ACCEPT' in l]
    _delete_matching_rules(accept_lines, table_prefix=None)

    # Insertar ACCEPT con coincidencia IP+MAC si está disponible; si no, por IP (fallback)
    if mac:
        print(f"Permitiendo tráfico para la IP: {ip} y MAC: {mac}")
        subprocess.run(['sudo', 'iptables', '-I', 'FORWARD', '1', '-m', 'mac', '--mac-source', mac, '-s', ip, '-j', 'ACCEPT'], check=False)
    else:
        print(f"Permitiendo tráfico para la IP (sin MAC disponible): {ip}")
        subprocess.run(['sudo', 'iptables', '-I', 'FORWARD', '1', '-s', ip, '-j', 'ACCEPT'], check=False)

    return True
