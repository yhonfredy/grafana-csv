import os
import pyodbc
import json
import time
from datetime import datetime
from influxdb_client import InfluxDBClient, Point, WritePrecision

# 1. Configuración de InfluxDB
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG = json.load(open(os.path.join(BASE_DIR, "config.json"))) # Asumiendo un json de config

INFLUX_URL = _CONFIG["INFLUX_URL"]
INFLUX_TOKEN = _CONFIG["INFLUX_TOKEN"]
INFLUX_ORG = _CONFIG["INFLUX_ORG"]
INFLUX_BUCKET = _CONFIG["INFLUX_BUCKET"]

# 2. Configuración de SQL Server (Ajusta IP, Usuario y Password)
SQL_SERVER = "SQL04SBCC04" # O la IP del servidor de la imagen
SQL_USER = "TU_USUARIO_MONITOREO" # Usuario con permisos de VIEW ANY DATABASE
SQL_PASS = "TU_CONTRASEÑA"
SQL_DATABASE = "master" # Base de datos para la conexión inicial

# Cadena de conexión (Usa el driver correcto instalado en el servidor Linux)
conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SQL_SERVER};DATABASE={SQL_DATABASE};UID={SQL_USER};PWD={SQL_PASS}'

def main():
    write_api = None
    conn = None
    try:
        # Iniciar Clientes
        client_influx = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        write_api = client_influx.write_api(write_options=SYNCHRONOUS)
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # --- A. Consultas SQL ---
        # 1. Chequeo de Conexión y Versión
        cursor.execute("SELECT @@VERSION")
        sql_version = cursor.fetchone()[0]

        # 2. Estado de Bases de Datos
        cursor.execute("""
            SELECT name, state_desc
            FROM sys.databases
            WHERE database_id > 4 -- Excluye las de sistema (master, model, msdb, tempdb)
        """)
        db_states = cursor.fetchall()

        # 3. Estado de Réplica Always On (Opcional, si aplica)
        # cursor.execute("... (consulta Always On de arriba) ...")
        # replica_states = cursor.fetchall()

        # --- B. Procesar y Subir Datos a InfluxDB ---
        
        # Punto 1: Estado General de la Conexión
        connection_point = Point("status_check_sqlDataBase") \
            .tag("instance_name", SQL_SERVER) \
            .tag("ambiente", "PRODUCCION") \
            .field("version", sql_version) \
            .field("connection_status", 1) \
            .time(datetime.utcnow(), WritePrecision.NS)
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=connection_point)

        # Punto 2: Estado de cada Base de Datos individual
        for db_name, db_state in db_states:
            # Determinamos la métrica numérica (1=Online, 0=Cualquier otro estado)
            status_value = 1 if db_state == 'ONLINE' else 0
            
            # Determinamos la criticidad según el nombre
            criticidad = "ALTA" if db_name in ['CF_Admin', 'CF_Auth', 'SunSystemsData'] else "MEDIA"

            db_point = Point("status_check_sqlDataBase_individual") \
                .tag("instance_name", SQL_SERVER) \
                .tag("database_name", db_name) \
                .tag("criticidad", criticidad) \
                .field("state_desc", db_state) \
                .field("status_value", status_value) \
                .time(datetime.utcnow(), WritePrecision.NS)
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=db_point)
            print(f"✅ SQL Server: Base {db_name} estado {db_state} subido.")

        print(f"✅ Monitoreo profundo de SQL Server ({SQL_SERVER}) completado con éxito.")

    except Exception as e:
        print(f"❌ Error en monitoreo de SQL Server: {e}")
        # En caso de error, subimos un registro de "Error de Conexión"
        # para que InfluxDB sepa que el servidor no está respondiendo.
        if write_api:
             error_point = Point("status_check_sqlDataBase") \
                .tag("instance_name", SQL_SERVER) \
                .tag("ambiente", "PRODUCCION") \
                .field("connection_status", 0) \
                .field("error_message", str(e)) \
                .time(datetime.utcnow(), WritePrecision.NS)
             write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=error_point)
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    main()
