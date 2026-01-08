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

# Verificar acceso
keytool -list -keystore "$KEYSTORE" -storepass "$STOREPASS" >/dev/null 2>&1 || {
    echo "ERROR: No se puede acceder al keystore"
    exit 1
}

HOY_EPOCH=$(date +%s)

# Mapa meses español/inglés → número
declare -A mes_num
mes_num=( ["ene"]=01 ["jan"]=01 ["feb"]=02 ["mar"]=03 ["abr"]=04 ["apr"]=04
          ["may"]=05 ["jun"]=06 ["jul"]=07 ["ago"]=08 ["aug"]=08
          ["sep"]=09 ["oct"]=10 ["nov"]=11 ["dic"]=12 ["dec"]=12 )

declare -a certificados=()

# Procesar directamente desde keytool
keytool -list -keystore "$KEYSTORE" -storepass "$STOREPASS" 2>/dev/null | \
grep -i entry | \
while IFS= read -r linea; do

    # Quitar coma final si existe
    linea="${linea%,}"

    # Separar por coma + espacio
    IFS=', ' read -ra campos <<< "$linea"

    # Buscar el año (4 dígitos)
    year=""
    for campo in "${campos[@]}"; do
        if [[ "$campo" =~ ^[0-9]{4}$ ]]; then
            year="$campo"
            break
        fi
    done
    [[ -z "$year" ]] && continue

    # Tipo (último campo)
    tipo="${campos[-1]}"

    # Todo lo anterior al año es alias + fecha
    resto=$(IFS=', '; echo "${campos[@]:0:${#campos[@]}-2}")

    # Extraer fecha: los últimos 3 campos antes del tipo (año ya encontrado)
    # Ej: "13 dic. 2023" o "dic. 13, 2023"
    fecha_partes=()
    for ((i=${#campos[@]}-3; i<${#campos[@]}-1; i++)); do
        [[ -n "${campos[i]}" ]] && fecha_partes+=("${campos[i]}")
    done

    # Detectar formato: día mes año o mes día año
    dia=""
    mes_abbr=""
    if [[ ${fecha_partes[0]} =~ ^[0-9]+$ ]] && [[ ${fecha_partes[1]} =~ ^[A-Za-z]+\.?$$ ]]; then
        # Formato: 13 dic. 2023
        dia="${fecha_partes[0]}"
        mes_abbr=$(echo "${fecha_partes[1]}" | tr '[:upper:]' '[:lower:]' | sed 's/\.$//')
    elif [[ ${fecha_partes[1]} =~ ^[0-9]+$ ]] && [[ ${fecha_partes[0]} =~ ^[A-Za-z]+\.?$$ ]]; then
        # Formato: dic. 13, 2023
        mes_abbr=$(echo "${fecha_partes[0]}" | tr '[:upper:]' '[:lower:]' | sed 's/\.$//')
        dia="${fecha_partes[1]}"
    else
        # Fallback: buscar número y mes en los últimos campos
        for p in "${fecha_partes[@]}"; do
            if [[ "$p" =~ ^[0-9]+$ ]]; then dia="$p"; fi
            if [[ "$p" =~ ^[A-Za-z]+\.?$ ]]; then mes_abbr=$(echo "$p" | tr '[:upper:]' '[:lower:]' | sed 's/\.$//'); fi
        done
    fi

    [[ -z "$dia" || -z "$mes_abbr" ]] && continue

    # Alias = resto menos la fecha
    alias=$(echo "$resto" | sed -e "s/ $dia $mes_abbr.*$//" -e "s/ $mes_abbr $dia.*$//" | xargs)

    # Normalizar
    dia_mostrar=$(echo "$dia" | sed 's/^0*//')
    mes_mostrar=$(echo "$mes_abbr" | sed 's/\.$//')
    num_mes=${mes_num[$mes_mostrar]}
    [[ -z "$num_mes" ]] && continue

    fecha_mostrar="$dia_mostrar $mes_mostrar $year"
    fecha_iso="$year-$num_mes-$(printf "%02d" "$dia")"

    certificados+=("$alias | $fecha_mostrar | $tipo | $fecha_iso")
done

# Si no hay certificados
(( ${#certificados[@]} == 0 )) && {
    echo "No se encontraron certificados o formato de fecha desconocido."
    exit 1
}

echo "Certificados encontrados: ${#certificados[@]}"
echo
printf "%-55s | %-16s | %-20s | %10s | [%s]\n" "ALIAS" "VENCE" "TIPO" "DÍAS" "ESTADO"
printf "%-.55s-+-%-.16s-+-%-.20s-+-%-.10s-+-%-.10s\n" "-------------------------------------------------------" "----------------" "--------------------" "----------" "----------"

# Mostrar y calcular
for cert in "${certificados[@]}"; do
    IFS='|' read -r alias fecha_mostrar tipo fecha_iso <<< "$cert"
    alias=$(echo "$alias" | xargs)
    fecha_mostrar=$(echo "$fecha_mostrar" | xargs)
    tipo=$(echo "$tipo" | xargs)

    vence_epoch=$(date -d "$fecha_iso" +%s 2>/dev/null || date -j -f "%Y-%m-%d" "$fecha_iso" +%s 2>/dev/null)

    if [[ -n "$vence_epoch" ]]; then
        dias=$(( (vence_epoch - HOY_EPOCH) / 86400 ))
        dias_texto="$dias días"

        if (( dias < 0 )); then
            estado="VENCIDO";   color="\033[0;31m"
        elif (( dias <= DIAS_CRITICO )); then
            estado="CRÍTICO";   color="\033[1;31m"
        elif (( dias <= DIAS_ALERTA )); then
            estado="POR VENCER"; color="\033[0;33m"
        else
            estado="VIGENTE";   color="\033[0;32m"
        fi
    else
        dias_texto="error"; estado="ERROR"; color="\033[1;35m"
    fi

    printf "%-55s | %-16s | %-20s | %10s | %s%-10s\033[0m\n" \
        "$alias" "$fecha_mostrar" "$tipo" "$dias_texto" "$color" "$estado"
done

echo
echo "¡Análisis completado sin archivos temporales!"
