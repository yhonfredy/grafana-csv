#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import telnetlib   # ← esto es lo nuevo
import sys
import json
from datetime import datetime

# ==================== CONFIGURACIÓN ====================
CSV_FILE = "ListadoWebLogic.csv"
TELNET_TIMEOUT = 8      # segundos (un poco más que antes)
JSON_LOG = True
# ======================================================

def check_telnet(ip, port):
    """Devuelve True si hay banner o respuesta Telnet (WebLogic vivo)"""
    try:
        tn = telnetlib.Telnet(ip, port, timeout=TELNET_TIMEOUT)
        # WebLogic suele responder algo como "BEA-" o "Oracle WebLogic" en los primeros bytes
        respuesta = tn.read_some()  # lee hasta 1024 bytes o timeout
        tn.close()
        return True
    except Exception as e:
        return False

# ==================== LECTURA CSV Y CHECKS ====================
print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Iniciando verificación WebLogic vía Telnet")

results = []
up_count = 0
total_count = 0

try:
    with open(CSV_FILE, mode='r', encoding='utf-8', errors='ignore') as f:
        sample = f.read(4096)
        f.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        f.seek(0)
        reader = csv.reader(f, dialect)

        header = next(reader)
        header = [col.strip().lower() for col in header]

        col_nombre = next((i for i, h in enumerate(header) if "nombre" in h or "admin" in h), 0)
        col_ip     = next((i for i, h in enumerate(header) if "ip" in h), 1)
        col_puerto = next((i for i, h in enumerate(header) if "puerto" in h), 2)

        for num_linea, row in enumerate(reader, start=2):
            if len(row) < max(col_nombre, col_ip, col_puerto) + 1:
                continue

            nombre = row[col_nombre].strip() or f"Servidor_fila_{num_linea}"
            ip     = row[col_ip].strip()
            puerto = row[col_puerto].strip()

            if not ip or not puerto.isdigit():
                continue

            total_count += 1
            esta_up = check_telnet(ip, int(puerto))
            status = "up" if esta_up else "down"

            print(f"{'UP' if esta_up else 'DOWN'} {nombre.ljust(40)} → {ip}:{puerto} → {'RESPONDIO' if esta_up else 'SIN RESPUESTA'}")

            if esta_up:
                up_count += 1

            results.append({
                "nombre": nombre,
                "ip": ip,
                "puerto": int(puerto),
                "status": status,
                "puerto_abierto": 1 if esta_up else 0
            })

# ==================== GUARDAR JSON LOCAL ====================
if JSON_LOG and results:
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    filename = f"weblogic_check_{timestamp}.json"
    final_json = {
        "check_timestamp": datetime.now().isoformat() + "Z",
        "total_servers": total_count,
        "summary": {"up": up_count, "down": total_count - up_count,
                    "up_percentage": round(up_count / total_count * 100, 2) if total_count else 0},
        "servers": results
    }
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)
    print(f"JSON de log guardado → {filename}")

# ==================== SUBIR A FIREBASE ====================
try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        cred = credentials.Certificate("setisegurosbolivar-firebase.json")
        firebase_admin.initialize_app(cred)

    db = firestore.client()
    collection = db.collection("weblogic_checks")

    print("Subiendo datos a Firestore vía Telnet...")
    batch = db.batch()
    count = 0

    for srv in results:
        doc_id = f"{srv['nombre']}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}"
        ref = collection.document(doc_id)
        doc_data = {
            "nombre": srv["nombre"],
            "ip": srv["ip"],
            "puerto": srv["puerto"],
            "status": srv["status"],
            "puerto_abierto": srv["puerto_abierto"],
            "timestamp": datetime.utcnow(),
            "check_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "metodo": "telnet"
        }
        batch.set(ref, doc_data)
        count += 1
        if count % 500 == 0:
            batch.commit()
            batch = db.batch()
    if count % 500 != 0:
        batch.commit()

    print(f"¡Subidos {len(results)} registros (check por Telnet) a Firestore!")

except ImportError:
    print("firebase-admin no instalado → sudo pip3 install firebase-admin")
except Exception as e:
    print(f"Error Firebase: {e}")

# ==================== RESUMEN ====================
print("\n" + "="*70)
print(f"RESUMEN (check por Telnet): {up_count}/{total_count} servidores RESPONDIERON")
print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*70)
