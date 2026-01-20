#!/bin/bash

# ==================================================
# CONFIGURACIÓN
# ==================================================
KEYSTORE="identity.jks"
STOREPASS="identity"

DIAS_ALERTA=30
DIAS_CRITICO=7

echo "[INFO] ====================================="
echo "[INFO] Inicio análisis de certificados JKS"
echo "[INFO] Keystore : $KEYSTORE"
echo "[INFO] Fecha    : $(date '+%Y-%m-%d %H:%M:%S')"
echo "[INFO] ====================================="
echo

# ==================================================
# FECHA ACTUAL UTC
# ==================================================
HOY_EPOCH=$(date -u +%s)

# ==================================================
# EJECUCIÓN KEYTOOL + AWK
# ==================================================
keytool -list -v -keystore "$KEYSTORE" -storepass "$STOREPASS" 2>/dev/null |
awk -v HOY="$HOY_EPOCH" -v ALERTA="$DIAS_ALERTA" -v CRITICO="$DIAS_CRITICO" '

BEGIN {
    OFS=" | "
    print "NOMBRE_CERT | ENTRY_NAME | ENTRY_TYPE | CERT | VALID_UNTIL | DIAS | ESTADO"
    print "---------------------------------------------------------------------------------------------"
}

# Alias interno del JKS
/Alias name:/ {
    entry_name=$3
    cn=""
    cert=""
}

# Tipo de entrada
/Entry type:/ {
    tipo=$3
}

# Número de certificado
/Certificate\[/ {
    cert=$0
    gsub(":","",cert)
}

# Subject / Owner
/Owner:/ {
    owner=$0
    sub(/^Owner: /,"",owner)

    if (match(owner,/CN=[^,]+/))
        cn=substr(owner,RSTART,RLENGTH)
}

# Fecha de vencimiento
/until:/ {
    fecha_raw=$0
    sub(/^.*until: /,"",fecha_raw)

    # Limpiar zona horaria textual
    gsub(/[A-Z]{3,4}/, "", fecha_raw)

    # Epoch
    cmd="date -d \"" fecha_raw "\" +%s 2>/dev/null"
    cmd | getline vence
    close(cmd)

    if (vence == "" || vence == 0)
        next

    dias=int((vence - HOY) / 86400)

    if (dias < 0)
        estado="VENCIDO"
    else if (dias <= CRITICO)
        estado="CRÍTICO"
    else if (dias <= ALERTA)
        estado="POR VENCER"
    else
        estado="VIGENTE"

    # Fecha UTC formateada
    cmd2="date -u -d @" vence " \"+%Y-%m-%d %H:%M:%S UTC\""
    cmd2 | getline valid_until
    close(cmd2)

    if (cert == "")
        cert="Certificate[1]"

    nombre = (cn != "" ? cn : entry_name)

    printf "%s%s%s%s%s%s%s%s%s%s%d%s[%s]\n",
        nombre,OFS,
        entry_name,OFS,
        tipo,OFS,
        cert,OFS,
        valid_until,OFS,
        dias,OFS,
        estado
}
'

echo
echo "[INFO] Análisis finalizado correctamente."
