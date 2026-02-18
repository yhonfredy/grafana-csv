#!/usr/bin/env python3
import subprocess
import csv
import json
import os
import sys
import time
import socket
from datetime import datetime
from zoneinfo import ZoneInfo

# =========================
# CONFIGURACIÓN
# =========================
# Lectura del CSV
CSV_INPUT = sys.argv[1] if len(sys.argv) > 1 else "estadoSaludBD.csv"
TIMEOUT_TCP = 10  # Segundos para el intento de conexión

INFLUX_BUCKET_NAME = "status_services"
INFLUX_MEASUREMENT = "status_check_oracleDB" # Medida solicitada

# =========================
# ANÁLISIS DE ERRORES DE RED/DB
# =========================
def analizar_error_red(ip, puerto):
    """
    Intenta una conexión TCP básica para determinar si el puerto está abierto.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT_TCP)
        result = sock.connect_ex((ip, puerto))
        sock.close()
        
        if result == 0:
            return {
                "tipo_error": "OK",
                "error_principal": "Puerto Abierto",
                "significado": "La red permite llegar al puerto 1521",
                "causa_probable": "Servicio disponible a nivel de red",
                "accion_recomendada": "Ninguna",
                "tcp_up": True
            }
        elif result == 111: # Connection refused
            return {
                "tipo_error": "SERVIDOR",
                "error_principal": "Connection refused",
                "significado": "IP alcanzable, pero el puerto está cerrado o el Listener caído",
                "causa_probable": "Servicio Oracle no iniciado o Firewall local bloqueando",
                "accion_recomendada": "Revisar status del listener (lsnrctl status)",
                "tcp_up": False
            }
        else: # Timeout u otros (110)
            return {
                "tipo_error": "RED_FIREWALL",
                "error_principal": "Connection timed out",
                "significado": "No hay respuesta de la IP/Puerto",
                "causa_probable": "Firewall perimetral bloqueando el tráfico o IP inexistente",
                "accion_recomendada": "Solicitar apertura de firewall (como el caso que montaste)",
                "tcp_up": False
            }
    except Exception as e:
        return {
            "tipo_error": "EXCEPCION",
            "error_principal": str(e),
            "significado": "Error al intentar socket",
            "causa_probable": "Error interno del script",
            "accion_recomendada": "Verificar permisos de red del servidor de monitoreo",
            "tcp_up": False
        }

# =========================
# EJECUCIÓN PRINCIPAL
# =========================
def main():
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Diagnóstico OracleDB -> InfluxDB")
    
    if not os.path.exists(CSV_INPUT):
        print(f"❌ ERROR: No se encuentra '{CSV_INPUT}'")
        sys.exit(1)

    # Crear estructura de carpetas de logs solicitada
    log_dir = "Logs/oracleDB"
    os.makedirs(log_dir, exist_ok=True)
    
    now_bogota = datetime.now(ZoneInfo("America/Bogota"))
    timestamp_str = now_bogota.strftime("%Y%m%d_%H%M%S")
    
    results = []
    
    # Procesar el CSV de salud (delimitador ;)
    with open(CSV_INPUT, encoding="utf-8") as f:
        # Usamos DictReader con el delimitador adecuado para tu archivo
        reader = csv.DictReader(f, delimiter=";")

        for row in reader:
            db_id = row.get('BD_ID', 'N/A')
            ip = row.get('DIRECCION_IP', '').strip()
            ambiente = row.get('AMBIENTE', 'N/A')
            status_previo = row.get('STATUS', 'UNKNOWN')
            
            if not ip: continue

            print(f"🔍 Validando {db_id} en {ip}...")

            # Realizar el chequeo técnico
            diagnostico = analizar_error_red(ip, 1521)
            
            # Unificar datos
            resultado_final = {
                "db_id": db_id,
                "ip": ip,
                "ambiente": ambiente,
                "puerto": 1521,
                "status_oracle": status_previo,
                "tcp_status": "up" if diagnostico["tcp_up"] else "down",
                "timestamp": now_bogota.isoformat(),
                **diagnostico
            }
            results.append(resultado_final)

    # =========================
    # GUARDAR LOG LOCAL (JSON Y TXT)
    # =========================
    log_json = f"{log_dir}/db_check_{timestamp_str}.json"
    with open(log_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    log_txt = f"{log_dir}/db_check_{timestamp_str}.txt"
    with open(log_txt, "w", encoding="utf-8") as f:
        f.write(f"REPORTE DE CONECTIVIDAD ORACLE - {timestamp_str}\n")
        f.write("-" * 80 + "\n")
        f.write(f"{'DB_ID':<25} {'IP':<15} {'TCP':<6} {'TIPO ERROR'}\n")
        for r in results:
            f.write(f"{r['db_id']:<25} {r['ip']:<15} {r['tcp_status']:<6} {r['tipo_error']}\n")

    print(f"✅ Logs guardados en {log_dir}")

    # =========================
    # SUBIDA A INFLUXDB
    # =========================
    try:
        from influxdb_client import InfluxDBClient, Point, WritePrecision
        from influxdb_client.client.write_api import SYNCHRONOUS

        # Leer variables.txt
        creds = {}
        with open("variables.txt", "r") as vf:
            for line in vf:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    creds[k.strip()] = v.strip()

        client = InfluxDBClient(url=creds["INFLUX_URL"], token=creds["INFLUX_TOKEN"], org=creds["INFLUX_ORG"])
        write_api = client.write_api(write_options=SYNCHRONOUS)

        for res in results:
            point = (
                Point(INFLUX_MEASUREMENT)
                .tag("db_id", res["db_id"])
                .tag("ip", res["ip"])
                .tag("ambiente", res["ambiente"])
                .tag("tipo_error", res["tipo_error"])
                .field("status_tcp", 1 if res["tcp_status"] == "up" else 0)
                .field("error_msg", res["error_principal"])
                .field("causa", res["causa_probable"])
                .time(datetime.utcnow(), WritePrecision.S)
            )
            write_api.write(bucket=INFLUX_BUCKET_NAME, org=creds["INFLUX_ORG"], record=point)

        client.close()
        print(f"📤 Datos enviados a InfluxDB (Bucket: {INFLUX_BUCKET_NAME})")

    except Exception as e:
        print(f"⚠️ Error InfluxDB: {e}")

if __name__ == "__main__":
    main()
