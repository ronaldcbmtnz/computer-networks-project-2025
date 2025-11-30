#!/bin/bash

# Script de arranque para Portal Cautivo por ETHERNET
# Recibe internet por wlo1 (WiFi) y comparte por una interfaz Ethernet.

# --- ¡IMPORTANTE! ---
# Reemplaza 'eth0' con el nombre de tu interfaz de red cableada si es diferente.
# Puedes encontrar el nombre con el comando: ip addr
export INTERFAZ_SALIDA="eno1"
export INTERFAZ_ENTRADA="wlo1" # Interfaz que recibe internet

set -e

echo "🔒 Iniciando Portal Cautivo por Ethernet en '$INTERFAZ_SALIDA'"
echo "========================================================"

# Verificar permisos root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Ejecutar con: sudo ./start_captive_portal_ethernet.sh"
    exit 1
fi

# Limpiar servicios previos
echo "[1/5] Limpiando servicios anteriores..."
pkill dnsmasq 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true
sleep 1

# Asignar IP estática a la interfaz de salida
echo "[2/5] Configurando interfaz de red '$INTERFAZ_SALIDA'..."
ip addr flush dev $INTERFAZ_SALIDA || true
ip addr add 192.168.100.1/24 brd + dev $INTERFAZ_SALIDA
ip link set dev $INTERFAZ_SALIDA up
echo "✅ Interfaz configurada: 192.168.100.1/24"

# Habilitar enrutamiento y configurar NAT
echo "[3/5] Habilitando enrutamiento y NAT..."
echo 1 > /proc/sys/net/ipv4/ip_forward
iptables -t nat -F
iptables -t nat -A POSTROUTING -o $INTERFAZ_ENTRADA -j MASQUERADE
iptables -A FORWARD -i $INTERFAZ_ENTRADA -o $INTERFAZ_SALIDA -m state --state RELATED,ESTABLISHED -j ACCEPT
# La siguiente línea es importante para que el portal pueda bloquear. No la descomentes.
# iptables -A FORWARD -i $INTERFAZ_SALIDA -o $INTERFAZ_ENTRADA -j ACCEPT
echo "✅ NAT configurado"

# Configurar y iniciar DNSMASQ para DHCP
echo "[4/5] Iniciando servidor DHCP..."
cat > /tmp/dnsmasq_eth.conf << EOF
interface=$INTERFAZ_SALIDA
bind-interfaces
dhcp-range=192.168.100.50,192.168.100.150,12h
dhcp-option=3,192.168.100.1
dhcp-option=6,192.168.100.1
# dnsmasq actúa como DNS local y reenvía a servidores públicos
server=8.8.8.8
log-dhcp
EOF

dnsmasq -C /tmp/dnsmasq_eth.conf &
sleep 1

if ! pgrep dnsmasq > /dev/null; then
    echo "❌ Error iniciando DHCP (dnsmasq)"
    exit 1
fi
echo "✅ Servidor DHCP activo"

# Iniciar servidor Python del portal
echo "[5/5] Iniciando servidor del portal..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/Portal Cautivo"
if [ -f "server.py" ]; then
    echo "Ejecutando server.py desde $PWD"
    # Pasar el interfaz del portal al monitor de IPs
    sudo CAPTIVE_IFACE=$INTERFAZ_SALIDA python3 server.py
else
    echo "❌ No se encuentra server.py en $PWD"
    echo "El gateway está funcionando. Para iniciar el portal web:"
    echo "cd $SCRIPT_DIR/Portal Cautivo && python3 server.py"
    trap "echo ''; echo '🛑 Deteniendo portal...'; pkill dnsmasq; exit" INT
    while true; do
        sleep 60
        echo "Portal cautivo (Ethernet) activo... (Ctrl+C para detener)"
    done
fi
