import socket
import sys
import time
import json
from datetime import datetime
import urllib.request # Módulo nativo para descargar URLs

# URL DEL ARCHIVO JSON PÚBLICO
PUBLIC_JSON_URL = "https://raw.githubusercontent.com/yhonfredy/grafana-csv/refs/heads/main/urls/RevisionesCMDB_PROD.json"

# ==================================
# FUNCIÓN CENTRAL DE VERIFICACIÓN TCP
# ==================================
def check_tcp(ip, port, timeout=5):
    """Verifica si el puerto TCP está abierto usando el módulo socket."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    start_time = time.time()
    
    try:
        result = sock.connect_ex((ip, port))
        response_time = round((time.time() - start_time) * 1000, 2)
        
        if result == 0:
            return {
                "status": "up", 
                "message": f"OK ({response_time}ms)", 
                "response_time_ms": response_time
            }
        else:
            # Códigos de error comunes
            message = {
                110: "Timeout (5 segundos)",
                111: "Conexión rechazada (Cerrado/Firewall)",
                113: "Sin ruta"
            }.get(result, f"Error de socket {result}")
            
            return {
                "status": "down", 
                "message": message, 
                "response_time_ms": None
            }
            
    except Exception as e:
        return {
            "status": "down", 
            "message": f"Error: {e}", 
            "response_time_ms": None
        }
    finally:
        sock.close()

# ==================================
# LÓGICA PRINCIPAL: DESCARGAR Y PROCESAR
# ==================================
def download_and_process():
    """
    Descarga el JSON de GitHub, itera sobre los servidores y realiza la verificación TCP.
    """
    all_results = []
    up_count = 0
    total_count = 0

    print("--- 📥 Descargando lista de servidores desde GitHub... ---")
    try:
        with urllib.request.urlopen(PUBLIC_JSON_URL) as url:
            data = url.read().decode()
            servidores = json.loads(data)
    except urllib.error.URLError as e:
        print(f"🔴 ERROR de red al descargar la URL: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"🔴 ERROR al procesar el JSON descargado: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"--- 📋 Iniciando verificación para {len(servidores)} servidores ---")

    for srv in servidores:
        nombre = srv.get("Nombre", "Desconocido")
        ip = srv.get("IP", "")
        dominio = srv.get("Dominio", "")
        
        # Lógica para obtener el puerto (Weblogic/Puerto)
        try:
            puerto = int(srv.get("Puerto_Weblogic") or srv.get("Puerto", 0) or 0)
        except:
            puerto = 0
        
        if not ip or puerto <= 0:
            print(f"⚪ {nombre} - Saltado: IP o Puerto inválido/vacío.")
            continue
        
        total_count += 1
        
        # Ejecutar la verificación TCP
        check_result = check_tcp(ip, puerto)
        
        # Reportar en la consola
        emoji = "🟢" if check_result["status"] == "up" else "🔴"
        print(f"{emoji} {nombre} ({ip}:{puerto}) → {check_result['message']}")
        
        if check_result["status"] == "up":
            up_count += 1
        
        # Agregar el resultado al listado final
        all_results.append({
            "nombre": nombre,
            "dominio": dominio,
            "ip": ip,
            "puerto": puerto,
            "status": check_result["status"],
            "response_time_ms": check_result["response_time_ms"],
            "message": check_result["message"]
        })

    # Construir el JSON final
    final_json = {
        "check_timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "total_servers": total_count,
        "summary": {
            "up": up_count,
            "down": total_count - up_count,
            "up_percentage": round((up_count / total_count * 100), 2) if total_count else 0
        },
        "servers": all_results
    }
    
    # Imprimir y guardar
    print("\n--- JSON de Resultados Finales ---")
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    filename = f"port-check_{timestamp}_FINAL.json"
    
    # Imprimir a la consola
    print(json.dumps(final_json, ensure_ascii=False, indent=2))
    
    # Guardar en archivo local
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)
        
    print(f"\n✅ Archivo de resultados guardado localmente: {filename}")


if __name__ == "__main__":
    download_and_process()
