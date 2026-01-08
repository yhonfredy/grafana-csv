#!/bin/bash

KEYSTORE="/oracle/app/wlogic12c/certificados/identity/identity.jks"
STOREPASS="identity"

# Arrays en memoria
declare -a lineas_base=()
declare -a certificados_final=()

# Capturar salida base
while IFS= read -r linea; do
    lineas_base+=("$linea")
done < <(keytool -list -keystore "$KEYSTORE" -storepass "$STOREPASS" 2>/dev/null | \
         grep -E ",.*[0-9]{4},.*Entry" | \
         sed 's/, / | /g' | \
         sed 's/,$//')

# Normalizar fechas (orden correcto: día mes año)
for linea in "${lineas_base[@]}"; do
    linea_tab=$(echo "$linea" | sed 's/ | /\t/g')
    IFS=$'\t' read -r alias mes_ing dia year tipo <<< "$linea_tab"

    mes_ing_lower=$(echo "$mes_ing" | tr '[:upper:]' '[:lower:]')

    case $mes_ing_lower in
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
        *)   mes_esp=$mes_ing_lower ;;
    esac

    dia_sin_cero=$(echo "$dia" | sed 's/^0*//')
    fecha_mostrar="$dia_sin_cero $mes_esp $year"

    certificados_final+=("$alias | $fecha_mostrar | $tipo")
done

# Cálculo de vencimiento y salida simple
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
        ESTADO="[DESCONOCIDO]"
    else
        dia_fmt=$(printf "%02d" "$dia")
        VENCE_EPOCH=$(date -d "$year-$mes-$dia_fmt" +%s 2>/dev/null || date -j -f "%Y-%m-%d" "$year-$mes-$dia_fmt" +%s 2>/dev/null)
        if [ -n "$VENCE_EPOCH" ]; then
            DIAS=$(( (VENCE_EPOCH - HOY_EPOCH) / 86400 ))
            DIAS_TEXTO="$DIAS días"
            if [ "$DIAS" -lt 0 ]; then
                ESTADO="[VENCIDO]"
            elif [ "$DIAS" -le 7 ]; then
                ESTADO="[CRÍTICO]"
            elif [ "$DIAS" -le 30 ]; then
                ESTADO="[POR VENCER]"
            else
                ESTADO="[VIGENTE]"
            fi
        else
            DIAS_TEXTO="no calculable"
            ESTADO="[ERROR DATE]"
        fi
    fi

    # Salida simple: alias; fecha; días; [ESTADO]
    printf "%s; %s %s; %s; %s\n" "$ALIAS" "$TIPO" "$FECHA" "$DIAS_TEXTO" "$ESTADO"
done
