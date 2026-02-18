#!/usr/bin/env python3
import subprocess
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import socket

# =========================
# CONFIGURACIÓN
# =========================
CSV_URLS = sys.argv[1] if len(sys.argv) > 1 else "listado_urls_completo.csv"
TIMEOUT_CONEXION = 10
TIMEOUT_TOTAL = 45
VERBOSE_CURL = True  # Cambiar a False para menos detalles

INFLUX_BUCKET_NAME = "status_services"
INFLUX_MEASUREMENT = "status_check_http"

# =========================
# ANÁLISIS INTELIGENTE DE ERRORES
# =========================
def analizar_error(verbose_output, http_code, url):
    """
    Analiza el error y retorna diagnóstico estructurado
    Similar a tu tabla de diagnóstico
    """
    url_parts = urlparse(url)
    hostname = url_parts.hostname
    port = url_parts.port or (443 if url_parts.scheme == 'https' else 80)

    # Extraer IP si es una IP directa
    ip = None
    try:
        if hostname and all(c.isdigit() or c == '.' for c in hostname if c != '.'):
            ip = hostname
        elif hostname:
            # Intentar resolver (solo si no es ya una IP)
            ip = socket.gethostbyname(hostname)
    except:
        ip = None

    error_data = {
        "tipo_error": "DESCONOCIDO",
        "error_principal": f"Código HTTP {http_code}",
        "significado": "Error no identificado",
        "causa_probable": "Problema de red o configuración",
        "accion_recomendada": "Revisar logs detallados"
    }

    verbose_lower = verbose_output.lower()

    # 1. ERRORES DE DNS
    if "could not resolve host" in verbose_lower or "name or service not known" in verbose_lower:
        error_data.update({
            "tipo_error": "DNS",
            "error_principal": f"Could not resolve host: {hostname}",
            "significado": "El servidor no puede traducir el nombre a una IP (DNS falla)",
            "causa_probable": "Problema de DNS (no resuelve nombres externos o internos)",
            "accion_recomendada": f"Verifica DNS con: nslookup {hostname} o ping {hostname}"
        })

    # 2. CONNECTION REFUSED
    elif "connection refused" in verbose_lower:
        error_data.update({
            "tipo_error": "SERVIDOR",
            "error_principal": f"Connection refused (puerto {port})",
            "significado": f"La máquina llega a la IP, pero nadie está escuchando en el puerto {port}",
            "causa_probable": "El servicio no está corriendo o firewall bloquea el puerto",
            "accion_recomendada": f"En el servidor: netstat -tuln | grep :{port} o systemctl status del servicio"
        })

    # 3. CONNECTION TIMEOUT
    elif "connection timed out" in verbose_lower or "operation timed out" in verbose_lower:
        error_data.update({
            "tipo_error": "RED",
            "error_principal": "Connection timed out",
            "significado": "El tiempo de conexión expiró (no responde)",
            "causa_probable": "Firewall bloqueando, servidor caído o problemas de ruta",
            "accion_recomendada": f"Verifica conectividad: ping {hostname or ip or 'el_servidor'} y telnet {hostname or ip} {port}"
        })

    # 4. EMPTY REPLY
    elif "empty reply from server" in verbose_lower:
        error_data.update({
            "tipo_error": "APLICACION",
            "error_principal": "Empty reply from server",
            "significado": "Se conecta al puerto, envía petición, pero servidor no responde",
            "causa_probable": "Servicio corriendo pero: 1) No entiende HTTP 2) Está colgado 3) Config errónea",
            "accion_recomendada": f"Prueba: telnet {hostname or ip} {port} → GET / HTTP/1.0 + Enter x2"
        })

    # 5. SSL ERRORS
    elif "ssl" in verbose_lower or "certificate" in verbose_lower or "tls" in verbose_lower:
        error_data.update({
            "tipo_error": "SSL",
            "error_principal": "Error de certificado SSL/TLS",
            "significado": "Problema con el certificado o configuración SSL",
            "causa_probable": "Certificado expirado, autofirmado o no confiable",
            "accion_recomendada": "Usar -k para pruebas internas o verificar certificado con openssl s_client"
        })

    # 6. PROXY ERRORS
    elif "proxy" in verbose_lower:
        error_data.update({
            "tipo_error": "PROXY",
            "error_principal": "Error de proxy",
            "significado": "Fallo en la conexión a través del proxy",
            "causa_probable": "Configuración incorrecta de proxy o proxy caído",
            "accion_recomendada": "Verificar variables HTTP_PROXY, HTTPS_PROXY, NO_PROXY"
        })

    # 7. HTTP 4xx ERRORS
    elif str(http_code).startswith('4'):
        error_data.update({
            "tipo_error": "CLIENTE_HTTP",
            "error_principal": f"Error HTTP {http_code}",
            "significado": "Error del cliente (página no encontrada, acceso denegado)",
            "causa_probable": "URL incorrecta, falta autenticación o permisos insuficientes",
            "accion_recomendada": "Verificar URL completa y credenciales si son necesarias"
        })

    # 8. HTTP 5xx ERRORS
    elif str(http_code).startswith('5'):
        error_data.update({
            "tipo_error": "SERVER_HTTP",
            "error_principal": f"Error HTTP {http_code}",
            "significado": "Error interno del servidor",
            "causa_probable": "Problema en la aplicación o servidor web backend",
            "accion_recomendada": "Revisar logs del servidor y estado de la aplicación"
        })

    # 9. NO RESPONSE (000)
    elif http_code == "000" or http_code == 0:
        error_data.update({
            "tipo_error": "SIN_CONEXION",
            "error_principal": "Sin respuesta (000)",
            "significado": "No se pudo establecer conexión alguna",
            "causa_probable": "Servidor caído, firewall bloqueando completamente o ruta incorrecta",
            "accion_recomendada": f"Verificar si el servidor {hostname or ip} está activo y accesible desde la red"
        })

    # 10. SUCCESS
    elif str(http_code).startswith('2') or str(http_code).startswith('3'):
        error_data.update({
            "tipo_error": "OK",
            "error_principal": f"Código HTTP {http_code}",
            "significado": "Conexión exitosa",
            "causa_probable": "Servicio funcionando correctamente",
            "accion_recomendada": "Ninguna acción requerida"
        })

    return error_data

