#!/usr/bin/env bash

# =============================================================================
# Diagnóstico de URLs desde CSV - Muestra errores reales de curl
# Uso: ./test_urls_from_csv.sh otros.csv
#      o simplemente: ./test_urls_from_csv.sh   (usa por defecto otros.csv)
# =============================================================================

CSV_FILE="${1:-otros.csv}"

if [ ! -f "$CSV_FILE" ]; then
    echo "Error: No se encuentra el archivo '$CSV_FILE'"
    echo "Uso: $0 [ruta_al_csv]"
    exit 1
fi

echo ""
echo "=== DIAGNÓSTICO DE URLs desde $CSV_FILE - $(date '+%Y-%m-%d %H:%M:%S') ==="
echo "Formato esperado: Nombre;URL"
echo ""

# ────────────────────────────────────────────────
# 1. Información básica del entorno
# ────────────────────────────────────────────────
echo "Entorno rápido:"
echo "  - Usuario: $(whoami)"
echo "  - Host:    $(hostname)"
echo "  - Proxy?:  $(env | grep -i proxy || echo 'ninguno detectado')"
echo ""

# ────────────────────────────────────────────────
# 2. Pruebas generales (internet + DNS)
# ────────────────────────────────────────────────
echo "Pruebas básicas de conectividad:"
ping -c 3 8.8.8.8     2>/dev/null | grep -E "packets transmitted|loss" || echo "  → No responde 8.8.8.8 (problema de salida)"
echo ""
nslookup google.com 8.8.8.8 2>/dev/null | grep -E "Address:|Name:" || echo "  → Problema de DNS (no resuelve con 8.8.8.8)"
echo ""

# ────────────────────────────────────────────────
# 3. Prueba cada URL del CSV
# ────────────────────────────────────────────────
echo "=== Pruebas detalladas por URL ==="
echo ""

# Saltamos la primera línea (cabecera) y procesamos el resto
tail -n +2 "$CSV_FILE" | while IFS=';' read -r nombre url; do
    # Limpiamos espacios
    nombre=$(echo "$nombre" | xargs)
    url=$(echo "$url" | xargs)

    if [ -z "$url" ]; then
        echo "→ Línea vacía o mal formada → saltando"
        continue
    fi

    echo "Nombre: $nombre"
    echo "URL:    $url"
    echo "----------------------------------------"

    # Curl con verbose + timeout razonable + capturamos salida de error
    curl_output=$(curl -k -L -s -o /dev/null \
        --connect-timeout 12 \
        --max-time 30 \
        -w "%{http_code}\n" \
        -v "$url" 2>&1)

    http_code=$(echo "$curl_output" | tail -n1)
    error_lines=$(echo "$curl_output" | grep -E "curl: \(|\* |< HTTP|Connection timed out|Could not resolve|refused|No route|proxy|SSL|certificate|Failed to connect")

    if [[ "$http_code" =~ ^[2-3][0-9]{2}$ ]]; then
        echo "→ OK (código $http_code)"
    elif [ "$http_code" = "000" ] || [ -z "$http_code" ]; then
        echo "→ FALLÓ completamente (000 o sin respuesta)"
    else
        echo "→ Respuesta HTTP: $http_code"
    fi

    # Mostramos las líneas relevantes del verbose
    if [ -n "$error_lines" ]; then
        echo "Errores / detalles importantes:"
        echo "$error_lines" | sed 's/^/  /'
    else
        echo "  (sin errores obvios en verbose)"
    fi

    echo ""
done

echo "=== FIN del diagnóstico ==="
echo ""
echo "Consejo: Copia y pega las líneas que digan 'curl: (' o 'Connection timed out' o 'Could not resolve host'"
echo "Eso casi siempre dice exactamente cuál es el problema (DNS, firewall, proxy, etc.)"
echo ""
