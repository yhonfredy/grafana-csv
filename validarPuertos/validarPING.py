import csv
import socket
import sys
import json
from datetime import datetime

# ================= CONFIG =================
CSV_FILE = "ListadoWebLogic.csv"
TIMEOUT = 5                        # segundos
# =========================================

def check_tcp(ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(TIMEOUT)
    result = sock.connect_ex((ip, int(port)))
    sock.close()
    return result == 0

def extraer_ip_puerto(url):
    url = url.strip()
    if "http://" in url:
        url = url.replace("http://", "")
    if "https://" in url:
        url = url.replace("https://", "")
    # Quitar path y query
    host_port = url.split("/")[0]
    if ":" in host_port:
        ip, puerto = host_port.split(":")
        return ip.strip(), puerto.strip()
    else:
        return host_port.strip(), None

# ================= MAIN =================
results = []
up_count = 0
total_count = 0

print(f"--- Verificando puertos TCP de consolas WebLogic desde {CSV_FILE} ---")

with open(CSV_FILE, mode='r', encoding='utf-8') as f:
    reader = csv.reader(f)
    rows = [row for row in reader if row]  # eliminar filas vacías

# Buscar columna con URLs
url_col = 0
for i, cell in enumerate(rows[0]):
    if any(x in cell.lower() for x in ["http", "url", "console"]):
        url_col = i
        break

for row in rows[1:]:  # saltar encabezado
    if len(row) <= url_col or not row[url_col].strip():
        continue

    url = row[url_col].strip()
    nombre = row[0] if len(row) > 0 and row[0].strip() else url.split("/")[2] if "/" in url else "SinNombre"

    ip, puerto = extraer_ip_puerto(url)
    if not ip or not puerto:
        print(f"SKIP {nombre} → No se pudo extraer IP:Puerto de: {url}")
        continue

    total_count += 1
    esta_up = check_tcp(ip, puerto)

    status = "up" if esta_up else "down"
    emoji = "UP" if esta_up else "DOWN"
    print(f"{emoji} {nombre.ljust(25)} → {ip}:{puerto} → {'ABIERTO' if esta_up else 'CERRADO'}")

    if esta_up:
        up_count += 1

    results.append({
        "nombre": nombre,
        "ip": ip,
        "puerto": int(puerto),
        "url_original": url,
        "puerto_abierto": esta_up,
        "status": status
    })

# === JSON FINAL ===
final = {
    "check_timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    "total": total_count,
    "up": up_count,
    "down": total_count - up_count,
    "up_percentage": round(up_count/total_count*100, 2) if total_count else 0,
    "consolas": results
}

timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
filename = f"weblogic_tcp_check_{timestamp}.json"
with open(filename, 'w', encoding='utf-8') as f:
    json.dump(final, f, ensure_ascii=False, indent=2)

print("\n" + "="*60)
print(f"RESUMEN: {up_count}/{total_count} consolas con puerto TCP abierto")
print(f"Archivo: {filename}")
print("="*60)
