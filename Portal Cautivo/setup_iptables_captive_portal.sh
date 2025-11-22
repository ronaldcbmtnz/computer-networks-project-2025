#!/bin/bash
# Script para configurar iptables para portal cautivo
# Bloquea todo el tráfico externo por defecto y permite solo el acceso al portal cautivo (puerto 8080)


# Elimina cualquier regla global de bloqueo en FORWARD
sudo iptables -D FORWARD -j REJECT 2>/dev/null

# Permitir acceso al portal cautivo (puerto 8080)
sudo iptables -I INPUT -p tcp --dport 8080 -j ACCEPT

echo "Reglas iptables para portal cautivo aplicadas."
