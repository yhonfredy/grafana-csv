"""
influxdb_alert_mailer.py
Lee InfluxDB con ventana exacta de 15 minutos, filtra errores (status=0 / status!=1)
y envía correo HTML con el diseño de Seguros Bolívar.

Measurements reales del framework:
  - status_check              → validarServicios.py      (puertos: weblogic, sql, ipm, oracle…)
  - status_check_http         → registroMonitoreo.py     (URLs HTTP)
  - status_check_oracleDataBase → status_check_oracleDataBase.py (Oracle DB via oracledb)
  - status_check_IPM          → estandar_ejecutar_coleccion_influx.py (SOAP IPM)

Lógica de ventana de 15 minutos:
  Ejecución 02:05 → range(start: 02:00, stop: now)
  Ejecución 02:18 → range(start: 02:15, stop: now)
  Ejecución 02:33 → range(start: 02:30, stop: now)

Cron recomendado:
  */15 * * * * /usr/bin/python3 /home/ssm-user/SETI/validarServicios/influxdb_alert_mailer.py >> /var/log/influx_mailer.log 2>&1

Dependencias:
  pip install influxdb-client
"""

import os
import smtplib
import ssl
import time
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from influxdb_client import InfluxDBClient

# ─────────────────────────────────────────────
# CONFIGURACIÓN — lee variables.txt igual que tus otros scripts
# ─────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
VARIABLES_FILE = os.path.join(BASE_DIR, "variables.txt")

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
GMAIL_PASS = _CREDS.get("GMAIL_PASS", os.getenv("GMAIL_PASS", ""))   # App Password Google
EMAIL_TO   = _CREDS.get("EMAIL_TO",   os.getenv("EMAIL_TO",   "destinatario@empresa.com"))
EMAIL_CC   = _CREDS.get("EMAIL_CC",   os.getenv("EMAIL_CC",   ""))

WINDOW_MINUTES = 15
SEND_ALWAYS    = _CREDS.get("SEND_ALWAYS", os.getenv("SEND_ALWAYS", "false")).lower() == "true"
RUN_AS_DAEMON  = _CREDS.get("RUN_AS_DAEMON", os.getenv("RUN_AS_DAEMON", "false")).lower() == "true"


