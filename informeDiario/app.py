
import oracledb
import csv
from datetime import datetime

# === CONFIGURACIÓN ===
ARCHIVO_ENTRADA = 'estadoSaludBD.csv'
ARCHIVO_SALIDA = f'Reporte_Salud_Generado_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'

def probar_conexion_real(ip, service):
    """ Intenta conectar para ver si la instancia responde (Nivel 2.5) """
    dsn = f"{ip}:1521/{service}"
    try:
        # Intentamos con credenciales falsas
        oracledb.connect(user="USER_MONITOR", password="WRONG_PASSWORD", dsn=dsn, conn_timeout=5)
        return "OPEN", "A", "Activa"
    except oracledb.DatabaseError as e:
        error_code = e.args[0].code
        # ORA-01017 o ORA-01045 indican que la instancia está UP
        if error_code in [1017, 1045]:
            return "OPEN", "A", "Instancia Up (Confirmado)"
        else:
            return "DOWN", "I", f"Error ORA-{error_code}"
    except Exception:
        return "DOWN", "I", "Fallo de Red/Timeout"

def ejecutar():
    print(f"--- Iniciando Validación Automática ---")
    resultados = []

    try:
        # IMPORTANTE: Se añade delimiter=';' para que coincida con tu archivo
        with open(ARCHIVO_ENTRADA, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f, delimiter=';')
            columnas = reader.fieldnames
            
            # Si faltan las columnas de salida en el original, las agregamos al encabezado
            nuevas_cols = ['STATUS', 'ESTADO', 'FECHA_REGISTRO', 'DISPONIBILIDAD']
            for col in nuevas_cols:
                if col not in columnas:
                    columnas.append(col)

            for fila in reader:
                ip = fila.get('DIRECCION_IP')
                servicio = fila.get('BD_ID')
                
                if not ip or not servicio:
                    continue
                    
                print(f"Validando: {servicio} en {ip}...")
                
                status, estado, detalle = probar_conexion_real(ip, servicio)
                
                # Llenamos los datos
                fila['STATUS'] = status
                fila['ESTADO'] = estado
                fila['FECHA_REGISTRO'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                fila['DISPONIBILIDAD'] = detalle
                
                resultados.append(fila)

        # Guardamos el resultado (usando coma para que Excel lo abra fácil o punto y coma si prefieres)
        with open(ARCHIVO_SALIDA, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=columnas, delimiter=';')
            writer.writeheader()
            writer.writerows(resultados)

        print(f"\n✅ PROCESO EXITOSO")
        print(f"Se ha creado el archivo: {ARCHIVO_SALIDA}")

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")

if __name__ == "__main__":
    ejecutar()
