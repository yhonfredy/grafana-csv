#!/bin/sh

# #######################################
# Consulta el estado de TABLESPACES:
# #######################################
# Este script se conecta por SQL*Plus a un servidor y base de datos, y consulta el estado de los tablespaces.
# Use sh para ejecutar esta shell y especifique una IP en la cual ingresar.
# e.g. sh check_tbs_send_mail.sh 10.1.5.168 > check_tbs_send_mail.html

# Use el siguiente código para enviar correo en formato HTML con el contenido del archivo resultante check_tbs_send_mail.html
# EMAIL_LIST=jcalderon@asesoftware.com
# SEND_MAIL()
# {
# {
# echo "To: $EMAIL_LIST"
# echo "Subject:Alerta de Tablespace Lleno! $ORACLE_SID@`hostname`"
# echo "MIME-Version: 1.0"
# echo "Content-Type: text/html"
# echo "Content-Disposition: inline"
# cat  /tmp/prueba_correo/pru.html
# } | /usr/sbin/sendmail $EMAIL_LIST
# }
# SEND_MAIL

echo "<html>"
echo "<head>"
echo '<meta http-equiv="Content-Type" content="text/html; charset=WINDOWS-1252">'
echo "<style type='text/css'> body {font:10pt Arial,Helvetica,sans-serif; color:black; background:White;} p {font:10pt Arial,Helvetica,sans-serif; color:black; background:White;} table,tr,td {font:10pt Arial,Helvetica,sans-serif; color:Black; background:#f7f7e7; padding:0px 0px 0px 0px; margin:0px 0px 0px 0px;} th {font:bold 10pt Arial,Helvetica,sans-serif; color:#336699; background:#cccc99; padding:0px 0px 0px 0px;} h1 {font:16pt Arial,Helvetica,Geneva,sans-serif; color:#336699; background-color:White; border-bottom:1px solid #cccc99; margin-top:0pt; margin-bottom:0pt; padding:0px 0px 0px 0px;} h2 {font:bold 10pt Arial,Helvetica,Geneva,sans-serif; color:#336699; background-color:White; margin-top:4pt; margin-bottom:0pt;} a {font:9pt Arial,Helvetica,sans-serif; color:#663300; background:#ffffff; margin-top:0pt; margin-bottom:0pt; vertical-align:top;}.blink {animation: blinker 0.6s linear infinite; color: #1c87c9; font-size: 30px; font-weight: bold; font-family: sans-serif;}@keyframes blinker { 50% {opacity: 0; }}#parr{color:#FF0000;background:#f7f7e7;font: bold 10pt Arial;}
</style>"
echo "</head>"
echo "<body>"

echo "<p>==============================================<br />Este script obtiene informacion de estado de TABLESPACE.<br />==============================================</p>"

echo
sleep 1

# ##########
# VARIABLES:
# ##########

# Define the MAXSIZE for the LOGFILE in KB:
# 100 MB:
MAXSIZE=102400

# #######################################
# Excluded INSTANCES:
# #######################################
# Here you can mention the instances the script will IGNORE and will NOT run against:
# Use pipe "|" as a separator between each instance name.
# e.g. Excluding: -MGMTDB, ASM instances:

EXL_DB="\-MGMTDB|ASM|APX"                           #Excluded INSTANCES [Will not get reported offline].

IP_SERVIDOR_ELEGIDO=$1

USUARIO="admdba09"
CONTRASENA="admdba09*"

# ###########################
# Listing Available Databases:
# ###########################

# Count Instance Numbers:
INS_COUNT=$( ps -ef|grep pmon|grep -v grep|egrep -v ${EXL_DB}|wc -l )

# Exit if No DBs are running:
if [ $INS_COUNT -eq 0 ]
 then
   echo No Database Running !
   exit
fi

