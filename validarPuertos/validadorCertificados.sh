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

# -------- GENERACIÓN BASE ----------
keytool -list -keystore "$KEYSTORE" -storepass "$STOREPASS" 2>/dev/null | \
grep -E ",.*[0-9]{4},.*Entry" | \
sed 's/, / | /g' | \
sed 's/,$//' | \
tee "$LOG_FILE"

# -------- NORMALIZACIÓN REAL ----------
awk -F'\\|' '
{
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0)

    if ($2 ~ /[A-Za-z]/ && $3 ~ /^[0-9]{4}$/) {
        printf "%s | %s %s | %s |\n",
               $1, $2, $3, $4
    } else {
        print
    }
}
' "$LOG_FILE" > "$FIXED_FILE"

TOTAL=$(wc -l < "$FIXED_FILE" | tr -d ' ')

echo
echo "✔ $TOTAL certificados normalizados guardados en $FIXED_FILE"
