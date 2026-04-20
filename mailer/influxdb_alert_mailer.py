#esta version incluye la palabra errores despues del numero.
#En la franja de resumen (roja/verde): Ya no se verá solo un "6", sino:
#⚠️ REPORTE: 6 error(es) detectado(s) en el bloque 06:00
#En el recuadro rojo lateral (de cada zona): Seguirá apareciendo el número resaltado en rojo 
#para que visualmente se identifique dónde está el problema rápidamente.
#En el Asunto del correo (Subject): También aparecerá corregido:
#⚠️ [06:03] Monitoreo Seguros Bolívar - 6 error(es)
#⚠️ nueva lógica de destinatarios diferenciados (CC solo en reportes fijos, alertas directas solo al destinatario principal)
#⚠️ BLOQUE ORIGINAL (Líneas 108 aprox)
#for rec in t.records:
#    row = {"time": rec.get_time().strftime("%Y-%m-%d %H:%M:%S UTC")}
# BLOQUE CORREGIDO (Resta 5 horas para Colombia)
#for rec in t.records:
    # Restamos 5 horas al objeto datetime que viene de Influx
#    hora_colombia = rec.get_time() - timedelta(hours=5)
#    row = {"time": hora_colombia.strftime("%Y-%m-%d %H:%M:%S")}
# La hora +5 nop es error de imfluxDB. No es que InfluxDB tenga un "error"
# sino que InfluxDB sigue un estándar mundial de bases de datos.
# siempre guarda la información en hora UTC (Tiempo Universal Coordinado) por diseño.

import os
import smtplib
import ssl
import time
import json
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from influxdb_client import InfluxDBClient

# ──────────────────────────────────────────────────────────
# 1. CONFIGURACIÓN Y CARGA DE VARIABLES
# ──────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
VARIABLES_FILE = os.path.join(BASE_DIR, "variables.txt")
SCHEDULE_FILE  = os.path.join(BASE_DIR, "horarios.json")

def _load_creds() -> dict:
    creds = {}
    if not os.path.exists(VARIABLES_FILE): return creds
    with open(VARIABLES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip()
    return creds

_CONFIG = _load_creds()

INFLUX_URL    = _CONFIG.get("INFLUX_URL")
INFLUX_TOKEN  = _CONFIG.get("INFLUX_TOKEN")
INFLUX_ORG    = _CONFIG.get("INFLUX_ORG")
INFLUX_BUCKET = _CONFIG.get("INFLUX_BUCKET")
GMAIL_USER    = _CONFIG.get("GMAIL_USER")
GMAIL_PASS    = _CONFIG.get("GMAIL_PASS")
EMAIL_TO      = _CONFIG.get("EMAIL_TO")
EMAIL_CC      = _CONFIG.get("EMAIL_CC")

# ──────────────────────────────────────────────────────────
# 2. LÓGICA DE TIEMPO
# ──────────────────────────────────────────────────────────
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
    return es_fija, (6 <= ahora.hour < 22), bloque_horario

def get_window() -> tuple:
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=15)
    return start, now

