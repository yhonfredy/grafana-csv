#!/usr/bin/env python3
# validarServicios.py
# Validación de puertos (WebLogic / SQL / futuros)
# Log JSON local + subida a InfluxDB

import telnetlib
import csv
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

# =========================
# CONFIGURACIÓN
# =========================

CSV_FILES = [
    "weblogic.csv",
    "sql.csv"
    # "simones.csv"
]

TIMEOUT = 5  # segundos

INFLUX_BUCKET_NAME = "servicios_status"
INFLUX_MEASUREMENT = "status_check"

# =========================
# FUNCIONES
# =========================

def check_port(ip, port):
    try:
        tn = telnetlib.Telnet()
        tn.open(ip, port, timeout=TIMEOUT)
        tn.close()
        return True
    except Exception:
        return False


def get_tipo_from_filename(filename):
    return os.path.splitext(os.path.basename(filename))[0].lower()

# =========================
# EJECUCIÓN
# =========================

print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Check de servicios (timeout {TIMEOUT}s)")
print("=" * 70)

results = []
up = total = 0

for CSV_FILE in CSV_FILES:

    tipo = get_tipo_from_filename(CSV_FILE)
    print(f"\nProcesando archivo: {CSV_FILE} → tipo = {tipo}")

    try:
        with open(CSV_FILE, encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=";")
            next(reader, None)  # saltar cabecera

            for row in reader:
                if len(row) < 3:
                    continue

                nombre, ip, puerto_str = row[0].strip(), row[1].strip(), row[2].strip()

                if not ip or not puerto_str.isdigit():
                    continue

                puerto = int(puerto_str)
                total += 1

                if check_port(ip, puerto):
                    print(f"UP   {tipo.upper():<10} {nombre.ljust(45)} → {ip}:{puerto}")
                    status = "up"
                    up += 1
                else:
                    print(f"DOWN {tipo.upper():<10} {nombre.ljust(45)} → {ip}:{puerto}")
                    status = "down"

                results.append({
                    "tipo": tipo,
                    "nombre": nombre,
                    "ip": ip,
                    "puerto": puerto,
                    "status": status
                })

    except FileNotFoundError:
        print(f"Archivo no encontrado: {CSV_FILE}")
    except Exception as e:
        print(f"Error procesando {CSV_FILE}: {e}")

# =========================
# JSON LOCAL (HISTÓRICO)
# =========================

if total > 0:
    now = datetime.now(ZoneInfo("America/Bogota"))
    folder = now.strftime("logs/%Y-%m-%d")
    os.makedirs(folder, exist_ok=True)

    log_file = f"{folder}/status_check_{now:%Y-%m-%d_%H-%M-%S}.json"

    try:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump({
                "check_timestamp_local": now.isoformat(),
                "check_timestamp_utc": datetime.utcnow().isoformat() + "Z",
                "total_services": total,
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

    # Leer credenciales
    creds = {}
    with open("variables.txt", "r", encoding="utf-8") as vf:
        for line in vf:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                creds[k.strip()] = v.strip()

    url = creds.get("INFLUX_URL")
    token = creds.get("INFLUX_TOKEN")
    org = creds.get("INFLUX_ORG")

    if not url or not token or not org:
        raise Exception("Credenciales incompletas en variables.txt")

    client = InfluxDBClient(url=url, token=token, org=org)
    write_api = client.write_api()

    print("\nSubiendo resultados a InfluxDB...")

    for srv in results:
        point = (
            Point(INFLUX_MEASUREMENT)
            .tag("tipo", srv["tipo"])
            .tag("nombre", srv["nombre"])
            .tag("ip", srv["ip"])
            .field("puerto", srv["puerto"])
            .field("puerto_abierto", 1 if srv["status"] == "up" else 0)
            .field("status", 1 if srv["status"] == "up" else 0)
            .time(datetime.utcnow(), WritePrecision.S)
        )
        write_api.write(bucket=INFLUX_BUCKET_NAME, org=org, record=point)

    client.close()
    print(f"¡Subidos {len(results)} registros a InfluxDB!")

except ImportError:
    print("influxdb-client no instalado → pip3 install influxdb-client")
except FileNotFoundError:
    print("Archivo 'variables.txt' no encontrado.")
except Exception as e:
    print(f"Error subiendo a InfluxDB: {e}")
finally:
    if "write_api" in locals():
        try:
            write_api.close()
        except:
            pass

# =========================
# RESUMEN FINAL
# =========================

print("\n" + "=" * 70)
if total > 0:
    print(f"RESUMEN: {up}/{total} servicios UP ({round(up/total*100,2)}%)")
else:
    print("No se procesaron servicios.")
print("=" * 70)
