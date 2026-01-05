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

# 1. Generar lista base: alias, mes dia, año, tipo → separados por " | "
keytool -list -keystore "$KEYSTORE" -storepass "$STOREPASS" 2>/dev/null | \
grep -E ",.*[0-9]{4},.*Entry" | \
sed 's/, / | /g' | \
sed 's/,$//' | \
tee "$LOG_FILE"

# 2. Normalizar: unir mes + día + año → formato español "DD mes YYYY"
#    y dejar solo: alias | fecha_español | tipo
awk -F' \\| ' '
BEGIN {
    # Mapa de meses inglés → español (minúsculas)
    mes["jan"] = "ene"; mes["feb"] = "feb"; mes["mar"] = "mar";
    mes["apr"] = "abr"; mes["may"] = "may"; mes["jun"] = "jun";
    mes["jul"] = "jul"; mes["aug"] = "ago"; mes["sep"] = "sep";
    mes["oct"] = "oct"; mes["nov"] = "nov"; mes["dec"] = "dic";
}
{
    # Limpiar espacios al inicio/final
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0)

    alias = $1
    mes_ing = tolower($2)
    dia = $3
    year = $4
    tipo = $5

    # Convertir mes a español
    mes_esp = mes[mes_ing]
    if (mes_esp == "") mes_esp = mes_ing  # fallback si ya viene en español

    # Formatear día sin cero inicial (si aplica)
    gsub(/^0+/, "", dia)

    # Construir fecha final: "13 dic 2023"
    fecha_final = dia " " mes_esp " " year

    # Imprimir: alias | fecha | tipo
    print alias " | " fecha_final " | " tipo
}
' "$LOG_FILE" > "$FINAL_FILE"

TOTAL=$(wc -l < "$FINAL_FILE" | tr -d ' ')

echo
echo "¡Listo! $TOTAL certificados con fecha en formato español."
echo "Guardados en: $FINAL_FILE"
echo
echo "=== Vista previa ==="
cat "$FINAL_FILE"
