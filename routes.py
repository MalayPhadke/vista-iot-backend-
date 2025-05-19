#!/usr/bin/env python3
import yaml
from flask import request, jsonify
from snmpy import build_snmpv1_command, build_snmpv2c_command, build_snmpv3_command
from utils import execute_snmp_command

def register_routes(app):
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
