#!/bin/bash

KEYSTORE="identity.jks"
STOREPASS="identity"
DIAS_ALERTA=30
DIAS_CRITICO=7

clear
echo "========================================"
echo "ANÁLISIS COMPLETO DE CERTIFICADOS EN $KEYSTORE"
echo "Fecha actual: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
echo

if ! keytool -list -keystore "$KEYSTORE" -storepass "$STOREPASS" >/dev/null 2>&1; then
    echo "ERROR: No se puede acceder al keystore"
    exit 1
fi

declare -a lineas_base=()
declare -a certificados_final=()

while IFS= read -r linea; do
    lineas_base+=("$linea")
done < <(keytool -list -keystore "$KEYSTORE" -storepass "$STOREPASS" 2>/dev/null | \
         grep -E ",.*[0-9]{4},.*Entry" | \
         sed 's/, / | /g' | \
         sed 's/,$//')

if [ ${#lineas_base[@]} -eq 0 ]; then
    echo "No se encontraron certificados."
    exit 1
fi

for linea in "${lineas_base[@]}"; do
    # <<<=== ESTA ES LA ÚNICA PARTE QUE CAMBIA ===>>>
    linea_tab=$(echo "$linea" | sed 's/ | /\t/g')
    IFS=$'\t' read -r alias mes_ing dia year tipo <<< "$linea_tab"
    # <<<=== FIN DEL CAMBIO ===>>>

    case $(echo "$mes_ing" | tr '[:upper:]' '[:lower:]') in
        jan) mes_esp="ene" ;;
        feb) mes_esp="feb" ;;
        mar) mes_esp="mar" ;;
        apr) mes_esp="abr" ;;
        may) mes_esp="may" ;;
        jun) mes_esp="jun" ;;
        jul) mes_esp="jul" ;;
        aug) mes_esp="ago" ;;
        sep) mes_esp="sep" ;;
        oct) mes_esp="oct" ;;
        nov) mes_esp="nov" ;;
        dec) mes_esp="dic" ;;
        *)   mes_esp=$(echo "$mes_ing" | tr '[:upper:]' '[:lower:]') ;;
    esac

    dia_sin_cero=$(echo "$dia" | sed 's/^0*//')
    certificados_final+=("$alias | $dia_sin_cero $mes_esp $year | $tipo")
done

echo "Certificados encontrados: ${#certificados_final[@]}"
echo
printf "%-55s | %-16s | %-20s | %10s | [%s]\n" "ALIAS" "VENCE" "TIPO" "DÍAS" "ESTADO"
printf "%-55s-|-%-16s-|-%-20s-|-%-10s-|-%-10s\n" "-------------------------------------------------------" "----------------" "--------------------" "----------" "----------"

HOY_EPOCH=$(date +%s)

for linea in "${certificados_final[@]}"; do
    IFS="|" read -r ALIAS FECHA TIPO _ <<< "$linea"
    ALIAS=$(echo "$ALIAS" | xargs)
    FECHA=$(echo "$FECHA" | xargs)
    TIPO=$(echo "$TIPO" | xargs)

    dia=$(echo "$FECHA" | awk '{print $1}')
    mes_abbr=$(echo "$FECHA" | awk '{print tolower($2)}')
    year=$(echo "$FECHA" | awk '{print $3}')

    case $mes_abbr in
        ene|jan) mes=01 ;; feb) mes=02 ;; mar) mes=03 ;;
        abr|apr) mes=04 ;; may) mes=05 ;; jun) mes=06 ;;
        jul) mes=07 ;; ago|aug) mes=08 ;; sep) mes=09 ;;
        oct) mes=10 ;; nov) mes=11 ;; dic|dec) mes=12 ;;
        *) mes="" ;;
    esac

    if [ -z "$mes" ]; then
        DIAS_TEXTO="no calculable"
        ESTADO="DESCONOCIDO"
        COLOR="\033[0;33m"
    else
        dia_fmt=$(printf "%02d" "$dia")
        VENCE_EPOCH=$(date -d "$year-$mes-$dia_fmt" +%s 2>/dev/null || date -j -f "%Y-%m-%d" "$year-$mes-$dia_fmt" +%s 2>/dev/null)
        DIAS=$(( (VENCE_EPOCH - HOY_EPOCH) / 86400 ))
        DIAS_TEXTO="$DIAS días"
        if [ "$DIAS" -lt 0 ]; then ESTADO="VENCIDO"; COLOR="\033[0;31m"
        elif [ "$DIAS" -le "$DIAS_CRITICO" ]; then ESTADO="CRÍTICO"; COLOR="\033[1;31m"
        elif [ "$DIAS" -le "$DIAS_ALERTA" ]; then ESTADO="POR VENCER"; COLOR="\033[0;33m"
        else ESTADO="VIGENTE"; COLOR="\033[0;32m"; fi
    fi

    printf "%-55s | %-16s | %-20s | %10s | %s[%s]\033[0m\n" \
        "$ALIAS" "$FECHA" "$TIPO" "$DIAS_TEXTO" "$COLOR" "$ESTADO"
done

echo
echo "¡Análisis completado! Todo procesado en memoria, sin archivos temporales."
