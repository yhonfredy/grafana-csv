import oracledb
import csv
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# === CONFIGURACIÓN DE RUTAS ABSOLUTAS ===
BASE_DIR = "/home/ssm-user/SETI/validarServicios"
ARCHIVO_ENTRADA = f"{BASE_DIR}/estadoSaludBD.csv"
VARIABLES_FILE = f"{BASE_DIR}/variables.txt"

# Carpeta de logs según tu estructura: logs/fecha_actual/Oracle
FECHA_HOY = datetime.now().strftime("%Y-%m-%d")
LOG_DIR = f"{BASE_DIR}/logs/{FECHA_HOY}/Oracle"

INFLUX_BUCKET_NAME = "status_services"
INFLUX_MEASUREMENT = "status_check_oracleDB"

def probar_conexion_real(ip, service):
    dsn = f"{ip.strip()}:1521/{service.strip()}"
    try:
        # Intento de login real para validar que la instancia responda
        oracledb.connect(user="USER_MONITOR", password="WRONG_PASSWORD_123", dsn=dsn)
        return "up", "OK", "Instancia Up (Login Ok)"
    except oracledb.DatabaseError as e:
        error_obj, = e.args
        code = error_obj.code
        # Si responde ORA-01017 o ORA-01045, el motor está vivo
        if code in [1017, 1045]:
            return "up", "OK", f"Instancia Up (ORA-{code})"
        else:
            return "down", f"ORA-{code}", error_obj.message.strip()
    except Exception as e:
        return "down", "NETWORK_ERROR", str(e)[:50]

def subir_a_influx(datos):
    try:
        from influxdb_client import InfluxDBClient, Point
        from influxdb_client.client.write_api import SYNCHRONOUS

        if not os.path.exists(VARIABLES_FILE):
            print(f"⚠️ No se encontró {VARIABLES_FILE}, saltando InfluxDB.")
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
                .field("status_value", 1 if r["status"] == "up" else 0)\
                .field("detalle", r["detalle"])\
                .time(datetime.utcnow())
            write_api.write(bucket=INFLUX_BUCKET_NAME, record=p)
        
        client.close()
        print(f"✅ Datos subidos a InfluxDB correctamente.")
    except Exception as e:
        print(f"⚠️ Error en InfluxDB: {e}")

def ejecutar():
    if not os.path.exists(ARCHIVO_ENTRADA):
        print(f"❌ Error: No existe el archivo {ARCHIVO_ENTRADA}")
        return

    # Crear la carpeta de logs del día si no existe
    os.makedirs(LOG_DIR, exist_ok=True)
    
    now_bogota = datetime.now(ZoneInfo("America/Bogota"))
    resultados_json = []
    
    print(f"--- Iniciando Escaneo Oracle: {now_bogota.strftime('%H:%M:%S')} ---")

    try:
        with open(ARCHIVO_ENTRADA, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f, delimiter=';')
            
            for fila in reader:
                # Limpiar encabezados
                fila = {k.strip(): v for k, v in fila.items() if k}
                
                ip = fila.get('DIRECCION_IP', '').strip()
                id_bd = fila.get('BD_ID', '').strip()

                if not ip or not id_bd: continue

                print(f"Validando {id_bd:20}...", end=" ", flush=True)
                status, tipo_err, detalle = probar_conexion_real(ip, id_bd)
                print(f"[{status.upper()}]")

                resultados_json.append({
                    "db_id": id_bd,
                    "ip": ip,
                    "ambiente": fila.get('AMBIENTE', 'N/A'),
                    "status": status,
                    "tipo_error": tipo_err,
                    "detalle": detalle,
                    "timestamp": now_bogota.isoformat()
                })

        # 1. Guardar Log JSON en la ruta: /logs/YYYY-MM-DD/Oracle/
        log_file = f"{LOG_DIR}/check_oracle_{now_bogota.strftime('%H%M%S')}.json"
        with open(log_file, "w") as jf:
            json.dump(resultados_json, jf, indent=2)
        print(f"\n📝 Log guardado en: {log_file}")

        # 2. Subida a InfluxDB
        subir_a_influx(resultados_json)

    except KeyboardInterrupt:
        print("\n🚫 Proceso cancelado.")
    except Exception as e:
        print(f"\n❌ Error General: {e}")

if __name__ == "__main__":
    ejecutar()