# If there is ONLY one DB set it as default without prompt for selection:
if [ $INS_COUNT -gt 1 ]
 then
	export ORACLE_SID=`echo $( ps -ef|grep pmon|grep -v grep|egrep -v ASM|awk '{print $NF}'|sed -e 's/ora_pmon_//g'|grep -v sed|grep -v "s///g" ) | awk '{print $1}'`
fi

# #########################
# Getting ORACLE_HOME
# #########################
  ORA_USER=`ps -ef|grep ${ORACLE_SID}|grep pmon|grep -v grep|egrep -v ${EXL_DB}|grep -v "\-MGMTDB"|awk '{print $1}'|tail -1`
  USR_ORA_HOME=`grep ${ORA_USER} /etc/passwd| cut -f6 -d ':'|tail -1`

# SETTING ORATAB:
if [ -f /etc/oratab ]
  then
  ORATAB=/etc/oratab
  export ORATAB
## If OS is Solaris:
elif [ -f /var/opt/oracle/oratab ]
  then
  ORATAB=/var/opt/oracle/oratab
  export ORATAB
fi

# ATTEMPT1: Get ORACLE_HOME using pwdx command:
export PGREP=`which pgrep`
export PWDX=`which pwdx`
if [[ -x ${PGREP} ]] && [[ -x ${PWDX} ]]
then
PMON_PID=`ps -fea | grep pmon | grep -v grep | grep _pmon_${ORACLE_SID}|awk '{print $2}'`
export PMON_PID
ORACLE_HOME=`grep -v '^\#' $ORATAB | grep -v '^$'| grep -i "^${ORACLE_SID}:" | perl -lpe'$_ = reverse' | cut -f3 | perl -lpe'$_ = reverse' |cut -f2 -d':'|sed -e 's/\/dbs//g'`
export ORACLE_HOME
fi
#echo "ORACLE_HOME from PWDX is ${ORACLE_HOME}"

# ATTEMPT2: If ORACLE_HOME not found get it from oratab file:
if [ ! -f ${ORACLE_HOME}/bin/sqlplus ]
 then
## If OS is Linux:
if [ -f /etc/oratab ]
  then
  ORATAB=/etc/oratab
  ORACLE_HOME=`grep -v '^\#' $ORATAB | grep -v '^$'| grep -i "^${ORACLE_SID}:" | perl -lpe'$_ = reverse' | cut -f3 | perl -lpe'$_ = reverse' |cut -f2 -d':'`
  export ORACLE_HOME

## If OS is Solaris:
elif [ -f /var/opt/oracle/oratab ]
  then
  ORATAB=/var/opt/oracle/oratab
  ORACLE_HOME=`grep -v '^\#' $ORATAB | grep -v '^$'| grep -i "^${ORACLE_SID}:" | perl -lpe'$_ = reverse' | cut -f3 | perl -lpe'$_ = reverse' |cut -f2 -d':'`
  export ORACLE_HOME
fi
#echo "ORACLE_HOME from oratab is ${ORACLE_HOME}"
fi

# ATTEMPT3: If ORACLE_HOME is still not found, search for the environment variable: [Less accurate]
if [ ! -f ${ORACLE_HOME}/bin/sqlplus ]
 then
  ORACLE_HOME=`env|grep -i ORACLE_HOME|sed -e 's/ORACLE_HOME=//g'`
  export ORACLE_HOME
#echo "ORACLE_HOME from environment  is ${ORACLE_HOME}"
fi

# ATTEMPT4: If ORACLE_HOME is not found in the environment search user's profile: [Less accurate]
if [ ! -f ${ORACLE_HOME}/bin/sqlplus ]
 then
  ORACLE_HOME=`grep -h 'ORACLE_HOME=\/' $USR_ORA_HOME/.bash_profile $USR_ORA_HOME/.*profile | perl -lpe'$_ = reverse' |cut -f1 -d'=' | perl -lpe'$_ = reverse'|tail -1`
  export ORACLE_HOME
#echo "ORACLE_HOME from User Profile is ${ORACLE_HOME}"
fi

