#!/usr/bin/env python3
import os
import time
import json
import logging
import requests
from pycti import OpenCTIApiClient
import re
from dotenv import load_dotenv

load_dotenv()

# Logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(message)s")

# Config desde ENV
OPENCTI_URL = os.getenv("OPENCTI_URL")
OPENCTI_TOKEN = os.getenv("OPENCTI_TOKEN")
TREND_API_URL = os.getenv("TREND_API_URL")
TAG_FILTER = os.getenv("TAG_FILTER", "trendmicro_share")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "300"))  # segundos
CACHE_FILE = os.getenv("CACHE_FILE", "/data/sent_cache.json")
PAGE_SIZE = int(os.getenv("PAGE_SIZE", "50"))
raw = os.getenv("TENANTS", [])

try:
    TENANTS = json.loads(raw)       # ahora es una lista de diccionarios, para soportar multitenants
except json.JSONDecodeError as e:
    logging.error(f"Error decodificando TENANTS: {e}")
    TENANTS = []

if not all([OPENCTI_URL, OPENCTI_TOKEN]):
    logging.error("Faltan variables de entorno: revisa OPENCTI_URL/OPENCTI_TOKEN/TREND_API_URL")
    raise SystemExit(1)

client = OpenCTIApiClient(OPENCTI_URL, OPENCTI_TOKEN)

def load_cache(path):
    try:
        with open(path, "r") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_cache(path, s):
    try:
        with open(path, "w") as f:
            json.dump(list(s), f)
    except Exception as e:
        logging.warning(f"Error guardando cache: {e}")


def parse_pattern(pattern):
    """
    Parse a STIX indicator pattern and return (ioc_type, ioc_value).
    Examples handled:
      [domain-name:value = 'evil.com']              -> ('domain', 'evil.com')
      [ipv4-addr:value = '1.2.3.4']                 -> ('ip', '1.2.3.4')
      [file:hashes.'SHA-256' = 'abcd...']          -> ('file_sha256', 'abcd...')
      [file:hashes."MD5" = 'aaa...']               -> ('file_md5', 'aaa...')
      [url:value = 'https://...']                  -> ('url', 'https://...')
    Returns (None, None) if no parse.
    """
    if not pattern or not isinstance(pattern, str):
        return None, None
    p = pattern.strip()

    # 1) file hashes first (handles quotes around alg 'SHA-256' or "SHA-256" or unquoted)
    file_hash_re = re.compile(
        r"\[file:hashes\.(?:'(?P<alg1>[^']+)'|\"(?P<alg2>[^\"]+)\"|(?P<alg3>[^=\s]+))\s*=\s*'(?P<val>[0-9a-fA-F]+)'\]",
        re.IGNORECASE
    )
    m = file_hash_re.search(p)
    if m:
        alg = m.group('alg1') or m.group('alg2') or m.group('alg3')
        val = m.group('val')
        # normalize algorithm name -> e.g. "SHA-256" -> "sha256"
        alg_norm = re.sub(r'[^a-z0-9]', '', alg.lower())
        return f"file_{alg_norm}", val

    # 2) generic pattern like [type:prop = 'value'] (covers domain, ip, url, email, file fallback)
    # allow operators = MATCHES LIKE etc. but we capture quoted value
    generic_re = re.compile(
        r"\[(?P<stix_type>[\w-]+):(?P<prop>[\w\.\-']+)\s*(?:=|MATCHES|like)\s*'(?P<val>[^']+)'\]",
        re.IGNORECASE
    )
    m = generic_re.search(p)
    if m:
        stix_type = m.group('stix_type').lower()
        prop = m.group('prop').lower()
        val = m.group('val')

        # map common STIX types -> normalized types for Trend
        if stix_type in ("domain-name", "domain"):
            return "domain", val
        if stix_type in ("ipv4-addr", "ipv6-addr", "ip"):
            return "ip", val
        if stix_type == "url":
            return "url", val
        if stix_type in ("email-addr", "email"):
            return "email", val
        if stix_type == "file":
            # fallback: prop may include hashes.<alg> (without the full file:hashes.'ALG' form)
            hm = re.search(r"hashes\.(?:'(?P<a1>[^']+)'|\"(?P<a2>[^\"]+)\"|(?P<a3>[^=\s]+))", prop, re.IGNORECASE)
            if hm:
                alg = hm.group('a1') or hm.group('a2') or hm.group('a3')
                alg_norm = re.sub(r'[^a-z0-9]', '', alg.lower())
                return f"file_{alg_norm}", val
            # otherwise return generic file and the pattern string
            return "file", val

        # default fallback: return raw stix_type (so caller can handle it)
        return stix_type, val

    # 3) try double-quoted value forms (rare)
    file_hash_re2 = re.compile(
        r'\[file:hashes\.(?:"(?P<algq>[^"]+)"|\'(?P<algsq>[^\']+)\')\s*=\s*"(?P<vq>[^"]+)"\]',
        re.IGNORECASE
    )
    m = file_hash_re2.search(p)
    if m:
        alg = m.group('algq') or m.group('algsq')
        val = m.group('vq')
        alg_norm = re.sub(r'[^a-z0-9]', '', alg.lower())
        return f"file_{alg_norm}", val

    # no match
    return None, None


