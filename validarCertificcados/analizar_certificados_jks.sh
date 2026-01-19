#!/bin/bash

# ==================================================
# CONFIGURACIÓN
# ==================================================
KEYSTORE="/oracle/app/wlogic12c/certificados/identity/identity.jks"
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
    print "NOMBRE_CERT | ENTRY_TYPE | CERT | DIAS | ESTADO"
    print "--------------------------------------------------------------------------"
}

# Alias técnico del JKS
/Alias name:/ {
    alias_jks=$3
    cn=""
}

# Tipo de entrada
/Entry type:/ {
    tipo=$3
}

# Número de certificado dentro de la cadena
/Certificate\[/ {
    cert=$0
    gsub(":","",cert)
}

# Owner (Subject) del certificado
/Owner:/ {
    owner=$0
    sub(/^Owner: /,"",owner)

    # Extraer CN
    if (match(owner,/CN=[^,]+/))
        cn=substr(owner,RSTART,RLENGTH)
}

# Fecha de vencimiento
/until:/ {
    fecha_raw=$0
    sub(/^.*until: /,"",fecha_raw)

    # Quitar zona horaria textual (COT, GMT, etc.)
    gsub(/[A-Z]{3,4}/, "", fecha_raw)

    # Convertir a epoch
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

    nombre = (cn != "" ? cn : alias_jks)

    printf "%s%s%s%s%s%s%d%s[%s]\n",
        nombre,OFS,
        tipo,OFS,
        cert,OFS,
        dias,OFS,
        estado
}
'

echo
echo "[INFO] Análisis finalizado correctamente."