# ─────────────────────────────────────────────
# VENTANA DE 15 MINUTOS
# ─────────────────────────────────────────────
def get_window() -> tuple:
    """
    Calcula el inicio del ciclo de 15 min al que pertenece el momento actual.
      02:05 → start=02:00   02:18 → start=02:15
      02:33 → start=02:30   02:47 → start=02:45
    """
    now = datetime.now(timezone.utc)
    floored = (now.minute // WINDOW_MINUTES) * WINDOW_MINUTES
    start   = now.replace(minute=floored, second=0, microsecond=0)
    return start, now


def flux_range(start: datetime, stop: datetime) -> str:
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return f"|> range(start: {start.strftime(fmt)}, stop: {stop.strftime(fmt)})"


# ─────────────────────────────────────────────
# QUERIES — una por cada sección del HTML
# Cada query usa {range} y {bucket} como placeholders
# ─────────────────────────────────────────────

# ── 1. PUERTOS (validarServicios.py) ──────────────────────────────────────────
# measurement: status_check | field: status (1=up, 0=down)
# tags: tipo (weblogic/sql/ipm/oracle/…), nombre, ip
QUERIES_PUERTOS = {

    "listener": """
        from(bucket: "{bucket}")
          {range}
          |> filter(fn: (r) => r._measurement == "status_check")
          |> filter(fn: (r) => r._field == "status")
          |> filter(fn: (r) => r.tipo == "oracle" or r.tipo == "listado_oracle")
          |> filter(fn: (r) => r._value == 0)
          |> keep(columns: ["_time","_value","nombre","ip","tipo"])
    """,

    "weblogic_puertos": """
        from(bucket: "{bucket}")
          {range}
          |> filter(fn: (r) => r._measurement == "status_check")
          |> filter(fn: (r) => r._field == "status")
          |> filter(fn: (r) => r.tipo == "weblogic")
          |> filter(fn: (r) => r._value == 0)
          |> keep(columns: ["_time","_value","nombre","ip","tipo"])
    """,

    "ipm_puertos": """
        from(bucket: "{bucket}")
          {range}
          |> filter(fn: (r) => r._measurement == "status_check")
          |> filter(fn: (r) => r._field == "status")
          |> filter(fn: (r) => r.tipo == "ipm")
          |> filter(fn: (r) => r._value == 0)
          |> keep(columns: ["_time","_value","nombre","ip","tipo"])
    """,

    "simon_puertos": """
        from(bucket: "{bucket}")
          {range}
          |> filter(fn: (r) => r._measurement == "status_check")
          |> filter(fn: (r) => r._field == "status")
          |> filter(fn: (r) => r.tipo == "simonweb" or r.tipo == "quotation")
          |> filter(fn: (r) => r._value == 0)
          |> keep(columns: ["_time","_value","nombre","ip","tipo"])
    """,
}

# ── 2. URLs HTTP (registroMonitoreo.py) ───────────────────────────────────────
# measurement: status_check_http | field: status (1=up, 0=down)
# tags: nombre, url, tipo_error
QUERIES_HTTP = {

    "simon_web_url": """
        from(bucket: "{bucket}")
          {range}
          |> filter(fn: (r) => r._measurement == "status_check_http")
          |> filter(fn: (r) => r._field == "status")
          |> filter(fn: (r) => r._value == 0)
          |> keep(columns: ["_time","_value","nombre","url","tipo_error"])
    """,
}

# ── 3. ORACLE DB (status_check_oracleDataBase.py) ─────────────────────────────
# measurement: status_check_oracleDataBase | field: status_value (1=OPEN, 0=error)
# tags: db_id, ip, ambiente, tipo_error
QUERIES_ORACLE = {

    "db_prod": """
        from(bucket: "{bucket}")
          {range}
          |> filter(fn: (r) => r._measurement == "status_check_oracleDataBase")
          |> filter(fn: (r) => r._field == "status_value")
          |> filter(fn: (r) => r.ambiente == "PRODUCCION" or r.ambiente == "PRD")
          |> filter(fn: (r) => r._value == 0)
          |> keep(columns: ["_time","_value","db_id","ip","ambiente","instance"])
    """,

    "db_test": """
        from(bucket: "{bucket}")
          {range}
          |> filter(fn: (r) => r._measurement == "status_check_oracleDataBase")
          |> filter(fn: (r) => r._field == "status_value")
          |> filter(fn: (r) => r.ambiente == "TEST" or r.ambiente == "QA")
          |> filter(fn: (r) => r._value == 0)
          |> keep(columns: ["_time","_value","db_id","ip","ambiente","instance"])
    """,

    "db_dev": """
        from(bucket: "{bucket}")
          {range}
          |> filter(fn: (r) => r._measurement == "status_check_oracleDataBase")
          |> filter(fn: (r) => r._field == "status_value")
          |> filter(fn: (r) => r.ambiente == "DESARROLLO" or r.ambiente == "DEV")
          |> filter(fn: (r) => r._value == 0)
          |> keep(columns: ["_time","_value","db_id","ip","ambiente","instance"])
    """,
}

# ── 4. IPM SOAP (estandar_ejecutar_coleccion_influx.py) ───────────────────────
# measurement: status_check_IPM | field: status_code (200=ok, otro=error)
# tags: servicio, url
QUERIES_IPM = {

    "ipm_soap": """
        from(bucket: "{bucket}")
          {range}
          |> filter(fn: (r) => r._measurement == "status_check_IPM")
          |> filter(fn: (r) => r._field == "status_code")
          |> filter(fn: (r) => r._value != 200)
          |> keep(columns: ["_time","_value","servicio","url","estado_msg"])
    """,
}

# Mapa completo: zone_id → query
ALL_QUERIES = {
    **QUERIES_PUERTOS,
    **QUERIES_HTTP,
    **QUERIES_ORACLE,
    **QUERIES_IPM,
}


# ─────────────────────────────────────────────
# CONSULTA INFLUXDB
# ─────────────────────────────────────────────
def query_influx(window_start: datetime, window_stop: datetime) -> dict:
    """
    Ejecuta todas las queries dentro de [window_start, window_stop].
    Retorna dict { zone_id: [ {col: val, ...}, ... ] }
    """
    rng    = flux_range(window_start, window_stop)
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    api    = client.query_api()
    results = {}

    for zone, flux in ALL_QUERIES.items():
        filled = flux.replace("{bucket}", INFLUX_BUCKET).replace("{range}", rng)
        try:
            tables = api.query(filled)
            rows = []
            for table in tables:
                for rec in table.records:
                    # Construir fila con todos los valores disponibles
                    row = {
                        "time":  rec.get_time().strftime("%Y-%m-%d %H:%M:%S UTC")
                                 if rec.get_time() else "—",
                        "value": rec.get_value(),
                    }
                    # Agregar tags relevantes (excluir metadatos internos de Flux)
                    skip = {"_start","_stop","_time","_value","_field",
                            "_measurement","result","table"}
                    for k, v in rec.values.items():
                        if k not in skip and v is not None:
                            row[k] = str(v)
                    rows.append(row)
            results[zone] = rows
        except Exception as exc:
            results[zone] = [{"time": "—", "value": "—", "error": str(exc)}]

    client.close()
    return results


# ─────────────────────────────────────────────
# CONSTRUCCIÓN DEL HTML DEL CORREO
# ─────────────────────────────────────────────

# Metadatos de cada zona: (icono, label, nivel)
# nivel: "l1" = separador principal, "l2" = subsección, "l3" = sub-subsección
ZONE_META = {
    # Bloque Oracle
    "listener":         ("💾", "Listener Oracle – Puerto 1521",                    "l2"),
    "db_prod":          ("🗂️", "Bases de Datos Producción",                        "l3"),
    "db_test":          ("🗂️", "Bases de Datos TEST (Pruebas / Testing)",           "l3"),
    "db_dev":           ("🗂️", "Bases de Datos Desarrollo",                        "l3"),
    # Bloque Simon
    "simon_puertos":    ("💻", "Simon Web / Quotation – Puertos",                  "l2"),
    "simon_web_url":    ("💻", "Simon Web – URLs HTTP",                            "l2"),
    # Bloque Servicios Web
    "weblogic_puertos": ("🌐", "WebLogic – Puertos",                              "l2"),
    # Bloque IPM
    "ipm_puertos":      ("💻", "Servidores IPM – Puertos",                        "l2"),
    "ipm_soap":         ("🔄", "Colección SOAP – Operaciones IPM",                "l2"),
}

# Orden de secciones principales
SECTIONS = [
    {
        "icon": "💽", "title": "Infraestructura de Base de Datos Oracle",
        "sub":  "Monitoreo de conexión – Estado en tiempo real",
        "zones": [
            ("listener",  "💾", "Verificación de disponibilidad del Listener (Puerto 1521)"),
            ("db_prod",   "📡", "Disponibilidad Global – Producción"),
            ("db_test",   "📡", "Disponibilidad Global – TEST"),
            ("db_dev",    "📡", "Disponibilidad Global – Desarrollo"),
        ],
    },
    {
        "icon": "🖥️", "title": "Plataforma Digital SIMON",
        "sub":  "Estado de aplicaciones Simon Web y Simon Quotation",
        "zones": [
            ("simon_puertos", "💻", "Simon Web / Quotation – Puertos"),
            ("simon_web_url", "💻", "Simon Web – URLs HTTP"),
        ],
    },
    {
        "icon": "🌐", "title": "Servicios Web – Estado de Salud",
        "sub":  "Health check de endpoints y APIs",
        "zones": [
            ("weblogic_puertos", "🌐", "Plataforma WebLogic – Puertos"),
        ],
    },
    {
        "icon": "📊", "title": "IPM en Oracle – Intelligent Performance Management",
        "sub":  "Monitoreo de rendimiento y operaciones SOAP",
        "zones": [
            ("ipm_puertos", "💻", "Servidores IPM – Puertos"),
            ("ipm_soap",    "🔄", "Colección Estandarizada de Operaciones SOAP"),
        ],
    },
]


def _rows_to_html(rows: list) -> str:
    """Convierte lista de dicts en tabla HTML inline."""
    if not rows:
        return '<p style="color:#28A745;font-weight:700;margin:8px 0;">✅ Sin errores en esta ventana</p>'

    # Columnas: primero las conocidas, luego el resto
    priority = ["time", "nombre", "db_id", "servicio", "ip", "url",
                "ambiente", "instance", "tipo", "tipo_error", "value", "error"]
    all_keys = list(dict.fromkeys(
        [k for k in priority if any(k in r for r in rows)] +
        [k for r in rows for k in r if k not in priority]
    ))

    th = "".join(
        f'<th style="background:#038450;color:#fff;padding:7px 10px;'
        f'text-align:left;font-size:11px;white-space:nowrap;">{k.upper()}</th>'
        for k in all_keys
    )
    body = ""
    for i, r in enumerate(rows):
        bg = "#fff" if i % 2 == 0 else "#F5F5F5"
        tds = "".join(
            f'<td style="padding:6px 10px;border-bottom:1px solid #E1E1E1;'
            f'font-size:11px;max-width:280px;overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap;">{r.get(k,"—")}</td>'
            for k in all_keys
        )
        body += f'<tr style="background:{bg};">{tds}</tr>'

    return (
        f'<div style="overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;font-size:11px;">'
        f'<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'
    )


def build_email_html(data: dict, window_start: datetime,
                     window_stop: datetime) -> str:
    ts_fmt   = "%Y-%m-%d %H:%M UTC"
    ts_label = window_stop.strftime(ts_fmt)
    w_start  = window_start.strftime(ts_fmt)
    w_stop   = window_stop.strftime(ts_fmt)

    total_errors = sum(len(v) for v in data.values())
    sum_color    = "#DC3545" if total_errors > 0 else "#28A745"
    sum_icon     = "⚠️" if total_errors > 0 else "✅"
    sum_text     = (f"{total_errors} error(es) detectado(s)"
                    if total_errors > 0 else "Sin errores en esta ventana")

    # Construir secciones
    sections_html = ""
    for sec in SECTIONS:
        zones_html = ""
        for zone_id, z_icon, z_label in sec["zones"]:
            rows      = data.get(zone_id, [])
            count     = len(rows)
            dot_color = "#DC3545" if count > 0 else "#28A745"
            dot_label = f"{count} error(es)" if count > 0 else "OK"

            zones_html += f"""
            <div style="margin:10px 0 0;">
              <div style="background:#009056;border-left:4px solid #FFE16F;
                          padding:8px 16px;display:flex;align-items:center;gap:8px;">
                <span style="font-size:14px;">{z_icon}</span>
                <span style="font-size:12px;font-weight:700;color:#fff;
                             text-transform:uppercase;letter-spacing:.4px;flex:1;">{z_label}</span>
                <span style="background:{dot_color};color:#fff;border-radius:12px;
                             padding:2px 10px;font-size:11px;font-weight:700;
                             white-space:nowrap;">{dot_label}</span>
              </div>
              <div style="padding:12px 16px;background:#fff;
                          border-left:4px solid #E1E1E1;">
                {_rows_to_html(rows)}
              </div>
            </div>"""

        sections_html += f"""
        <div style="margin-top:20px;">
          <div style="background:#038450;border-left:6px solid #FFE16F;
                      padding:14px 20px;display:flex;align-items:center;gap:12px;">
            <div style="width:34px;height:34px;background:#FFE16F;border-radius:50%;
                        display:flex;align-items:center;justify-content:center;
                        font-size:16px;flex-shrink:0;">{sec["icon"]}</div>
            <div>
              <div style="font-size:14px;font-weight:700;color:#fff;
                          text-transform:uppercase;letter-spacing:.6px;">{sec["title"]}</div>
              <div style="font-size:11px;color:rgba(255,255,255,.75);margin-top:2px;">{sec["sub"]}</div>
            </div>
          </div>
          {zones_html}
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#FAFAFA;font-family:'Roboto',Arial,sans-serif;color:#1B1B1B;">
<div style="max-width:960px;margin:0 auto;padding-bottom:32px;">

  <!-- HEADER -->
  <div style="background:#038450;border-left:6px solid #FFE16F;
              padding:18px 24px;display:flex;align-items:center;
              justify-content:space-between;">
    <div>
      <div style="display:flex;align-items:center;gap:12px;">
        <div style="width:42px;height:42px;background:#FFE16F;border-radius:50%;
                    display:flex;align-items:center;justify-content:center;font-size:20px;">🛡️</div>
        <span style="font-size:22px;font-weight:700;color:#fff;
                     text-transform:uppercase;letter-spacing:1px;">Centro de Operaciones</span>
      </div>
      <p style="font-size:12px;font-weight:700;color:#FFE16F;margin:6px 0 2px 54px;">
        Seguros Bolívar – Monitoreo en Tiempo Real</p>
      <p style="font-size:11px;color:rgba(255,255,255,.8);margin:0 0 0 54px;">
        Actualizado: {ts_label}</p>
    </div>
    <div style="background:#fff;border-radius:8px;padding:8px 14px;
                font-size:28px;box-shadow:0 2px 8px rgba(0,0,0,.15);">🦁</div>
  </div>

  <!-- RESUMEN DE VENTANA -->
  <div style="background:#fff;padding:14px 24px;margin-top:12px;
              border-left:4px solid {sum_color};
              box-shadow:2px 2px 16px rgba(115,115,115,.1);">
    <div style="font-size:14px;font-weight:700;color:{sum_color};">
      {sum_icon} {sum_text}
    </div>
    <div style="font-size:11px;color:#757575;margin-top:4px;">
      Ventana analizada: <strong>{w_start}</strong> → <strong>{w_stop}</strong>
      &nbsp;|&nbsp; Bucket: <strong>{INFLUX_BUCKET}</strong>
    </div>
  </div>

  <!-- SECCIONES -->
  {sections_html}

  <!-- FOOTER -->
  <div style="margin-top:28px;padding:12px 24px;background:#038450;
              text-align:center;color:rgba(255,255,255,.7);font-size:11px;">
    Seguros Bolívar · Centro de Operaciones · {ts_label}
    &nbsp;|&nbsp; Generado automáticamente desde InfluxDB
  </div>

</div>
</body>
</html>"""


# ─────────────────────────────────────────────
# ENVÍO DE CORREO POR GMAIL
# ─────────────────────────────────────────────
def send_email(html_body: str, total_errors: int,
               window_start: datetime, window_stop: datetime):
    fmt      = "%Y-%m-%d %H:%M UTC"
    w_label  = f"{window_start.strftime(fmt)} → {window_stop.strftime(fmt)}"
    icon     = "⚠️" if total_errors > 0 else "✅"
    subject  = (
        f"{icon} [{window_stop.strftime('%Y-%m-%d %H:%M')}] "
        f"Centro de Operaciones – {total_errors} error(es) | {w_label}"
        if total_errors > 0
        else f"{icon} [{window_stop.strftime('%Y-%m-%d %H:%M')}] "
             f"Centro de Operaciones – Sin errores | {w_label}"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = EMAIL_TO
    if EMAIL_CC:
        msg["Cc"] = EMAIL_CC

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    recipients = [EMAIL_TO]
    if EMAIL_CC:
        recipients += [e.strip() for e in EMAIL_CC.split(",") if e.strip()]

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as srv:
        srv.login(GMAIL_USER, GMAIL_PASS)
        srv.sendmail(GMAIL_USER, recipients, msg.as_string())

    print(f"   ✅ Correo enviado → {recipients}")


# ─────────────────────────────────────────────
# ESPERA AL PRÓXIMO CICLO EXACTO
# ─────────────────────────────────────────────
def wait_until_next_cycle():
    """
    Bloquea hasta el próximo múltiplo exacto de WINDOW_MINUTES.
    Si ya estamos dentro de los primeros 3 segundos del ciclo, no espera.
    """
    now              = datetime.now(timezone.utc)
    seconds_in_cycle = (now.minute % WINDOW_MINUTES) * 60 + now.second
    if seconds_in_cycle <= 3:
        return
    wait_secs = WINDOW_MINUTES * 60 - seconds_in_cycle
    next_tick = now + timedelta(seconds=wait_secs)
    print(f"   ⏳ Próximo ciclo en {wait_secs}s "
          f"({next_tick.strftime('%H:%M:%S UTC')})")
    time.sleep(wait_secs)


# ─────────────────────────────────────────────
# CICLO ÚNICO DE EJECUCIÓN
# ─────────────────────────────────────────────
def run_cycle():
    # 1. Calcular ventana ANTES de cualquier otra operación
    window_start, window_stop = get_window()
    fmt = "%Y-%m-%d %H:%M:%S UTC"

    print("─" * 64)
    print(f"🕐 Ejecución  : {window_stop.strftime(fmt)}")
    print(f"📅 Ventana    : {window_start.strftime(fmt)}  →  {window_stop.strftime(fmt)}")
    print(f"🔍 InfluxDB   : {INFLUX_URL}  bucket={INFLUX_BUCKET}")

    # 2. Consultar InfluxDB
    data = query_influx(window_start, window_stop)

    # Resumen por zona
    for zone, rows in data.items():
        estado = f"❌ {len(rows)} error(es)" if rows else "✅ OK"
        print(f"   {zone:<22} {estado}")

    total_errors = sum(len(v) for v in data.values())
    print(f"   {'─'*40}")
    print(f"   Total errores: {total_errors}")

    # 3. Generar HTML y enviar
    if total_errors > 0 or SEND_ALWAYS:
        html = build_email_html(data, window_start, window_stop)

        # Guardar copia local para auditoría/debug
        report_name = f"reporte_{window_start.strftime('%Y%m%d_%H%M')}.html"
        report_path = os.path.join(BASE_DIR, "logs", report_name)
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"   💾 HTML guardado → {report_path}")

        send_email(html, total_errors, window_start, window_stop)
    else:
        print("   → Sin errores. Correo no enviado (SEND_ALWAYS=false).")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    """
    MODO CRON (por defecto):
      El cron dispara el script cada */15 min, calcula la ventana y termina.
      Cron: */15 * * * * python3 /ruta/influxdb_alert_mailer.py

    MODO DAEMON (RUN_AS_DAEMON=true en variables.txt):
      El script corre indefinidamente, espera al ciclo exacto y repite.
      Útil si no tienes acceso a cron.
    """
    if RUN_AS_DAEMON:
        print(f"🔄 Modo DAEMON — ciclos cada {WINDOW_MINUTES} minutos")
        while True:
            wait_until_next_cycle()
            run_cycle()
            time.sleep(5)   # pequeña pausa para no re-disparar en el mismo segundo
    else:
        run_cycle()


if __name__ == "__main__":
    main()
