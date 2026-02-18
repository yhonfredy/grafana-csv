import oracledb
import csv
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# === CONFIGURACIÓN ===
ARCHIVO_ENTRADA = 'estadoSaludBD.csv'
LOG_DIR = "Logs/oracleDB"
INFLUX_BUCKET_NAME = "status_services"
INFLUX_MEASUREMENT = "status_check_oracleDB"

def probar_conexion_real(ip, service):
    dsn = f"{ip.strip()}:1521/{service.strip()}"
    try:
        # Modo Thin de oracledb (No requiere cliente Oracle instalado)
        oracledb.connect(user="USER_MONITOR", password="WRONG_PASSWORD_123", dsn=dsn)
        return "up", "OK", "Instancia Up (Login Ok)"
    except oracledb.DatabaseError as e:
        error_obj, = e.args
        code = error_obj.code
        # ORA-01017 o ORA-01045 significan que la BD respondió (está viva)
        if code in [1017, 1045]:
            return "up", "OK", f"Instancia Up (ORA-{code})"
        else:
            return "down", f"ORA-{code}", error_obj.message.strip()
    except Exception as e:
        return "down", "NETWORK_ERROR", str(e)[:50]

def ejecutar():
    if not os.path.exists(ARCHIVO_ENTRADA):
        print(f"❌ Error: No existe {ARCHIVO_ENTRADA}")
        return

    os.makedirs(LOG_DIR, exist_ok=True)
    now_bogota = datetime.now(ZoneInfo("America/Bogota"))
    resultados_json = []
    
    print(f"--- Iniciando Escaneo: {now_bogota.strftime('%Y-%m-%d %H:%M:%S')} ---")
    print("Pulse Ctrl+C para detener.\n")

    try:
        # utf-8-sig elimina el BOM (caracteres raros al inicio del Excel)
        with open(ARCHIVO_ENTRADA, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f, delimiter=';')
            
            for fila in reader:
                # Limpiar espacios en los nombres de las columnas
                fila = {k.strip(): v for k, v in fila.items() if k}
                
                ip = fila.get('DIRECCION_IP', '').strip()
                id_bd = fila.get('BD_ID', '').strip()

                if not ip or not id_bd:
                    continue

                print(f"Validando {id_bd:20} ({ip})...", end=" ", flush=True)
                
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

        # 1. Guardar Log JSON
        log_file = f"{LOG_DIR}/check_{now_bogota.strftime('%Y%m%d_%H%M%S')}.json"
        with open(log_file, "w") as jf:
            json.dump(resultados_json, jf, indent=2)
        
        # 2. Subir a InfluxDB
        subir_a_influx(resultados_json)

    except KeyboardInterrupt:
        print("\n\n🚫 Escaneo cancelado por el usuario.")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")

def subir_a_influx(datos):
    try:
        from influxdb_client import InfluxDBClient, Point
        from influxdb_client.client.write_api import SYNCHRONOUS

        if not os.path.exists("variables.txt"): return

        creds = {}
        with open("variables.txt", "r") as vf:
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
        print(f"\n✅ Datos enviados a InfluxDB")
    except Exception as e:
        print(f"\n⚠️ InfluxDB no actualizado: {e}")

if __name__ == "__main__":
    ejecutar()
