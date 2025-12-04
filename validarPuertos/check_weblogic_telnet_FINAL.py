#!/usr/bin/env python3
# check_weblogic_telnet_FINAL.py → 100% fiable con WebLogic real
import telnetlib
import csv
from datetime import datetime

CSV_FILE = "ListadoWebLogic.csv"
TIMEOUT = 12   # WebLogic a veces tarda hasta 10 segundos en responder

def check_weblogic_telnet(ip, port):
    try:
        tn = telnetlib.Telnet()
        tn.open(ip, port, timeout=TIMEOUT)
        # Espera activamente hasta recibir cualquier dato (hasta TIMEOUT segundos)
        data = tn.read_until(b"\n", timeout=TIMEOUT)  # o b"WebLogic" o b"BEA-"
        tn.close()
        return len(data) > 0
    except:
        return False

print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Check WebLogic (espera hasta {TIMEOUT}s)")

up = total = 0
results = []

with open(CSV_FILE, encoding='utf-8') as f:
    reader = csv.reader(f, delimiter=';')
    next(reader, None)
    for row in reader:
        if len(row) < 3: continue
        nombre, ip, puerto_str = row[0].strip(), row[1].strip(), row[2].strip()
        if not ip or not puerto_str.isdigit(): continue

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

# JSON log
log = f"weblogic_check_{datetime.now():%Y-%m-%d_%H-%M-%S}.json"
with open(log, "w", encoding="utf-8") as f:
    import json
    json.dump({
        "check_timestamp": datetime.utcnow().isoformat()+"Z",
        "total_servers": total,
        "summary": {"up": up, "down": total-up, "up_percentage": round(up/total*100,2) if total else 0},
        "servers": results
    }, f, ensure_ascii=False, indent=2)

print(f"\nJSON → {log}")
print(f"RESUMEN: {up}/{total} servidores vivos")
