script para determinar el esatdo del listener y simulacion del acceso de la base de datos.
* archivo check_oracle_influx_v1.py, maneja solo inspeccion del puerto 1521

UPDATE, Script Mejorado con Validación de Login:
*  check_oracle_influx, este ya lo deje en nivel 2.5, con USER y PWD ficticios.
Este script intentará:
--> Conectar al puerto 1521 (Red).
--> Si el puerto está abierto, intentará un login con un usuario ficticio.
--> Si Oracle responde ORA-01017: invalid username/password, el script marcará el estado como UP, porque la base de datos respondió.

Por qué esta lógica es mejor:
Detección de Firewall: Si el script se queda colgado en la parte de TCP, ya sabemos que es Firewall.

Detección de Listener: Si el puerto 1521 responde pero el login dice "No listener", el servidor está prendido pero el servicio de Oracle está apagado.

Detección de Base de Datos: Si el login devuelve el error ORA-01017 (Username/Password inválido), es la mejor noticia posible: significa que la petición atravesó el Firewall, llegó al Listener, y la Base de Datos procesó la solicitud. Por lo tanto, la BD está UP, y asi lo puedo procesar.

