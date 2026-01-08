#!/bin/bash

KEYSTORE="/oracle/app/wlogic12c/certificados/identity/identity.jks"
STOREPASS="identity"
DIAS_ALERTA=30
DIAS_CRITICO=7

clear
echo "========================================"
echo "ANÁLISIS COMPLETO DE CERTIFICADOS EN"
echo "$KEYSTORE"
echo "Fecha actual: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
echo

# Verificar acceso al keystore
if ! keytool -list -keystore "$KEYSTORE" -storepass "$STOREPASS" >/dev/null 2>&1; then
    echo "ERROR: No se puede acceder al keystore (ruta o contraseña incorrecta)"
    exit 1
fi

HOY_EPOCH=$(date +%s)

# Mapa de meses inglés → español
declare -A mes_esp
mes_esp=( ["jan"]="ene" ["feb"]="feb" ["mar"]="mar" ["apr"]="abr" ["may"]="may"
          ["jun"]="jun" ["jul"]="jul" ["aug"]="ago" ["sep"]="sep"
          ["oct"]="oct" ["nov"]="nov" ["dec"]="dic" )

# Array para almacenar las líneas procesadas (solo en memoria)
declare -a certificados=()

# 1. Extraer y normalizar directamente desde keytool → array
while IFS= read -r line; do
    # Filtrar líneas con certificados
    [[ ! "$line" =~ ,[[:space:]]*[0-9]{4},.*Entry$ ]] && continue

    # Quitar coma final y separar por ", "
    line="${line%,}"
    IFS=', ' read -ra partes <<< "$line"

    # Buscar posición del año (campo de 4 dígitos solo)
    pos_year=-1
    for i in "${!partes[@]}"; do
        [[ "${partes[i]}" =~ ^[0-9]{4}$ ]] && pos_year=$i && year="${partes[i]}" && break
    done
    ((pos_year == -1)) && continue

    tipo="${partes[-1]}"

    # Alias: todo antes de la fecha
    alias_parts=("${partes[@]:0:pos_year-1}")
    alias=$(IFS=", "; echo "${alias_parts[*]}")

    # Fecha original: mes día año (ej: Sep 12 2025)
    mes_ing=$(echo "${partes[pos_year-1]}" | tr '[:upper:]' '[:lower:]')
    dia_raw="${partes[pos_year-2]}"
    # Quitar posible punto final en mes español (ej: "sep.")
    mes_ing=${mes_ing%.}

    mes_final=${mes_esp[$mes_ing]:-$mes_ing}  # español si existe, sino original
    dia=$(echo "$dia_raw" | sed 's/^0*//')   # quitar cero inicial

    fecha_esp="$dia $mes_final $year"

    # Guardar en array: alias | fecha_español | tipo | fecha_original_para_calculo
    certificados+=("$alias | $fecha_esp | $tipo | $dia $mes_ing $year")

done < <(keytool -list -keystore "$KEYSTORE" -storepass "$STOREPASS" 2>/dev/null)

# Si no hay certificados
if [ ${#certificados[@]} -eq 0 ]; then
    echo "No se encontraron certificados en el keystore."
    exit 1
fi

echo "Certificados encontrados: ${#certificados[@]}"
echo
printf "%-55s | %-16s | %-20s | %10s | [%s]\n" "ALIAS" "VENCE" "TIPO" "DIAS" "ESTADO"
printf "%-55s-|-%-16s-|-%-20s-|-%-10s-|-%-10s\n" "-------------------------------------------------------" "----------------" "--------------------" "----------" "----------"

# 2. Recorrer el array y calcular vencimiento
for cert in "${certificados[@]}"; do
    IFS='|' read -r alias fecha_esp tipo fecha_calc <<< "$cert"

    alias=$(echo "$alias" | xargs)
    fecha_esp=$(echo "$fecha_esp" | xargs)
    tipo=$(echo "$tipo" | xargs)

    # Extraer día, mes (en inglés para date), año de fecha_calc
    dia=$(echo "$fecha_calc" | awk '{print $1}')
    mes_abbr=$(echo "$fecha_calc" | awk '{print tolower($2)}')
    year=$(echo "$fecha_calc" | awk '{print $3}')

    case $mes_abbr in
        ene|jan) mes=01 ;; feb) mes=02 ;; mar) mes=03 ;;
        abr|apr) mes=04 ;; may) mes=05 ;; jun) mes=06 ;;
        jul) mes=07 ;; ago|aug) mes=08 ;; sep) mes=09 ;;
        oct) mes=10 ;; nov) mes=11 ;; dic|dec) mes=12 ;;
        *) mes="" ;;
    esac

    if [ -z "$mes" ]; then
        dias_texto="no calc."
        estado="DESCONOCIDO"
        color="\033[0;33m"
    else
        dia_fmt=$(printf "%02d" "$dia")
        fecha_iso="$year-$mes-$dia_fmt"

        vence_epoch=$(date -d "$fecha_iso" +%s 2>/dev/null || date -j -f "%Y-%m-%d" "$fecha_iso" +%s 2>/dev/null)

        if [ -n "$vence_epoch" ]; then
            dias=$(( (vence_epoch - HOY_EPOCH) / 86400 ))
            dias_texto="$dias días"

            if [ "$dias" -lt 0 ]; then
                estado="VENCIDO"
                color="\033[0;31m"      # rojo
            elif [ "$dias" -le "$DIAS_CRITICO" ]; then
                estado="CRÍTICO"
                color="\033[1;31m"      # rojo brillante
            elif [ "$dias" -le "$DIAS_ALERTA" ]; then
                estado="POR VENCER"
                color="\033[0;33m"      # amarillo
            else
                estado="VIGENTE"
                color="\033[0;32m"      # verde
            fi
        else
            dias_texto="error date"
            estado="ERROR"
            color="\033[1;35m"
        fi
    fi

    printf "%-55s | %-16s | %-20s | %10s | %s%-10s\033[0m\n" \
        "$alias" "$fecha_esp" "$tipo" "$dias_texto" "$color" "$estado"

done

echo
echo "¡Análisis completado! Todo procesado en memoria, sin archivos temporales."
