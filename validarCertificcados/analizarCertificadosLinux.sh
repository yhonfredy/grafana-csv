#!/bin/bash

# ==============================
# CONFIGURACIÓN
# ==============================
KEYSTORE="/oracle/app/wlogic12c/certificados/identity/identity.jks"
STOREPASS="identity"

DIAS_ALERTA=30
DIAS_CRITICO=7

echo "[INFO] ====================================="
echo "[INFO] Inicio análisis de certificados"
echo "[INFO] Keystore : $KEYSTORE"
echo "[INFO] Fecha    : $(date '+%Y-%m-%d %H:%M:%S')"
echo "[INFO] ====================================="
echo

# ==============================
# FECHA ACTUAL EN EPOCH (UTC)
# ==============================
HOY_EPOCH=$(date -u +%s)
echo "[DEBUG] HOY_EPOCH (UTC) = $HOY_EPOCH"
echo

# ==============================
# EJECUCIÓN KEYTOOL
# ==============================
keytool -list -v -keystore "$KEYSTORE" -storepass "$STOREPASS" 2>/dev/null |
awk '
BEGIN {
    print "[AWK] Procesando salida de keytool..." > "/dev/stderr"
}

/Alias name:/ {
    alias=$3
}

/Entry type:/ {
    tipo=$3
}

/until:/ {
    fecha_raw=$0
    sub(/^.*until: /,"",fecha_raw)

    # Eliminar zona horaria (COT, GMT, etc.)
    fecha_limpia=fecha_raw
    gsub(/[A-Z]{3,4}/, "", fecha_limpia)

    # Convertir a epoch
    cmd = "date -d \"" fecha_limpia "\" +%s 2>/dev/null"
    cmd | getline vence_epoch
    close(cmd)

    if (vence_epoch == "" || vence_epoch == 0)
        next

    # Calcular días restantes
    dias = int((vence_epoch - '"$HOY_EPOCH"') / 86400)

    if (dias < 0)
        estado="VENCIDO"
    else if (dias <= '"$DIAS_CRITICO"')
        estado="CRÍTICO"
    else if (dias <= '"$DIAS_ALERTA"')
        estado="POR VENCER"
    else
        estado="VIGENTE"

    # Fecha en formato YYYY-MM-DD (UTC)
    cmd2 = "date -u -d @" vence_epoch " \"+%Y-%m-%d\""
    cmd2 | getline fecha_fmt
    close(cmd2)

    printf "%s; %s; %d días; [%s]\n", alias, fecha_fmt, dias, estado
}

END {
    print "[AWK] Fin del procesamiento." > "/dev/stderr"
}'
echo
echo "[INFO] Análisis finalizado correctamente."
