#!/bin/bash
# check_weblogic_telnet.sh 
# Solo bash + telnet + jq

CSV_FILE="ListadoWebLogic.csv"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
TIMESTAMP_LOCAL=$(date +"%Y-%m-%d %H:%M:%S")
RUN_ID=$(date +"%Y%m%d_%H%M")

UP=0
TOTAL=0
RESULTS_JSON="[]"

echo "=== Check WebLogic vía Telnet – $(date '+%Y-%m-%d %H:%M:%S') ==="

# Lee el CSV saltando la cabecera
while IFS=';,	' read -r nombre ip puerto rest || [ -n "$nombre ]; do
    # Ignora líneas comentadas o vacías
    [[ "$nombre" =~ ^#.*$ ]] && continue
    [[ -z "$ip" || -z "$puerto" ]] && continue
    [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || continue
    [[ "$puerto" =~ ^[0-9]+$ ]] || continue

    ((TOTAL++))

    # Check con telnet (más fiable que solo puerto abierto)
    if timeout 10 bash -c "echo > /dev/tcp/$ip/$puerto" 2>/dev/null && \
       timeout 8 telnet "$ip" "$puerto" </dev/null 2>/dev/null | grep -q .; then
        STATUS="up"
        ((UP++))
        echo "UP   $nombre → $ip:$puerto"
    else
        STATUS="down"
        echo "DOWN $nombre → $ip:$puerto"
    fi

    # Añade al array JSON
    DOC=$(jq -n \
      --arg n "$nombre" \
      --arg i "$ip" \
      --argjson p "$puerto" \
      --arg s "$STATUS" \
      '{nombre:$n, ip:$i, puerto:$p, status:$s, puerto_abierto:($s=="up"|if . then 1 else 0 end)}')

    RESULTS_JSON=$(echo "$RESULTS_JSON" | jq --argjson d "$DOC" '. += [$d]')

done < <(tail -n +2 "$CSV_FILE")

# Guarda el JSON de log 
LOG_FILE="weblogic_check_$(date +%Y-%m-%d_%H-%M-%S).json"
jq -n \
  --arg t "$TIMESTAMP" \
  --argjson total "$TOTAL" \
  --argjson up "$UP" \
  --argjson arr "$RESULTS_JSON" \
  '{
    check_timestamp: $t,
    total_servers: $total,
    summary: {
      up: $up,
      down: ($total - $up),
      up_percentage: (if $total > 0 then ($up/$total*100)|round else 0 end)
    },
    servers: $arr
  }' > "$LOG_FILE"

echo "JSON de log guardado → $LOG_FILE"
echo "=== RESUMEN: $UP/$TOTAL servidores RESPONDIERON ==="
echo "Fecha: $TIMESTAMP_LOCAL"
echo "===================================================="
