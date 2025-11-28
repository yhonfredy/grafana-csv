#!/bin/bash

# --- IMPORTAR VARIABLES ---
# Obtiene la ruta donde está el script y carga el archivo de claves.
SCRIPT_DIR=$(dirname "$0")
source "$SCRIPT_DIR/claves.env"

# --- CONFIGURACIÓN RESTANTE ---
# GITHUB_TOKEN="aca"  # <<<< ESTA LÍNEA DEBE SER ELIMINADA O COMENTADA
# REPO="yhonfredy/grafana-csv" # <<<< ESTA LÍNEA DEBE SER ELIMINADA O COMENTADA
# BRANCH="main" # <<<< ESTA LÍNEA DEBE SER ELIMINADA O COMENTADA

SERVIDORES_FILE="urls/RevisionesCMDB_PROD.json"
LOGS_FOLDER="logs"
INPUT_FILE="servidores_tmp.json"
TEMP_RESULTS="resultados_tmp.log"
FINAL_JSON_BUILDER="build_json.py"
# ---------------------

# Colores para la salida en terminal
VERDE='\033[0;32m'
ROJO='\033[0;31m'
NC='\033[0m' # No Color

# Función para limpiar archivos temporales al salir
cleanup() {
    rm -f $INPUT_FILE $TEMP_RESULTS
}
trap cleanup EXIT # Asegura que se ejecute cleanup al salir (incluso con error)

echo "--- 📋 Inicio de la Verificación de Puertos ---"
echo "Descargando archivo de servidores..."

# 1. DESCARGAR ARCHIVO DE SERVIDORES DESDE GITHUB
DOWNLOAD_URL="https://api.github.com/repos/${REPO}/contents/${SERVIDORES_FILE}?ref=${BRANCH}"
CONTENT_URL=$(curl -s -H "Authorization: token $GITHUB_TOKEN" -H "Accept: application/vnd.github.v3+json" $DOWNLOAD_URL | grep -o '"download_url": "[^"]*' | grep -o '[^"]*$')

if [ -z "$CONTENT_URL" ]; then
    echo -e "${ROJO}ERROR: No se pudo obtener la URL de descarga o el token es inválido.${NC}"
    exit 1
fi

curl -s $CONTENT_URL -o $INPUT_FILE

if [ $? -ne 0 ]; then
    echo -e "${ROJO}ERROR: Falló la descarga del archivo de servidores.${NC}"
    exit 1
fi

echo "Descarga exitosa. Iniciando verificación de puertos..."
# Crear archivo de resultados vacío
echo "" > $TEMP_RESULTS

# 2. ITERAR Y VERIFICAR PUERTOS TCP
# Usamos el script de Python para parsear y extraer los datos relevantes de forma segura
if [ ! -f "$FINAL_JSON_BUILDER" ]; then
    echo -e "${ROJO}ERROR: Falta el script auxiliar de Python ($FINAL_JSON_BUILDER). Asegúrate de crearlo.${NC}"
    exit 1
fi

# El script build_json.py en modo "extraer" imprime cada servidor con su IP y puerto
python3 $FINAL_JSON_BUILDER extract $INPUT_FILE | while read -r line; do
    # Formato de la línea: Nombre|Dominio|IP|Puerto
    NOMBRE=$(echo "$line" | cut -d'|' -f1)
    DOMINIO=$(echo "$line" | cut -d'|' -f2)
    IP=$(echo "$line" | cut -d'|' -f3)
    PUERTO=$(echo "$line" | cut -d'|' -f4)

    # Saltar si IP o PUERTO son inválidos/vacíos
    if [ -z "$IP" ] || [ "$PUERTO" -le 0 ]; then
        echo -e "⚪ $NOMBRE - Saltado: IP o Puerto inválido/vacío."
        continue
    fi

    # Verificación de conexión TCP con netcat (-z: cero I/O, -w: timeout de 5 segundos)
    # Ejecutamos en segundo plano con un timeout estricto
    START_TIME=$(date +%s%N)
    nc -z -w 5 $IP $PUERTO &> /dev/null
    NC_EXIT_CODE=$?
    END_TIME=$(date +%s%N)
    
    # Calcular tiempo de respuesta en milisegundos
    RT_NS=$((END_TIME - START_TIME))
    RT_MS=$((RT_NS / 1000000))
    
    # Manejar el resultado
    if [ $NC_EXIT_CODE -eq 0 ]; then
        STATUS="up"
        MESSAGE="OK (${RT_MS}ms)"
        EMOJI="🟢"
        echo -e "$EMOJI $NOMBRE ($IP:$PUERTO) → $MESSAGE"
    else
        STATUS="down"
        # nc exit code 1 suele ser "connection refused" o "timeout"
        # Asumimos que 5s de timeout es la causa principal de fallo para simplificar
        if [ $RT_MS -ge 5000 ]; then
            MESSAGE="Timeout (5000ms)"
        else
            MESSAGE="Puerto cerrado/firewall"
        fi
        RT_MS="null" # No consideramos tiempo de respuesta válido si falló
        EMOJI="🔴"
        echo -e "$EMOJI $NOMBRE ($IP:$PUERTO) → $MESSAGE"
    fi

    # Guardar el resultado en el archivo temporal de logs (formato CSV simple)
    echo "$NOMBRE|$DOMINIO|$IP|$PUERTO|$STATUS|$RT_MS|$MESSAGE" >> $TEMP_RESULTS

done

# 3. CONSTRUIR JSON FINAL Y SUBIR A GITHUB (OPCIONAL)
echo ""
echo "Verificación de puertos completa. Generando JSON final..."
# El script build_json.py en modo "build" toma el log simple y genera el JSON final
FINAL_JSON=$(python3 $FINAL_JSON_BUILDER build $TEMP_RESULTS)

# Opcional: GUARDAR Y/O SUBIR EL JSON FINAL (reemplazar esta sección si quieres subir a GitHub)
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
FILENAME="port-check_${TIMESTAMP}_FINAL.json"
echo "$FINAL_JSON" > $FILENAME
echo "Archivo de resultados guardado localmente: ${FILENAME}"

echo "--- ✅ Tarea Finalizada ---"

# Nota: La lógica de 'upload_to_github' de tu Lambda debe ser implementada
# en Bash o en un paso extra de Python si deseas mantener la subida automática.
# Por ahora, solo se guarda localmente.
