#!/bin/bash

# Script para detener el Portal Cautivo por ETHERNET

# --- ¡IMPORTANTE! ---
# Reemplaza 'eth0' con el nombre de tu interfaz de red cableada si es diferente.
export INTERFAZ_SALIDA="eno1"
export INTERFAZ_ENTRADA="wlo1"

echo "🛑 Deteniendo Portal Cautivo por Ethernet..."

# Verificar permisos root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Ejecutar con: sudo ./stop_captive_portal_ethernet.sh"
    exit 1
fi

# Detener dnsmasq
echo "[1/4] Deteniendo servidor DHCP..."
pkill dnsmasq 2>/dev/null || true

# Detener servidor Python
echo "[2/4] Deteniendo servidor web..."
pkill -f "python3 server.py" 2>/dev/null || true

# Limpiar reglas iptables
echo "[3/4] Limpiando reglas de firewall..."
iptables -t nat -F
iptables -F FORWARD
# Restaurar política por defecto si se cambió
iptables -P FORWARD ACCEPT

# Desactivar forwarding
echo 0 > /proc/sys/net/ipv4/ip_forward

# Limpiar la interfaz y reiniciar NetworkManager
echo "[4/4] Restaurando configuración de red..."
ip addr flush dev $INTERFAZ_SALIDA 2>/dev/null || true
systemctl restart NetworkManager

echo ""
echo "✅ Portal Cautivo detenido"
echo "🔌 La configuración de red ha sido restaurada."
