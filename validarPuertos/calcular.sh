#!/bin/bash

LOG_FILE="certificados_identity.log"
LOG_CON_DIAS="certificados_con_dias.log"

DIAS_ALERTA=30
DIAS_CRITICO=7

echo "========================================"
echo "DÍAS VENCIDOS/REMANENTES"
echo "Fecha actual: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
echo

if [ ! -f "$LOG_FILE" ]; then
  echo "Error: No existe el archivo $LOG_FILE"
  echo "Ejecuta primero el script generador."
  exit 1
fi

> "$LOG_CON_DIAS"

HOY_EPOCH=$(date "+%s")

while IFS= read -r line; do
  # Separar con |
  ALIAS=$(echo "$line" | cut -d'|' -f1 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  FECHA_STR=$(echo "$line" | cut -d'|' -f2 | sed 's/^[[:space:]]*//')
  TIPO=$(echo "$line" | cut -d'|' -f3 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

  # Extraer día, mes y año (maneja ambos formatos)
  if [[ "$FECHA_STR" =~ \. ]]; then
    # Español: "29 jul. 2022"
    dia=$(echo "$FECHA_STR" | awk '{print $1}')
    mes_abbr=$(echo "$FECHA_STR" | awk '{print $2}' | sed 's/\.//g' | tr '[:upper:]' '[:lower:]')
    year=$(echo "$FECHA_STR" | awk '{print $3}')
  else
    # Inglés: "Jul 29, 2022"
    mes_abbr=$(echo "$FECHA_STR" | awk '{print $1}' | tr '[:upper:]' '[:lower:]')
    dia=$(echo "$FECHA_STR" | awk '{gsub(/,/, "", $2); print $2}')
    year=$(echo "$FECHA_STR" | awk '{print $3}')
  fi

  dia=$(echo "$dia" | sed 's/^0*//')

  case $mes_abbr in
    ene|jan) mes_num="01" ;;
    feb) mes_num="02" ;;
    mar) mes_num="03" ;;
    abr|apr) mes_num="04" ;;
    may) mes_num="05" ;;
    jun) mes_num="06" ;;
    jul) mes_num="07" ;;
    ago|aug) mes_num="08" ;;
    sep) mes_num="09" ;;
    oct) mes_num="10" ;;
    nov) mes_num="11" ;;
    dic|dec) mes_num="12" ;;
    *) mes_num="" ;;
  esac

  if [ -z "$mes_num" ]; then
    DIAS_TEXTO="no calculable"
    ESTADO="DESCONOCIDO"
  else
    dia_formateado=$(printf "%02d" "$dia")
    fecha_ddmmyyyy="$dia_formateado-$mes_num-$year"

    VENCE_EPOCH=$(date -d "$year-$mes_num-$dia_formateado" "+%s" 2>/dev/null || \
                  date -j -f "%d-%m-%Y" "$fecha_ddmmyyyy" "+%s" 2>/dev/null)

    if [ -n "$VENCE_EPOCH" ]; then
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
    else
      DIAS_TEXTO="no calculable"
      ESTADO="DESCONOCIDO"
    fi
  fi

  echo "$ALIAS | $FECHA_STR | $TIPO | $DIAS_TEXTO | [$ESTADO]"
  echo "$ALIAS | $FECHA_STR | $TIPO | $DIAS_TEXTO | [$ESTADO]" >> "$LOG_CON_DIAS"
done < "$LOG_FILE"

echo
echo "¡Listo! Días calculados (compatible con macOS y Linux)."
echo "Log guardado en: $LOG_CON_DIAS"