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
# CONFIGURACIÓN
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
        print(f"⚠️  {VARIABLES_FILE} no encontrado — usando variables de entorno")
    return creds

_CREDS = _load_creds()

INFLUX_URL    = _CREDS.get("INFLUX_URL",    os.getenv("INFLUX_URL",    "http://localhost:8086"))
INFLUX_TOKEN  = _CREDS.get("INFLUX_TOKEN",  os.getenv("INFLUX_TOKEN",  ""))
INFLUX_ORG    = _CREDS.get("INFLUX_ORG",    os.getenv("INFLUX_ORG",    ""))
INFLUX_BUCKET = _CREDS.get("INFLUX_BUCKET", os.getenv("INFLUX_BUCKET", "status_services"))

GMAIL_USER = _CREDS.get("GMAIL_USER", os.getenv("GMAIL_USER", "tu_correo@gmail.com"))
GMAIL_PASS = _CREDS.get("GMAIL_PASS", os.getenv("GMAIL_PASS", ""))
EMAIL_TO   = _CREDS.get("EMAIL_TO",   os.getenv("EMAIL_TO",   "destinatario@empresa.com"))
EMAIL_CC   = _CREDS.get("EMAIL_CC",   os.getenv("EMAIL_CC",   ""))

WINDOW_MINUTES = 15
SEND_ALWAYS    = _CREDS.get("SEND_ALWAYS", os.getenv("SEND_ALWAYS", "false")).lower() == "true"
RUN_AS_DAEMON  = _CREDS.get("RUN_AS_DAEMON", os.getenv("RUN_AS_DAEMON", "false")).lower() == "true"

# ─────────────────────────────────────────────
# VALIDACIÓN DE HORARIO
# ─────────────────────────────────────────────
def es_hora_de_ejecutar() -> bool:
    """Verifica si el HH:MM actual coincide con la lista en horarios.json"""
    try:
        if not os.path.exists(SCHEDULE_FILE):
            print(f"⚠️  No se encontró {SCHEDULE_FILE}. Ejecutando por defecto.")
            return True
            
        with open(SCHEDULE_FILE, 'r', encoding="utf-8") as f:
            config = json.load(f)
            
        horas_permitidas = config.get("horas_permitidas", [])
        ahora = datetime.now().strftime("%H:%M")
        
        return ahora in horas_permitidas
    except Exception as e:
        print(f"❌ Error leyendo horarios.json: {e}")
        return False

# ─────────────────────────────────────────────
# VENTANA E INFLUXDB
# ─────────────────────────────────────────────
def get_window() -> tuple:
    now = datetime.now(timezone.utc)
    floored = (now.minute // WINDOW_MINUTES) * WINDOW_MINUTES
    start   = now.replace(minute=floored, second=0, microsecond=0)
    return start, now

def flux_range(start: datetime, stop: datetime) -> str:
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return f"|> range(start: {start.strftime(fmt)}, stop: {stop.strftime(fmt)})"

# Queries (Mismas del archivo original)
QUERIES_PUERTOS = {
    "listener": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r.tipo == "oracle" or r.tipo == "listado_oracle") |> filter(fn: (r) => r._value == 0) |> keep(columns: ["_time","_value","nombre","ip","tipo"])""",
    "weblogic_puertos": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r.tipo == "weblogic") |> filter(fn: (r) => r._value == 0) |> keep(columns: ["_time","_value","nombre","ip","tipo"])""",
    "ipm_puertos": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r.tipo == "ipm") |> filter(fn: (r) => r._value == 0) |> keep(columns: ["_time","_value","nombre","ip","tipo"])""",
    "simon_puertos": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r.tipo == "simonweb" or r.tipo == "quotation") |> filter(fn: (r) => r._value == 0) |> keep(columns: ["_time","_value","nombre","ip","tipo"])""",
}
QUERIES_HTTP = {
    "simon_web_url": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check_http") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r._value == 0) |> keep(columns: ["_time","_value","nombre","url","tipo_error"])""",
}
QUERIES_ORACLE = {
    "db_prod": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check_oracleDataBase") |> filter(fn: (r) => r._field == "status_value") |> filter(fn: (r) => r.ambiente == "PRODUCCION" or r.ambiente == "PRD") |> filter(fn: (r) => r._value == 0) |> keep(columns: ["_time","_value","db_id","ip","ambiente","instance"])""",
    "db_test": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check_oracleDataBase") |> filter(fn: (r) => r._field == "status_value") |> filter(fn: (r) => r.ambiente == "TEST" or r.ambiente == "QA") |> filter(fn: (r) => r._value == 0) |> keep(columns: ["_time","_value","db_id","ip","ambiente","instance"])""",
    "db_dev": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check_oracleDataBase") |> filter(fn: (r) => r._field == "status_value") |> filter(fn: (r) => r.ambiente == "DESARROLLO" or r.ambiente == "DEV") |> filter(fn: (r) => r._value == 0) |> keep(columns: ["_time","_value","db_id","ip","ambiente","instance"])""",
}
QUERIES_IPM = {
    "ipm_soap": """from(bucket: "{bucket}") {range} |> filter(fn: (r) => r._measurement == "status_check_IPM") |> filter(fn: (r) => r._field == "status_code") |> filter(fn: (r) => r._value != 200) |> keep(columns: ["_time","_value","servicio","url","estado_msg"])""",
}
ALL_QUERIES = {**QUERIES_PUERTOS, **QUERIES_HTTP, **QUERIES_ORACLE, **QUERIES_IPM}

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
        except Exception as exc: results[zone] = [{"time": "—", "value": "—", "error": str(exc)}]
    client.close()
    return results

