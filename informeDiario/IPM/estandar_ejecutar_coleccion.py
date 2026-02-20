
import requests
import json
import urllib3

# Esto limpia la consola de avisos de seguridad de HTTPS
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def ejecutar_coleccion(archivo_json):
    try:
        with open(archivo_json, 'r', encoding='utf-8') as f:
            peticiones = json.load(f)
    except Exception as e:
        print(f"❌ Error leyendo el archivo JSON: {e}")
        return

    print(f"📂 Cargadas {len(peticiones)} operaciones desde la colección.\n")

    for p in peticiones:
        # USAMOS .get() PARA QUE NO SE ROMPA SI CAMBIA EL NOMBRE DE LA LLAVE
        # Busca 'operacion', si no existe busca 'nombre', si no pone 'Sin_Nombre'
        nombre = p.get('operacion') or p.get('nombre') or "Sin_Nombre"
        url = p.get('endpoint') or p.get('url')
        payload = p.get('payload') or p.get('body')
        action = p.get('soap_action')

        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': action
        }

        print(f"🚀 Ejecutando: {nombre}")
        print(f"   URL: {url}")

        try:
            # Petición real
            response = requests.post(url, data=payload, headers=headers, verify=False, timeout=20)

            if response.status_code == 200:
                if "<html>" in response.text:
                    print(f"  ⚠️  RESPUESTA AMBIGUA: Se recibió HTML. Revisa la URL.")
                else:
                    print(f"  ✅ ÉXITO: Respuesta XML recibida.")
                    with open(f"res_{nombre}.xml", "w", encoding="utf-8") as f_res:
                        f_res.write(response.text)
            else:
                print(f"  ❌ FALLÓ: Código {response.status_code}")
                # Guardamos el detalle del error (importante para los errores 500)
                with open(f"error_{nombre}.xml", "w", encoding="utf-8") as f_err:
                    f_err.write(response.text)
                print(f"     Detalle del error guardado en: error_{nombre}.xml")

        except Exception as e:
            print(f"  ⛔ ERROR DE CONEXIÓN: {e}")

        print("-" * 60)

if __name__ == "__main__":
    # AQUÍ ponemos el nombre del archivo que usaremos
    ejecutar_coleccion('estandar_peticiones_servicios.json')
