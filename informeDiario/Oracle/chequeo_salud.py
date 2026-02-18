import oracledb
import csv
from datetime import datetime

# === CONFIGURACIÓN ===
ARCHIVO_ENTRADA = 'estadoSaludBD.csv'
ARCHIVO_SALIDA = f'Reporte_Salud_Real_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'

def probar_conexion_real(ip, service):
    # .strip() elimina espacios y saltos de línea invisibles (\r, \n)
    ip = ip.strip()
    service = service.strip()
    
    # Construimos la cadena de conexión
    dsn = f"{ip}:1521/{service}"
    
    try:
        # Intentamos conectar (Modo Thin por defecto)
        oracledb.connect(user="USER_CHECK", password="WRONG_PASSWORD", dsn=dsn, conn_timeout=10)
        return "OPEN", "A", "Conexión Exitosa (Raro)"
    except oracledb.DatabaseError as e:
        error_obj, = e.args
        code = error_obj.code
        # ORA-01017 o ORA-01045 significan que la BD está abierta y respondió
        if code in [1017, 1045]:
            return "OPEN", "A", "Instancia UP (Confirmado por ORA-01017)"
        else:
            return "DOWN", "I", f"Error Oracle: ORA-{code}"
    except Exception as e:
        # Aquí capturamos errores de red o de formato
        return "DOWN", "I", f"Error de Red/Sistema: {str(e)[:50]}"

def ejecutar():
    print(f"--- Iniciando Escaneo de Salud ---")
    resultados = []

    try:
        # Usamos utf-8-sig para limpiar el archivo si viene de Excel
        with open(ARCHIVO_ENTRADA, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f, delimiter=';')
            columnas = list(reader.fieldnames)
            
            # Aseguramos que existan las columnas de reporte
            for col in ['STATUS', 'ESTADO', 'FECHA_REGISTRO', 'DISPONIBILIDAD']:
                if col not in columnas:
                    columnas.append(col)

            for fila in reader:
                # Limpiamos los datos de entrada
                ip = fila.get('DIRECCION_IP', '').strip()
                id_bd = fila.get('BD_ID', '').strip()
                
                if not ip or not id_bd:
                    continue
                
                print(f"Verificando {id_bd} ({ip})...", end=" ", flush=True)
                
                status, estado, detalle = probar_conexion_real(ip, id_bd)
                
                print(f"[{status}]")
                
                fila['STATUS'] = status
                fila['ESTADO'] = estado
                fila['FECHA_REGISTRO'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                fila['DISPONIBILIDAD'] = detalle
                
                resultados.append(fila)

        # Guardamos el resultado final
        with open(ARCHIVO_SALIDA, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=columnas, delimiter=';')
            writer.writeheader()
            writer.writerows(resultados)

        print(f"\n✅ REPORTE GENERADO: {ARCHIVO_SALIDA}")

    except Exception as e:
        print(f"\n❌ ERROR CRÍTICO: {str(e)}")

if __name__ == "__main__":
    ejecutar()
