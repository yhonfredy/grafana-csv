#!/usr/bin/env python3
# check_weblogic_telnet_FIXED.py  + subida opcional a Firestore
import telnetlib
import csv
import json
from datetime import datetime

CSV_FILE = "ListadoWebLogic.csv"
TIMEOUT = 5  # segundos

def check_weblogic_telnet(ip, port):
    try:
        tn = telnetlib.Telnet()
        tn.open(ip, port, timeout=TIMEOUT)
        tn.close()
        return True
    except Exception:
        return False

print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Check WebLogic (timeout {TIMEOUT}s)")

up = total = 0
results = []

try:
    with open(CSV_FILE, encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=';')
        next(reader, None)  # Saltar cabecera
        for row in reader:
            if len(row) < 3:
                continue
            nombre, ip, puerto_str = row[0].strip(), row[1].strip(), row[2].strip()
            if not ip or not puerto_str.isdigit():
                continue
            puerto = int(puerto_str)
            total += 1

            if check_weblogic_telnet(ip, puerto):
                print(f"UP   {nombre.ljust(50)} → {ip}:{puerto}")
                up += 1
                status = "up"
            else:
                print(f"DOWN {nombre.ljust(50)} → {ip}:{puerto}")
                status = "down"

            results.append({"nombre": nombre, "ip": ip, "puerto": puerto, "status": status})

except FileNotFoundError:
    print(f"Error: Archivo CSV '{CSV_FILE}' no encontrado.")
    total = 0
except Exception as e:
    print(f"Error procesando CSV: {e}")
    total = 0

# === JSON local (log histórico) ===
if total > 0:
    log = f"weblogic_check_{datetime.now():%Y-%m-%d_%H-%M-%S}.json"
    try:
        with open(log, "w", encoding="utf-8") as f:
            json.dump({
                "check_timestamp": datetime.utcnow().isoformat() + "Z",
                "total_servers": total,
                "summary": {
                    "up": up,
                    "down": total - up,
                    "up_percentage": round(up / total * 100, 2) if total else 0
                },
                "servers": results
            }, f, ensure_ascii=False, indent=2)
        print(f"\nJSON local guardado → {log}")
    except Exception as e:
        print(f"Error guardando JSON: {e}")

# === SUBIDA A FIRESTORE (opcional, pero activada) ===
try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        cred = credentials.Certificate("setisegurosbolivar-firebase-adminsdk.json")  # ← archivo JSON
        firebase_admin.initialize_app(cred)

    db = firestore.client()
    collection = db.collection("weblogic_checks")

    print("Subiendo resultados a Firestore...")
    for srv in results:
        doc_id = f"{srv['nombre']}_{datetime.now().strftime('%Y%m%d_%H%M')}"
        doc_data = {
            "nombre": srv["nombre"],
            "ip": srv["ip"],
            "puerto": srv["puerto"],
            "status": srv["status"],
            "puerto_abierto": 1 if srv["status"] == "up" else 0,
            "timestamp": datetime.utcnow(),
            "check_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        collection.document(doc_id).set(doc_data)

    print(f"¡Subidos {len(results)} registros a Firestore!")
except ImportError:
    print("firebase-admin no instalado → sudo pip3 install firebase-admin")
except Exception as e:
    print(f"Error subiendo a Firestore: {e}")

# === RESUMEN FINAL ===
if total > 0:
    print(f"\nRESUMEN: {up}/{total} servidores vivos ({round(up/total*100,2)}%)")
else:
    print("\nNo se procesaron servidores.")

print("=" * 70)
