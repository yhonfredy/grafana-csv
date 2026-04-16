import os
import smtplib
import ssl
import time
import json
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from influxdb_client import InfluxDBClient

# ─────────────────────────────────────────────
# CONFIGURACIÓN DE RUTAS Y ARCHIVOS
# ─────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
VARIABLES_FILE = os.path.join(BASE_DIR, "variables.txt")
SCHEDULE_FILE  = os.path.join(BASE_DIR, "horarios.json")

def _load_creds() -> dict:
    creds = {}
    try:
        with open(VARIABLES_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    creds[k.strip()] = v.strip()
    except FileNotFoundError:
        print(f"⚠️  {VARIABLES_FILE} no encontrado.")
    return creds

_CREDS = _load_creds()

# Variables de InfluxDB
INFLUX_URL    = _CREDS.get("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN  = _CREDS.get("INFLUX_TOKEN", "")
INFLUX_ORG    = _CREDS.get("INFLUX_ORG", "")
INFLUX_BUCKET = _CREDS.get("INFLUX_BUCKET", "status_services")

# Variables de Correo
GMAIL_USER = _CREDS.get("GMAIL_USER", "tu_correo@gmail.com")
GMAIL_PASS = _CREDS.get("GMAIL_PASS", "")
EMAIL_TO   = _CREDS.get("EMAIL_TO", "destinatario@empresa.com")
EMAIL_CC   = _CREDS.get("EMAIL_CC", "")

# Comportamiento
WINDOW_MINUTES = 15
SEND_ALWAYS    = _CREDS.get("SEND_ALWAYS", "false").lower() == "true"
RUN_AS_DAEMON  = _CREDS.get("RUN_AS_DAEMON", "false").lower() == "true"

# ─────────────────────────────────────────────
# VALIDACIÓN DE HORARIO CON REDONDEO (SOLUCIÓN RETRASO)
# ─────────────────────────────────────────────
def es_hora_de_ejecutar() -> bool:
    """
    Valida si el bloque de cron actual está permitido en horarios.json.
    Si el script se demora y llega a las 06:03, lo redondea a las 06:00.
    """
    try:
        if not os.path.exists(SCHEDULE_FILE):
            print(f"⚠️  {SCHEDULE_FILE} no existe. Ejecutando por defecto.")
            return True
            
        with open(SCHEDULE_FILE, 'r', encoding="utf-8") as f:
            config = json.load(f)
            horas_permitidas = config.get("horas_permitidas", [])
            
        ahora = datetime.now()
        # Redondeo al múltiplo de 15 min anterior (0, 15, 30, 45)
        minuto_bloque = (ahora.minute // 15) * 15
        bloque_horario = ahora.replace(minute=minuto_bloque).strftime("%H:%M")
        
        print(f"🕒 Hora Actual: {ahora.strftime('%H:%M')} | Bloque Cron Detectado: {bloque_horario}")
        
        return bloque_horario in horas_permitidas
    except Exception as e:
        print(f"❌ Error validando horarios.json: {e}")
        return False

# ─────────────────────────────────────────────
# LÓGICA DE VENTANA DE TIEMPO PARA INFLUX
# ─────────────────────────────────────────────
def get_window() -> tuple:
    now = datetime.now(timezone.utc)
    # Ventana de los últimos 15 min reales
    floored = (now.minute // WINDOW_MINUTES) * WINDOW_MINUTES
    start   = now.replace(minute=floored, second=0, microsecond=0)
    return start, now

def flux_range(start: datetime, stop: datetime) -> str:
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return f"|> range(start: {start.strftime(fmt)}, stop: {stop.strftime(fmt)})"

# ─────────────────────────────────────────────
# CONSULTAS INFLUXDB (QUERIES)
# ─────────────────────────────────────────────
ALL_QUERIES = {
    "listener": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r.tipo == "oracle" or r.tipo == "listado_oracle") |> filter(fn: (r) => r._value == 0) |> keep(columns: ["_time","_value","nombre","ip","tipo"])""",
    "weblogic_puertos": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r.tipo == "weblogic") |> filter(fn: (r) => r._value == 0) |> keep(columns: ["_time","_value","nombre","ip","tipo"])""",
    "ipm_puertos": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r.tipo == "ipm") |> filter(fn: (r) => r._value == 0) |> keep(columns: ["_time","_value","nombre","ip","tipo"])""",
    "simon_puertos": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r.tipo == "simonweb" or r.tipo == "quotation") |> filter(fn: (r) => r._value == 0) |> keep(columns: ["_time","_value","nombre","ip","tipo"])""",
    "simon_web_url": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check_http") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r._value == 0) |> keep(columns: ["_time","_value","nombre","url","tipo_error"])""",
    "db_prod": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check_oracleDataBase") |> filter(fn: (r) => r._field == "status_value") |> filter(fn: (r) => r.ambiente == "PRODUCCION" or r.ambiente == "PRD") |> filter(fn: (r) => r._value == 0) |> keep(columns: ["_time","_value","db_id","ip","ambiente","instance"])""",
    "db_test": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check_oracleDataBase") |> filter(fn: (r) => r._field == "status_value") |> filter(fn: (r) => r.ambiente == "TEST" or r.ambiente == "QA") |> filter(fn: (r) => r._value == 0) |> keep(columns: ["_time","_value","db_id","ip","ambiente","instance"])""",
    "db_dev": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check_oracleDataBase") |> filter(fn: (r) => r._field == "status_value") |> filter(fn: (r) => r.ambiente == "DESARROLLO" or r.ambiente == "DEV") |> filter(fn: (r) => r._value == 0) |> keep(columns: ["_time","_value","db_id","ip","ambiente","instance"])""",
    "ipm_soap": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check_IPM") |> filter(fn: (r) => r._field == "status_code") |> filter(fn: (r) => r._value != 200) |> keep(columns: ["_time","_value","servicio","url","estado_msg"])""",
}

def query_influx(window_start: datetime, window_stop: datetime) -> dict:
    rng = flux_range(window_start, window_stop)
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    api = client.query_api()
    results = {}
    for zone, flux in ALL_QUERIES.items():
        filled = flux.replace("{bucket}", INFLUX_BUCKET).replace("{range}", rng)
        try:
            tables = api.query(filled)
            rows = []
            for table in tables:
                for rec in table.records:
                    row = {"time": rec.get_time().strftime("%Y-%m-%d %H:%M:%S UTC") if rec.get_time() else "—", "value": rec.get_value()}
                    skip = {"_start","_stop","_time","_value","_field","_measurement","result","table"}
                    for k, v in rec.values.items():
                        if k not in skip and v is not None: row[k] = str(v)
                    rows.append(row)
            results[zone] = rows
        except Exception as exc: 
            results[zone] = [{"time": "—", "value": "—", "error": str(exc)}]
    client.close()
    return results

# ─────────────────────────────────────────────
# DISEÑO HTML (CON LOGO BOLÍVAR CONMIGO)
# ─────────────────────────────────────────────
SECTIONS = [
    {"icon": "💽", "title": "Infraestructura DB Oracle", "sub": "Monitoreo conexión", "zones": [("listener", "💾", "Listener Oracle"), ("db_prod", "📡", "PROD"), ("db_test", "📡", "TEST"), ("db_dev", "📡", "DEV")]},
    {"icon": "🖥️", "title": "Plataforma SIMON", "sub": "Simon Web/Quotation", "zones": [("simon_puertos", "💻", "Simon Puertos"), ("simon_web_url", "💻", "Simon URLs")]},
    {"icon": "🌐", "title": "Servicios Web", "sub": "Health check", "zones": [("weblogic_puertos", "🌐", "WebLogic")]},
    {"icon": "📊", "title": "IPM Oracle", "sub": "Rendimiento SOAP", "zones": [("ipm_puertos", "💻", "IPM Puertos"), ("ipm_soap", "🔄", "SOAP IPM")]},
]

def _rows_to_html(rows: list) -> str:
    if not rows: return '<p style="color:#28A745;font-weight:700;margin:8px 0;">✅ Sin errores en esta ventana</p>'
    priority = ["time", "nombre", "db_id", "servicio", "ip", "url", "ambiente", "instance", "tipo", "value", "error"]
    all_keys = list(dict.fromkeys([k for k in priority if any(k in r for r in rows)] + [k for r in rows for k in r if k not in priority]))
    th = "".join(f'<th style="background:#038450;color:#fff;padding:7px 10px;text-align:left;font-size:11px;white-space:nowrap;">{k.upper()}</th>' for k in all_keys)
    body = "".join([f'<tr style="background:{"#fff" if i%2==0 else "#F5F5F5"};">' + "".join([f'<td style="padding:6px 10px;border-bottom:1px solid #E1E1E1;font-size:11px;">{r.get(k,"—")}</td>' for k in all_keys]) + '</tr>' for i, r in enumerate(rows)])
    return f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:11px;"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'

def build_email_html(data: dict, window_start: datetime, window_stop: datetime) -> str:
    ts_label = window_stop.strftime("%Y-%m-%d %H:%M UTC")
    total_errors = sum(len(v) for v in data.values())
    sum_color = "#DC3545" if total_errors > 0 else "#28A745"
    sum_icon = "⚠️" if total_errors > 0 else "✅"
    
    sections_html = ""
    for sec in SECTIONS:
        zones_html = ""
        for zone_id, z_icon, z_label in sec["zones"]:
            rows = data.get(zone_id, []); count = len(rows)
            dot_color = "#DC3545" if count > 0 else "#28A745"
            zones_html += f'<div style="margin:10px 0 0;"><div style="background:#009056;border-left:4px solid #FFE16F;padding:8px 16px;display:flex;align-items:center;gap:8px;"><span style="font-size:12px;font-weight:700;color:#fff;text-transform:uppercase;flex:1;">{z_icon} {z_label}</span><span style="background:{dot_color};color:#fff;border-radius:12px;padding:2px 10px;font-size:11px;font-weight:700;">{count if count > 0 else "OK"}</span></div><div style="padding:12px 16px;background:#fff;border-left:4px solid #E1E1E1;">{_rows_to_html(rows)}</div></div>'
        sections_html += f'<div style="margin-top:20px;"><div style="background:#038450;border-left:6px solid #FFE16F;padding:14px 20px;"><div style="font-size:14px;font-weight:700;color:#fff;text-transform:uppercase;">{sec["icon"]} {sec["title"]}</div></div>{zones_html}</div>'

    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"></head><body style="margin:0;padding:0;background:#FAFAFA;font-family:Arial,sans-serif;"><div style="max-width:900px;margin:0 auto;padding:20px;">
    <div style="background:#038450;border-left:6px solid #FFE16F;padding:20px;display:flex;align-items:center;justify-content:space-between;">
      <div>
        <div style="font-size:22px;font-weight:700;color:#fff;text-transform:uppercase;">🛡️ Centro de Operaciones</div>
        <div style="font-size:12px;color:#FFE16F;font-weight:700;">Seguros Bolívar – Monitoreo Integral</div>
        <div style="font-size:11px;color:rgba(255,255,255,.8);">{ts_label}</div>
      </div>
      <div style="background:white; padding:10px; border-radius:12px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
        <img src="https://d9b6rardqz97a.cloudfront.net/wp-content/uploads/2019/11/31104435/icon-bolivar-conmigo.png" alt="Logo" style="width:70px; height:auto;">
      </div>
    </div>
    <div style="background:#fff;padding:15px 20px;margin-top:10px;border-left:4px solid {sum_color};font-weight:700;color:{sum_color};">
        {sum_icon} REPORTE: {total_errors} error(es) detectado(s)
    </div>
    {sections_html}
    <div style="margin-top:20px;text-align:center;font-size:10px;color:#777;">Seguros Bolívar · Automatización Monitoreo</div>
    </div></body></html>"""

# ─────────────────────────────────────────────
# ENVÍO Y MOTOR DE EJECUCIÓN
# ─────────────────────────────────────────────
def send_email(html_body, total_errors, window_start, window_stop):
    subject = f"{'⚠️' if total_errors > 0 else '✅'} [{window_stop.strftime('%H:%M')}] Monitoreo Seguros Bolívar - {total_errors} errores"
    msg = MIMEMultipart("alternative"); msg["Subject"] = subject; msg["From"] = GMAIL_USER; msg["To"] = EMAIL_TO
    if EMAIL_CC: msg["Cc"] = EMAIL_CC
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    recipients = [EMAIL_TO] + ([e.strip() for e in EMAIL_CC.split(",") if e.strip()] if EMAIL_CC else [])
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as srv:
        srv.login(GMAIL_USER, GMAIL_PASS); srv.sendmail(GMAIL_USER, recipients, msg.as_string())
    print(f"✅ Correo enviado a {recipients}")

def run_cycle():
    window_start, window_stop = get_window()
    print(f"🔍 Consultando InfluxDB para ventana: {window_start.strftime('%H:%M')} a {window_stop.strftime('%H:%M')}")
    data = query_influx(window_start, window_stop)
    total_errors = sum(len(v) for v in data.values())
    if total_errors > 0 or SEND_ALWAYS:
        html = build_email_html(data, window_start, window_stop)
        send_email(html, total_errors, window_start, window_stop)
    else:
        print("→ Sin errores. No se envía mail (SEND_ALWAYS=false).")

def main():
    if RUN_AS_DAEMON:
        while True:
            if es_hora_de_ejecutar(): run_cycle()
            time.sleep(60)
    else:
        # Ejecución controlada por Cron y horarios.json
        if es_hora_de_ejecutar():
            run_cycle()
        else:
            print(f"💤 Hora fuera de programación ({datetime.now().strftime('%H:%M')}). No se procesa envío.")

if __name__ == "__main__":
    main()
