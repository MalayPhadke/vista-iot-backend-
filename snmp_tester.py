#!/usr/bin/env python3
"""
SNMP Testing Script for IoT Gateway

This script tests SNMP functionality on the IoT gateway with
support for SNMPv1, SNMPv2c, and SNMPv3. It can be run on any device
in the same network as the gateway.

Usage:
  python3 snmp_tester.py [options]

Options:
  --gateway-ip IP    The IP address of the gateway (default: 192.168.47.190)
  --version VER      SNMP version to use (1, 2c, 3) (default: 2c)
  --community STR    Community string for SNMPv1/v2c (default: public)
  --operation OP     Operation to perform (get, walk, set) (default: get)
  --oid OID          OID to operate on (default: 1.3.6.1.2.1.1.1.0)
  --type TYPE        Type for set operation (i, s, o, a, u) (default: s)
  --value VAL        Value for set operation
  --username USER    SNMPv3 username
  --auth-protocol AP SNMPv3 authentication protocol (MD5, SHA)
  --auth-key KEY     SNMPv3 authentication key
  --priv-protocol PP SNMPv3 privacy protocol (DES, AES)
  --priv-key KEY     SNMPv3 privacy key
  --security-level L SNMPv3 security level (noAuthNoPriv, authNoPriv, authPriv)
  --generate-yaml    Generate YAML for gateway API (default: False)
"""

import argparse
import subprocess
import yaml
import json
import requests
import logging
import sys
import os
from contextlib import contextmanager

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Default gateway IP
DEFAULT_GATEWAY_IP = "192.168.47.190"

# Common OIDs
COMMON_OIDS = {
    "system": "1.3.6.1.2.1.1.1.0",        # System description
    "uptime": "1.3.6.1.2.1.1.3.0",        # System uptime
    "hostname": "1.3.6.1.2.1.1.5.0",      # System name
    "interfaces": "1.3.6.1.2.1.2.1.0",    # Number of interfaces
    "ifDescr": "1.3.6.1.2.1.2.2.1.2",     # Interface descriptions
    "ifOperStatus": "1.3.6.1.2.1.2.2.1.8" # Interface operational status
}

@contextmanager
def colored_output(color_code):
    """Context manager for colored terminal output"""
    try:
        sys.stdout.write(f"\033[{color_code}m")
        yield
    finally:
        sys.stdout.write("\033[0m")

def print_success(message):
    """Print success message in green"""
    with colored_output(32):
        print(f"✓ {message}")

def print_error(message):
    """Print error message in red"""
    with colored_output(31):
        print(f"✗ {message}")

def print_info(message):
    """Print info message in blue"""
    with colored_output(36):
        print(f"ℹ {message}")

def print_warning(message):
    """Print warning message in yellow"""
    with colored_output(33):
        print(f"⚠ {message}")

def print_separator():
    """Print a separator line"""
    print("-" * 80)

def run_snmp_command(command, verbose=True):
    """Run an SNMP command and return the result"""
    try:
        if verbose:
            print_info(f"Running command: {' '.join(command)}")
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            if verbose:
                print_success("Command succeeded")
            return {
                "success": True,
                "output": result.stdout,
                "command": ' '.join(command)
            }
        else:
            if verbose:
                print_error(f"Command failed: {result.stderr}")
            return {
                "success": False,
                "error": result.stderr,
                "command": ' '.join(command)
            }
    except Exception as e:
        if verbose:
            print_error(f"Exception: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "command": ' '.join(command) if command else "Unknown"
        }

def build_snmpv1_command(operation, args):
    """Build SNMPv1 command"""
    cmd = [f"snmp{operation}", "-v1"]
    
    # Add community string
    cmd.extend(["-c", args.community])
    
    # Add host
    host = args.gateway_ip
    target = f"{host}:161"
    
    # Add OID
    cmd.append(target)
    cmd.append(args.oid)
    
    # Add type and value for set operations
    if operation == "set":
        if not args.type or not args.value:
            print_error("Missing type or value for SNMP set operation")
            sys.exit(1)
        
        cmd.append(args.type)
        cmd.append(args.value)
    
    return cmd

def build_snmpv2c_command(operation, args):
    """Build SNMPv2c command"""
    cmd = [f"snmp{operation}", "-v2c"]
    
    # Add community string
    cmd.extend(["-c", args.community])
    
    # Add host
    host = args.gateway_ip
    target = f"{host}:161"
    
    # Add OID
    cmd.append(target)
    cmd.append(args.oid)
    
    # Add type and value for set operations
    if operation == "set":
        if not args.type or not args.value:
            print_error("Missing type or value for SNMP set operation")
            sys.exit(1)
        
        cmd.append(args.type)
        cmd.append(args.value)
    
    return cmd