# =========================
# FUNCIÓN MEJORADA DE CHECK URL
# =========================
def check_url_detallado(url):
    """
    Versión mejorada que captura verbose output para análisis
    """
    try:
        start_time = time.time()

        # Comando curl con verbose para diagnóstico
        comando = (
            f"curl -k -L -s -o /dev/null -w '%{{http_code}}' "
            f"--connect-timeout {TIMEOUT_CONEXION} "
            f"-m {TIMEOUT_TOTAL} "
            f"-v '{url}' 2>&1"
        )

        output = subprocess.check_output(comando, shell=True, timeout=TIMEOUT_TOTAL+5).decode('utf-8')

        # Extraer código HTTP (última línea)
        lines = output.strip().split('\n')
        http_code = lines[-1] if lines else "000"

        # Tiempo de respuesta
        elapsed_ms = int((time.time() - start_time) * 1000)

        # Extraer verbose output (todo menos última línea)
        verbose_output = '\n'.join(lines[:-1]) if len(lines) > 1 else output

        return {
            "http_code": http_code,
            "verbose_output": verbose_output,
            "tiempo_ms": elapsed_ms,
            "exito": http_code == "200"  # O podrías considerar 2xx como éxito
        }

    except subprocess.TimeoutExpired:
        return {
            "http_code": "000",
            "verbose_output": "curl: (28) Operation timed out",
            "tiempo_ms": TIMEOUT_TOTAL * 1000,
            "exito": False
        }
    except subprocess.CalledProcessError as e:
        return {
            "http_code": "000",
            "verbose_output": str(e.output.decode('utf-8') if e.output else str(e)),
            "tiempo_ms": 0,
            "exito": False
        }
    except Exception as e:
        return {
            "http_code": "000",
            "verbose_output": f"Error inesperado: {str(e)}",
            "tiempo_ms": 0,
            "exito": False
        }

