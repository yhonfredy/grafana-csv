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
grep -E "Entry" | \
awk -F', ' '
{
  alias=$1
  raw_date=$2
  tipo=$NF

  # Normalizar fecha:
  # Español: "31 jul. 2025"
  # Inglés : "Jul 31, 2025"

  gsub(/\./,"",raw_date)
  gsub(/,/,"",raw_date)

  split(raw_date, d, " ")

  if (d[1] ~ /^[0-9]+$/) {
    # Español → DD mes YYYY
    dia=d[1]; mes=d[2]; year=d[3]
  } else {
    # Inglés → mes DD YYYY
    dia=d[2]; mes=d[1]; year=d[3]
  }

  print alias " | " dia " " mes " " year " | " tipo
}' | tee "$LOG_FILE"

TOTAL=$(wc -l < "$LOG_FILE" | tr -d ' ')

echo
echo "✔ $TOTAL certificados guardados en $LOG_FILE"
