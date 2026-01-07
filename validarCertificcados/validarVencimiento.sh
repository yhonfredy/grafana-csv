#!/bin/bash

LOG_FILE="certificados_final.log"
LOG_SALIDA="certificados_vencimiento.log"

DIAS_ALERTA=30
DIAS_CRITICO=7

echo "========================================"
echo "ESTADO DE VENCIMIENTO DE CERTIFICADOS"
echo "Fecha actual: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
echo

[ ! -f "$LOG_FILE" ] && echo "No existe $LOG_FILE" && exit 1
> "$LOG_SALIDA"

HOY_EPOCH=$(date +%s)

while IFS="|" read -r ALIAS FECHA TIPO _; do
  ALIAS=$(echo "$ALIAS" | xargs)
  FECHA=$(echo "$FECHA" | xargs)
  TIPO=$(echo "$TIPO" | xargs)

  # Saltar líneas vacías
  [ -z "$ALIAS" ] && continue

  # FECHA = DD mes YYYY
  dia=$(echo "$FECHA" | awk '{print $1}')
  mes_abbr=$(echo "$FECHA" | awk '{print tolower($2)}')
  year=$(echo "$FECHA" | awk '{print $3}')

  case $mes_abbr in
    ene|jan) mes=01 ;;
    feb) mes=02 ;;
    mar) mes=03 ;;
    abr|apr) mes=04 ;;
    may) mes=05 ;;
    jun) mes=06 ;;
    jul) mes=07 ;;
    ago|aug) mes=08 ;;
    sep) mes=09 ;;
    oct) mes=10 ;;
    nov) mes=11 ;;
    dic|dec) mes=12 ;;
    *) mes="" ;;
  esac

  if [ -z "$mes" ]; then
    DIAS_TEXTO="no calculable"
    ESTADO="DESCONOCIDO"
  else
    dia=$(printf "%02d" "$dia")

    VENCE_EPOCH=$(date -d "$year-$mes-$dia" +%s 2>/dev/null || \
                  date -j -f "%Y-%m-%d" "$year-$mes-$dia" +%s 2>/dev/null)

    DIAS=$(( (VENCE_EPOCH - HOY_EPOCH) / 86400 ))
    DIAS_TEXTO="$DIAS días"

    if [ "$DIAS" -lt 0 ]; then
      ESTADO="VENCIDO"
    elif [ "$DIAS" -le "$DIAS_CRITICO" ]; then
      ESTADO="CRÍTICO"
    elif [ "$DIAS" -le "$DIAS_ALERTA" ]; then
      ESTADO="POR VENCER"
    else
      ESTADO="VIGENTE"
    fi
  fi

  echo "$ALIAS | $FECHA | $TIPO | $DIAS_TEXTO | [$ESTADO]" | tee -a "$LOG_SALIDA"

done < "$LOG_FILE"

echo
echo "✔ Reporte generado en: $LOG_SALIDA"
