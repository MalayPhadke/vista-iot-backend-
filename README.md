# SNMP Flask API Server

This is a Flask-based server that implements the SNMP protocol with endpoints for SNMPv1, SNMPv2c, and SNMPv3 operations.

## Features

- Three dedicated endpoints for different SNMP versions:
  - `/api/snmp/v1` - SNMPv1 operations
  - `/api/snmp/v2c` - SNMPv2c operations
  - `/api/snmp/v3` - SNMPv3 operations
- Supports all common SNMP operations:
  - `get` - Retrieve a specific OID value
  - `walk` - Retrieve a subtree of OID values
  - `set` - Set a specific OID value
- Full YAML configuration support
- Comprehensive error handling

## Installation

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Make sure you have SNMP utilities installed on your system:
```bash
apt-get update && apt-get install -y snmp snmp-mibs-downloader
```

## Usage

Start the server:
```bash
python app.py
```

Or with gunicorn:
```bash
gunicorn app:app
```

## API Endpoints

All endpoints accept POST requests with YAML content. The YAML should follow the structure outlined in the SNMP documentation and should include a `protocols.snmp` section with the appropriate configuration.

### Example YAML Payloads

#### SNMPv1 Example

```yaml
protocols:
  snmp:
    operation: get
    version: 1
    target:
      host: 192.168.1.1
      port: 161
    authentication:
      version1:
        community: public
    oid: 1.3.6.1.2.1.1.1.0
```

#### SNMPv2c Example

```yaml
protocols:
  snmp:
    operation: get
    version: 2c
    target:
      host: 192.168.1.1
      port: 161
    authentication:
      version2c:
        community: public
    oid: 1.3.6.1.2.1.1.1.0
```

#### SNMPv3 Example

```yaml
protocols:
  snmp:
    operation: get
    version: 3
    target:
      host: 192.168.1.1
      port: 161
    authentication:
      version3:
        username: snmpuser
        level: authPriv
        auth_protocol: SHA
        auth_passphrase: authpassword
        privacy_protocol: AES
        privacy_passphrase: privpassword
    oid: 1.3.6.1.2.1.1.1.0
```

#### SNMP Set Operation Example

```yaml
protocols:
  snmp:
    operation: set
    version: 2c
    target:
      host: 192.168.1.1
      port: 161
    authentication:
      version2c:
        community: private
    oid: 1.3.6.1.2.1.1.4.0
    type: s
    value: "contact@example.com"
```

### SNMPv1 Example

```bash
curl -X POST -H "Content-Type: application/x-yaml" --data-binary @v1_example.yaml http://localhost:5000/api/snmp/v1
```

### SNMPv2c Example

```bash
curl -X POST -H "Content-Type: application/x-yaml" --data-binary @v2c_example.yaml http://localhost:5000/api/snmp/v2c
```

### SNMPv3 Example

```bash
curl -X POST -H "Content-Type: application/x-yaml" --data-binary @v3_example.yaml http://localhost:5000/api/snmp/v3
```

## Response Format

The server responds with JSON output containing:

- `success`: Boolean indicating if the operation was successful
- `output`: The stdout from the SNMP command (if successful)
- `error`: Error message (if failed)
- `stderr`: The stderr from the SNMP command (if failed)
- `command`: The command that was executed

## Error Handling

The server handles various error scenarios:
- Invalid YAML format
- Missing required parameters
- SNMP command execution errors
- Authorization and authentication issues

## Security Considerations

- SNMP credentials are never logged or stored
- All user input is validated before execution
- Error messages are sanitized to prevent information leakage

## OPC UA Data Gateway and Aggregation

This project includes a sophisticated OPC UA system designed to act as a gateway to various PLC (Programmable Logic Controller) devices, aggregate their data, and expose it through a consolidated OPC UA server.

### Architecture

The OPC UA functionality is comprised of several key components:

1.  **`opcua_backend.py` (FastAPI Backend)**:
    *   Serves as the central control point for the OPC UA components.
    *   Provides a REST API endpoint (`POST /api/opcua/control/start`) to dynamically start and configure the OPC UA gateway client and the CSV data server.
    *   Uses an `opcua_start.json` file to receive configuration parameters for the client and server components during the API call.

2.  **`opcua_gateway_client.py` (Gateway Client)**:
    *   Connects to one or more external OPC UA servers (simulated by `virtual_plc_server.py` or real PLCs).
    *   Reads specified data points (nodes) from these PLCs based on the configuration provided in `opcua_start.json`.
    *   Logs the collected data, including timestamps, PLC names, node IDs, values, and status codes, into a CSV file (`plc_data_log.csv`).

