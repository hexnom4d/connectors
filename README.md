# connectors
OpenCTI Connectors

El presente proyecto planea recopilar todos los conectores que por necesidad operativa debo contruir y no estan disponibles en el proyecto actual, iniciando con trend micro, para esto necesitamos principalmente dos sitios de documentacion.

La documnetacion de la version publica de la api v3 de trend micro que se encuentra en este sitio: 

https://automation.trendmicro.com/xdr/api-v3/

Y la documentacion de desarrollo de conectores de opencti, en mi caso prefiero desarrollarlo como servicio y tenerlo todo integrado en un solo docker compose

https://docs.opencti.io/latest/development/connectors/

Inicialmente desarrolamos el conector que se compone de 3 archivos y un directorio:

1. Dockerfile: Contiene la configuracion del docker correspondiente a mi conector, instalacion de requirementes, directorios de trabajo, copia de servicio al docker en directorio app, ejecucion del servicio y los requerimientos previos de librerias:

   - Python
   - libmagic1

2. requirements.txt: Contiene las librerias de python necesarias para trabajar

  - pycti 6.4.10 (Importante que sea la version correspondiente a su version de opencti)
  - requests
  - python-dotenv (Parsing json)

3. connector.py: Codigo fuente del conector (Aqui va la salsa)

==================================================================

Por otra parte he decidido poner toda la informacion de variables en el archivo .env, aqui se puede usar docker secrets (Uds deciden)

<img width="1214" height="246" alt="image" src="https://github.com/user-attachments/assets/0a7815a6-70bc-42f9-b330-5cb577258041" />

Informacion importante: El Tag Filter corresponde al ID del label que determinen se va a usar para el envio de IoCs a Trend Vision One, si no lo hacen con ID no funciona, si encuentran una forma con el Label directamente me lo dicen por favor.

===================================================================

Finalmente lo que se debe agregar en el docker_compose.yml

services:
  opencti-trend-connector:
    build: ./connectors/opencti-trend-connector #Ruta al directorio del conector
    container_name: opencti-trend-connector
    restart: unless-stopped
    environment:
      - OPENCTI_URL=http://opencti:8080
      - OPENCTI_TOKEN= Token de Open CTI
      - TREND_API_URL=${TREND_API_URL}
      - TREND_API_KEY=${TREND_API_KEY}
      - TAG_FILTER=${TAG_FILTER}
      - POLL_INTERVAL=${POLL_INTERVAL}
      - TENANTS=${TREND_TENANTS}
      - CACHE_FILE=/data/sent_cache.json
    volumes:
      - ./connectors/opencti-trend-connector/data:/data #Revisa estas rutas en tu implementacion.
    depends_on:
      - opencti




