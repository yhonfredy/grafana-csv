#esta version incluye la palabra errores despues del numero.
#En la franja de resumen (roja/verde): Ya no se verá solo un "6", sino:
#⚠️ REPORTE: 6 error(es) detectado(s) en el bloque 06:00
#En el recuadro rojo lateral (de cada zona): Seguirá apareciendo el número resaltado en rojo 
#para que visualmente se identifique dónde está el problema rápidamente.
#En el Asunto del correo (Subject): También aparecerá corregido:
#⚠️ [06:03] Monitoreo Seguros Bolívar - 6 error(es)
#⚠️ nueva lógica de destinatarios diferenciados (CC solo en reportes fijos, alertas directas solo al destinatario principal)

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
        if not os.path.exists(VARIABLES_FILE):
            print(f"❌ ERROR CRÍTICO: No se encuentra el archivo {VARIABLES_FILE}")
            return creds
            
        with open(VARIABLES_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    creds[k.strip()] = v.strip()
    except Exception as e:
        print(f"❌ Error leyendo {VARIABLES_FILE}: {e}")
    return creds

# CARGA ÚNICA DE VARIABLES DESDE EL TXT
_CONFIG = _load_creds()

# InfluxDB (Dependencia total del TXT)
INFLUX_URL    = _CONFIG.get("INFLUX_URL")
INFLUX_TOKEN  = _CONFIG.get("INFLUX_TOKEN")
INFLUX_ORG    = _CONFIG.get("INFLUX_ORG")
INFLUX_BUCKET = _CONFIG.get("INFLUX_BUCKET")

# Correo (Dependencia total del TXT)
GMAIL_USER = _CONFIG.get("GMAIL_USER")
GMAIL_PASS = _CONFIG.get("GMAIL_PASS")
EMAIL_TO   = _CONFIG.get("EMAIL_TO")
EMAIL_CC   = _CONFIG.get("EMAIL_CC")

# Comportamiento
WINDOW_MINUTES = 15
SEND_ALWAYS    = _CONFIG.get("SEND_ALWAYS", "true").lower() == "true"

# ─────────────────────────────────────────────
# LÓGICA DE TIEMPO (REDONDEO Y VENTANAS)
# ─────────────────────────────────────────────
def check_status_envio():
    ahora = datetime.now()
    minuto_bloque = (ahora.minute // 15) * 15
    bloque_horario = ahora.replace(minute=minuto_bloque).strftime("%H:%M")
    
    es_fija = False
    if os.path.exists(SCHEDULE_FILE):
        with open(SCHEDULE_FILE, 'r', encoding="utf-8") as f:
            config = json.load(f)
            if bloque_horario in config.get("horas_permitidas", []):
                es_fija = True

    es_alerta = 6 <= ahora.hour < 22
    return es_fija, es_alerta, bloque_horario

def get_window() -> tuple:
    now = datetime.now(timezone.utc)
    floored = (now.minute // WINDOW_MINUTES) * WINDOW_MINUTES
    start = now.replace(minute=floored, second=0, microsecond=0)
    return start, now

# ─────────────────────────────────────────────
# CONSULTAS INFLUXDB (QUERIES)
# ─────────────────────────────────────────────
ALL_QUERIES = {
    "listener": """from(bucket: "{bucket}") |> range(start: {start}, stop: {stop}) |> filter(fn: (r) => r._measurement == "status_check") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r.tipo == "oracle" or r.tipo == "listado_oracle") |> filter(fn: (r) => r._value == 0)""",
    "weblogic_puertos": """from(bucket: "{bucket}") |> range(start: {start}, stop: {stop}) |> filter(fn: (r) => r._measurement == "status_check") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r.tipo == "weblogic") |> filter(fn: (r) => r._value == 0)""",
    "ipm_puertos": """from(bucket: "{bucket}") |> range(start: {start}, stop: {stop}) |> filter(fn: (r) => r._measurement == "status_check") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r.tipo == "ipm") |> filter(fn: (r) => r._value == 0)""",
    "simon_puertos": """from(bucket: "{bucket}") |> range(start: {start}, stop: {stop}) |> filter(fn: (r) => r._measurement == "status_check") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r.tipo == "simonweb" or r.tipo == "quotation") |> filter(fn: (r) => r._value == 0)""",
    "simon_web_url": """from(bucket: "{bucket}") |> range(start: {start}, stop: {stop}) |> filter(fn: (r) => r._measurement == "status_check_http") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r._value == 0)""",
    "db_prod": """from(bucket: "{bucket}") |> range(start: {start}, stop: {stop}) |> filter(fn: (r) => r._measurement == "status_check_oracleDataBase") |> filter(fn: (r) => r._field == "status_value") |> filter(fn: (r) => r.ambiente == "PRODUCCION" or r.ambiente == "PRD") |> filter(fn: (r) => r._value == 0)""",
    "db_test": """from(bucket: "{bucket}") |> range(start: {start}, stop: {stop}) |> filter(fn: (r) => r._measurement == "status_check_oracleDataBase") |> filter(fn: (r) => r._field == "status_value") |> filter(fn: (r) => r.ambiente == "TEST" or r.ambiente == "QA") |> filter(fn: (r) => r._value == 0)""",
    "db_dev": """from(bucket: "{bucket}") |> range(start: {start}, stop: {stop}) |> filter(fn: (r) => r._measurement == "status_check_oracleDataBase") |> filter(fn: (r) => r._field == "status_value") |> filter(fn: (r) => r.ambiente == "DESARROLLO" or r.ambiente == "DEV") |> filter(fn: (r) => r._value == 0)""",
    "ipm_soap": """from(bucket: "{bucket}") |> range(start: {start}, stop: {stop}) |> filter(fn: (r) => r._measurement == "status_check_IPM") |> filter(fn: (r) => r._field == "status_code") |> filter(fn: (r) => r._value != 200)""",
}

def query_influx(start: datetime, stop: datetime) -> dict:
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    s_str, p_str = start.strftime(fmt), stop.strftime(fmt)
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    api = client.query_api()
    results = {}
    for zone, flux in ALL_QUERIES.items():
        query = flux.replace("{bucket}", str(INFLUX_BUCKET)).replace("{start}", s_str).replace("{stop}", p_str)
        try:
            tables = api.query(query)
            rows = []
            for t in tables:
                for rec in t.records:
                    row = {"time": rec.get_time().strftime("%H:%M:%S"), "value": rec.get_value()}
                    for k, v in rec.values.items():
                        if k not in ["_start","_stop","_time","_value","_field","_measurement","result","table"] and v:
                            row[k] = str(v)
                    rows.append(row)
            results[zone] = rows
        except: results[zone] = []
    client.close()
    return results

# ─────────────────────────────────────────────
# DISEÑO HTML (SECCIONES COMPLETAS)
# ─────────────────────────────────────────────
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

def _rows_to_html(rows: list) -> str:
    if not rows: return '<p style="color:#28A745;font-weight:700;margin:8px 0;">✅ Sin errores en esta ventana</p>'
    cols = ["time", "nombre", "db_id", "servicio", "ip", "url", "ambiente", "instance", "tipo", "value"]
    actual_cols = [c for c in cols if any(c in r for r in rows)]
    th = "".join(f'<th style="background:#038450;color:#fff;padding:8px;text-align:left;font-size:11px;">{c.upper()}</th>' for c in actual_cols)
    tr = "".join([f'<tr style="background:{"#fff" if i%2==0 else "#f9f9f9"};">' + "".join([f'<td style="padding:8px;border-bottom:1px solid #eee;font-size:11px;">{r.get(c,"—")}</td>' for c in actual_cols]) + '</tr>' for i,r in enumerate(rows)])
    return f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;margin-top:5px;"><thead>{th}</thead><tbody>{tr}</tbody></table></div>'

def build_email_html(data, window_label, total_errors):
    sum_color = "#DC3545" if total_errors > 0 else "#28A745"
    sum_icon = "⚠️" if total_errors > 0 else "✅"
    sections_html = ""
    for sec in SECTIONS:
        zones_html = ""
        for zid, zicon, zlabel in sec["zones"]:
            rows = data.get(zid, [])
            count = len(rows)
            status_style = f"background:{'#DC3545' if count>0 else '#28A745'};color:#fff;border-radius:10px;padding:2px 10px;font-size:11px;font-weight:700;"
            zones_html += f"""<div style="margin-bottom:15px;">
                <div style="background:#009056;padding:8px 15px;display:flex;align-items:center;border-left:4px solid #FFE16F;">
                    <span style="color:#fff;font-size:12px;font-weight:700;flex:1;">{zicon} {zlabel}</span>
                    <span style="{status_style}">{count if count>0 else "OK"}</span>
                </div>
                <div style="padding:10px;background:#fff;border:1px solid #eee;border-top:none;">{_rows_to_html(rows)}</div>
            </div>"""
        sections_html += f"""<div style="margin-top:25px;">
            <div style="background:#038450;padding:15px;border-left:6px solid #FFE16F;">
                <div style="color:#fff;font-size:15px;font-weight:700;text-transform:uppercase;">{sec['icon']} {sec['title']}</div>
                <div style="color:rgba(255,255,255,0.8);font-size:11px;">{sec['sub']}</div>
            </div>{zones_html}</div>"""

    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:20px;">
    <div style="max-width:900px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 4px 15px rgba(0,0,0,0.1);">
        <div style="background:#038450;padding:25px;color:#fff;display:flex;align-items:center;justify-content:space-between;border-left:8px solid #FFE16F;">
            <div><div style="font-size:24px;font-weight:700;">🛡️ Centro de Operaciones</div><div style="font-size:13px;color:#FFE16F;font-weight:700;margin-top:5px;">Seguros Bolívar – Monitoreo Integral</div></div>
            <div style="background:#fff;padding:10px;border-radius:10px;"><img src="https://d9b6rardqz97a.cloudfront.net/wp-content/uploads/2019/11/31104435/icon-bolivar-conmigo.png" width="80"></div>
        </div>
        <div style="padding:20px;">
            <div style="background:{sum_color};color:#fff;padding:15px;font-weight:700;border-radius:5px;">{sum_icon} REPORTE: {total_errors} error(es) detectado(s) en el bloque {window_label}</div>
            {sections_html}
        </div>
        <div style="background:#f9f9f9;padding:15px;text-align:center;font-size:11px;color:#888;">Seguros Bolívar © 2024 - Sistema de Alertas Automáticas</div>
    </div></body></html>"""

# ─────────────────────────────────────────────
# ENVÍO Y EJECUCIÓN
# ─────────────────────────────────────────────
def send_email(html, total_errors, label, incluir_cc=True):
    subject = f"{'⚠️' if total_errors > 0 else '✅'} [{label}] Monitoreo Seguros Bolívar - {total_errors} error(es)"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = EMAIL_TO
    
    recipients = [EMAIL_TO] if EMAIL_TO else []
    if incluir_cc and EMAIL_CC:
        msg["Cc"] = EMAIL_CC
        recipients += [e.strip() for e in EMAIL_CC.split(",") if e.strip()]

    if not recipients:
        print("⚠️ No hay destinatarios definidos en variables.txt. Abortando envío.")
        return

    msg.attach(MIMEText(html, "html"))
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as srv:
            srv.login(GMAIL_USER, GMAIL_PASS)
            srv.sendmail(GMAIL_USER, recipients, msg.as_string())
        print(f"✅ Enviado a: {', '.join(recipients)}")
    except Exception as e:
        print(f"❌ Error SMTP: {e}")

def main():
    es_fija, es_alerta, label = check_status_envio()
    
    if not es_fija and not es_alerta:
        print(f"💤 Fuera de horario ({label}).")
        return

    start, stop = get_window()
    data = query_influx(start, stop)
    total_errors = sum(len(v) for v in data.values())

    if es_fija:
        print(f"📢 Reporte Programado JSON ({label}). Enviando a TO y CC...")
        html = build_email_html(data, label, total_errors)
        send_email(html, total_errors, label, incluir_cc=True)
    elif es_alerta and total_errors > 0:
        print(f"🚨 ALERTA detectada ({total_errors} errores). Enviando solo a TO...")
        html = build_email_html(data, label, total_errors)
        send_email(html, total_errors, label, incluir_cc=False)
    else:
        print(f"✅ Bloque {label}: Todo OK. No se requiere envío de alerta.")

if __name__ == "__main__":
    main()
