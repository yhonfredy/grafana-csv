# ==============================================================================
# CONTROL DE CAMBIOS
# 1. Se agregó el campo 'disponibilidad_str' para evitar el uso de ceros (0) en el reporte.
# 2. Se ajustó el tag 'ambiente' a 'PROD' para consistencia con el monitoreo Oracle.
# 3. Se implementó la captura de error detallado en el bloque Exception para la instancia.
# 4. Se estandarizó la métrica 'status_value' para disparar las alertas (0=Error, 1=OK).
# ==============================================================================

import os
import pyodbc
import json
import time
from datetime import datetime
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# 1. Configuración de InfluxDB
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Asegúrate de que config.json tenga las credenciales correctas
_CONFIG = json.load(open(os.path.join(BASE_DIR, "config.json")))

INFLUX_URL = _CONFIG["INFLUX_URL"]
INFLUX_TOKEN = _CONFIG["INFLUX_TOKEN"]
INFLUX_ORG = _CONFIG["INFLUX_ORG"]
INFLUX_BUCKET = _CONFIG["INFLUX_BUCKET"]

# 2. Configuración de SQL Server
SQL_SERVER = "10.1.5.6"  # IP
SQL_USER = _CONFIG["INFLUX_SQLUSER"]
SQL_PASS = _CONFIG["INFLUX_SQLPASS"]
SQL_DATABASE = "master"

# Cadena de conexión
conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SQL_SERVER};DATABASE={SQL_DATABASE};UID={SQL_USER};PWD={SQL_PASS}'

def main():
    write_api = None
    conn = None
    try:
        # Iniciar Clientes
        client_influx = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        write_api = client_influx.write_api(write_options=SYNCHRONOUS)
        
        # Intento de conexión a SQL Server
        conn = pyodbc.connect(conn_str, timeout=10)
        cursor = conn.cursor()

        # --- A. Consultas SQL ---
        # 1. Obtener versión
        cursor.execute("SELECT @@VERSION")
        sql_version = cursor.fetchone()[0]

        # 2. Estado de Bases de Datos
        cursor.execute("""
            SELECT name, state_desc 
            FROM sys.databases 
            WHERE database_id > 4
        """)
        db_states = cursor.fetchall()

        # --- B. Procesar y Subir Datos a InfluxDB ---
        
        # Punto 1: Estado General de la Instancia
        connection_point = Point("status_check_sqlDataBase") \
            .tag("instance_name", SQL_SERVER) \
            .tag("ambiente", "PROD") \
            .field("version", sql_version[:100]) \
            .field("status_value", 1) \
            .field("disponibilidad_str", "Instancia SQL Online") \
            .time(datetime.utcnow(), WritePrecision.NS)
        
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=connection_point)

        # Punto 2: Estado de cada Base de Datos individual (Arquitectura SQL)
        for db_name, db_state in db_states:
            # 1=Online, 0=Cualquier otro estado (Restoring, Recovery, Offline, etc.)
            status_value = 1 if db_state == 'ONLINE' else 0
            
            # Definir mensaje descriptivo para el reporte (Adiós al 0)
            if status_value == 1:
                msg_disponibilidad = f"Base de datos {db_name} operativa"
            else:
                msg_disponibilidad = f"CRÍTICO: Base {db_name} en estado {db_state}"

            # Criticidad manual
            criticidad = "ALTA" if db_name in ['CF_Admin', 'CF_Auth', 'SunSystemsData'] else "MEDIA"

            db_point = Point("status_check_sqlDataBase") \
                .tag("instance_name", SQL_SERVER) \
                .tag("database_name", db_name) \
                .tag("ambiente", "PROD") \
                .tag("criticidad", criticidad) \
                .field("status_value", status_value) \
                .field("disponibilidad_str", msg_disponibilidad) \
                .field("state_desc", db_state) \
                .time(datetime.utcnow(), WritePrecision.NS)
            
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=db_point)
            print(f"✅ SQL Server: {db_name} -> {db_state}")

    except Exception as e:
        error_msg = str(e).replace("'", "").replace('"', "")
        print(f"❌ Error en monitoreo: {error_msg}")
        
        if write_api:
             # Registro de falla total para que el reporte salga ROJO
             error_point = Point("status_check_sqlDataBase_individual") \
                .tag("instance_name", SQL_SERVER) \
                .tag("database_name", "ERROR_CONEXION") \
                .tag("ambiente", "PROD") \
                .field("status_value", 0) \
                .field("disponibilidad_str", f"Falla de acceso SQL: {error_msg[:150]}") \
                .time(datetime.utcnow(), WritePrecision.NS)
             
             write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=error_point)

    finally:
        if conn:
            conn.close()
        print("--- Proceso Finalizado ---")

if __name__ == "__main__":
    main()