def build_snmpv3_command(operation, args):
    """Build SNMPv3 command"""
    cmd = [f"snmp{operation}", "-v3"]
    
    # Add username
    if not args.username:
        print_error("Missing username for SNMPv3")
        sys.exit(1)
    
    cmd.extend(["-u", args.username])
    
    # Add security level
    if not args.security_level:
        print_error("Missing security level for SNMPv3")
        sys.exit(1)
    
    cmd.extend(["-l", args.security_level])
    
    # Add authentication protocol and key if needed
    if args.security_level in ["authNoPriv", "authPriv"]:
        if not args.auth_protocol or not args.auth_key:
            print_error("Missing authentication protocol or key for SNMPv3")
            sys.exit(1)
        
        cmd.extend(["-a", args.auth_protocol])
        cmd.extend(["-A", args.auth_key])
    
    # Add privacy protocol and key if needed
    if args.security_level == "authPriv":
        if not args.priv_protocol or not args.priv_key:
            print_error("Missing privacy protocol or key for SNMPv3")
            sys.exit(1)
        
        cmd.extend(["-x", args.priv_protocol])
        cmd.extend(["-X", args.priv_key])
    
    # Add host
    host = args.gateway_ip
    target = f"{host}:161"
    
    # Add OID
    cmd.append(target)
    cmd.append(args.oid)
    
    # Add type and value for set operations
    if operation == "set":
        if not args.type or not args.value:
            print_error("Missing type or value for SNMP set operation")
            sys.exit(1)
        
        cmd.append(args.type)
        cmd.append(args.value)
    
    return cmd

def generate_yaml_for_gateway(args):
    """Generate YAML configuration for the gateway API"""
    print_info("Generating YAML configuration for gateway API...")
    
    config = {
        "protocols": {
            "snmp": {
                "operation": args.operation,
                "oid": args.oid,
                "target": {
                    "host": args.gateway_ip,
                    "port": 161
                },
                "authentication": {}
            }
        }
    }
    
    # Add version-specific configuration
    if args.version == "1":
        config["protocols"]["snmp"]["authentication"]["version1"] = {
            "community": args.community
        }
    elif args.version == "2c":
        config["protocols"]["snmp"]["authentication"]["version2c"] = {
            "community": args.community
        }
    elif args.version == "3":
        v3_auth = {
            "username": args.username,
            "level": args.security_level
        }
        
        if args.security_level in ["authNoPriv", "authPriv"]:
            v3_auth["auth_protocol"] = args.auth_protocol
            v3_auth["auth_passphrase"] = args.auth_key
        
        if args.security_level == "authPriv":
            v3_auth["priv_protocol"] = args.priv_protocol
            v3_auth["priv_passphrase"] = args.priv_key
        
        config["protocols"]["snmp"]["authentication"]["version3"] = v3_auth
    
    # Add type and value for set operations
    if args.operation == "set":
        config["protocols"]["snmp"]["type"] = args.type
        config["protocols"]["snmp"]["value"] = args.value
    
    # Convert to YAML
    yaml_str = yaml.dump(config, default_flow_style=False)
    
    # Save to file
    yaml_path = os.path.join(os.getcwd(), "snmp_config.yaml")
    with open(yaml_path, "w") as f:
        f.write(yaml_str)
    
    print_success(f"YAML configuration saved to {yaml_path}")
    
    # Print curl command example
    endpoint = f"http://{args.gateway_ip}:5000/api/snmp/v{args.version}"
    curl_cmd = f"curl -X POST -H 'Content-Type: application/x-yaml' --data-binary @{yaml_path} {endpoint}"
    
    print_info("Example curl command to send to gateway API:")
    print(curl_cmd)
    
    return yaml_str

def test_gateway_api(args, yaml_str):
    """Test the gateway API directly"""
    print_info(f"Testing gateway API at {args.gateway_ip}...")
    
    endpoint = f"http://{args.gateway_ip}:5000/api/snmp/v{args.version}"
    
    try:
        response = requests.post(
            endpoint,
            data=yaml_str,
            headers={"Content-Type": "application/x-yaml"},
            timeout=5
        )
        
        if response.status_code == 200:
            print_success(f"API request succeeded: {response.status_code}")
            print_info("Response:")
            print(json.dumps(response.json(), indent=2))
        else:
            print_error(f"API request failed: {response.status_code}")
            print_error(f"Response: {response.text}")
    
    except requests.exceptions.ConnectionError:
        print_error(f"Could not connect to gateway API at {endpoint}")
    except requests.exceptions.Timeout:
        print_error("API request timed out")
    except Exception as e:
        print_error(f"Exception during API request: {str(e)}")

