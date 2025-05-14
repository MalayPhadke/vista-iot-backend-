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
