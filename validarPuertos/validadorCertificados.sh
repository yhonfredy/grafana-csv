#!/bin/bash

KEYSTORE="identity.jks"
STOREPASS="identity"
LOG_FILE="certificados_identity.log"
FINAL_FILE="certificados_final.log"

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
sed 's/,$//' | \
tee "$LOG_FILE"

awk -F' \\| ' '
BEGIN {
    mes["jan"]="ene"; mes["feb"]="feb"; mes["mar"]="mar";
    mes["apr"]="abr"; mes["may"]="may"; mes["jun"]="jun";
    mes["jul"]="jul"; mes["aug"]="ago"; mes["sep"]="sep";
    mes["oct"]="oct"; mes["nov"]="nov"; mes["dec"]="dic";
}
{
    alias = $1
    split($2, md, " ")
    mes_ing = tolower(md[1])
    dia = md[2]
    year = $3
    tipo = $4

    mes_esp = mes[mes_ing]
    if (mes_esp == "") mes_esp = mes_ing

    print alias " | " dia " " mes_esp " " year " | " tipo
}
' "$LOG_FILE" > "$FINAL_FILE"

TOTAL=$(wc -l < "$FINAL_FILE" | tr -d ' ')

echo
echo "¡Listo! $TOTAL certificados con fecha en formato español."
echo "Guardados en: $FINAL_FILE"
echo
echo "=== Vista previa ==="
cat "$FINAL_FILE"
