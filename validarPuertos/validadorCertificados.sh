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
awk -F',' '
/Entry$/ {
    alias=$1
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", alias)

    fecha=$2
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", fecha)

    tipo=$NF
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", tipo)

    print alias " | " fecha " | " tipo
}
' | tee "$LOG_FILE"

TOTAL=$(wc -l < "$LOG_FILE" | tr -d ' ')

echo
echo "✔ $TOTAL certificados guardados en $LOG_FILE"
