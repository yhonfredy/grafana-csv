import sys
import json
from datetime import datetime

# Modo de uso: python3 build_json.py extract <input_file>
def extract_servers(input_file):
    """
    Extrae Nombre, Dominio, IP, Puerto de Weblogic/Puerto del JSON de entrada
    e imprime cada uno en una línea con formato Nombre|Dominio|IP|Puerto.
    """
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            servidores = json.load(f)
    except Exception as e:
        print(f"Error al cargar el archivo JSON de servidores: {e}", file=sys.stderr)
        sys.exit(1)

    for srv in servidores:
        nombre = srv.get("Nombre", "").replace('|', ' ') # Limpieza básica para el delimitador
        dominio = srv.get("Dominio", "").replace('|', ' ')
        ip = srv.get("IP", "")
        # Lógica para obtener el puerto (similar a tu Lambda)
        try:
            puerto = int(srv.get("Puerto_Weblogic") or srv.get("Puerto", 0) or 0)
        except:
            puerto = 0
            
        if ip and puerto > 0:
            print(f"{nombre}|{dominio}|{ip}|{puerto}")

# Modo de uso: python3 build_json.py build <results_log_file>
def build_final_json(results_log_file):
    """
    Lee el log de resultados (formato Nombre|Dominio|IP|Puerto|Status|RT_MS|Message)
    y construye el JSON final de salida.
    """
    all_results = []
    up_count = 0
    total_count = 0
    
    try:
        with open(results_log_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # Nombre|Dominio|IP|Puerto|Status|RT_MS|Message
                parts = line.split('|', 6) # Split solo 6 veces para asegurar que el mensaje no se parta
                
                if len(parts) < 7:
                    continue
                
                nombre, dominio, ip, puerto_str, status, rt_ms_str, message = parts
                
                total_count += 1
                if status == "up":
                    up_count += 1
                
                # Convertir RT_MS a número o None (JSON null)
                try:
                    rt_ms = float(rt_ms_str)
                except:
                    rt_ms = None
                
                all_results.append({
                    "nombre": nombre,
                    "dominio": dominio,
                    "ip": ip,
                    "puerto": int(puerto_str),
                    "status": status,
                    "response_time_ms": rt_ms,
                    "message": message
                })
    except Exception as e:
        print(f"Error al procesar el archivo de resultados: {e}", file=sys.stderr)
        sys.exit(1)

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
    
    # Imprimir el JSON final
    print(json.dumps(final_json, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python3 build_json.py <extract|build> <archivo>", file=sys.stderr)
        sys.exit(1)
        
    command = sys.argv[1]
    input_file = sys.argv[2]
    
    if command == "extract":
        extract_servers(input_file)
    elif command == "build":
        build_final_json(input_file)
    else:
        print(f"Comando desconocido: {command}", file=sys.stderr)
        sys.exit(1)