# ──────────────────────────────────────────────────────────
# 3. CONSULTAS INFLUXDB
# ──────────────────────────────────────────────────────────
def query_influx(start: datetime, stop: datetime) -> dict:
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    s_str, p_str = start.strftime(fmt), stop.strftime(fmt)
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    api = client.query_api()
    
    queries = {
        "listener": f'from(bucket: "{INFLUX_BUCKET}") |> range(start: {s_str}, stop: {p_str}) |> filter(fn: (r) => r._measurement == "status_check") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r.tipo == "oracle" or r.tipo == "listado_oracle") |> filter(fn: (r) => r._value == 0)',
        "weblogic_puertos": f'from(bucket: "{INFLUX_BUCKET}") |> range(start: {s_str}, stop: {p_str}) |> filter(fn: (r) => r._measurement == "status_check") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r.tipo == "weblogic") |> filter(fn: (r) => r._value == 0)',
        "ipm_puertos": f'from(bucket: "{INFLUX_BUCKET}") |> range(start: {s_str}, stop: {p_str}) |> filter(fn: (r) => r._measurement == "status_check") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r.tipo == "ipm") |> filter(fn: (r) => r._value == 0)',
        "simon_puertos": f'from(bucket: "{INFLUX_BUCKET}") |> range(start: {s_str}, stop: {p_str}) |> filter(fn: (r) => r._measurement == "status_check") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r.tipo == "simonweb" or r.tipo == "quotation") |> filter(fn: (r) => r._value == 0)',
        "simon_web_url": f'from(bucket: "{INFLUX_BUCKET}") |> range(start: {s_str}, stop: {p_str}) |> filter(fn: (r) => r._measurement == "status_check_http") |> filter(fn: (r) => r._field == "status") |> filter(fn: (r) => r._value == 0)',
        "db_prod": f'from(bucket: "{INFLUX_BUCKET}") |> range(start: {s_str}, stop: {p_str}) |> filter(fn: (r) => r._measurement == "status_check_oracleDataBase") |> filter(fn: (r) => r._field == "status_value") |> filter(fn: (r) => r.ambiente == "PRODUCCION" or r.ambiente == "PRD") |> filter(fn: (r) => r._value == 0)',
        "db_test": f'from(bucket: "{INFLUX_BUCKET}") |> range(start: {s_str}, stop: {p_str}) |> filter(fn: (r) => r._measurement == "status_check_oracleDataBase") |> filter(fn: (r) => r._field == "status_value") |> filter(fn: (r) => r.ambiente == "TEST" or r.ambiente == "QA") |> filter(fn: (r) => r._value == 0)',
        "db_dev": f'from(bucket: "{INFLUX_BUCKET}") |> range(start: {s_str}, stop: {p_str}) |> filter(fn: (r) => r._measurement == "status_check_oracleDataBase") |> filter(fn: (r) => r._field == "status_value") |> filter(fn: (r) => r.ambiente == "DESARROLLO" or r.ambiente == "DEV") |> filter(fn: (r) => r._value == 0)',
        "ipm_soap": f'from(bucket: "{INFLUX_BUCKET}") |> range(start: {s_str}, stop: {p_str}) |> filter(fn: (r) => r._measurement == "status_check_IPM") |> filter(fn: (r) => r._field == "status_code") |> filter(fn: (r) => r._value != 200)'
    }
    
    results = {}
    for zone, query in queries.items():
        try:
            tables = api.query(query)
            rows = []
            for t in tables:
            # BLOQUE CORREGIDO (Resta 5 horas para Colombia)
                for rec in t.records:
                    # Restamos 5 horas al objeto datetime que viene de Influx
                    hora_colombia = rec.get_time() - timedelta(hours=5)
                    row = {"time": hora_colombia.strftime("%Y-%m-%d %H:%M:%S")}
                #for rec in t.records: estos traen los datos de influx
                    #row = {"time": rec.get_time().strftime("%Y-%m-%d %H:%M:%S UTC")} 
                    for k, v in rec.values.items():
                        if k not in ["_start","_stop","_time","_field","_measurement","result","table"]:
                            row[k] = str(v)
                    rows.append(row)
            results[zone] = rows
        except: results[zone] = []
    client.close()
    return results

# ──────────────────────────────────────────────────────────
# 4. DISEÑO HTML (EL MÁS BONITO)
# ──────────────────────────────────────────────────────────
SECTIONS = [
    {"title": "INFRAESTRUCTURA DE BASE DE DATOS ORACLE", "sub": "Monitoreo de conexión – Estado en tiempo real", 
     "zones": [("listener", "VERIFICACIÓN DE DISPONIBILIDAD DEL LISTENER (PUERTO 1521)"), ("db_prod", "DISPONIBILIDAD GLOBAL – PRODUCCIÓN"), ("db_test", "DISPONIBILIDAD GLOBAL – TEST"), ("db_dev", "DISPONIBILIDAD GLOBAL – DESARROLLO")]},
    {"title": "PLATAFORMA DIGITAL SIMON", "sub": "Estado de aplicaciones Simon Web y Simon Quotation", 
     "zones": [("simon_puertos", "SIMON WEB / QUOTATION – PUERTOS"), ("simon_web_url", "SIMON WEB – URLS HTTP")]},
    {"title": "SERVICIOS WEB – ESTADO DE SALUD", "sub": "Health check de endpoints y APIs", 
     "zones": [("weblogic_puertos", "PLATAFORMA WEBLOGIC – PUERTOS")]},
    {"title": "IPM EN ORACLE – INTELLIGENT PERFORMANCE MANAGEMENT", "sub": "Monitoreo de rendimiento y operaciones SOAP", 
     "zones": [("ipm_puertos", "SERVIDORES IPM – PUERTOS"), ("ipm_soap", "COLECCIÓN ESTANDARIZADA DE OPERACIONES SOAP")]},
]

def _rows_to_html(rows: list) -> str:
    if not rows: return '<p style="color:#28A745; margin:10px 0;">✅ Sin errores en esta ventana</p>'
    cols = ["time", "nombre", "db_id", "servicio", "ip", "url", "ambiente", "tipo", "_value"]
    actual_cols = [c for c in cols if any(c in r for r in rows)]
    
    html = '<table style="width:100%; border-collapse:collapse; margin-top:10px; font-size:12px; border: 1px solid #ddd;">'
    html += '<tr style="background-color:#038450; color:white;">'
    for c in actual_cols: html += f'<th style="padding:10px; text-align:left; border:1px solid #ddd;">{c.replace("_","").upper()}</th>'
    html += '</tr>'
    
    for i, r in enumerate(rows):
        # FILAS CEBRA (Intercaladas blanca y gris suave)
        bg = "#FFFFFF" if i % 2 == 0 else "#F2F2F2"
        html += f'<tr style="background-color:{bg};">'
        for c in actual_cols: html += f'<td style="padding:8px; border:1px solid #ddd;">{r.get(c,"—")}</td>'
        html += '</tr>'
    return html + '</table>'

