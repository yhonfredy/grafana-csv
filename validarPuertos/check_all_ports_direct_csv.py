import csv
import socket
import sys
import json
from datetime import datetime

# =============== CONFIGURACIÓN ===============
CSV_FILE = "ListadoWebLogic.csv"   
TIMEOUT = 5                        # segundos de timeout
# =============================================

def check_tcp(ip, port):
    """Devuelve True si el puerto está ABIERTO"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        result = sock.connect_ex((ip, int(port)))
        sock.close()
        return result == 0
    except:
        return False
    finally:
        sock.close()

# =================== MAIN ====================
print(f"--- Verificando puertos WebLogic desde el CSV: {CSV_FILE} ---")

results = []
up_count = 0
total_count = 0

with open(CSV_FILE, mode='r', encoding='utf-8', errors='ignore') as f:
    # Detectar automáticamente el separador (coma, punto y coma, tab…)
    sample = f.read(4096)
    f.seek(0)
    dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    f.seek(0)
    reader = csv.reader(f, dialect)

    # Lee la primera fila como encabezado
    header = next(reader)
    header = [col.strip().lower() for col in header]

    # Encuentra índices de columnas (insensible a mayúsculas y orden)
    try:
        col_nombre = next(i for i, h in enumerate(header) if "nombre" in h or "admin" in h)
        col_ip     = next(i for i, h in enumerate(header) if "ip" in h)
        col_puerto = next(i for i, h in enumerate(header) if "puerto" in h)
    except StopIteration:
        print("No se encontraron las columnas esperadas (Nombre, IP, Puerto)")
        sys.exit(1)

    for num_linea, row in enumerate(reader, start=2):
        if len(row) < 3:
            continue

        nombre = row[col_nombre].strip() or f"Servidor_fila_{num_linea}"
        ip     = row[col_ip].strip()
        puerto = row[col_puerto].strip()

        if not ip or not puerto.isdigit():
            print(f"Saltando fila {num_linea}: IP o Puerto inválido → {row}")
            continue

        total_count += 1
        esta_up = check_tcp(ip, puerto)

        status = "up" if esta_up else "down"
        emoji = "UP" if esta_up else "DOWN"
        print(f"{emoji} {nombre.ljust(35)} → {ip}:{puerto} → {'ABIERTO' if esta_up else 'CERRADO'}")

        if esta_up:
            up_count += 1

        results.append({
            "nombre": nombre,
            "ip": ip,
            "puerto": int(puerto),
            "status": status,
            "puerto_abierto": esta_up
        })

# =============== JSON FINAL (igual que antes) ===============
final_json = {
    "check_timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    "total_servers": total_count,
    "summary": {
        "up": up_count,
        "down": total_count - up_count,
        "up_percentage": round(up_count / total_count * 100, 2) if total_count > 0 else 0
    },
    "servers": results
}

timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
filename = f"weblogic_tcp_check_{timestamp}.json"

with open(filename, 'w', encoding='utf-8') as f:
    json.dump(final_json, f, ensure_ascii=False, indent=2)

print("\n" + "="*70)
print(f"RESUMEN: {up_count}/{total_count} puertos WebLogic ABIERTOS")
print(f"Archivo generado → {filename}")
print("="*70)
