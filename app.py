#!/usr/bin/env python3
import os
import yaml
import json
import subprocess
from flask import Flask, request, jsonify

app = Flask(__name__)

def execute_snmp_command(command):
    """
    Execute an SNMP command and return the result
    """
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True
        )
        return {
            "success": True,
            "output": result.stdout,
            "command": " ".join(command)
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": str(e),
            "stderr": e.stderr,
            "command": " ".join(command)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "command": " ".join(command) if command else "Unknown"
        }

def build_snmpv1_command(operation, config):
    """Build SNMP v1 command based on the provided configuration"""
    if not config.get("target", {}).get("host"):
        raise ValueError("Missing target host in configuration")
    
    cmd = [f"snmp{operation}", "-v1"]
    
    # Add community string
    if "community" not in config.get("authentication", {}).get("version1", {}):
        raise ValueError("Missing community string for SNMPv1")
    
    community = config["authentication"]["version1"]["community"]
    cmd.extend(["-c", community])
    
    # Add host
    host = config["target"]["host"]
    port = config["target"].get("port", 161)
    target = f"{host}:{port}"
    
    # Add OID
    if "oid" not in config:
        raise ValueError("Missing OID in configuration")
    
    cmd.append(target)
    cmd.append(config["oid"])
    
    # Add type and value for set operations
    if operation == "set":
        if "type" not in config or "value" not in config:
            raise ValueError("Missing type or value for SNMP set operation")
        cmd.append(config["type"])
        cmd.append(config["value"])
    
    return cmd

def build_snmpv2c_command(operation, config):
    """Build SNMP v2c command based on the provided configuration"""
    if not config.get("target", {}).get("host"):
        raise ValueError("Missing target host in configuration")
    
    cmd = [f"snmp{operation}", "-v2c"]
    
    # Add community string
    if "community" not in config.get("authentication", {}).get("version2c", {}):
        raise ValueError("Missing community string for SNMPv2c")
    
    community = config["authentication"]["version2c"]["community"]
    cmd.extend(["-c", community])
    
    # Add host
    host = config["target"]["host"]
    port = config["target"].get("port", 161)
    target = f"{host}:{port}"
    
    # Add OID
    if "oid" not in config:
        raise ValueError("Missing OID in configuration")
    
    cmd.append(target)
    cmd.append(config["oid"])
    
    # Add type and value for set operations
    if operation == "set":
        if "type" not in config or "value" not in config:
            raise ValueError("Missing type or value for SNMP set operation")
        cmd.append(config["type"])
        cmd.append(config["value"])
    
    return cmd

def build_snmpv3_command(operation, config):
    """Build SNMP v3 command based on the provided configuration"""
    if not config.get("target", {}).get("host"):
        raise ValueError("Missing target host in configuration")
    
    cmd = [f"snmp{operation}", "-v3"]
    
    v3_auth = config.get("authentication", {}).get("version3", {})
    if not v3_auth.get("username"):
        raise ValueError("Missing username for SNMPv3")
    
    # Add username
    cmd.extend(["-u", v3_auth["username"]])
    
    # Add security level
    level = v3_auth.get("level", "noAuthNoPriv")
    cmd.extend(["-l", level])
    
    # Add authentication protocol and passphrase if needed
    if level in ["authNoPriv", "authPriv"]:
        if not v3_auth.get("auth_protocol") or not v3_auth.get("auth_passphrase"):
            raise ValueError("Authentication protocol and passphrase required for authNoPriv or authPriv")
        
        cmd.extend(["-a", v3_auth["auth_protocol"]])
        cmd.extend(["-A", v3_auth["auth_passphrase"]])
    
    # Add privacy protocol and passphrase if needed
    if level == "authPriv":
        if not v3_auth.get("privacy_protocol") or not v3_auth.get("privacy_passphrase"):
            raise ValueError("Privacy protocol and passphrase required for authPriv")
        
        cmd.extend(["-x", v3_auth["privacy_protocol"]])
        cmd.extend(["-X", v3_auth["privacy_passphrase"]])
    
    # Add host
    host = config["target"]["host"]
    port = config["target"].get("port", 161)
    target = f"{host}:{port}"
    
    # Add OID
    if "oid" not in config:
        raise ValueError("Missing OID in configuration")
    
    cmd.append(target)
    cmd.append(config["oid"])
    
    # Add type and value for set operations
    if operation == "set":
        if "type" not in config or "value" not in config:
            raise ValueError("Missing type or value for SNMP set operation")
        cmd.append(config["type"])
        cmd.append(config["value"])
    
    return cmd

