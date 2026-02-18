#!/usr/bin/env python3
import csv
import json
import os
import sys
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

# =========================
# CONFIGURACIÓN
# =========================
CSV_INPUT = sys.argv[1] if len(sys.argv) > 1 else "estadoSaludBD.csv"
TIMEOUT_SEC = 2  # Tiempo rápido para no demorar el reporte
LOG_DIR = "Logs/oracleDB"

INFLUX_BUCKET_NAME = "status_services"
INFLUX_MEASUREMENT = "status_check_oracleDB"

def check_socket_native(ip, port=1521):
    """ Verifica conectividad sin librerías externas """
    cmd = f"timeout {TIMEOUT_SEC} bash -c 'cat < /dev/tcp/{ip}/{port}' 2>&1"
    try:
        process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if process.returncode == 0:
            return "up", "OK", "Puerto Abierto"
        
        stderr = process.stderr.lower()
        if "refused" in stderr:
            return "down", "LISTENER_DOWN", "Conexion rechazada (Listener apagado)"
        else:
            return "down", "FIREWALL_TIMEOUT", "Sin respuesta (Posible Firewall)"
    except:
        return "down", "ERROR_SISTEMA", "No se pudo ejecutar bash"

def main():
    if not os.path.exists(CSV_INPUT):
        print(f"❌ Error: No se encuentra el archivo {CSV_INPUT}")
        sys.exit(1)

    os.makedirs(LOG_DIR, exist_ok=True)
    results = []
    now_bogota = datetime.now(ZoneInfo("America/Bogota"))
    print(f"📊 Procesando reporte: {CSV_INPUT}")

    with open(CSV_INPUT, encoding="utf-8") as f:
        # Usamos ; como delimitador porque es el estándar de tus reportes
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            db_id = row.get('BD_ID', 'N/A')
            ip = row.get('DIRECCION_IP', '').strip()
            if not ip: continue

            status, tipo, msg = check_socket_native(ip)
            print(f"-> {db_id} ({ip}): {status.upper()} [{tipo}]")

            results.append({
                "db_id": db_id,
                "ip": ip,
                "ambiente": row.get('AMBIENTE', 'N/A'),
                "status": status,
                "tipo_error": tipo,
                "detalle": msg,
                "timestamp": now_bogota.isoformat()
            })

    # Guardar LOG en la carpeta solicitada
    log_file = f"{LOG_DIR}/check_{now_bogota.strftime('%Y%m%d_%H%M%S')}.json"
    with open(log_file, "w") as jf:
        json.dump(results, jf, indent=2)
    print(f"📝 Log guardado en: {log_file}")

    # --- Subida a InfluxDB ---
    try:
        from influxdb_client import InfluxDBClient, Point
        from influxdb_client.client.write_api import SYNCHRONOUS

        creds = {}
        with open("variables.txt", "r") as vf:
            for line in vf:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    creds[k.strip()] = v.strip()

        client = InfluxDBClient(url=creds["INFLUX_URL"], token=creds["INFLUX_TOKEN"], org=creds["INFLUX_ORG"])
        write_api = client.write_api(write_options=SYNCHRONOUS)

        for r in results:
            p = Point(INFLUX_MEASUREMENT)\
                .tag("db_id", r["db_id"])\
                .tag("ip", r["ip"])\
                .tag("tipo_error", r["tipo_error"])\
                .field("status_value", 1 if r["status"] == "up" else 0)\
                .field("detalle", r["detalle"])\
                .time(datetime.utcnow())
            write_api.write(bucket=INFLUX_BUCKET_NAME, record=p)
        
        client.close()
        print(f"✅ Datos subidos a InfluxDB bucket: {INFLUX_BUCKET_NAME}")
    except Exception as e:
        print(f"⚠️ Nota: No se subió a InfluxDB (Verifica variables.txt)")

if __name__ == "__main__":
    main()
