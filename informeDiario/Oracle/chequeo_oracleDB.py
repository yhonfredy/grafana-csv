import oracledb
import csv
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# === CONFIGURACIÓN DE RUTAS ===
# El script busca el CSV en la misma carpeta donde se ejecuta el comando
BASE_DIR_PROYECTO = "/home/ssm-user/SETI/validarServicios"
ARCHIVO_ENTRADA = 'estadoSaludBD.csv'  
VARIABLES_FILE = f"{BASE_DIR_PROYECTO}/variables.txt"

# Configuración de Logs: /logs/Oracle/YYYY-MM-DD
FECHA_HOY = datetime.now().strftime("%Y-%m-%d")
LOG_DIR = f"{BASE_DIR_PROYECTO}/logs/Oracle/{FECHA_HOY}"

# Configuración InfluxDB
INFLUX_BUCKET_NAME = "status_services"
INFLUX_MEASUREMENT = "status_check_oracleDB"

def probar_conexion_real(ip, service):
    """ Valida disponibilidad mediante protocolo Oracle real y categoriza errores """
    dsn = f"{ip.strip()}:1521/{service.strip()}"
    
    # Listado extendido de errores conocidos para un reporte profesional
    ERRORES_MAP = {
        # Red e Infraestructura
        12170: "TIMEOUT (Posible Firewall bloqueando)",
        12543: "Error de red: Destino inalcanzable",
        12541: "TNS: No hay listener (Puerto cerrado/Servicio apagado)",
        
        # Configuración de TNS
        12154: "TNS: No se pudo resolver el nombre (Check DSN)",
        12514: "TNS: Servicio/SID no encontrado en el listener",
        12505: "TNS: SID incorrecto o no registrado",
        
        # Estado de la Instancia
        1017:  "Instancia Up (Login validado)",
        1045:  "Instancia Up (Falta permiso de sesión)",
        1033:  "Instancia en proceso de INICIO o APAGADO",
        
        # Recursos y Capacidad
        12516: "TNS: Límite de procesos excedido (DB Saturada)",
        12520: "TNS: Límite de sesiones excedido",
        257:   "ERROR: Archive Log lleno (DB bloqueada)"
    }

    try:
        # Intento de conexión modo Thin (no requiere cliente Oracle instalado)
        oracledb.connect(user="USER_MONITOR", password="WRONG_PASSWORD_123", dsn=dsn)
        return "up", "OK", "Instancia Up (Login Ok)"
        
    except oracledb.DatabaseError as e:
        error_obj, = e.args
        code = error_obj.code
        
        # Si es un error que confirma que el motor respondió (Login/Permisos)
        if code in [1017, 1045]:
            return "up", "OK", ERRORES_MAP.get(code)
        
        # Si el error está en el mapa, usamos la descripción amigable.
        # Si NO está (ej. ORA-12190), guarda el código y el mensaje original recortado.
        detalle = ERRORES_MAP.get(code, f"ORA-{code}: {error_obj.message.strip()[:50]}")
        return "down", f"ORA-{code}", detalle
        
    except Exception as e:
        return "down", "NETWORK_ERROR", str(e)[:50]

def subir_a_influx(datos):
    """ Envía los resultados a InfluxDB utilizando las credenciales de variables.txt """
    try:
        from influxdb_client import InfluxDBClient, Point
        from influxdb_client.client.write_api import SYNCHRONOUS
        
        if not os.path.exists(VARIABLES_FILE):
            print(f"⚠️ No se encontró {VARIABLES_FILE}, saltando subida a InfluxDB.")
            return
        
        creds = {}
        with open(VARIABLES_FILE, "r") as vf:
            for line in vf:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    creds[k.strip()] = v.strip()
                    
        client = InfluxDBClient(url=creds["INFLUX_URL"], token=creds["INFLUX_TOKEN"], org=creds["INFLUX_ORG"])
        write_api = client.write_api(write_options=SYNCHRONOUS)
        
        for r in datos:
            p = Point(INFLUX_MEASUREMENT)\
                .tag("db_id", r["db_id"])\
                .tag("ip", r["ip"])\
                .field("status_value", 1 if r["status"] == "up" else 0)\
                .field("detalle", r["detalle"])\
                .time(datetime.utcnow())
            write_api.write(bucket=INFLUX_BUCKET_NAME, record=p)
            
        client.close()
        print(f"✅ Datos enviados a InfluxDB.")
    except Exception as e:
        print(f"⚠️ Error al subir a InfluxDB: {e}")

def ejecutar():
    # Validación de existencia del CSV en la carpeta local de ejecución
    if not os.path.exists(ARCHIVO_ENTRADA):
        print(f"❌ Error: No se encuentra el archivo {ARCHIVO_ENTRADA}")
        print(f"Asegúrate de ejecutar el script desde: {os.path.dirname(os.path.abspath(__file__))}")
        return
        
    # Crear estructura de carpetas de logs
    os.makedirs(LOG_DIR, exist_ok=True)
    
    now = datetime.now(ZoneInfo("America/Bogota"))
    resultados = []
    
    print(f"--- Iniciando Escaneo Oracle ({now.strftime('%Y-%m-%d %H:%M:%S')}) ---")
    
    with open(ARCHIVO_ENTRADA, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter=';')
        for fila in reader:
            # Limpieza de espacios en cabeceras y valores
            fila = {k.strip(): v for k, v in fila.items() if k}
            ip = fila.get('DIRECCION_IP', '').strip()
            id_bd = fila.get('BD_ID', '').strip()
            
            if not ip or not id_bd:
                continue
            
            print(f"Validando {id_bd:20} ({ip})...", end=" ", flush=True)
            status, tipo, detalle = probar_conexion_real(ip, id_bd)
            print(f"[{status.upper()}] - {detalle}")
            
            resultados.append({
                "db_id": id_bd, 
                "ip": ip, 
                "status": status,
                "tipo_error": tipo, 
                "detalle": detalle, 
                "timestamp": now.isoformat()
            })
            
    # Guardar resultado en formato JSON
    archivo_log = f"{LOG_DIR}/scan_{now.strftime('%H%M%S')}.json"
    with open(archivo_log, "w") as jf:
        json.dump(resultados, jf, indent=2)
        
    print(f"\n📂 Reporte JSON generado en: {archivo_log}")
    
    # Procesar subida a base de datos de métricas
    subir_a_influx(resultados)

if __name__ == "__main__":
    ejecutar()
