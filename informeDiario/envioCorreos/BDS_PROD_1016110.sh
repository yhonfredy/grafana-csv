USUARIO=""
CONTRASENA="*"

MAQUINA=$1
IP_SERVIDOR=$2

BDS_PROD="catalog19c \
dbnam1 \
dbnam2"

export BDS_PROD;

if [[ "${MAQUINA}" == "${IP_SERVIDOR}" ]]
	then	
	AZUL=`echo "$(echo '"text-decoration: underline;color: #0000ff;"')"`
	echo "<p>================================================================<br />Estatus de Base de Datos en el servidor <span style=${AZUL}>[${MAQUINA}]</span><br />================================================================</p>"
	echo

	echo "<p>"
	echo "<table border='1' width='90%' align='center' summary='Script output'>"
	echo "<tr>"
	echo '	<th scope="col">INSTANCE_NAME</th>'
	echo '	<th scope="col">HOST_NAME</th>'
	echo '	<th scope="col">STATUS</th>'
	echo '	<th scope="col">DATABASE_STATUS</th>'
	echo '	<th scope="col">INSTANCE_ROLE</th>'
	echo '	<th scope="col">LOGINS</th>'
	echo '	<th scope="col">VERSION</th>'
	echo '	<th scope="col">STARTUP_TIME</th>'
	echo '	<th scope="col">DISPONIBILIDAD</th>'
	echo "</tr>"
	
	for bds in ${BDS_PROD}
	do	
		
		PRDBNAME_RAW="$(${ORACLE_HOME}/bin/sqlplus ${USUARIO}/${CONTRASENA}@${MAQUINA}:1521/${bds} << _eof
--PROMPT Conectado a:
exit
_eof
)"

		if [[ "${PRDBNAME_RAW}" == *"Conectado a:"* ]] || [[ "${PRDBNAME_RAW}" == *"Connected to:"* ]]
			then
				${ORACLE_HOME}/bin/sqlplus -S ${USUARIO}/${CONTRASENA}@${MAQUINA}:1521/${bds} << _eof
				SET LINESIZE 200
				SET PAGES 0
				SET FEEDBACK OFF 					
				SET ECHO OFF
				SELECT '<tr><td>'||INSTANCE_NAME||'</td>',
					   '<td>'||HOST_NAME||'</td>',
					   CASE
						WHEN STATUS NOT LIKE 'OPEN'
							THEN
								'<td><em id="parr">'||STATUS||'</em></td>'
						WHEN STATUS LIKE 'OPEN'
							THEN
								'<td><em><span style="color:#228B22;background:#f7f7e7;font: bold 10pt Arial;">'||STATUS||'</span></em></td>'
						END AS "STATUS",
					   CASE
						WHEN DATABASE_STATUS NOT LIKE 'ACTIVE'
							THEN
								'<td><em id="parr">'||STATUS||'</em></td>'
						WHEN DATABASE_STATUS LIKE 'ACTIVE'
							THEN
								'<td><em><span style="color:#228B22;background:#f7f7e7;font: bold 10pt Arial;">'||DATABASE_STATUS||'</span></em></td>'
						END AS "DATABASE_STATUS",
					   '<td>'||INSTANCE_ROLE||'</td>',
					   CASE
						WHEN LOGINS NOT LIKE 'ALLOWED'
							THEN
								'<td><em><span style="color:#FFD700;background:#f7f7e7;font: bold 10pt Arial;">'||LOGINS||'</em></td>'
						WHEN LOGINS LIKE 'ALLOWED'
							THEN
								'<td><em><span style="color:#228B22;background:#f7f7e7;font: bold 10pt Arial;">'||LOGINS||'</span></em></td>'
						END AS "LOGINS",
					   '<td><em><span style="color:#483D8B;background:#f7f7e7;font: bold 10pt Arial;">'||VERSION||'</span></em></td>' as "VERSION",
					   '<td>'||TO_CHAR (STARTUP_TIME, 'DD-MON-YYYY HH24:MI:SS AM')||'</td>' AS "STARTUP_TIME",
					'<td>'||TRUNC(TO_DATE(TO_CHAR(SYSDATE, 'DD-MON-YYYY HH24:MI:SS'), 'DD-MON-YYYY HH24:MI:SS') - TO_DATE(TO_CHAR(STARTUP_TIME, 'DD-MON-YYYY HH24:MI:SS'), 'DD-MON-YYYY HH24:MI:SS')) || ' Dias,  ' ||
					TRUNC(MOD((TO_DATE(TO_CHAR(SYSDATE, 'DD-MON-YYYY HH24:MI:SS'), 'DD-MON-YYYY HH24:MI:SS') - TO_DATE(TO_CHAR(STARTUP_TIME, 'DD-MON-YYYY HH24:MI:SS'), 'DD-MON-YYYY HH24:MI:SS'))* 24, 24)) || ' Horas,  ' /*AS UPTIME*/ ||
					TRUNC(MOD((TO_DATE(TO_CHAR(SYSDATE, 'DD-MON-YYYY HH24:MI:SS'), 'DD-MON-YYYY HH24:MI:SS') - TO_DATE(TO_CHAR(STARTUP_TIME, 'DD-MON-YYYY HH24:MI:SS'), 'DD-MON-YYYY HH24:MI:SS'))* (60 * 24), 60)) || ' Min y ' ||
					TRUNC(MOD((TO_DATE(TO_CHAR(SYSDATE, 'DD-MON-YYYY HH24:MI:SS'), 'DD-MON-YYYY HH24:MI:SS') - TO_DATE(TO_CHAR(STARTUP_TIME, 'DD-MON-YYYY HH24:MI:SS'), 'DD-MON-YYYY HH24:MI:SS'))* (60 * 60 * 24), 60)) || ' Seg. '||'</td></tr>' AS DISPONIBILIDAD
				  FROM DUAL, GV\$INSTANCE
				  ORDER BY 1 ASC;
exit	
_eof
		else			
			echo "<tr><td>${bds}</td>"
			echo "<td>--</td>"
			#PRDBNAME_RAW_2=`echo ${PRDBNAME_RAW} | awk '{print $1}'`
			echo '<td><em id="parr">ERROR:</em></td>'
			echo "<td>--</td>"
			echo "<td>--</td>"
			echo "<td>--</td>"
			echo "<td>--</td>"
			echo "<td>--</td>"
			echo "<td>--</td></tr>"
		fi
	done
	
echo "</table>"
echo "<p>"

fi