def _rows_to_html(rows: list) -> str:
    if not rows: return '<p style="color:#28A745;font-weight:700;margin:8px 0;">✅ Sin errores en esta ventana</p>'
    priority = ["time", "nombre", "db_id", "servicio", "ip", "url", "ambiente", "instance", "tipo", "tipo_error", "value", "error"]
    all_keys = list(dict.fromkeys([k for k in priority if any(k in r for r in rows)] + [k for r in rows for k in r if k not in priority]))
    th = "".join(f'<th style="background:#038450;color:#fff;padding:7px 10px;text-align:left;font-size:11px;white-space:nowrap;">{k.upper()}</th>' for k in all_keys)
    body = "".join([f'<tr style="background:{"#fff" if i%2==0 else "#F5F5F5"};">' + "".join([f'<td style="padding:6px 10px;border-bottom:1px solid #E1E1E1;font-size:11px;">{r.get(k,"—")}</td>' for k in all_keys]) + '</tr>' for i, r in enumerate(rows)])
    return f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:11px;"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'

SECTIONS = [
    {"icon": "💽", "title": "Infraestructura de Base de Datos Oracle", "sub": "Monitoreo de conexión – Estado en tiempo real", 
     "zones": [("listener", "💾", "Verificación de disponibilidad del Listener (Puerto 1521)"), ("db_prod", "📡", "Disponibilidad Global – Producción"), ("db_test", "📡", "Disponibilidad Global – TEST"), ("db_dev", "📡", "Disponibilidad Global – Desarrollo")]},
    {"icon": "🖥️", "title": "Plataforma Digital SIMON", "sub": "Estado de aplicaciones Simon Web y Simon Quotation", 
     "zones": [("simon_puertos", "💻", "Simon Web / Quotation – Puertos"), ("simon_web_url", "💻", "Simon Web – URLs HTTP")]},
    {"icon": "🌐", "title": "Servicios Web – Estado de Salud", "sub": "Health check de endpoints y APIs", 
     "zones": [("weblogic_puertos", "🌐", "Plataforma WebLogic – Puertos")]},
    {"icon": "📊", "title": "IPM en Oracle – Intelligent Performance Management", "sub": "Monitoreo de rendimiento y operaciones SOAP", 
     "zones": [("ipm_puertos", "💻", "Servidores IPM – Puertos"), ("ipm_soap", "🔄", "Colección Estandarizada de Operaciones SOAP")]},
]

