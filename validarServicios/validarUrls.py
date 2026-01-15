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
TIMEOUT_TOTAL = 45

INFLUX_BUCKET_NAME = "status_services"
INFLUX_MEASUREMENT = "status_check_http"

# =========================
# FUNCIONES
# =========================
def check_url(url):
    try:
        # Comando curl optimizado
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

                print(f"Validando: {nombre.ljust(45)}", end=" ", flush=True)
                codigo_status = check_url(url)

                # Consideramos UP si el código es 200
                is_up = (codigo_status == "200")
                if is_up:
                    up += 1
                    status_text = "up"
                    print(f"→ DONE ({codigo_status})")
                else:
                    status_text = "down"
                    print(f"→ FAIL ({codigo_status})")

                # Estructura idéntica a validarServicios.py para consistencia
                results.append({
                    "tipo": "url_http",
                    "nombre": nombre,
                    "ip": url,          # Usamos la URL en el campo IP para el tag
                    "puerto": 80 if url.startswith("http://") else 443,
                    "status": status_text,
                    "status_code": int(codigo_status)
                })

    except Exception as e:
        print(f"Error procesando CSV: {e}")

# =========================
# JSON LOCAL (HISTÓRICO)
# =========================
if total > 0:
    now = datetime.now(ZoneInfo("America/Bogota"))
    folder = now.strftime("logs/%Y-%m-%d")
    os.makedirs(folder, exist_ok=True)

    log_file = f"{folder}/urls_check_{now:%Y-%m-%d_%H-%M-%S}.json"

    try:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump({
                "check_timestamp_local": now.isoformat(),
                "check_timestamp_utc": datetime.utcnow().isoformat() + "Z",
                "total_urls": total,
                "summary": {
                    "up": up,
                    "down": total - up,
                    "up_percentage": round(up / total * 100, 2)
                },
                "services": results
            }, f, ensure_ascii=False, indent=2)
        print(f"\nJSON local guardado → {log_file}")
    except Exception as e:
        print(f"Error guardando JSON: {e}")

# =========================
# SUBIDA A INFLUXDB
# =========================
try:
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS

    # Leer credenciales
    creds = {}
    with open("variables.txt", "r", encoding="utf-8") as vf:
        for line in vf:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                creds[k.strip()] = v.strip()

    url_inf = creds.get("INFLUX_URL")
    token = creds.get("INFLUX_TOKEN")
    org = creds.get("INFLUX_ORG")

    if not url_inf or not token or not org:
        raise Exception("Credenciales incompletas en variables.txt")

    client = InfluxDBClient(url=url_inf, token=token, org=org)
    # Usamos SYNCHRONOUS para asegurar que los datos se envíen antes de cerrar
    write_api = client.write_api(write_options=SYNCHRONOUS)

    print("Subiendo resultados a InfluxDB...")

    for srv in results:
        point = (
            Point(INFLUX_MEASUREMENT)
            .tag("tipo", srv["tipo"])
            .tag("nombre", srv["nombre"])
            .tag("ip", srv["ip"])  # Aquí va la URL
            .field("puerto", srv["puerto"])
            .field("puerto_abierto", 1 if srv["status"] == "up" else 0)
            .field("status", 1 if srv["status"] == "up" else 0)
            .field("http_code", srv["status_code"]) # Campo extra útil para HTTP
            .time(datetime.utcnow(), WritePrecision.S)
        )
        write_api.write(bucket=INFLUX_BUCKET_NAME, org=org, record=point)

    write_api.close()
    client.close()
    print(f"¡Subidos {len(results)} registros a InfluxDB!")

except ImportError:
    print("influxdb-client no instalado → pip3 install influxdb-client")
except Exception as e:
    print(f"Error InfluxDB: {e}")

# =========================
# RESUMEN FINAL
# =========================
print("\n" + "=" * 70)
if total > 0:
    print(f"RESUMEN: {up}/{total} URLs OK ({round(up/total*100,2)}%)")
else:
    print("No se procesaron URLs.")
print("=" * 70)
