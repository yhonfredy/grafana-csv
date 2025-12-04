#!/bin/bash

CSV_FILE="ListadoWebLogic.csv"
TIMEOUT=5 # Timeout en segundos

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Check WebLogic con Netcat (espera hasta ${TIMEOUT}s)"

# Leer el archivo CSV, ignorando la primera línea (cabecera)
# IFS=';' define el delimitador
# -r previene el tratamiento especial de backslashes
tail -n +2 "$CSV_FILE" | while IFS=';' read -r nombre_raw ip_raw puerto_str_raw resto; do
    
    # 1. Limpiar los espacios en blanco iniciales/finales de las variables usando sed
    nombre=$(echo "$nombre_raw" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    ip=$(echo "$ip_raw" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    puerto_str=$(echo "$puerto_str_raw" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

    # 2. Validar que la IP y el Puerto no estén vacíos y que el puerto sea un número
    if [ -z "$ip" ] || [ -z "$puerto_str" ] || ! [[ "$puerto_str" =~ ^[0-9]+$ ]]; then
        continue
    fi

    # 3. Comprobación con Netcat (nc -z: solo escanear, -w: timeout)
    if timeout "${TIMEOUT}" nc -z -w "${TIMEOUT}" "$ip" "$puerto_str" 2>/dev/null; then
        echo "UP   $(printf "%-50s" "$nombre") → $ip:$puerto_str"
    else
        echo "DOWN $(printf "%-50s" "$nombre") → $ip:$puerto_str"
    fi
done

echo ""
echo "Comprobación finalizada."
