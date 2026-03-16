#!/bin/bash
# =========================================================
# CONFIGURACIÓN DE ENTORNO
# =========================================================
export TZ="America/Bogota"

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

FECHA=$(date '+%Y-%m-%d')
HORA=$(date '+%H-%M-%S')
LOG_DIR="logs/$FECHA"
LOG_FILE="$LOG_DIR/ejecucion_integral_$HORA.log"

mkdir -p "$LOG_DIR"

# =========================================================
# EJECUCIÓN CON SALIDA DUAL (PANTALLA Y ARCHIVO)
# =========================================================
{
echo "========================================================="
echo "INICIANDO MONITOREO INTEGRAL: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================================="

# 1. Validación de Puertos
echo -e "\n1. Validando Puertos y Servicios..."
python3 validarServicios.py
echo -e "\n---------------------------------------------------------"
sleep 1

# 2. Validación de URLs HTTP
echo -e "\n2. Validando URLs HTTP..."
python3 registroMonitoreo.py
echo -e "\n---------------------------------------------------------"
sleep 1

# 3. Validación Oracle DB
echo -e "\n3. Validando estado de Oracle DB..."
cd Oracle
python3 status_check_oracleDataBase.py
cd ..
echo -e "\n---------------------------------------------------------"
sleep 1

# 4. Colección IPM hacia Influx
echo -e "\n4. Ejecutando colección de servicios IPM..."
cd IPM
python3 estandar_ejecutar_coleccion_influx.py
cd ..
echo -e "\n---------------------------------------------------------"
sleep 1

# 5. Envío de reporte por correo (lee InfluxDB con ventana de 15 min)
echo -e "\n5. Generando y enviando reporte de alertas por correo..."
python3 influxdb_alert_mailer.py
echo -e "\n---------------------------------------------------------"

echo ""
echo "========================================================="
echo "MONITOREO COMPLETADO CON ÉXITO: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Log detallado en: $LOG_FILE"
echo "========================================================="

} 2>&1 | tee "$LOG_FILE"