# ATTEMPT5: If ORACLE_HOME is still not found, search for orapipe: [Least accurate]
if [ ! -f ${ORACLE_HOME}/bin/sqlplus ]
 then
  ORACLE_HOME=`locate -i orapipe|head -1|sed -e 's/\/bin\/orapipe//g'`
  export ORACLE_HOME
#echo "ORACLE_HOME from orapipe search is ${ORACLE_HOME}"
fi

# TERMINATE: If all above attempts failed to get ORACLE_HOME location, EXIT the script:
if [ ! -f ${ORACLE_HOME}/bin/sqlplus ]
 then
  echo "Please export ORACLE_HOME variable in your .bash_profile file under oracle user home directory in order to get this script to run properly"
  echo "e.g."
  echo "export ORACLE_HOME=/u01/app/oracle/product/11.2.0/db_1"
exit
fi

export LD_LIBRARY_PATH=${ORACLE_HOME}/lib

DIRECCIONES_PROD="10.1.5.10 \
10.1.5.11 \
10.1.5.156 \
10.1.5.168 \
10.1.5.18 \
10.1.5.25 \
10.1.5.5 \
10.1.5.6 \
10.1.5.7 \
10.1.5.70 \
10.1.5.8 \
10.1.5.9 \
10.1.6.110 \
10.1.5.214"

export DIRECCIONES_PROD;


DIRECCIONES_STBY="10.1.16.104 \
10.1.16.105 \
10.1.16.106 \
10.1.16.107 \
10.1.16.108 \
10.1.16.109"

export DIRECCIONES_STBY;

BDS_PROD="adeb \
adebol \
analitic \
astb \
audio \
biee \
bizagi \
capi \
catalog19c \
catalog \
CDBGEN \
cics \
conc \
concilia \
conciso \
contralo \
cryptov \
dataint \
DBADMIN \
dbnam1 \
dbnam2 \
dgh \
dmcia \
dmgen \
dmventas \
emrep \
failover \
filenet \
fina \
fonbol \
fondos \
gadata \
hpccenter \
hpdengine \
hyperion \
infrabol \
intranet \
invesa \
ipm \
lineg \
logerr \
moniplus \
mriesgo \
novell \
nomi \
parp \
pres \
prod11 \
pruebadg \
psai \
psaij \
rightnow \
saghi \
salu \
saludarp \
sant \
siar \
siebel \
sifv \
sig \
sigla \
sigsb \
simasol \
sipla \
sitr \
SOA \
spyg \
sundb \
svpa \
terceros \
tnaf \
tron \
userapp \
ventas \
WFLOW \
zabbix25"

export BDS_PROD;

ASM_PRODS="+ASM \
+ASM1 \
+ASM2"

echo

AZUL=`echo "$(echo '"text-decoration: underline;color: #0000ff;"')"`		


# #####################################
# SQLPLUS: Getting All tablespace Info:
# #####################################

for maquina in ${DIRECCIONES_PROD}
do

	if [[ ${maquina} == ${IP_SERVIDOR_ELEGIDO} ]]
		then				
		
		for bds in ${BDS_PROD}
		do	
PRDBNAME_RAW="$(${ORACLE_HOME}/bin/sqlplus -S ${USUARIO}/${CONTRASENA}@${maquina}:1521/${bds} << _eof
PROMPT conectado
exit	
_eof
)"



HSNAME="$(${ORACLE_HOME}/bin/sqlplus -S ${USUARIO}/${CONTRASENA}@${maquina}:1521/${bds} << _eof
SET LINESIZE 160
SET PAGES 0
SET FEEDBACK OFF
SET ECHO OFF
SELECT HOST_NAME FROM V\$INSTANCE;
exit	
_eof
)"

export HSNAME