def build_email_html(data: dict, window_start: datetime, window_stop: datetime) -> str:
    ts_label = window_stop.strftime("%Y-%m-%d %H:%M UTC")
    total_errors = sum(len(v) for v in data.values())
    sum_color = "#DC3545" if total_errors > 0 else "#28A745"
    sum_icon = "⚠️" if total_errors > 0 else "✅"
    sum_text = f"{total_errors} error(es) detectado(s)" if total_errors > 0 else "Sin errores en esta ventana"
    
    sections_html = ""
    for sec in SECTIONS:
        zones_html = ""
        for zone_id, z_icon, z_label in sec["zones"]:
            rows = data.get(zone_id, []); count = len(rows)
            dot_color = "#DC3545" if count > 0 else "#28A745"
            zones_html += f'<div style="margin:10px 0 0;"><div style="background:#009056;border-left:4px solid #FFE16F;padding:8px 16px;display:flex;align-items:center;gap:8px;"><span style="font-size:14px;">{z_icon}</span><span style="font-size:12px;font-weight:700;color:#fff;text-transform:uppercase;flex:1;">{z_label}</span><span style="background:{dot_color};color:#fff;border-radius:12px;padding:2px 10px;font-size:11px;font-weight:700;">{count if count > 0 else "OK"}</span></div><div style="padding:12px 16px;background:#fff;border-left:4px solid #E1E1E1;">{_rows_to_html(rows)}</div></div>'
        sections_html += f'<div style="margin-top:20px;"><div style="background:#038450;border-left:6px solid #FFE16F;padding:14px 20px;display:flex;align-items:center;gap:12px;"><div style="width:34px;height:34px;background:#FFE16F;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:16px;">{sec["icon"]}</div><div><div style="font-size:14px;font-weight:700;color:#fff;text-transform:uppercase;">{sec["title"]}</div><div style="font-size:11px;color:rgba(255,255,255,.75);">{sec["sub"]}</div></div></div>{zones_html}</div>'

    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"></head><body style="margin:0;padding:0;background:#FAFAFA;font-family:Arial,sans-serif;color:#1B1B1B;"><div style="max-width:960px;margin:0 auto;padding-bottom:32px;">
    
    <div style="background:#038450;border-left:6px solid #FFE16F;padding:18px 24px;display:flex;align-items:center;justify-content:space-between;">
      <div>
        <div style="display:flex;align-items:center;gap:12px;">
            <div style="width:42px;height:42px;background:#FFE16F;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:20px;">🛡️</div>
            <span style="font-size:22px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:1px;">Centro de Operaciones</span>
        </div>
        <p style="font-size:12px;font-weight:700;color:#FFE16F;margin:6px 0 2px 54px;">Seguros Bolívar – Monitoreo en Tiempo Real</p>
        <p style="font-size:11px;color:rgba(255,255,255,.8);margin:0 0 0 54px;">Actualizado: {ts_label}</p>
      </div>
      
      <div style="text-align:center; width:15%;">
        <div style="background:white; padding:15px; border-radius:12px; box-shadow: 0 6px 20px rgba(0,0,0,0.25);">
          <img src="https://d9b6rardqz97a.cloudfront.net/wp-content/uploads/2019/11/31104435/icon-bolivar-conmigo.png"
               alt="Seguros Bolívar"
               style="width:85px; height:auto; border-radius:8px;">
        </div>
      </div>
    </div>

    <div style="background:#fff;padding:14px 24px;margin-top:12px;border-left:4px solid {sum_color};"><div style="font-size:14px;font-weight:700;color:{sum_color};">{sum_icon} {sum_text}</div><div style="font-size:11px;color:#757575;margin-top:4px;">Ventana: {window_start.strftime("%H:%M")} → {window_stop.strftime("%H:%M")} UTC</div></div>
    {sections_html}
    
    <div style="margin-top:28px;padding:12px 24px;background:#038450;text-align:center;color:rgba(255,255,255,.7);font-size:11px;">Seguros Bolívar · Centro de Operaciones · {ts_label}</div>
    </div></body></html>"""

# ─────────────────────────────────────────────
# ENVÍO Y MOTOR
# ─────────────────────────────────────────────
def send_email(html_body, total_errors, window_start, window_stop):
    subject = f"{'⚠️' if total_errors > 0 else '✅'} [{window_stop.strftime('%H:%M')}] Centro de Operaciones – {total_errors} error(es)"
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
    data = query_influx(window_start, window_stop)
    total_errors = sum(len(v) for v in data.values())
    if total_errors > 0 or SEND_ALWAYS:
        html = build_email_html(data, window_start, window_stop)
        send_email(html, total_errors, window_start, window_stop)
    else: print("→ Sin errores. No se envía mail.")

def main():
    if RUN_AS_DAEMON:
        while True:
            if es_hora_de_ejecutar(): run_cycle()
            time.sleep(60)
    else:
        if es_hora_de_ejecutar():
            print(f"✅ Ejecución autorizada por horario ({datetime.now().strftime('%H:%M')}).")
            run_cycle()
        else: print(f"💤 Hora ({datetime.now().strftime('%H:%M')}) no programada en JSON. Saltando.")

if __name__ == "__main__":
    main()
