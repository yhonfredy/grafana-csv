#!/bin/bash

CSV_FILE="ListadoWebLogic.csv"
TIMEOUT=5 # Timeout más corto para el comando nc

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Check WebLogic con Netcat (espera hasta ${TIMEOUT}s)"

# Leer el archivo CSV, ignorando la primera línea (cabecera)
tail -n +2 "$CSV_FILE" | while IFS=';' read -r nombre ip puerto_str resto; do
    # Eliminar espacios en blanco
    nombre=$(echo "$nombre" | xargs)
    ip=$(echo "$ip" | xargs)
    puerto_str=$(echo "$puerto_str" | xargs)

    # Validar que el puerto sea un número
    if ! [[ "$puerto_str" =~ ^[0-9]+$ ]]; then
        continue
    fi

    # Comprobación con Netcat (nc -z: solo escanear, -w: timeout)
    # 2>/dev/null suprime la salida de error de nc
    if timeout "${TIMEOUT}" nc -z -w "${TIMEOUT}" "$ip" "$puerto_str" 2>/dev/null; then
        echo "UP   $(printf "%-50s" "$nombre") → $ip:$puerto_str"
    else
        echo "DOWN $(printf "%-50s" "$nombre") → $ip:$puerto_str"
    fi
done

echo ""
echo "Comprobación finalizada."