TBS_ALERTADOS="$(${ORACLE_HOME}/bin/sqlplus -S ${USUARIO}/${CONTRASENA}@${maquina}:1521/${bds} << _eof
SET LINE 300 PAGES 0 FEEDBACK OFF ECHO OFF TIMING OFF TIME OFF
CLEAR COLUMN
SELECT
	DISTINCT 'SUCCESS' AS "PCT_MAX_USED"
FROM (SELECT a.tablespace_name,
			 ROUND (a.bytes_alloc / 1024 / 1024)
				 megs_alloc,
			 ROUND (NVL (b.bytes_free, 0) / 1024 / 1024)
				 megs_free,
			 ROUND ((a.bytes_alloc - NVL (b.bytes_free, 0)) / 1024 / 1024)
				 megs_used,
			 ROUND ((NVL (b.bytes_free, 0) / a.bytes_alloc) * 100)
				 Pct_Free,
			 100 - ROUND ((NVL (b.bytes_free, 0) / a.bytes_alloc) * 100)
				 Pct_used,
			 ROUND (maxbytes / 1048576)
				 MAX
		FROM (  SELECT f.tablespace_name,
					   SUM (f.bytes)                  bytes_alloc,
					   SUM (
						   DECODE (f.autoextensible,
								   'YES', f.maxbytes,
								   'NO', f.bytes))    maxbytes
				  FROM dba_data_files f
			  GROUP BY tablespace_name) a,
			 (  SELECT ts.name                            tablespace_name,
					   SUM (fs.blocks) * ts.blocksize     bytes_free
				  FROM DBA_LMT_FREE_SPACE fs, sys.ts\$ ts
				 WHERE ts.ts# = fs.tablespace_id
			  GROUP BY ts.name, ts.blocksize) b
	   WHERE a.tablespace_name = b.tablespace_name(+)
	  UNION ALL
		SELECT h.tablespace_name,
			   ROUND (SUM (h.bytes_free + h.bytes_used) / 1048576)
				   megs_alloc,
			   ROUND (
					 SUM (
						   (h.bytes_free + h.bytes_used)
						 - NVL (p.bytes_used, 0))
				   / 1048576)
				   megs_free,
			   ROUND (SUM (NVL (p.bytes_used, 0)) / 1048576)
				   megs_used,
			   ROUND (
					 (  SUM (
							  (h.bytes_free + h.bytes_used)
							- NVL (p.bytes_used, 0))
					  / SUM (h.bytes_used + h.bytes_free))
				   * 100)
				   Pct_Free,
				 100
			   - ROUND (
					   (  SUM (
								(h.bytes_free + h.bytes_used)
							  - NVL (p.bytes_used, 0))
						/ SUM (h.bytes_used + h.bytes_free))
					 * 100)
				   pct_used,
			   ROUND (
				   SUM (
						 DECODE (f.autoextensible,
								 'YES', f.maxbytes,
								 'NO', f.bytes)
					   / 1048576))
				   MAX
		  FROM sys.v_\$TEMP_SPACE_HEADER h,
			   sys.dba_temp_files    f,
			   sys.v_\$TEMP_EXTENT_POOL p
		 WHERE     p.file_id(+) = h.file_id
			   AND p.tablespace_name(+) = h.tablespace_name
			   AND f.file_id = h.file_id
			   AND f.tablespace_name = h.tablespace_name
	  GROUP BY h.tablespace_name) size_info,
	 sys.dba_tablespaces ts
WHERE 	ts.tablespace_name = size_info.tablespace_name
	AND round(((100/size_info.MAX)*(size_info.megs_alloc)),0) > 90
	AND (ts.tablespace_name NOT LIKE '%TEMP%' 	AND
		 ts.tablespace_name NOT LIKE '%UNDO%' 	AND
		 ts.tablespace_name NOT LIKE '%SYSTEM%' AND
		 ts.tablespace_name NOT LIKE '%SYSAUX%'	AND
		 ts.tablespace_name NOT LIKE '%USERS%');
