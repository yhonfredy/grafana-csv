#!/usr/bin/env python3
# check_weblogic_real_t3.py
# Usa el cliente oficial Oracle T3 (wlthint3client.jar)
# Detecta servidores colgados, reiniciados, etc.

import csv
import subprocess
import json
from datetime import datetime

CSV_FILE = "ListadoWebLogic.csv"
JAR = "wlthint3client.jar"   # ← tu archivo de 5.5M

def check_t3_real(ip, puerto, admin_user="weblogic", admin_pass="TuPassword2025"):
    cmd = [
        "java", "-cp", JAR,
        "weblogic.Admin",
        f"t3://{ip}:{puerto}",
        "-adminurl", f"t3://{ip}:{puerto}",
        "-username", admin_user,
        "-password", admin_pass,
        "VERSION"   # comando más ligero que existe
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return result.returncode == 0
    except:
        return False

print(f"[{datetime.now()}] Check WebLogic REAL T3 (wlthint3client)")

results = []
up = 0
total = 0

with open(CSV_FILE, encoding='utf-8') as f:
    reader = csv.reader(f, delimiter=';')
    next(reader)
    for row in reader:
        if len(row) < 3: continue
        nombre = row[0].strip()
        ip = row[1].strip()
        puerto = row[2].strip()
        total += 1

        if check_t3_real(ip, puerto):
            status = "up"
            up += 1
            print(f"UP   {nombre.ljust(50)} → {ip}:{puerto}")
        else:
            status = "down"
            print(f"DOWN {nombre.ljust(50)} → {ip}:{puerto}")

        results.append({"nombre": nombre, "ip": ip, "puerto": int(puerto), "status": status})

# JSON log
log = f"weblogic_t3_check_{datetime.now():%Y-%m-%d_%H-%M-%S}.json"
with open(log, "w", encoding="utf-8") as f:
    json.dump({
        "check_timestamp": datetime.utcnow().isoformat()+"Z",
        "total": total, "up": up, "down": total-up,
        "servers": results
    }, f, ensure_ascii=False, indent=2)

print(f"\nJSON → {log}")
print(f"RESUMEN REAL T3: {up}/{total} servidores vivos")
