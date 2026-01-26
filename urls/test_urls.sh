#!/usr/bin/env bash

# =============================================================================
# Script de diagnóstico rápido para problemas de conectividad HTTP/HTTPS
# Uso: ./test_urls.sh
# =============================================================================

echo ""
echo "=== DIAGNÓSTICO DE CONECTIVIDAD - $(date '+%Y-%m-%d %H:%M:%S') ==="
echo ""

# ────────────────────────────────────────────────
# 1. Información básica del entorno
# ────────────────────────────────────────────────
echo "Sistema: $(uname -a)"
echo "Usuario: $(whoami)"
echo "Directorio actual: $(pwd)"
echo ""

# ────────────────────────────────────────────────
# 2. Variables de proxy 
# ────────────────────────────────────────────────
echo "Variables de proxy detectadas:"
env | grep -i proxy || echo "  → Ninguna variable de proxy encontrada"
echo ""

# ────────────────────────────────────────────────
# 3. Pruebas de conectividad básica (capa 3 y DNS)
# ────────────────────────────────────────────────
echo "→ ping 8.8.8.8 (prueba de salida a internet)..."
ping -c 4 8.8.8.8 | grep -E "packets|loss" || echo "  → FALLÓ"

echo ""
echo "→ ping google.com (prueba DNS + salida)..."
ping -c 3 google.com | grep -E "packets|loss" || echo "  → FALLÓ"

echo ""
echo "→ Resolución DNS..."
nslookup google.com 8.8.8.8 2>/dev/null | grep -E "Address:|Name:" || echo "  → No resolvió con DNS de Google"
cat /etc/resolv.conf 2>/dev/null | grep nameserver || echo "  → No se pudo leer /etc/resolv.conf"

# ────────────────────────────────────────────────
# 4. Pruebas curl detalladas (con verbose)
# ────────────────────────────────────────────────
echo ""
echo "=== Pruebas curl detalladas ==="
echo ""

urls=(
  "https://www.google.com"
  "https://1.1.1.1"
  "http://httpbin.org/status/200"
  "https://8.8.8.8"           # IP directa (sin DNS)
)

for url in "${urls[@]}"; do
  echo "Probando: $url"
  echo "----------------------------------------"
  curl -k -L --connect-timeout 10 --max-time 20 -v "$url" -o /dev/null 2>&1 | \
    grep -E "^* |< HTTP|curl: \(|Could not resolve|Connection timed out|refused|No route|proxy|SSL|certificate"
  echo ""
done

# ────────────────────────────────────────────────
# 5. Prueba con IP directa (evita DNS)
# ────────────────────────────────────────────────
echo "Prueba extra sin DNS (IP de google.com - puede cambiar):"
echo "curl -k -v https://142.251.167.100"   # Ejemplo IP google (actualízala si falla)
curl -k -v --connect-timeout 8 https://142.251.167.100 -o /dev/null 2>&1 | head -n 15
echo ""

# ────────────────────────────────────────────────
# 6. Recomendaciones según síntomas comunes
# ────────────────────────────────────────────────
echo ""
echo "=== Posibles conclusiones rápidas ==="
if ! ping -c 1 8.8.8.8 >/dev/null 2>&1; then
  echo "✗ No hay salida a internet → Firewall / ruta / proveedor bloqueando"
elif ! nslookup google.com >/dev/null 2>&1; then
  echo "✗ Problema de DNS → Revisa /etc/resolv.conf o usa 8.8.8.8 manualmente"
elif env | grep -qi proxy; then
  echo "⚠ Proxy detectado → Prueba: export https_proxy=http://tu-proxy:puerto"
  echo "   y vuelve a correr el script"
else
  echo "Posible firewall selectivo (solo bloquea ciertos puertos o dominios)"
  echo "Prueba también con: curl -v https://tu-dominio-interno.local"
fi

echo ""
echo "Listo. Copia y pega los errores que veas (sobre todo líneas con 'curl: (') y compártelos."
echo "¡Suerte!"
