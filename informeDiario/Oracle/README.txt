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
NOTA: No me funciono por problemas con la instalcion de las liibrerias. 
Es requisito previo, Opción A: pip install python-oracledb
Opción B: Usar cx_Oracle (Versión anterior)
A veces python-oracledb no aparece en repositorios muy viejos, pero cx_Oracle sí. pip install cx_Oracle

Opción C: El "Plan B" (Sin librerías, usando Telnet/Bash)
Si no podemos instalar nada porque las políticas de seguridad son muy estrictas, podemos engañar al sistema usando un script de Bash que use timeout y el dispositivo de red de Linux.

Esta función reemplaza la necesidad de la librería y detecta si el puerto está abierto (Firewall OK) o si hay rechazo (Listener OK):

(number=10.1.20.90; port=1521; timeout 2 bash -c "</dev/tcp/$number/$port" && echo "PUERTO_ABIERTO" || echo "BLOQUEADO_O_CERRADO")

UPDATE, check_oracle_native.py:
Este método no necesita pip ni librerías externas, es extremadamente rápido y nos dirá exactamente si es un problema de Firewall (Timeout) o si el Servicio/Listener respondió pero rechazó la conexión.
Por qué usar este script ahora:
Independencia Total: No usa oracledb, ni cx_Oracle, ni pip. Solo Python base y Bash

Diferenciación de Errores:

Si el puerto está bloqueado por Firewall, el comando timeout cortará la ejecución y reportará FIREWALL_TIMEOUT.

UPDATE, 
El script que me compartiste **SÍ hace una solicitud real de usuario y contraseña**. No hace un simple telnet.

En tu código, la validación ocurre en esta parte:

```python
oracledb.connect(user="USER_MONITOR", password="WRONG_PASSWORD_123", dsn=dsn)

```

### ¿Cómo funciona exactamente esa validación?

1. **Protocolo Oracle:** El script intenta establecer una sesión de base de datos completa usando la librería `oracledb`.
2. **Negociación con el Listener:** Primero contacta al puerto 1521, pero no se queda ahí. Le pide al Listener hablar con la instancia específica (`BD_ID`).
3. **Intento de Login:** Envía el usuario y la contraseña al motor de la base de datos.
4. **Respuesta del Motor:**
* **Si la BD está ARRIBA:** El motor recibe los datos y, aunque la contraseña sea incorrecta, responde con un código de error específico (**ORA-01017: invalid username/password**).
* **El truco:** Como el motor fue capaz de decirte que el password está mal, el script interpreta que **la base de datos está encendida y funcionando**.
* **Si la BD está ABAJO:** No llegas al paso del password; el script recibe un error de red o de "Listener no disponible" y marca la base como **DOWN**.



### Resumen de la diferencia:

* **Telnet (Puerto 1521):** Solo te dice si la "puerta" está abierta. Pero la puerta puede estar abierta y la base de datos estar apagada o congelada.
* **Tu Script (oracledb.connect):** Toca la puerta, entra y habla con el guardia. Si el guardia te responde (aunque sea para regañarte por el password), confirmas que **hay alguien vivo adentro**.

Por eso tu script anterior te marcaba `[OPEN]` en casos donde un simple ping no sería suficiente. Es mucho más confiable.

¿Quieres que mantengamos esa lógica de "password incorrecto" en la versión que sube los datos a InfluxDB?

Si el Firewall está abierto pero el Listener está caído, Linux recibirá un paquete "RST" y el script reportará LISTENER_DOWN.