3.  **`opcua_csv_data_server.py` (CSV Data OPC UA Server)**:
    *   Runs its own OPC UA server.
    *   Monitors `plc_data_log.csv` for new data.
    *   Reads the data from the CSV file and structures it within its own OPC UA address space. PLC names become folders, and their respective data points (from NodeIDs in the CSV) become variables under these folders.
    *   This allows other OPC UA clients to connect to this server and browse/read the aggregated data originally collected by the `opcua_gateway_client.py`.

4.  **`virtual_plc_server.py` (PLC Simulator)**:
    *   A utility script that simulates multiple OPC UA-enabled PLCs.
    *   Useful for development and testing the `opcua_gateway_client.py` without needing real PLC hardware.
    *   Can be configured to expose various data types and structures.

5.  **Configuration Files**:
    *   `opcua_start.json`: JSON file defining the runtime configuration for both the gateway client (PLC endpoints, nodes to monitor, security settings) and the CSV data server (its OPC UA endpoint, CSV file path, update interval). This file's content is sent as the payload to the `/api/opcua/control/start` endpoint.
    *   `plc_data_log.csv`: The intermediary CSV file used to store data polled by the gateway client. This file is then read by the CSV data server.

### Prerequisites

- Python 3.8+
- pip (Python package manager)

### Installation

1.  Clone the repository (if not already done):
    ```bash
    git clone <repository-url>
    cd vista-iot-backend
    ```

2.  Install general backend dependencies:
    ```bash
    pip install -r requirements.txt
    ```

3.  Install OPC UA specific dependencies:
    ```bash
    pip install -r requirements-opcua.txt
    ```

### Usage Workflow

1.  **Start PLC Simulators (Optional but Recommended for Testing)**:
    Run one or more instances of the virtual PLC server if you don't have real PLCs to connect to.
    ```bash
    python virtual_plc_server.py --name Virtual_PLC_1 --port 4841
    python virtual_plc_server.py --name Virtual_PLC_2 --port 4842
    # ... and so on, matching the PLCs defined in your opcua_start.json
    ```

2.  **Start the Main Backend Application**:
    This application hosts the API to control the OPC UA components.
    ```bash
    python opcua_backend.py
    # Or using a production server like Uvicorn for opcua_backend.py which is a FastAPI app
    # uvicorn opcua_backend:app --host 0.0.0.0 --port 8000
    ```
    The backend will typically run on `http://localhost:8000`.

3.  **Prepare `opcua_start.json`**:
    Ensure your `opcua_start.json` file is correctly configured with:
    *   Details of the PLCs the `opcua_gateway_client.py` should connect to (endpoints, nodes to monitor).
    *   Settings for the `opcua_csv_data_server.py` (e.g., its OPC UA server endpoint).
    *   Paths to the scripts if they are not in the default location expected by `opcua_backend.py`.

4.  **Initiate OPC UA Components via API Call**:
    Send a POST request to the backend API with the content of `opcua_start.json`.
    ```bash
    curl -X POST -H "Content-Type: application/json" -d @opcua_start.json http://localhost:8000/api/opcua/control/start
    ```
    This command will trigger the `opcua_backend.py` to:
    *   Start the `opcua_gateway_client.py` process.
    *   Wait for `plc_data_log.csv` to be created/populated by the client.
    *   Start the `opcua_csv_data_server.py` process.

5.  **Monitor and Access Data**:
    *   Check the console logs of `opcua_backend.py`, `opcua_gateway_client.py`, and `opcua_csv_data_server.py` for status and errors.
    *   Use an OPC UA client (like UaExpert or another Python client) to connect to the OPC UA server run by `opcua_csv_data_server.py` (e.g., `opc.tcp://0.0.0.0:4850/csv_data_server/`) to browse and read the aggregated PLC data.

### Key Scripts

- `opcua_backend.py`: Main FastAPI application for controlling OPC UA components.
- `opcua_gateway_client.py`: Client to poll data from PLCs and log to CSV.
- `opcua_csv_data_server.py`: Server to expose CSV data via OPC UA.
- `virtual_plc_server.py`: Simulates OPC UA PLCs for testing.
- `models.py`: Contains Pydantic models for configuration and API requests related to OPC UA.

This system provides a flexible and robust way to integrate data from multiple OPC UA sources into a centralized, accessible OPC UA server.
