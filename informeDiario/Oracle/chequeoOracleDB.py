import oracledb
import csv
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# === CONFIGURACIÓN DE RUTAS ===
BASE_DIR_PROYECTO = "/home/ssm-user/SETI/validarServicios"
ARCHIVO_ENTRADA = 'estadoSaludBD.csv'
VARIABLES_FILE = f"{BASE_DIR_PROYECTO}/variables.txt"

# Configuración de Logs: /logs/Oracle/YYYY-MM-DD
FECHA_HOY = datetime.now().strftime("%Y-%m-%d")
LOG_DIR = f"{BASE_DIR_PROYECTO}/logs/Oracle/{FECHA_HOY}"

# Configuración InfluxDB
INFLUX_BUCKET_NAME = "status_services"
INFLUX_MEASUREMENT = "status_check_oracleDB"

def probar_conexion_real(ip, service):
    """ Valida disponibilidad detectando respuestas del motor Oracle """
    
    # Construcción de DSN robusto (Modo TNS completo)
    # CONNECT_TIMEOUT ayuda a no quedar colgado si el servidor no responde rápido
    dsn = (
        f"(DESCRIPTION="
        f"(CONNECT_TIMEOUT=5)(TRANSPORT_CONNECT_TIMEOUT=3)"
        f"(ADDRESS=(PROTOCOL=TCP)(HOST={ip.strip()})(PORT=1521))"
        f"(CONNECT_DATA=(SERVICE_NAME={service.strip()})))"
    )

    # Diccionario de errores ORA conocidos para diagnóstico preciso
    ERRORES_MAP = {
        12170: "TIMEOUT (Posible Firewall bloqueando tráfico)",
        12543: "Error de red: Destino inalcanzable",
        12541: "TNS: No hay listener (El proceso Listener está abajo)",
        12154: "TNS: No se pudo resolver el nombre (Check SERVICE_NAME)",
        12514: "TNS: El Listener no conoce el servicio (Revisar lsnrctl status)",
        12505: "TNS: SID incorrecto o no registrado en el listener",
        1017:  "Instancia Up (Login validado)",
        1045:  "Instancia Up (Falta permiso de sesión)",
        1033:  "Instancia en proceso de INICIO o APAGADO",
        12516: "TNS: Límite de procesos excedido (DB Saturada)",
        12520: "TNS: Límite de sesiones excedido",
        257:   "ERROR: Archive Log lleno (DB bloqueada)",
        28000: "Instancia Up (Cuenta Bloqueada)",
        28001: "Instancia Up (Password Expirado)"
    }

    try:
        # Intento de conexión con credenciales erróneas (Modo Thin por defecto)
        oracledb.connect(user="USER_MONITOR", password="WRONG_PASSWORD_123", dsn=dsn)
        return "up", "OK", "Instancia Up (Login Ok)"

    except Exception as e:
        msg = str(e).upper()
        code = 0

        # Extraer el código ORA si es un DatabaseError
        if hasattr(e, 'args') and len(e.args) > 0 and hasattr(e.args[0], 'code'):
            code = e.args[0].code

        # --- 1. DETECCIÓN DE INSTANCIA VIVA (UP) ---
        # Si el código ORA confirma respuesta del motor (la base nos contestó que el login es malo, ergo está viva)
        if code in [1017, 1045, 28000, 28001]:
            return "up", "OK", ERRORES_MAP.get(code, f"Instancia Up (ORA-{code})")

        # Errores de compatibilidad o protocolos de autenticación
        if any(x in msg for x in ["DPY-3015", "DPY-3010", "0X939", "VERIFIER", "AUTHENTICATION"]):
            return "up", "OK", "Instancia Up (Login validado - Protocolo OK)"

        # --- 2. CATEGORIZACIÓN DE CAÍDAS (DOWN) ---
        if code != 0:
            detalle = ERRORES_MAP.get(code, f"ORA-{code}: {msg[:50]}")
            return "down", f"ORA-{code}", detalle

        # Errores específicos de la interfaz DPY de python-oracledb
        if "DPY-6005" in msg:
            # Si el puerto está abierto (visto por nc), DPY-6005 suele ser rechazo por parte del Listener
            return "down", "DPY-6005", "Rechazo del Listener (Puerto OK, pero conexión rechazada)"

        if "TIMEOUT" in msg or "DPY-6011" in msg:
            return "down", "TIMEOUT", "Timeout: Red lenta o Firewall descartando paquetes"

        # Fallo de red genérico o error desconocido
        return "down", "NETWORK_ERROR", msg[:60].replace("\n", " ")

def subir_a_influx(datos):
    """ Envía los resultados a InfluxDB """
    try:
        from influxdb_client import InfluxDBClient, Point
        from influxdb_client.client.write_api import SYNCHRONOUS
        
        if not os.path.exists(VARIABLES_FILE):
            print(f"⚠️ No se encontró el archivo de variables: {VARIABLES_FILE}")
            return

        creds = {}
        with open(VARIABLES_FILE, "r") as vf:
            for line in vf:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    creds[k.strip()] = v.strip()

        client = InfluxDBClient(url=creds["INFLUX_URL"], token=creds["INFLUX_TOKEN"], org=creds["INFLUX_ORG"])
        write_api = client.write_api(write_options=SYNCHRONOUS)

        for r in datos:
            p = Point(INFLUX_MEASUREMENT)\
                .tag("db_id", r["db_id"])\
                .tag("ip", r["ip"])\
                .tag("tipo_error", r["tipo_error"])\
                .field("status_value", 1 if r["status"] == "up" else 0)\
                .field("detalle", r["detalle"])\
                .time(datetime.utcnow())
            write_api.write(bucket=INFLUX_BUCKET_NAME, record=p)
            
        client.close()
        print(f"✅ InfluxDB actualizado correctamente.")
    except Exception as e:
        print(f"⚠️ InfluxDB Error: {e}")

def ejecutar():
    if not os.path.exists(ARCHIVO_ENTRADA):
        print(f"❌ Error: No existe el archivo de entrada {ARCHIVO_ENTRADA}")
        return

    os.makedirs(LOG_DIR, exist_ok=True)
    now = datetime.now(ZoneInfo("America/Bogota"))
    resultados = []

    print(f"--- Escaneando Oracle ({now.strftime('%Y-%m-%d %H:%M:%S')}) ---")

    with open(ARCHIVO_ENTRADA, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter=';')
        for fila in reader:
            # Limpiar espacios en los nombres de las columnas
            fila = {k.strip(): v for k, v in fila.items() if k}
            
            ip = fila.get('DIRECCION_IP', '').strip()
            id_bd = fila.get('BD_ID', '').strip()

            if not ip or not id_bd:
                continue

            print(f"Validando {id_bd:25}...", end=" ", flush=True)
            status, tipo, detalle = probar_conexion_real(ip, id_bd)
            print(f"[{status.upper()}] - {detalle}")

            resultados.append({
                "db_id": id_bd, 
                "ip": ip, 
                "status": status,
                "tipo_error": tipo, 
                "detalle": detalle, 
                "timestamp": now.isoformat()
            })

    # Guardar log local en JSON
    archivo_log = f"{LOG_DIR}/scan_{now.strftime('%H%M%S')}.json"
    with open(archivo_log, "w") as jf:
        json.dump(resultados, jf, indent=2)

    print(f"\n📂 Log generado: {archivo_log}")
    subir_a_influx(resultados)

if __name__ == "__main__":
    ejecutar()
