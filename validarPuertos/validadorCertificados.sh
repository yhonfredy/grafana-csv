#!/bin/bash

KEYSTORE="identity.jks"
STOREPASS="identity"
LOG_FILE="certificados_identity.log"
FIXED_FILE="certificados_identity_fixed.log"

clear
echo "========================================"
echo "GENERANDO LISTA DE CERTIFICADOS EN $KEYSTORE"
echo "Fecha actual: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
echo

> "$LOG_FILE"

# Generación base (tal como ya lo tienes)
keytool -list -keystore "$KEYSTORE" -storepass "$STOREPASS" 2>/dev/null | \
grep -E ",.*[0-9]{4},.*Entry" | \
sed 's/, / | /g' | \
sed 's/,$//' | \
tee "$LOG_FILE"

# ---- CORRECCIÓN DE FECHAS PARTIDAS ----
awk -F'\\|' '
{
    # cuenta de separadores
    if (NF > 4) {
        # Une campo 2 y 3 (fecha partida)
        printf "%s | %s %s | %s |\n", $1, $2, $3, $NF
    } else {
        print $0
    }
}
' "$LOG_FILE" > "$FIXED_FILE"

TOTAL=$(wc -l < "$FIXED_FILE" | tr -d ' ')

echo
echo "✔ $TOTAL certificados corregidos guardados en $FIXED_FILE"
