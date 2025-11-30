#!/bin/bash

# Script de arranque automático para Portal Cautivo
# Adaptado para interfaz física wlo1 y virtual wlan1_ap

set -e

echo "🔒 Iniciando Portal Cautivo"
echo "============================"

# Verificar permisos root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Ejecutar con: sudo ./start_captive_portal.sh"
    exit 1
fi

# Limpiar servicios previos
echo "[1/6] Limpiando servicios anteriores..."
pkill hostapd 2>/dev/null || true
pkill dnsmasq 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true
sleep 2

# Eliminar interfaz anterior si existe
echo "[2/6] Configurando interfaz de red..."
ip link set wlan1_ap down 2>/dev/null || true
iw dev wlan1_ap del 2>/dev/null || true
sleep 1

# Crear interfaz virtual AP
if ! iw dev wlo1 interface add wlan1_ap type __ap; then
    echo "❌ Error creando interfaz virtual"
    echo "Verifica: iw dev"
    exit 1
fi
sleep 1

# Levantar interfaz
ip link set dev wlan1_ap up
sleep 1

# Asignar IP
ip addr add 192.168.100.1/24 brd + dev wlan1_ap
sleep 1

# Verificar IP
if ! ip addr show wlan1_ap | grep -q "192.168.100.1"; then
    echo "❌ Error: No se asignó la IP"
    ip link show wlan1_ap
    ip addr show wlan1_ap
    exit 1
fi

echo "✅ Interfaz configurada: 192.168.100.1/24"

# Habilitar forwarding
echo "[3/6] Habilitando enrutamiento..."
echo 1 > /proc/sys/net/ipv4/ip_forward

# Configurar NAT
iptables -t nat -F
iptables -t nat -A POSTROUTING -o wlo1 -j MASQUERADE
# La siguiente línea permitía todo el tráfico, se comenta para que el portal cautivo pueda bloquear.
# iptables -A FORWARD -i wlan1_ap -o wlo1 -j ACCEPT
iptables -A FORWARD -i wlo1 -o wlan1_ap -m state --state RELATED,ESTABLISHED -j ACCEPT
echo "✅ NAT configurado"

# Configurar y iniciar DNSMASQ
echo "[4/6] Iniciando servidor DHCP..."
cat > /tmp/dnsmasq_ap.conf << EOF
interface=wlan1_ap
bind-interfaces
dhcp-range=192.168.100.50,192.168.100.150,12h
dhcp-option=3,192.168.100.1
dhcp-option=6,192.168.100.1
# dnsmasq actúa como DNS local y reenvía a servidores públicos
server=8.8.8.8
log-dhcp
EOF

dnsmasq -C /tmp/dnsmasq_ap.conf &
sleep 1

if ! pgrep dnsmasq > /dev/null; then
    echo "❌ Error iniciando DHCP"
    exit 1
fi
echo "✅ Servidor DHCP activo"

# Verificar/crear configuración hostapd
echo "[5/6] Configurando Access Point..."
if [ ! -f /etc/hostapd/hostapd.conf ]; then
    mkdir -p /etc/hostapd
    cat > /etc/hostapd/hostapd.conf << EOF
interface=wlan1_ap
driver=nl80211
ssid=PortalCautivo
hw_mode=g
channel=7
ieee80211n=1
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=12345678
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF
fi

# Iniciar hostapd
hostapd /etc/hostapd/hostapd.conf > /tmp/hostapd.log 2>&1 &
sleep 3

if pgrep hostapd > /dev/null; then
    echo "✅ Access Point iniciado"
else
    echo "❌ Error iniciando AP"
    tail -10 /tmp/hostapd.log
    exit 1
fi

# Mostrar estado
ip addr show wlan1_ap | grep "inet " | awk '{print "🌐 IP Gateway:", $2}'
echo "📶 SSID:     PortalCautivo"
echo "🔑 Password: 12345678"
echo "🖥️  Portal:   http://192.168.100.1:8080"

# Iniciar servidor Python
echo "[6/6] Configurando Access Point..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/Portal Cautivo"
if [ -f "server.py" ]; then
    echo "Ejecutando server.py desde $SCRIPT_DIR/Portal Cautivo"
    # Pasar el interfaz del portal al monitor de IPs
    sudo CAPTIVE_IFACE=wlan1_ap python3 server.py
else
    echo "❌ No se encuentra server.py en $SCRIPT_DIR/Portal Cautivo"
    echo "El gateway está funcionando. Para iniciar el portal web:"
    echo "cd $SCRIPT_DIR/Portal Cautivo && python3 server.py"
    trap "echo ''; echo '🛑 Deteniendo portal...'; pkill hostapd; pkill dnsmasq; exit" INT
    while true; do
        sleep 60
        echo "Portal cautivo activo... (Ctrl+C para detener)"
    done
fi
