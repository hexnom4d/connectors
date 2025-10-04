FROM python:3.11-slim

RUN apt-get update && apt-get install -y libmagic1 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# directorio para cache/volumen
RUN mkdir /data
VOLUME ["/data"]

COPY connector.py /app/

# Ejecutar el conector
CMD ["python", "/app/connector.py"]
