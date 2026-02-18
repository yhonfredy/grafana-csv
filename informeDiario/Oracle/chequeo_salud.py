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
        # Aquí cambiamos 'conn_timeout' por 'timeout' para que sea compatible con tu versión
        oracledb.connect(user="USER_CHECK", password="WRONG_PASSWORD", dsn=dsn, timeout=10)
        return "OPEN", "A", "Activa"
    except oracledb.DatabaseError as e:
        error_obj, = e.args
        code = error_obj.code
        # Si Oracle responde con error de credenciales, es que la base está UP
        if code in [1017, 1045]:
            return "OPEN", "A", "Instancia Up (Confirmado)"
        else:
            return "DOWN", "I", f"Error ORA-{code}"
    except Exception as e:
        return "DOWN", "I", f"Error Red: {str(e)[:50]}"

def ejecutar():
    print(f"--- Iniciando Validación (Versión Compatible) ---")
    resultados = []

    try:
        with open(ARCHIVO_ENTRADA, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f, delimiter=';')
            columnas = list(reader.fieldnames)
            
            for col in ['STATUS', 'ESTADO', 'FECHA_REGISTRO', 'DISPONIBILIDAD']:
                if col not in columnas: columnas.append(col)

            for fila in reader:
                ip = fila.get('DIRECCION_IP', '').strip()
                id_bd = fila.get('BD_ID', '').strip()
                
                if not ip or not id_bd: continue
                
                print(f"Validando {id_bd}...", end=" ", flush=True)
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

        print(f"\n✅ REPORTE GENERADO: {ARCHIVO_SALIDA}")

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")

if __name__ == "__main__":
    ejecutar()
