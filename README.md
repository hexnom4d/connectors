# OpenCTI Connectors

This project aims to centralize all custom OpenCTI connectors that need to be built due to operational requirements and are not yet available in the official project. The initial connector in this repository is for **Trend Micro XDR**.

The development of connectors relies on two main sources of documentation:

- **Trend Micro XDR API v3 (public version):**  
  [https://automation.trendmicro.com/xdr/api-v3/](https://automation.trendmicro.com/xdr/api-v3/)

- **OpenCTI Connector Development Guide:**  
  [https://docs.opencti.io/latest/development/connectors/](https://docs.opencti.io/latest/development/connectors/)

In this project, we prefer to implement connectors as services fully integrated into a single Docker Compose environment.

---

## Trend Micro Connector Structure

The connector consists of three main files and one directory:

1. **Dockerfile**  
   Defines the Docker configuration for the connector, including:  
   - Installing dependencies  
   - Setting the working directory  
   - Copying the service into `/app`  
   - Installing required libraries:
     - Python
     - `libmagic1`  

2. **requirements.txt**  
   Python libraries required to run the connector:  
   - `pycti==6.4.10` (must match your OpenCTI version)  
   - `requests`  
   - `python-dotenv` (for parsing environment variables)

3. **connector.py**  
   Main source code of the connector. This is where all the logic resides.

4. **/data**  
   Directory to store cache files or any other persistent data.

---

## Configuration

All configuration variables are defined in a `.env` file. Docker secrets can also be used if preferred.

<img width="1214" height="246" alt="Example .env" src="https://github.com/user-attachments/assets/0a7815a6-70bc-42f9-b330-5cb577258041" />

**Important notes:**

- `TAG_FILTER` must correspond to the **ID of the label** used to send IoCs to Trend Vision One. Using the label name directly will not work. If you find a method to use the label name instead, please let me know.

---

## Docker Compose Integration

To integrate the connector into your Docker Compose environment, add the following service:

```yaml
services:
  opencti-trend-connector:
    build: ./connectors/opencti-trend-connector  # Path to connector directory
    container_name: opencti-trend-connector
    restart: unless-stopped
    environment:
      - OPENCTI_URL=http://opencti:8080
      - OPENCTI_TOKEN=<OpenCTI Token>
      - TREND_API_URL=${TREND_API_URL}
      - TREND_API_KEY=${TREND_API_KEY}
      - TAG_FILTER=${TAG_FILTER}
      - POLL_INTERVAL=${POLL_INTERVAL}
      - TENANTS=${TREND_TENANTS}
      - CACHE_FILE=/data/sent_cache.json
    volumes:
      - ./connectors/opencti-trend-connector/data:/data
    depends_on:
      - opencti