# =========================
# GUARDAR LOGS EN MÚLTIPLES FORMATOS
# =========================
def guardar_logs_completos(results, log_dir):
    """Guarda logs en JSON, CSV y TXT (tabla)"""
    now = datetime.now(ZoneInfo("America/Bogota"))
    timestamp_str = now.strftime("%Y-%m-%d_%H-%M-%S")

    # 1. JSON DETALLADO (histórico completo)
    json_file = f"{log_dir}/urls_check_detailed_{timestamp_str}.json"
    json_data = {
        "check_timestamp_local": now.isoformat(),
        "check_timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "total_urls": len(results),
        "summary": {
            "up": sum(1 for r in results if r.get("status") == "up"),
            "down": sum(1 for r in results if r.get("status") == "down"),
            "up_percentage": round(sum(1 for r in results if r.get("status") == "up") / max(len(results), 1) * 100, 2)
        },
        "config": {
            "timeout_conexion": TIMEOUT_CONEXION,
            "timeout_total": TIMEOUT_TOTAL
        },
        "services": results
    }

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    # 2. CSV RESUMEN (para Excel/analytics)
    csv_file = f"{log_dir}/urls_check_summary_{timestamp_str}.csv"
    with open(csv_file, "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            'nombre', 'url', 'status', 'http_code', 'tiempo_ms',
            'tipo_error', 'error_principal', 'causa_probable', 'timestamp'
        ])
        writer.writeheader()
        for r in results:
            writer.writerow({
                'nombre': r.get('nombre', ''),
                'url': r.get('url', ''),
                'status': r.get('status', ''),
                'http_code': r.get('status_code', 0),
                'tiempo_ms': r.get('tiempo_ms', 0),
                'tipo_error': r.get('tipo_error', ''),
                'error_principal': r.get('error_principal', '')[:100],  # Truncar si es muy largo
                'causa_probable': r.get('causa_probable', ''),
                'timestamp': r.get('timestamp', '')
            })

    # 3. TXT FORMATEADO (tabla legible para humanos)
    txt_file = f"{log_dir}/urls_check_table_{timestamp_str}.txt"
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write("=" * 100 + "\n")
        f.write(f"DIAGNÓSTICO DE URLs - {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 100 + "\n\n")

        f.write(f"{'Nombre':<30} {'URL':<40} {'Estado':<8} {'Código':<6} {'Error'}\n")
        f.write("-" * 100 + "\n")

        for r in results:
            nombre = r.get('nombre', '')[:28]
            url = r.get('url', '')[:38]
            status = r.get('status', '')
            codigo = r.get('status_code', 0)
            error = r.get('error_principal', '')[:40]

            f.write(f"{nombre:<30} {url:<40} {status:<8} {codigo:<6} {error}\n")

        f.write("\n" + "=" * 100 + "\n")
        f.write("TABLA DE DIAGNÓSTICO DETALLADO\n")
        f.write("=" * 100 + "\n\n")

        for idx, r in enumerate(results, 1):
            f.write(f"[{idx}] {r.get('nombre', '')}\n")
            f.write(f"    URL: {r.get('url', '')}\n")
            f.write(f"    Estado: {r.get('status', '')} (HTTP {r.get('status_code', 0)})\n")
            f.write(f"    Tiempo: {r.get('tiempo_ms', 0)}ms\n")
            f.write(f"    Error: {r.get('error_principal', '')}\n")
            f.write(f"    Significado: {r.get('significado', '')}\n")
            f.write(f"    Causa probable: {r.get('causa_probable', '')}\n")
            f.write(f"    Acción recomendada: {r.get('accion_recomendada', '')}\n")
            if r.get('verbose_output') and VERBOSE_CURL:
                f.write(f"    Verbose (resumen):\n")
                for line in r.get('verbose_output', '').split('\n')[-5:]:  # Últimas 5 líneas
                    if line.strip():
                        f.write(f"      {line[:80]}\n")
            f.write("-" * 80 + "\n")

    return json_file, csv_file, txt_file

# =========================
# EJECUCIÓN PRINCIPAL MEJORADA
# =========================
def main():
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Diagnóstico avanzado de URLs")
    print("=" * 80)
    print(f"CSV: {CSV_URLS} | Timeout: {TIMEOUT_TOTAL}s | Verbose: {VERBOSE_CURL}")
    print("=" * 80)

    if not os.path.exists(CSV_URLS):
        print(f"❌ ERROR: No se encuentra el archivo '{CSV_URLS}'")
        print(f"Uso: {sys.argv[0]} [ruta_al_csv]")
        sys.exit(1)

    results = []
    up = total = 0

    # Prueba de conectividad básica
    print("\n🔍 Pruebas básicas de conectividad:")
    try:
        # Ping a Google DNS
        subprocess.run(['ping', '-c', '2', '8.8.8.8'],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        print("  ✓ Ping a 8.8.8.8 OK")
    except:
        print("  ⚠️  No responde 8.8.8.8 (posible problema de salida a internet)")

    try:
        socket.gethostbyname('google.com')
        print("  ✓ DNS funciona (resuelve google.com)")
    except socket.gaierror:
        print("  ⚠️  Problemas de DNS (no resuelve nombres externos)")

    print("\n" + "=" * 80)
    print("📋 PRUEBAS POR URL")
    print("=" * 80)

    # Leer y procesar CSV
    with open(CSV_URLS, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")

        for row_idx, row in enumerate(reader, 1):
            nombre = row.get('Nombre', f'URL_{row_idx}').strip()
            url = row.get('URL', '').strip()

            if not url:
                print(f"⚠️  Línea {row_idx}: URL vacía, saltando...")
                continue

            total += 1

            print(f"\n[{row_idx}] {nombre}")
            print(f"    URL: {url}")

            # Verificación mejorada
            resultado = check_url_detallado(url)
            http_code = resultado["http_code"]
            verbose_output = resultado["verbose_output"]
            tiempo_ms = resultado["tiempo_ms"]

            # Análisis inteligente del error
            diagnostico = analizar_error(verbose_output, http_code, url)

            # Determinar estado
            is_up = (http_code == "200")  # O podrías usar 2xx
            status_text = "up" if is_up else "down"

            if is_up:
                up += 1
                print(f"    ✅ OK (HTTP {http_code}, {tiempo_ms}ms)")
            else:
                print(f"    ❌ FALLÓ (HTTP {http_code}, {tiempo_ms}ms)")
                print(f"    🔍 Error: {diagnostico['error_principal']}")
                if VERBOSE_CURL and diagnostico['tipo_error'] != 'OK':
                    # Mostrar líneas relevantes del verbose
                    for line in verbose_output.split('\n'):
                        if any(keyword in line.lower() for keyword in
                              ['curl:', '*', 'failed', 'error', 'timeout', 'refused']):
                            print(f"      {line[:100]}")

            # Preparar resultado completo
            resultado_completo = {
                "tipo": "url_http",
                "nombre": nombre,
                "url": url,
                "ip": url,  # Mantener compatibilidad con tu script original
                "puerto": 443 if url.startswith("https://") else 80,
                "status": status_text,
                "status_code": int(http_code) if http_code.isdigit() else 0,
                "tiempo_ms": tiempo_ms,
                "timestamp": datetime.now(ZoneInfo("America/Bogota")).isoformat(),
                "verbose_output": verbose_output if VERBOSE_CURL else "",
                **diagnostico  # Incluir todo el diagnóstico
            }

            results.append(resultado_completo)

    # =========================
    # GUARDAR LOGS COMPLETOS
    # =========================
    if total > 0:
        now = datetime.now(ZoneInfo("America/Bogota"))
        folder = now.strftime("logs/%Y-%m-%d")
        os.makedirs(folder, exist_ok=True)

        print("\n" + "=" * 80)
        print("💾 GUARDANDO RESULTADOS")
        print("=" * 80)

        json_file, csv_file, txt_file = guardar_logs_completos(results, folder)

        print(f"  📄 JSON detallado: {json_file}")
        print(f"  📊 CSV resumen:    {csv_file}")
        print(f"  📝 Tabla legible:  {txt_file}")

        # Mostrar vista previa de la tabla
        print("\n📋 RESUMEN RÁPIDO:")
        print("-" * 80)
        print(f"{'Nombre':<25} {'Estado':<8} {'Código':<6} {'Error principal'}")
        print("-" * 80)
        for r in results[:10]:  # Mostrar primeras 10
            nombre = r['nombre'][:22] + "..." if len(r['nombre']) > 25 else r['nombre']
            estado = "✅ UP" if r['status'] == "up" else "❌ DOWN"
            print(f"{nombre:<25} {estado:<8} {r['status_code']:<6} {r['error_principal'][:30]}")

        if len(results) > 10:
            print(f"... y {len(results)-10} más")

    # =========================
    # SUBIDA A INFLUXDB (MANTENIENDO TU CÓDIGO)
    # =========================
    try:
        from influxdb_client import InfluxDBClient, Point, WritePrecision
        from influxdb_client.client.write_api import SYNCHRONOUS

        print("\n" + "=" * 80)
        print("📤 SUBIENDO A INFLUXDB")
        print("=" * 80)

        # Leer credenciales
        creds = {}
        with open("variables.txt", "r", encoding="utf-8") as vf:
            for line in vf:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    creds[k.strip()] = v.strip()

        url_inf = creds.get("INFLUX_URL")
        token = creds.get("INFLUX_TOKEN")
        org = creds.get("INFLUX_ORG")

        if not url_inf or not token or not org:
            raise Exception("Credenciales incompletas en variables.txt")

        client = InfluxDBClient(url=url_inf, token=token, org=org)
        write_api = client.write_api(write_options=SYNCHRONOUS)

        print(f"Conectado a InfluxDB: {url_inf}")
        print(f"Subiendo {len(results)} registros...")

        for srv in results:
            point = (
                Point(INFLUX_MEASUREMENT)
                .tag("tipo", srv["tipo"])
                .tag("nombre", srv["nombre"])
                .tag("url", srv["url"])  # Agregamos tag URL
                .tag("tipo_error", srv.get("tipo_error", "DESCONOCIDO"))  # Nuevo tag
                .field("puerto", srv["puerto"])
                .field("status", 1 if srv["status"] == "up" else 0)
                .field("http_code", srv["status_code"])
                .field("tiempo_respuesta", srv.get("tiempo_ms", 0))  # Nuevo campo
                .field("error_tipo", srv.get("tipo_error", ""))  # Nuevo campo
                .field("error_detalle", srv.get("error_principal", "")[:200])  # Campo de error
                .time(datetime.utcnow(), WritePrecision.S)
            )
            write_api.write(bucket=INFLUX_BUCKET_NAME, org=org, record=point)

        write_api.close()
        client.close()
        print(f"✅ Subidos {len(results)} registros a InfluxDB")

    except ImportError:
        print("⚠️  influxdb-client no instalado → pip3 install influxdb-client")
    except FileNotFoundError:
        print("⚠️  variables.txt no encontrado")
    except Exception as e:
        print(f"❌ Error InfluxDB: {e}")

    # =========================
    # RESUMEN FINAL
    # =========================
    print("\n" + "=" * 80)
    print("🎯 RESUMEN FINAL")
    print("=" * 80)

    if total > 0:
        porcentaje = (up / total) * 100 if total > 0 else 0

        # Estadísticas por tipo de error
        errores_por_tipo = {}
        for r in results:
            tipo = r.get('tipo_error', 'DESCONOCIDO')
            errores_por_tipo[tipo] = errores_por_tipo.get(tipo, 0) + 1

        print(f"📊 URLs procesadas: {total}")
        print(f"✅ URLs OK:         {up} ({porcentaje:.1f}%)")
        print(f"❌ URLs con error:  {total - up}")

        if errores_por_tipo:
            print("\n🔍 Distribución de errores:")
            for tipo, cantidad in sorted(errores_por_tipo.items()):
                if tipo != "OK":
                    print(f"   {tipo}: {cantidad}")

        print(f"\n💡 Consejo: Revisa {txt_file} para la tabla completa de diagnóstico")

    else:
        print("No se procesaron URLs.")

    print("=" * 80)

if __name__ == "__main__":
    main()
