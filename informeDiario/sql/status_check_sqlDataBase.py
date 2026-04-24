# ==============================================================================
# CONTROL DE CAMBIOS
# 1. Se agregó el campo 'disponibilidad_str' para evitar el uso de ceros (0).
# 2. Se ajustó el tag 'ambiente' a 'PROD'.
# 3. Se implementó la carga de variables desde .env y variables.txt (COMO EN ORACLE). # ESTE ES EL CAMBIO
# 4. Se estandarizó la métrica 'status_value' (0=Error, 1=OK).
# ==============================================================================

import os
import pyodbc
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo # ESTE ES EL CAMBIO 
from dotenv import load_dotenv # ESTE ES EL CAMBIO
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# 1. Cargar configuración (IGUAL QUE EN SCRIPT DE ORACLE OCULTO VARIABLES)
load_dotenv() # ESTE ES EL CAMBIO (Carga el archivo .env)

BASE_DIR_PROYECTO = "/home/ssm-user/SETI/validarServicios"
VARIABLES_FILE = f"{BASE_DIR_PROYECTO}/variables.txt"

# 2. Configuración de SQL Server desde el .env
# Validar primero de haber agregado SQL_USER, SQL_PASS y SQL_IP al .env
SQL_USER = os.getenv("SQL_USER") # ESTE ES EL CAMBIO
SQL_PASS = os.getenv("SQL_PASS") # ESTE ES EL CAMBIO
SQL_IP = os.getenv("SQL_IP")     # ESTE ES EL CAMBIO
SQL_DATABASE = "master"

# Cadena de conexión usando las variables del .env
# conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SQL_IP};DATABASE={SQL_DATABASE};UID={SQL_USER};PWD={SQL_PASS}'
# Se Cambia el 17 por el 18 y se agrega TrustServerCertificate
conn_str = f'DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={SQL_IP};DATABASE={SQL_DATABASE};UID={SQL_USER};PWD={SQL_PASS};TrustServerCertificate=yes'

def obtener_creds_influx():
    """ Lee las credenciales de Influx desde variables.txt igual que en Oracle """
    creds = {}
    if os.path.exists(VARIABLES_FILE):
        with open(VARIABLES_FILE, "r") as vf:
            for line in vf:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    creds[k.strip()] = v.strip()
    return creds

def main():
    write_api = None
    conn = None
    creds = obtener_creds_influx() # ESTE ES EL CAMBIO

    try:
        # Iniciar Clientes usando el diccionario creds (de variables.txt)
        client_influx = InfluxDBClient(
            url=creds["INFLUX_URL"], 
            token=creds["INFLUX_TOKEN"], 
            org=creds["INFLUX_ORG"]
        )
        write_api = client_influx.write_api(write_options=SYNCHRONOUS)
        
        # Intento de conexión a SQL Server
        conn = pyodbc.connect(conn_str, timeout=10)
        cursor = conn.cursor()

        # --- A. Consultas SQL ---
        cursor.execute("SELECT @@VERSION")
        sql_version = cursor.fetchone()[0]

        cursor.execute("SELECT name, state_desc FROM sys.databases WHERE database_id > 4")
        db_states = cursor.fetchall()

        # --- B. Procesar y Subir Datos a InfluxDB ---
        
        # Punto 1: Estado General de la Instancia
        connection_point = Point("status_check_oracleDataBase") \
            .tag("db_id", "SQL_SERVER_INSTANCE") \
            .tag("ip", SQL_IP) \
            .tag("ambiente", "PROD") \
            .field("status_value", 1) \
            .field("disponibilidad_str", "Instancia SQL Online") \
            .time(datetime.now(ZoneInfo("UTC"))) # ESTE ES EL CAMBIO
        
        write_api.write(bucket=creds["INFLUX_BUCKET"], record=connection_point)

        # Punto 2: Estado de cada Base de Datos individual
        for db_name, db_state in db_states:
            status_value = 1 if db_state == 'ONLINE' else 0
            
            if status_value == 1:
                msg_disponibilidad = f"Base de datos {db_name} operativa"
            else:
                msg_disponibilidad = f"CRÍTICO: Base {db_name} en estado {db_state}"

            # ESTA ESTRUCTURA ES IDÉNTICA A LA DE ORACLE
            db_point = Point("status_check_oracleDataBase") \
                .tag("db_id", db_name) \
                .tag("ip", SQL_IP) \
                .tag("ambiente", "PROD") \
                .tag("tipo_error", "OK" if status_value == 1 else "CHECK_STATUS") \
                .field("status_value", status_value) \
                .field("disponibilidad_str", msg_disponibilidad) \
                .time(datetime.now(ZoneInfo("UTC")))
            
            write_api.write(bucket=creds["INFLUX_BUCKET"], record=db_point)
            print(f"✅ SQL Server: {db_name} -> {db_state}")

    except Exception as e:
        error_msg = str(e).replace("'", "").replace('"', "")
        print(f"❌ Error en monitoreo: {error_msg}")
        
        if write_api:
             error_point = Point("status_check_oracleDataBase") \
                .tag("db_id", "ERROR_CONEXION_SQL") \
                .tag("ip", SQL_IP) \
                .tag("ambiente", "PROD") \
                .field("status_value", 0) \
                .field("disponibilidad_str", f"Falla acceso SQL: {error_msg[:100]}") \
                .time(datetime.now(ZoneInfo("UTC")))
             
             write_api.write(bucket=creds["INFLUX_BUCKET"], record=error_point)

    finally:
        if conn: conn.close()
        print("--- Proceso Finalizado ---")

if __name__ == "__main__":
    main()
