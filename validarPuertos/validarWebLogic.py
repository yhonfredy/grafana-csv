import csv
import sys
import json
import time
from datetime import datetime
import urllib.request
import urllib.error

# =============== CONFIGURACIÓN ===============
CSV_FILE = "urls_consolas.csv"  
TIMEOUT = 10                          # segundos
USER_AGENT = "WebLogic-Console-Checker/1.0"

# =============================================
def check_url(url):
    """Verifica si la URL responde con código 200"""
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    start_time = time.time()
    
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            response_time = round((time.time() - start_time) * 1000, 2)
            status_code = response.getcode()
            if 200 <= status_code < 300:
                return {
                    "status": "up",
                    "message": f"OK {status_code} ({response_time}ms)",
                    "response_time_ms": response_time,
                    "http_code": status_code
                }
            else:
                return {
                    "status": "down",
                    "message": f"HTTP {status_code}",
                    "response_time_ms": response_time,
                    "http_code": status_code
                }
    except urllib.error.HTTPError as e:
        response_time = round((time.time() - start_time) * 1000, 2)
        return {
            "status": "down",
            "message": f"HTTP {e.code} {e.reason}",
            "response_time_ms": response_time,
            "http_code": e.code
        }
    except urllib.error.URLError as e:
        return {
            "status": "down",
            "message": f"Error de conexión: {e.reason}",
            "response_time_ms": None,
            "http_code": None
        }
    except Exception as e:
        return {
            "status": "down",
            "message": f"Error inesperado: {str(e)}",
            "response_time_ms": None,
            "http_code": None
        }

# =============================================
def main():
    results = []
    up_count = 0
    total_count = 0

    print(f"--- Leyendo archivo CSV: {CSV_FILE} ---")
    
    try:
        with open(CSV_FILE, mode='r', encoding='utf-8') as file:
            # Detecta automáticamente el delimitador
            sample = file.read(2048)
            file.seek(0)
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(sample).delimiter
            has_header = sniffer.has_header(sample)
            
            reader = csv.reader(file, delimiter=delimiter)
            rows = list(reader)
            
            if not rows:
                print("El CSV está vacío.")
                return
                
            # Encuentra la columna que tiene "http" (la de las URLs)
            url_column_idx = None
            header_row = rows[0] if has_header else None
            
            for idx, cell in enumerate(rows[0] if has_header else rows[0]):
                if any(x in cell.lower() for x in ["url", "http", "console", "link"]):
                    url_column_idx = idx
                    break
            
            # Si no encuentra por nombre, busca la primera columna con "http://" o "https://"
            if url_column_idx is None:
                for row_idx, row in enumerate(rows):
                    for col_idx, cell in enumerate(row):
                        if cell.strip().startswith(("http://", "https://")):
                            url_column_idx = col_idx
                            start_row = 0
                            break
                    if url_column_idx is not None:
                        break
                start_row = 0
            else:
                start_row = 1 if has_header else 0

            print(f"Columna de URLs detectada: {url_column_idx} | Iniciando desde fila {start_row + 1}")

            for i in range(start_row, len(rows)):
                row = rows[i]
                if len(row) <= url_column_idx:
                    continue
                    
                raw_url = row[url_column_idx].strip()
                if not raw_url.startswith(("http://", "https://")):
                    continue
                    
                # Nombre amigable: usa la columna anterior o siguiente si existe
                nombre = "Desconocido"
                if url_column_idx > 0 and row[url_column_idx - 1].strip():
                    nombre = row[url_column_idx - 1].strip()
                elif len(row) > url_column_idx + 1 and row[url_column_idx + 1].strip():
                    nombre = row[url_column_idx + 1].strip()
                else:
                    # Último recurso: extrae del path
                    try:
                        nombre = raw_url.split("/")[2].split(":")[0] + "_console"
                    except:
                        nombre = raw_url

                total_count += 1
                result = check_url(raw_url)
                
                emoji = "Up" if result["status"] == "up" else "Down"
                print(f"{emoji} {nombre} → {raw_url} | {result['message']}")
                
                if result["status"] == "up":
                    up_count += 1

                results.append({
                    "nombre": nombre,
                    "url": raw_url,
                    "status": result["status"],
                    "response_time_ms": result["response_time_ms"],
                    "http_code": result["http_code"],
                    "message": result["message"]
                })

    except FileNotFoundError:
        print(f"Archivo no encontrado: {CSV_FILE}")
        sys.exit(1)
    except Exception as e:
        print(f"Error leyendo el CSV: {e}")
        sys.exit(1)

    # === JSON FINAL ===
    final_json = {
        "check_timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "total_consolas": total_count,
        "summary": {
            "up": up_count,
            "down": total_count - up_count,
            "up_percentage": round((up_count / total_count * 100), 2) if total_count > 0 else 0
        },
        "consolas": results
    }

    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    filename = f"console-check_{timestamp}_FINAL.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)
    
    print("\n" + "="*60)
    print(f"REPORTE FINAL: {up_count}/{total_count} consolas arriba")
    print(f"Archivo guardado: {filename}")
    print("="*60)

if __name__ == "__main__":
    main()
