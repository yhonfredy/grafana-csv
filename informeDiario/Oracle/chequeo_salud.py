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
    
    # Intentamos primero con 'timeout' (Versiones viejas) y luego con 'conn_timeout' (Versiones nuevas)
    for param_name in ['timeout', 'conn_timeout']:
        try:
            kwargs = {
                "user": "USER_MONITOR",
                "password": "WRONG_PASSWORD_123",
                "dsn": dsn,
                param_name: 5  # 5 segundos de espera es suficiente
            }
            oracledb.connect(**kwargs)
            return "OPEN", "A", "Activa (Login Ok)"
            
        except oracledb.DatabaseError as e:
            error_obj, = e.args
            code = error_obj.code
            # 1017: Usuario/Clave inválida | 1045: No tiene privilegios
            # En ambos casos, LA BASE DE DATOS ESTÁ VIVA
            if code in [1017, 1045]:
                return "OPEN", "A", "Instancia Up (Confirmado)"
            else:
                return "DOWN", "I", f"Error ORA-{code}"
                
        except TypeError as e:
            # Si el error es por el nombre del parámetro, intentamos el siguiente en el bucle
            if "unexpected keyword argument" in str(e):
                continue
            return "DOWN", "I", f"Error de Script: {str(e)[:40]}"
            
        except Exception as e:
            # Errores de red (Timeout, Connection Refused, etc)
            return "DOWN", "I", f"Error Red: {str(e)[:50]}"
            
    return "DOWN", "I", "Error: No se pudo establecer timeout"

def ejecutar():
    print(f"--- Iniciando Escaneo de Salud (Version Universal) ---")
    resultados = []

    try:
        # Detectar el delimitador automáticamente (por si acaso es , o ;)
        with open(ARCHIVO_ENTRADA, mode='r', encoding='utf-8-sig') as f:
            content = f.read(1024)
            dialect = csv.Sniffer().sniff(content)
            f.seek(0)
            reader = csv.DictReader(f, dialect=dialect)
            columnas = list(reader.fieldnames)
            
            for col in ['STATUS', 'ESTADO', 'FECHA_REGISTRO', 'DISPONIBILIDAD']:
                if col not in columnas: columnas.append(col)

            for fila in reader:
                ip = fila.get('DIRECCION_IP', '').strip()
                id_bd = fila.get('BD_ID', '').strip()
                
                if not ip or not id_bd: continue
                
                print(f"Verificando {id_bd:20} ({ip:15})...", end=" ", flush=True)
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

        print(f"\n✅ PROCESO COMPLETADO")
        print(f"Reporte generado: {ARCHIVO_SALIDA}")

    except Exception as e:
        print(f"\n❌ ERROR CRITICO: {str(e)}")

if __name__ == "__main__":
    ejecutar()
