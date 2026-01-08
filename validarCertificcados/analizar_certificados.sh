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

# Array para almacenar los certificados procesados
declare -a certificados=()

# Procesar salida de keytool directamente
keytool -list -keystore "$KEYSTORE" -storepass "$STOREPASS" 2>/dev/null | \
grep -E ",.*[0-9]{4},.*Entry" | \
while IFS= read -r line; do
    # Quitar coma final
    line="${line%,}"

    # Separar por ", "
    IFS=', ' read -ra partes <<< "$line"

    # Encontrar el año (campo con exactamente 4 dígitos)
    year=""
    pos_year=-1
    for i in "${!partes[@]}"; do
        if [[ "${partes[i]}" =~ ^[0-9]{4}$ ]]; then
            year="${partes[i]}"
            pos_year=$i
            break
        fi
    done

    # Si no encontramos año, saltar (línea inválida)
    [[ -z "$year" ]] && continue

    # Tipo de entrada (último campo)
    tipo="${partes[-1]}"

    # Alias: todo lo que está antes del mes/día/año
    alias=$(IFS=", "; echo "${partes[@]:0:pos_year-2}")

    # Mes y día: los dos campos antes del año
    mes_ing_raw="${partes[pos_year-1]}"
    dia_raw="${partes[pos_year-2]}"

    # Limpiar mes (quitar punto si existe: "sep." → "sep")
    mes_ing=$(echo "$mes_ing_raw" | tr '[:upper:]' '[:lower:]' | sed 's/\.$//')

    # Día sin ceros iniciales para mostrar
    dia_mostrar=$(echo "$dia_raw" | sed 's/^0*//')
    dia_calc=$(printf "%02d" "${dia_raw#0}")  # con cero para date

    # Mes en español
    mes_mostrar=${mes_esp[$mes_ing]:-$mes_ing}

    # Fecha para mostrar: "12 sep 2025"
    fecha_mostrar="$dia_mostrar $mes_mostrar $year"

    # Guardar en array: alias | fecha_mostrar | tipo | year-mes-dia (para cálculo)
    certificados+=("$alias | $fecha_mostrar | $tipo | $year-$mes_ing-$dia_calc")
done

# Si no hay certificados
if [ ${#certificados[@]} -eq 0 ]; then
    echo "No se encontraron certificados en el keystore."
    echo "(Posible causa: salida de keytool en formato inesperado o keystore vacío)"
    exit 1
fi

echo "Certificados encontrados: ${#certificados[@]}"
echo
printf "%-55s | %-16s | %-20s | %10s | [%s]\n" "ALIAS" "VENCE" "TIPO" "DÍAS" "ESTADO"
printf "%-55s-|-%-16s-|-%-20s-|-%-10s-|-%-10s\n" "-------------------------------------------------------" "----------------" "--------------------" "----------" "----------"

# Recorrer y calcular vencimiento
for cert in "${certificados[@]}"; do
    IFS='|' read -r alias fecha_mostrar tipo fecha_iso_calc <<< "$cert"

    alias=$(echo "$alias" | xargs)
    fecha_mostrar=$(echo "$fecha_mostrar" | xargs)
    tipo=$(echo "$tipo" | xargs)

    # Convertir mes inglés a número
    mes_ing=$(echo "$fecha_iso_calc" | cut -d'-' -f2)
    case $mes_ing in
        jan|ene) mes_num=01 ;; feb) mes_num=02 ;; mar) mes_num=03 ;;
        apr|abr) mes_num=04 ;; may) mes_num=05 ;; jun) mes_num=06 ;;
        jul) mes_num=07 ;; aug|ago) mes_num=08 ;; sep) mes_num=09 ;;
        oct) mes_num=10 ;; nov) mes_num=11 ;; dec|dic) mes_num=12 ;;
        *) mes_num="" ;;
    esac

    if [ -z "$mes_num" ]; then
        dias_texto="no calc."
        estado="DESCONOCIDO"
        color="\033[0;33m"
    else
        fecha_iso=$(echo "$fecha_iso_calc" | sed "s/-$mes_ing-/-$mes_num-/")
        vence_epoch=$(date -d "$fecha_iso" +%s 2>/dev/null || date -j -f "%Y-%m-%d" "$fecha_iso" +%s 2>/dev/null)

        if [ -n "$vence_epoch" ]; then
            dias=$(( (vence_epoch - HOY_EPOCH) / 86400 ))
            dias_texto="$dias días"

            if [ "$dias" -lt 0 ]; then
                estado="VENCIDO"
                color="\033[0;31m"
            elif [ "$dias" -le "$DIAS_CRITICO" ]; then
                estado="CRÍTICO"
                color="\033[1;31m"
            elif [ "$dias" -le "$DIAS_ALERTA" ]; then
                estado="POR VENCER"
                color="\033[0;33m"
            else
                estado="VIGENTE"
                color="\033[0;32m"
            fi
        else
            dias_texto="error date"
            estado="ERROR"
            color="\033[1;35m"
        fi
    fi

    printf "%-55s | %-16s | %-20s | %10s | %s%-10s\033[0m\n" \
        "$alias" "$fecha_mostrar" "$tipo" "$dias_texto" "$color" "$estado"
done

echo
echo "¡Análisis completado! Todo en memoria, sin archivos temporales."