def map_type(entity_type):
    ioc_type, ioc_value = parse_pattern(entity_type)
    logging.info(ioc_type)
    if "md5" in ioc_type:
        ioc_type = None
        ioc_value = None
        logging.info("Trend don't support md5")
    if 'sha256' in ioc_type:
        ioc_type = "fileSha256"
    if 'sha1 in 'ioc_type:
        ioc_type = "file_Sha1"
    if "email" in ioc_type:
        ioc_type = "senderMailAddress"

    return ioc_type, ioc_value

def get_value(ioc):
    # intenta distintos campos comunes
    return (ioc.get("observable_value") or ioc.get("value") or
            ioc.get("name") or ioc.get("x_opencti_value") or "")


def fetch_indicators(tag):
    logging.info("Listing Indicators with filters")
    filters = {
        "mode": "and",
        "filters": [
            {"key": "objectLabel", "values": [tag], "mode": "and"}
        ],
        "filterGroups": []
    }
    try:
        indicators = client.indicator.list(
            filters=filters,
            first=50
        )
        logging.info(f"Se obtuvieron {len(indicators or [])} indicators con tag '{tag}'")
        return indicators or []
    except Exception as e:
        logging.error(f"Error fetching indicators: {e}")
        return []

def send_to_trend(ioc_id, ioc_type, ioc_value):
    success = False

    for tenant in TENANTS:
        url = tenant["url"]
        key = tenant["key"]
        operation = tenant["name"]

        payload = [
            {
                ioc_type: ioc_value, 
                "description": "Incident Response IoC", 
            }
        ]
        headers = {
            "Authorization": f"Bearer {key}", 
            "Content-Type": "application/json;charset=utf-8"
        }
        query_params = {}

        logging.info(f"Enviando payload: {payload}")
        try:
            r = requests.post(url, params=query_params, json=payload, headers=headers, timeout=30)
            if 200 <= r.status_code < 300:
                logging.info(f"Enviado OK a {operation}: {ioc_value} ({ioc_type}) result {r.status_code}")
                return True
            else:
                logging.error(f"Error en tenant {operation} [{r.status_code}]: {r.text}")
                return False
        except Exception as e:
            logging.error(f"Exception al enviar a {operation}: {e}")
            return False

def main_loop():
    logging.info("Conector OpenCTI -> Trend Vision One iniciado")
    sent = load_cache(CACHE_FILE)
    logging.info(f"Cache cargada: {len(sent)} items")
    while True:
        try:
            indicators = fetch_indicators(TAG_FILTER)
            if not indicators:
                logging.debug("No hay indicators nuevos")
            for ioc in indicators:
                ioc_id = ioc.get("id")
                if not ioc_id:
                    logging.debug("Indicator sin id/valor, saltando")
                    continue
                if ioc_id in sent:
                    logging.debug(f"YA enviado: {ioc_id}")
                    continue
                ioc_type, ioc_value = map_type(ioc.get("pattern"))
                if not ioc_value:
                    logging.debug(f"Indicator sin valor: {ioc_id}")
                    continue
                ok = send_to_trend(ioc_id, ioc_type, ioc_value)
                if ok:
                    sent.add(ioc_id)
                    save_cache(CACHE_FILE, sent)
            logging.debug(f"Esperando {POLL_INTERVAL}s para siguiente ronda")
            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            logging.info("Interrupcion, guardando cache y saliendo")
            save_cache(CACHE_FILE, sent)
            break
        except Exception as e:
            logging.exception(f"Error en loop principal: {e}")
            time.sleep(30)  # espera breve y reintenta

if __name__ == "__main__":
    main_loop()