@app.route('/api/snmp/v1', methods=['POST'])
def snmp_v1():
    """
    Endpoint for SNMPv1 operations
    Expects a YAML payload with SNMP configuration
    """
    try:
        if request.content_type == 'application/x-yaml' or request.content_type == 'text/yaml':
            config = yaml.safe_load(request.data)
        else:
            return jsonify({"error": "Content-Type must be application/x-yaml or text/yaml"}), 400
        
        # Check for protocols and snmp configuration
        snmp_config = config.get("protocols", {}).get("snmp")
        if not snmp_config:
            return jsonify({"error": "Missing SNMP configuration in protocols section"}), 400
        
        # Get operation
        operation = snmp_config.get("operation", "get")
        if operation not in ["get", "walk", "set"]:
            return jsonify({"error": f"Unsupported operation: {operation}"}), 400
        
        # Build and execute command
        cmd = build_snmpv1_command(operation, snmp_config)
        result = execute_snmp_command(cmd)
        
        return jsonify(result)
    
    except yaml.YAMLError as e:
        return jsonify({"error": f"Invalid YAML: {str(e)}"}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/api/snmp/v2c', methods=['POST'])
def snmp_v2c():
    """
    Endpoint for SNMPv2c operations
    Expects a YAML payload with SNMP configuration
    """
    try:
        if request.content_type == 'application/x-yaml' or request.content_type == 'text/yaml':
            config = yaml.safe_load(request.data)
        else:
            return jsonify({"error": "Content-Type must be application/x-yaml or text/yaml"}), 400
        
        # Check for protocols and snmp configuration
        snmp_config = config.get("protocols", {}).get("snmp")
        if not snmp_config:
            return jsonify({"error": "Missing SNMP configuration in protocols section"}), 400
        
        # Get operation
        operation = snmp_config.get("operation", "get")
        if operation not in ["get", "walk", "set"]:
            return jsonify({"error": f"Unsupported operation: {operation}"}), 400
        
        # Build and execute command
        cmd = build_snmpv2c_command(operation, snmp_config)
        result = execute_snmp_command(cmd)
        
        return jsonify(result)
    
    except yaml.YAMLError as e:
        return jsonify({"error": f"Invalid YAML: {str(e)}"}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/api/snmp/v3', methods=['POST'])
def snmp_v3():
    """
    Endpoint for SNMPv3 operations
    Expects a YAML payload with SNMP configuration
    """
    try:
        if request.content_type == 'application/x-yaml' or request.content_type == 'text/yaml':
            config = yaml.safe_load(request.data)
        else:
            return jsonify({"error": "Content-Type must be application/x-yaml or text/yaml"}), 400
        
        # Check for protocols and snmp configuration
        snmp_config = config.get("protocols", {}).get("snmp")
        if not snmp_config:
            return jsonify({"error": "Missing SNMP configuration in protocols section"}), 400
        
        # Get operation
        operation = snmp_config.get("operation", "get")
        if operation not in ["get", "walk", "set"]:
            return jsonify({"error": f"Unsupported operation: {operation}"}), 400
        
        # Build and execute command
        cmd = build_snmpv3_command(operation, snmp_config)
        result = execute_snmp_command(cmd)
        
        return jsonify(result)
    
    except yaml.YAMLError as e:
        return jsonify({"error": f"Invalid YAML: {str(e)}"}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
