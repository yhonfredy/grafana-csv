#!/usr/bin/env python3
import subprocess
import csv
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

# =========================
# CONFIGURACIÓN
# =========================
CSV_URLS = "servicios.csv"
TIMEOUT_CONEXION = 10
TIMEOUT_TOTAL = 45  # Los 45 segundos que solicitaste

INFLUX_BUCKET_NAME = "status_services"
INFLUX_MEASUREMENT = "status_check_http" # Medición diferente para no mezclar con puertos

# =========================
# FUNCIONES
# =========================
def check_url(url):
    try:
        # Comando curl con los timeouts configurados
        comando = (
            f"curl -k -L -s -o /dev/null -w '%{{http_code}}' "
            f"--connect-timeout {TIMEOUT_CONEXION} "
            f"-m {TIMEOUT_TOTAL} '{url}'"
        )
        codigo = subprocess.check_output(comando, shell=True).decode('utf-8').strip()
        return codigo if codigo != "" else "000"
    except Exception:
        return "000"

# =========================
# EJECUCIÓN
# =========================
print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Check de URLs (Timeout Total: {TIMEOUT_TOTAL}s)")
print("=" * 70)

results = []
up = total = 0

if os.path.exists(CSV_URLS):
    try:
        with open(CSV_URLS, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                nombre = row['Nombre'].strip()
                url = row['URL'].strip()
                total += 1

                print(f"Validando: {nombre}...", end=" ", flush=True)
                codigo_status = check_url(url)
                
                # Consideramos UP si el código es 200 (puedes ajustar esto)
                is_up = (codigo_status == "200")
                if is_up:
                    up += 1
                    print(f"DONE -> {codigo_status}")
                else:
                    print(f"FAIL -> {codigo_status}")

                results.append({
                    "tipo": "url_http",
                    "nombre": nombre,
                    "url": url,
                    "status_code": int(codigo_status),
                    "is_up": 1 if is_up else 0
                })

    except Exception as e:
        print(f"Error procesando CSV: {e}")

# =========================
# SUBIDA A INFLUXDB (Misma lógica que tu script actual)
# =========================
if results:
    try:
        from influxdb_client import InfluxDBClient, Point, WritePrecision

        creds = {}
        with open("variables.txt", "r", encoding="utf-8") as vf:
            for line in vf:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    creds[k.strip()] = v.strip()

        client = InfluxDBClient(url=creds.get("INFLUX_URL"), 
                                token=creds.get("INFLUX_TOKEN"), 
                                org=creds.get("INFLUX_ORG"))
        write_api = client.write_api()

        for srv in results:
            point = (
                Point(INFLUX_MEASUREMENT)
                .tag("tipo", srv["tipo"])
                .tag("nombre", srv["nombre"])
                .field("url", srv["url"])
                .field("status", srv["status_code"])      # Guardamos el 200, 404, 500 o 000
                .field("is_up", srv["is_up"])             # 1 si es 200, 0 de lo contrario
                .time(datetime.utcnow(), WritePrecision.S)
            )
            write_api.write(bucket=INFLUX_BUCKET_NAME, org=creds.get("INFLUX_ORG"), record=point)
        
        client.close()
        print("\n¡Datos de URL subidos a InfluxDB!")
    except Exception as e:
        print(f"\nError InfluxDB: {e}")

print(f"\nRESUMEN: {up}/{total} URLs OK")