exit	
_eof
)"

				if [[ ${PRDBNAME_RAW} == "conectado" ]]
					then
						if [[ ${TBS_ALERTADOS} == 'SUCCESS' ]]
							then					
								#Para Bases de datos oracle 9i y 10g y en adelante:
								#echo ${PRDBNAME_RAW}
								echo "<p>================================================================<br />Estado actual de TBS en el servidor <span style=${AZUL}>[${HSNAME}] - [${maquina}]</span> Base de datos <span style=${AZUL}>[${bds}]</span> <br />================================================================</p>"
								echo							
								${ORACLE_HOME}/bin/sqlplus -S ${USUARIO}/${CONTRASENA}@${maquina}:1521/${bds} << _eof
								SET LINESIZE 160
								SET PAGES 32000
								SET FEEDBACK OFF
								SET ECHO OFF 

								SET MARKUP HTML ON ENTMAP OFF
								
								--Para oracle 9i y 10g:
								--El mejor para 9i y 10g.
								/* Formatted on 11/11/2022 9:52:04 a. m. (QP5 v5.362) */

								SET LINE 200

								COL "INSTANCE_NAME" FOR A13
								COL tablespace_name FOR A26 WORD_WRAPPED
								COL SEGMENT_SPACE_MANAGEMENT HEAD "SEGMENT_SPACE|MANAGEMENT" FOR A13
								COL allocation_type HEAD "ALLOCATION|TYPE" FOR A12
								COL extent_management HEAD "EXTENT|MANAGEMENT" FOR A12
								COL "PCT_USED" FOR A40 WORD_WRAPPED
								COL "TOTAL_MB" FOR 999999999
								COL "USED_MB" FOR 99999999
								COL "FREE_MB" FOR 99999999
								COL pct_free FOR 9999999
								COL PCT_MAX_USED FOR A40 WORD_WRAPPED

								COMPUTE SUM LABEL "Total: " OF TOTAL_MB used_mb free_mb ON REPORT 
								BREAK ON REPORT SKIP 1

  SELECT (SELECT INSTANCE_NAME FROM V\$INSTANCE) as "INSTANCE_NAME",
                 ts.tablespace_name,
                 size_info.megs_alloc AS "TOTAL_MB",
                 size_info.megs_used AS "USED_MB",
                 size_info.megs_free AS "FREE_MB",
                 CASE
                        WHEN size_info.pct_used >= 90 THEN
                                '<em id="parr">'||TO_CHAR(size_info.pct_used)||'%</em>'
                        ELSE
                                ''||size_info.pct_used||'%'
                 END AS "PCT_USED",
                 size_info.pct_free,
                 CASE
                        WHEN round(((100/size_info.MAX)*(size_info.megs_alloc)),0) >= 0 AND round(((100/size_info.MAX)*(size_info.megs_alloc)),0) <= 2 THEN
                                ''||round(((100/size_info.MAX)*(size_info.megs_alloc)),0)||'%'
                        WHEN round(((100/size_info.MAX)*(size_info.megs_alloc)),0) >= 90 THEN
                                '<em id="parr">'||round(((100/size_info.MAX)*(size_info.megs_alloc)),0)||'%</em>'
                        ELSE
                                ''||round(((100/size_info.MAX)*(size_info.megs_alloc)),0)||'%'
                 END AS "PCT_MAX_USED",
                 size_info.MAX,
                 ts.status,
                 ts.contents,
                 --ts.logging,
                 --ts.extent_management,
                 --ts.allocation_type,
                 --ts.plugged_in,
                 --ts.block_size,
                 ts.segment_space_management AS "SEGMENT_SPACE_MANAGEMENT"
                 --ts.force_logging,
        FROM (SELECT a.tablespace_name,
                                 ROUND (a.bytes_alloc / 1024 / 1024)
                                         megs_alloc,
                                 ROUND (NVL (b.bytes_free, 0) / 1024 / 1024)
                                         megs_free,
                                 ROUND ((a.bytes_alloc - NVL (b.bytes_free, 0)) / 1024 / 1024)
                                         megs_used,
                                 ROUND ((NVL (b.bytes_free, 0) / a.bytes_alloc) * 100)
                                         Pct_Free,
                                 100 - ROUND ((NVL (b.bytes_free, 0) / a.bytes_alloc) * 100)
                                         Pct_used,
                                 ROUND (maxbytes / 1048576)
                                         MAX
                        FROM (  SELECT f.tablespace_name,
                                                   SUM (f.bytes)                  bytes_alloc,
                                                   SUM (
                                                           DECODE (f.autoextensible,
                                                                           'YES', f.maxbytes,
                                                                           'NO', f.bytes))    maxbytes
                                          FROM dba_data_files f
                                  GROUP BY tablespace_name) a,
                                 (  SELECT ts.name                            tablespace_name,
                                                   SUM (fs.blocks) * ts.blocksize     bytes_free
                                          FROM DBA_LMT_FREE_SPACE fs, sys.ts\$ ts
                                         WHERE ts.ts# = fs.tablespace_id
                                  GROUP BY ts.name, ts.blocksize) b
                   WHERE a.tablespace_name = b.tablespace_name(+)
                  UNION ALL
                        SELECT h.tablespace_name,
                                   ROUND (SUM (h.bytes_free + h.bytes_used) / 1048576)
                                           megs_alloc,
                                   ROUND (
                                                 SUM (
                                                           (h.bytes_free + h.bytes_used)
                                                         - NVL (p.bytes_used, 0))
                                           / 1048576)
                                           megs_free,
                                   ROUND (SUM (NVL (p.bytes_used, 0)) / 1048576)
                                           megs_used,
                                   ROUND (
                                                 (  SUM (
                                                                  (h.bytes_free + h.bytes_used)
                                                                - NVL (p.bytes_used, 0))
                                                  / SUM (h.bytes_used + h.bytes_free))
                                           * 100)
                                           Pct_Free,
                                         100
                                   - ROUND (
                                                   (  SUM (
                                                                        (h.bytes_free + h.bytes_used)
                                                                  - NVL (p.bytes_used, 0))
                                                        / SUM (h.bytes_used + h.bytes_free))
                                                 * 100)
                                           pct_used,
                                   ROUND (
                                           SUM (
                                                         DECODE (f.autoextensible,
                                                                         'YES', f.maxbytes,
                                                                         'NO', f.bytes)
                                                   / 1048576))
                                           MAX
                          FROM sys.v_\$TEMP_SPACE_HEADER h,
                                   sys.dba_temp_files    f,
                                   sys.v_\$TEMP_EXTENT_POOL p
                         WHERE     p.file_id(+) = h.file_id
                                   AND p.tablespace_name(+) = h.tablespace_name
                                   AND f.file_id = h.file_id
                                   AND f.tablespace_name = h.tablespace_name
                  GROUP BY h.tablespace_name) size_info,
                 sys.dba_tablespaces ts
   WHERE ts.tablespace_name = size_info.tablespace_name
   AND round(((100/size_info.MAX)*(size_info.megs_alloc)),0) > 90
   AND (ts.tablespace_name NOT LIKE '%TEMP%'    AND
                ts.tablespace_name NOT LIKE '%UNDO%'    AND
                ts.tablespace_name NOT LIKE '%SYSTEM%'  AND
                ts.tablespace_name NOT LIKE '%SYSAUX%'  AND
                ts.tablespace_name NOT LIKE '%USERS%')
ORDER BY size_info.pct_used DESC;						
						
exit	
_eof
						else
						
							:						
						
						fi
				fi
		done
	fi
done

echo "<br />"
echo "<br />"

echo "<p>====================<br />Fin De Este Script<br />====================</p>"

echo "</body>"
echo "</html>"


# #############
# END OF SCRIPT
# #############
