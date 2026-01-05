#!/bin/bash

KEYSTORE="identity.jks"
STOREPASS="identity"
LOG_FILE="certificados_identity.log"

clear
echo "========================================"
echo "GENERANDO LISTA DE CERTIFICADOS EN $KEYSTORE"
echo "Fecha actual: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
echo

> "$LOG_FILE"

keytool -list -keystore "$KEYSTORE" -storepass "$STOREPASS" 2>/dev/null | \
grep -E ",.*[0-9]{4},.*Entry" | \
sed 's/, / | /g' | \
sed 's/\.\([[:space:]]*[0-9]\)/\1/g' | \
sed 's/,$//' | \
tee "$LOG_FILE"

TOTAL=$(wc -l < "$LOG_FILE" | tr -d ' ')

echo
echo "✔ $TOTAL certificados guardados en $LOG_FILE"
