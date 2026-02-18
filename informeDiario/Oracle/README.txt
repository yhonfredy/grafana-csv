script para determinar el esatdo del listener y simulacion del acceso de la base de datos.
* archivo check_oracle_influx_v1.py, maneja solo inspeccion del puerto 1521

UPDATE, Script Mejorado con Validación de Login:
*  check_oracle_influx, este ya lo deje en nivel 2.5, con USER y PWD ficticios.
Este script intentará:
--> Conectar al puerto 1521 (Red).
--> Si el puerto está abierto, intentará un login con un usuario ficticio.
--> Si Oracle responde ORA-01017: invalid username/password, el script marcará el estado como UP, porque la base de datos respondió.