def list_common_oids():
    """List common OIDs that can be used for testing"""
    print_info("Common OIDs for testing:")
    for name, oid in COMMON_OIDS.items():
        print(f"  {name}: {oid}")

def test_direct_snmp(args):
    """Test SNMP directly using Net-SNMP commands"""
    print_info(f"Testing direct SNMP {args.version} {args.operation} to {args.gateway_ip}...")
    
    # Build command based on SNMP version
    if args.version == "1":
        cmd = build_snmpv1_command(args.operation, args)
    elif args.version == "2c":
        cmd = build_snmpv2c_command(args.operation, args)
    elif args.version == "3":
        cmd = build_snmpv3_command(args.operation, args)
    else:
        print_error(f"Unsupported SNMP version: {args.version}")
        sys.exit(1)
    
    # Execute command
    result = run_snmp_command(cmd)
    
    if result["success"]:
        print_success("SNMP command succeeded")
        print("Output:")
        print(result["output"])
    else:
        print_error("SNMP command failed")
        print("Error:")
        print(result["error"])

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='SNMP Testing Script for IoT Gateway')
    
    parser.add_argument('--gateway-ip', type=str, default=DEFAULT_GATEWAY_IP,
                        help=f'IP address of the gateway (default: {DEFAULT_GATEWAY_IP})')
    parser.add_argument('--version', type=str, choices=['1', '2c', '3'], default='2c',
                        help='SNMP version (1, 2c, 3) (default: 2c)')
    parser.add_argument('--community', type=str, default='public',
                        help='Community string for SNMPv1/v2c (default: public)')
    parser.add_argument('--operation', type=str, choices=['get', 'walk', 'set'], default='get',
                        help='Operation to perform (get, walk, set) (default: get)')
    parser.add_argument('--oid', type=str, default='1.3.6.1.2.1.1.1.0',
                        help='OID to operate on (default: 1.3.6.1.2.1.1.1.0 - system description)')
    parser.add_argument('--type', type=str, default='s',
                        help='Type for set operation (i=integer, s=string, etc.) (default: s)')
    parser.add_argument('--value', type=str, help='Value for set operation')
    parser.add_argument('--username', type=str, help='SNMPv3 username')
    parser.add_argument('--auth-protocol', type=str, choices=['MD5', 'SHA'],
                        help='SNMPv3 authentication protocol (MD5, SHA)')
    parser.add_argument('--auth-key', type=str, help='SNMPv3 authentication key')
    parser.add_argument('--priv-protocol', type=str, choices=['DES', 'AES'],
                        help='SNMPv3 privacy protocol (DES, AES)')
    parser.add_argument('--priv-key', type=str, help='SNMPv3 privacy key')
    parser.add_argument('--security-level', type=str, 
                        choices=['noAuthNoPriv', 'authNoPriv', 'authPriv'],
                        help='SNMPv3 security level (noAuthNoPriv, authNoPriv, authPriv)')
    parser.add_argument('--generate-yaml', action='store_true',
                        help='Generate YAML configuration for gateway API')
    parser.add_argument('--test-api', action='store_true',
                        help='Test the gateway API directly')
    parser.add_argument('--list-oids', action='store_true',
                        help='List common OIDs for testing')
    
    return parser.parse_args()

def check_snmp_tools():
    """Check if SNMP tools are installed"""
    tools = ["snmpget", "snmpwalk", "snmpset"]
    
    for tool in tools:
        try:
            subprocess.run(["which", tool], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError:
            print_error(f"{tool} not found. Install net-snmp-utils package.")
            return False
    
    return True

def main():
    # Parse arguments
    args = parse_arguments()
    
    print_separator()
    print_info("SNMP Testing Script for IoT Gateway")
    print_separator()
    
    # List common OIDs if requested
    if args.list_oids:
        list_common_oids()
        print_separator()
    
    # Check for SNMP tools
    if not check_snmp_tools():
        print_error("SNMP tools not found. Please install net-snmp-utils package.")
        print_info("On Debian/Ubuntu: sudo apt-get install snmp snmp-mibs-downloader")
        print_info("On RHEL/CentOS: sudo yum install net-snmp-utils")
        sys.exit(1)
    
    # Generate YAML if requested
    yaml_str = None
    if args.generate_yaml:
        yaml_str = generate_yaml_for_gateway(args)
        print_separator()
    
    # Test gateway API if requested
    if args.test_api:
        if not yaml_str:
            yaml_str = generate_yaml_for_gateway(args)
        test_gateway_api(args, yaml_str)
        print_separator()
    
    # Test direct SNMP
    test_direct_snmp(args)
    print_separator()
    
    print_success("Testing completed")

if __name__ == "__main__":
    main()