def build_email_html(data, label, total_errors, start_dt, stop_dt):
    ahora_str = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    sum_color = "#DC3545" if total_errors > 0 else "#28A745"
    
    sections_html = ""
    for sec in SECTIONS:
        zones_html = ""
        for zid, zlabel in sec["zones"]:
            rows = data.get(zid, [])
            count = len(rows)
            badge_color = "#DC3545" if count > 0 else "#28A745"
            badge_text = f"{count} error(es)" if count > 0 else "OK"
            
            # BLOQUE DE CADA MÉTRICA CON ESPACIADO
            zones_html += f"""
            <div style="margin-bottom:20px;">
                <div style="background-color:#009056; padding:10px 15px; display:flex; align-items:center; justify-content:space-between; color:white; border-radius:4px 4px 0 0;">
                    <span style="font-weight:bold; font-size:13px;">📊 {zlabel}</span>
                    <span style="background-color:{badge_color}; padding:2px 10px; border-radius:15px; font-size:11px; font-weight:bold;">{badge_text}</span>
                </div>
                <div style="padding:15px; border:1px solid #ddd; border-top:none; background:white;">{_rows_to_html(rows)}</div>
            </div>"""

        # BLOQUE DE SECCIÓN PRINCIPAL CON MARGEN SUPERIOR
        sections_html += f"""
        <div style="margin-top:35px; margin-bottom:15px;">
            <div style="background-color:#038450; padding:15px; border-left:8px solid #FFE16F; color:white;">
                <h2 style="margin:0; font-size:17px;">{sec['title']}</h2>
                <p style="margin:5px 0 0; font-size:11px; opacity:0.9;">{sec['sub']}</p>
            </div>
            <div style="padding-top:15px;">{zones_html}</div>
        </div>"""

    return f"""
    <html><body style="font-family:'Segoe UI',Arial,sans-serif; background-color:#f8f9fa; padding:20px;">
        <div style="max-width:900px; margin:0 auto; background-color:white; border-radius:8px; overflow:hidden; box-shadow:0 4px 15px rgba(0,0,0,0.1);">
            <div style="background-color:#038450; padding:30px; color:white; border-left:10px solid #FFE16F; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h1 style="margin:0; font-size:26px;">CENTRO DE OPERACIONES</h1>
                    <p style="margin:5px 0 0; color:#FFE16F; font-weight:bold;">Seguros Bolívar – Monitoreo en Tiempo Real</p>
                    <p style="margin:5px 0 0; font-size:12px; opacity:0.8;">Actualizado: {ahora_str}</p>
                </div>
                <div style="background:white; padding:10px; border-radius:8px;"><img src="https://d9b6rardqz97a.cloudfront.net/wp-content/uploads/2019/11/31104435/icon-bolivar-conmigo.png" width="80"></div>
            </div>
            
            <div style="padding:30px;">
                <div style="margin-bottom:30px;">
                    <h3 style="color:{sum_color}; margin:0; font-size:18px;">⚠️ {total_errors} error(es) detectado(s)</h3>
                    <p style="margin:5px 0; font-size:13px; color:#555;">
                        Ventana analizada: <b>{start_dt.strftime('%Y-%m-%d %H:%M UTC')}</b> → <b>{stop_dt.strftime('%Y-%m-%d %H:%M UTC')}</b> | Bucket: <b>{INFLUX_BUCKET}</b>
                    </p>
                </div>
                {sections_html}
            </div>
            <div style="background:#f1f1f1; padding:15px; text-align:center; font-size:11px; color:#666;">Reporte Automático - Seguros Bolívar</div>
        </div>
    </body></html>"""

# ──────────────────────────────────────────────────────────
# 5. ENVÍO
# ──────────────────────────────────────────────────────────
def send_email(html, total_errors, label, incluir_cc=True):
    subject = f"{'⚠️' if total_errors > 0 else '✅'} [{label}] Monitoreo Seguros Bolívar - {total_errors} error(es)"
    msg = MIMEMultipart("alternative"); msg["Subject"] = subject; msg["From"] = GMAIL_USER; msg["To"] = EMAIL_TO
    recipients = [EMAIL_TO]
    if incluir_cc and EMAIL_CC:
        msg["Cc"] = EMAIL_CC
        recipients += [e.strip() for e in EMAIL_CC.split(",") if e.strip()]
    msg.attach(MIMEText(html, "html"))
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as srv:
            srv.login(GMAIL_USER, GMAIL_PASS)
            srv.sendmail(GMAIL_USER, recipients, msg.as_string())
        print(f"✅ Enviado a: {recipients}")
    except Exception as e: print(f"❌ Error: {e}")

def main():
    es_fija, es_alerta, label = check_status_envio()
    if not es_fija and not es_alerta: return
    start, stop = get_window()
    data = query_influx(start, stop)
    total_errors = sum(len(v) for v in data.values())
    html = build_email_html(data, label, total_errors, start, stop)
    if es_fija: send_email(html, total_errors, label, incluir_cc=True)
    elif total_errors > 0: send_email(html, total_errors, label, incluir_cc=False)

if __name__ == "__main__": main()
