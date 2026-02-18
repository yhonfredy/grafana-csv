#!/usr/bin/env python3
import csv
import json
import os
import sys
import socket
from datetime import datetime
from zoneinfo import ZoneInfo

# Intentar importar la librería de Oracle (pip install python-oracledb)
try:
    import oracledb
    ORACLE_LIB_AVAILABLE = True
except ImportError:
    ORACLE_LIB_AVAILABLE = False

# =========================
# CONFIGURACIÓN
# =========================
CSV_INPUT = sys.argv[1] if len(sys.argv) > 1 else "Reporte_Salud_Final_20260218_1936.csv"
TIMEOUT_TCP = 3
USER_TEST = "check_monitoreo"  # Usuario ficticio para probar
PASS_TEST = "temp_pass_123"

INFLUX_BUCKET_NAME = "status_services"
INFLUX_MEASUREMENT = "status_check_oracleDB"

def validar_db_full(ip, puerto, service_name):
    """
    Lógica de doble validación: Red + Aplicación (Login)
    """
    resultado = {
        "tipo_error": "OK",
        "error_principal": "UP",
        "status_final": "up",
        "nivel": "APP"
    }

    # 1. VALIDACIÓN DE RED (Socket)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT_TCP)
        conn_result = sock.connect_ex((ip, puerto))
        sock.close()
        
        if conn_result != 0:
            return {
                "tipo_error": "RED_FIREWALL",
                "error_principal": "Timeout / Firewall",
                "status_final": "down",
                "nivel": "RED"
            }
    except Exception as e:
        return {"tipo_error": "ERROR_SCRIPT", "error_principal": str(e), "status_final": "down", "nivel": "OS"}

    # 2. VALIDACIÓN DE LOGIN (Si la red funcionó)
    if ORACLE_LIB_AVAILABLE and service_name:
        try:
            # Intentamos conectar. oracledb.connect por defecto usa modo "thin" (sin cliente Oracle)
            oracledb.connect(user=USER_TEST, password=PASS_TEST, host=ip, port=puerto, service_name=service_name)
        except oracledb.Error as e:
            error_obj, = e.args
            # ORA-01017 es "credenciales inválidas". SI recibimos esto, ¡LA BD ESTÁ VIVA!
            if error_obj.code == 1017:
                resultado.update({"error_principal": "UP (Credenciales invalidas)", "status_final": "up"})
            # ORA-12541 es "TNS:no listener"
            elif error_obj.code == 12541:
                resultado.update({"tipo_error": "LISTENER_DOWN", "error_principal": "Listener no responde", "status_final": "down"})
            else:
                resultado.update({"tipo_error": f"ORA-{error_obj.code}", "error_principal": error_obj.message, "status_final": "down"})
    
    return resultado

def main():
    if not ORACLE_LIB_AVAILABLE:
        print("⚠️  Librería 'oracledb' no encontrada. Ejecute: pip install python-oracledb")
        print("Continuando solo con validación de RED (TCP)...")

    # Crear carpetas de logs
    log_dir = "Logs/oracleDB"
    os.makedirs(log_dir, exist_ok=True)
    now = datetime.now(ZoneInfo("America/Bogota"))
    
    results = []

    with open(CSV_INPUT, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            ip = row.get('DIRECCION_IP', '').strip()
            db_id = row.get('BD_ID', 'N/A')
            # Usamos INSTANCE_NAME o DATABASE_NAME como service_name para la conexión
            svc = row.get('INSTANCE_NAME') or row.get('DATABASE_NAME')

            if not ip: continue

            print(f"Testing {db_id} ({ip})... ", end="", flush=True)
            
            diag = validar_db_full(ip, 1521, svc)
            
            print(f"[{diag['status_final'].upper()}] - {diag['error_principal']}")

            results.append({
                "db_id": db_id,
                "ip": ip,
                "status": diag["status_final"],
                "error": diag["error_principal"],
                "tipo": diag["tipo_error"],
                "timestamp": now.isoformat()
            })

    # Guardar LOG Local
    log_file = f"{log_dir}/db_check_{now.strftime('%Y%m%d_%H%M%S')}.json"
    with open(log_file, "w") as jf:
        json.dump(results, jf, indent=2)

    # --- Envío a InfluxDB ---
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

        for res in results:
            p = Point(INFLUX_MEASUREMENT)\
                .tag("db_id", res["db_id"])\
                .tag("ip", res["ip"])\
                .field("status_value", 1 if res["status"] == "up" else 0)\
                .field("diagnostico", res["error"])\
                .time(datetime.utcnow())
            write_api.write(bucket=INFLUX_BUCKET_NAME, record=p)
        
        client.close()
        print("📤 Datos subidos a InfluxDB")
    except Exception as e:
        print(f"❌ Error InfluxDB: {e}")

if __name__ == "__main__":
    main()
