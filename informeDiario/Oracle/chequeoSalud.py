import oracledb
import csv
from datetime import datetime

# === CONFIGURACIÓN ===
ARCHIVO_ENTRADA = 'estadoSaludBD.csv'
ARCHIVO_SALIDA = f'Reporte_Salud_Final_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'

def probar_conexion_real(ip, service):
    ip = ip.strip()
    service = service.strip()
    dsn = f"{ip}:1521/{service}"
    
    try:
        # Intentamos conexión limpia sin parámetros de timeout conflictivos
        oracledb.connect(user="USER_MONITOR", password="WRONG_PASSWORD_123", dsn=dsn)
        return "OPEN", "A", "Activa (Login Ok)"
            
    except oracledb.DatabaseError as e:
        error_obj, = e.args
        code = error_obj.code
        # ORA-1017: credenciales inválidas. Indica que el listener y la instancia responden.
        if code in [1017, 1045]:
            return "OPEN", "A", "Instancia Up (Confirmado)"
        else:
            return "DOWN", "I", f"Error ORA-{code}"
            
    except Exception as e:
        # Esto atrapará errores de red (Connection refused, etc.)
        return "DOWN", "I", f"Error Red: {str(e)[:50]}"

def ejecutar():
    print(f"--- Iniciando Escaneo (Modo Compatibilidad Total) ---")
    resultados = []

    try:
        with open(ARCHIVO_ENTRADA, mode='r', encoding='utf-8-sig') as f:
            # Forzamos delimitador punto y coma ya que vimos que así es tu CSV
            reader = csv.DictReader(f, delimiter=';')
            columnas = reader.fieldnames
            
            # Asegurar columnas de salida
            for col in ['STATUS', 'ESTADO', 'FECHA_REGISTRO', 'DISPONIBILIDAD']:
                if col not in columnas: columnas.append(col)

            for fila in reader:
                ip = fila.get('DIRECCION_IP', '').strip()
                id_bd = fila.get('BD_ID', '').strip()
                
                if not ip or not id_bd: continue
                
                print(f"Validando {id_bd:20}...", end=" ", flush=True)
                status, estado, detalle = probar_conexion_real(ip, id_bd)
                print(f"[{status}]")
                
                fila['STATUS'] = status
                fila['ESTADO'] = estado
                fila['FECHA_REGISTRO'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                fila['DISPONIBILIDAD'] = detalle
                resultados.append(fila)

        with open(ARCHIVO_SALIDA, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=columnas, delimiter=';')
            writer.writeheader()
            writer.writerows(resultados)

        print(f"\n✅ REPORTE GENERADO EXITOSAMENTE: {ARCHIVO_SALIDA}")

    except Exception as e:
        print(f"\n❌ ERROR CRITICO: {str(e)}")

if __name__ == "__main__":
    ejecutar()
