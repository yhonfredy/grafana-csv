#!/usr/bin/env python3
# check_weblogic_telnet_FIXED.py → 100% fiable al verificar la CONEXIÓN TCP
import telnetlib
import csv
import json
from datetime import datetime

CSV_FILE = "ListadoWebLogic.csv"
TIMEOUT = 5   # Reducido a 5 segundos, ya que solo necesitamos abrir el socket.

def check_weblogic_telnet(ip, port):
    """
    Verifica si se puede establecer una conexión TCP al puerto.
    No intenta leer datos, solo verifica la apertura del socket.
    """
    try:
        tn = telnetlib.Telnet()
        # Intentar abrir la conexión. Si tiene éxito, el servidor está UP.
        tn.open(ip, port, timeout=TIMEOUT)
        
        # Si la apertura es exitosa, cerramos la conexión y devolvemos True.
        tn.close()
        return True 
    except Exception: # Captura cualquier error de conexión (Timeout, Refused, etc.)
        return False

print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Check WebLogic (espera hasta {TIMEOUT}s)")

up = total = 0
results = []

try:
    with open(CSV_FILE, encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=';')
        next(reader, None) # Saltar la cabecera
        for row in reader:
            # Asegurar que haya al menos 3 columnas para evitar IndexError
            if len(row) < 3: 
                continue 
            
            # Limpiar espacios en blanco (uso de .strip() seguro en Python)
            nombre, ip, puerto_str = row[0].strip(), row[1].strip(), row[2].strip()
            
            if not ip or not puerto_str.isdigit(): 
                continue

            puerto = int(puerto_str)
            total += 1

            # Llama a la función de verificación corregida
            if check_weblogic_telnet(ip, puerto):
                print(f"UP   {nombre.ljust(50)} → {ip}:{puerto}")
                up += 1
                status = "up"
            else:
                print(f"DOWN {nombre.ljust(50)} → {ip}:{puerto}")
                status = "down"

            results.append({"nombre": nombre, "ip": ip, "puerto": puerto, "status": status})

except FileNotFoundError:
    print(f"Error: El archivo CSV '{CSV_FILE}' no fue encontrado.")
    total = 0 # No hacer el resumen si no hay archivo
except Exception as e:
    print(f"Ocurrió un error al procesar el archivo CSV: {e}")
    total = 0

# JSON log
if total > 0:
    log = f"weblogic_check_{datetime.now():%Y-%m-%d_%H-%M-%S}.json"
    try:
        with open(log, "w", encoding="utf-8") as f:
            json.dump({
                "check_timestamp": datetime.utcnow().isoformat()+"Z",
                "total_servers": total,
                "summary": {"up": up, "down": total-up, "up_percentage": round(up/total*100,2) if total else 0},
                "servers": results
            }, f, ensure_ascii=False, indent=2)

        print(f"\nJSON → {log}")
        print(f"RESUMEN: {up}/{total} servidores vivos")
    except Exception as e:
         print(f"Error al escribir el archivo JSON: {e}")
else:
    print("\nNo se procesó ningún servidor o el archivo CSV no existe.")
