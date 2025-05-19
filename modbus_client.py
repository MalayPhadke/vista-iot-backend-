#!/usr/bin/env python3
"""
Modbus Client Script

This script provides a command-line interface to test Modbus functionality.
It can be run on another device in the same network to communicate with Modbus slaves
or with the IoT gateway's Modbus functionality.
"""

import os
import sys
import yaml
import json
import argparse
import logging
import requests
import time
from pymodbus.client.sync import ModbusTcpClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder, BinaryPayloadBuilder

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Utility functions for colored output
def print_success(message):
    """Print a success message in green"""
    print(f"\033[92m✓ {message}\033[0m")

def print_error(message):
    """Print an error message in red"""
    print(f"\033[91m✗ {message}\033[0m")

def print_info(message):
    """Print an information message in blue"""
    print(f"\033[94mℹ {message}\033[0m")

def print_separator():
    """Print a separator line"""
    print("-" * 80)

def read_modbus_value(client, address, count=1, unit=1, datatype="analog", conversion=""):
    """Read a value from a Modbus slave"""
    try:
        # Convert address to integer
        address = int(address)
        
        # Determine function code based on address range
        if 1 <= address <= 9999:  # Coils
            result = client.read_coils(address-1, count, unit=unit)
        elif 10001 <= address <= 19999:  # Discrete Inputs
            result = client.read_discrete_inputs(address-10001, count, unit=unit)
        elif 30001 <= address <= 39999:  # Input Registers
            result = client.read_input_registers(address-30001, count, unit=unit)
        elif 40001 <= address <= 49999:  # Holding Registers
            result = client.read_holding_registers(address-40001, count, unit=unit)
        else:
            logger.error(f"Invalid address: {address}")
            return None
        
        # Check for errors
        if result.isError():
            logger.error(f"Error reading from address {address}: {result}")
            return None
        
        # Process the result based on datatype and conversion
        if datatype.lower() == "discrete":
            return result.bits[0] if hasattr(result, 'bits') and result.bits else None
        
        # For analog data types
        if hasattr(result, 'registers') and result.registers:
            # Handle float conversion
            if conversion and "float" in conversion.lower():
                # Need at least 2 registers for a float
                if len(result.registers) >= 2:
                    # Different byte orders based on conversion string
                    if "little endian" in conversion.lower():
                        word_order = Endian.Little
                    else:
                        word_order = Endian.Big
                        
                    if "swap word" in conversion.lower():
                        # Swap the registers
                        registers = [result.registers[1], result.registers[0]]
                    else:
                        registers = result.registers
                    
                    # Create decoder
                    decoder = BinaryPayloadDecoder.fromRegisters(
                        registers,
                        byteorder=Endian.Big,
                        wordorder=word_order
                    )
                    
                    return decoder.decode_32bit_float()
            
            # Default handling for registers
            if len(result.registers) == 1:
                return result.registers[0]
            return result.registers
        
        # Default return
        return None
    
    except Exception as e:
        logger.error(f"Error reading from address {address}: {e}")
        return None

def write_modbus_value(client, address, value, unit=1, datatype="analog", conversion=""):
    """Write a value to a Modbus slave"""
    try:
        # Convert address to integer
        address = int(address)
        
        # Determine function code and prepare value based on address range and datatype
        if 1 <= address <= 9999:  # Coils
            # Convert value to boolean
            bool_value = bool(value)
            result = client.write_coil(address-1, bool_value, unit=unit)
        elif 40001 <= address <= 49999:  # Holding Registers
            if datatype.lower() == "analog":
                # Handle different data types
                if isinstance(value, float) or "float" in conversion.lower():
                    # Convert to float
                    float_value = float(value)
                    
                    # Different byte orders based on conversion string
                    if "little endian" in conversion.lower():
                        word_order = Endian.Little
                    else:
                        word_order = Endian.Big
                    
                    # Create builder
                    builder = BinaryPayloadBuilder(
                        byteorder=Endian.Big,
                        wordorder=word_order
                    )
                    
                    # Add float value
                    builder.add_32bit_float(float_value)
                    
                    # Get registers
                    registers = builder.to_registers()
                    
                    # Swap if needed
                    if "swap word" in conversion.lower():
                        registers = [registers[1], registers[0]]
                    
                    result = client.write_registers(address-40001, registers, unit=unit)
                else:
                    # Write as single register
                    result = client.write_register(address-40001, int(value), unit=unit)
            else:
                # Write as single register
                result = client.write_register(address-40001, int(value), unit=unit)
        else:
            logger.error(f"Invalid address or not writable: {address}")
            return False
        
        # Check for errors
        if result.isError():
            logger.error(f"Error writing to address {address}: {result}")
            return False
        
        return True
    
    except Exception as e:
        logger.error(f"Error writing to address {address}: {e}")
        return False

def test_direct_modbus(args):
    """Test Modbus slave directly using pymodbus"""
    print_info(f"Testing direct Modbus connection to {args.slave_ip}:{args.slave_port}...")
    
    try:
        # Create Modbus client
        client = ModbusTcpClient(
            host=args.slave_ip,
            port=args.slave_port,
            timeout=3
        )
        
        # Connect to slave
        if not client.connect():
            print_error(f"Failed to connect to {args.slave_ip}:{args.slave_port}")
            return
        
        print_success(f"Connected to {args.slave_ip}:{args.slave_port}")
        
        try:
            # Perform operation
            if args.operation == "read":
                # Read value
                print_info(f"Reading from address {args.address}...")
                
                value = read_modbus_value(
                    client=client,
                    address=args.address,
                    count=2 if args.datatype.lower() == "analog" and "float" in args.conversion.lower() else 1,
                    unit=args.slave_id,
                    datatype=args.datatype,
                    conversion=args.conversion
                )
                
                if value is not None:
                    print_success(f"Read value: {value}")
                else:
                    print_error("Failed to read value")
            
            elif args.operation == "write":
                # Check for value
                if args.value is None:
                    print_error("No value provided for write operation")
                    return
                
                # Write value
                print_info(f"Writing value {args.value} to address {args.address}...")
                
                success = write_modbus_value(
                    client=client,
                    address=args.address,
                    value=args.value,
                    unit=args.slave_id,
                    datatype=args.datatype,
                    conversion=args.conversion
                )
                
                if success:
                    print_success("Value written successfully")
                else:
                    print_error("Failed to write value")
            
            elif args.operation == "monitor":
                # Monitor value continuously
                print_info(f"Monitoring address {args.address}. Press Ctrl+C to stop...")
                
                try:
                    while True:
                        value = read_modbus_value(
                            client=client,
                            address=args.address,
                            count=2 if args.datatype.lower() == "analog" and "float" in args.conversion.lower() else 1,
                            unit=args.slave_id,
                            datatype=args.datatype,
                            conversion=args.conversion
                        )
                        
                        if value is not None:
                            print(f"Address {args.address}: {value}")
                        else:
                            print(f"Error reading address {args.address}")
                        
                        time.sleep(args.scan_rate)
                except KeyboardInterrupt:
                    print_info("Monitoring stopped")
        
        finally:
            # Disconnect
            client.close()
            print_info("Disconnected from Modbus slave")
    
    except Exception as e:
        print_error(f"Error: {e}")

def test_gateway_api(args):
    """Test the gateway's Modbus API"""
    print_info(f"Testing gateway Modbus API at {args.gateway_ip}:{args.gateway_port}...")
    
    # Build YAML configuration
    config = {
        "modbus": {
            "slaves": [
                {
                    "slave_name": args.slave_name,
                    "ip_address": args.slave_ip,
                    "port": args.slave_port,
                    "slave_id": args.slave_id,
                    "datatype": args.datatype,
                    "conversion": args.conversion,
                    "address": args.address,
                    "start_bit": args.start_bit,
                    "length_bit": args.length_bit,
                    "read_write_type": "read_write",
                    "scan_rate": args.scan_rate,
                    "scaling_type": args.scaling_type,
                    "formula": args.formula,
                    "scale": args.scale,
                    "offset": args.offset,
                    "clamp_to_span_low": args.clamp_to_span_low,
                    "clamp_to_span_high": args.clamp_to_span_high,
                    "clamp_to_zero": args.clamp_to_zero,
                    "max_users": args.max_users
                }
            ]
        }
    }
    
    # Convert to YAML
    yaml_str = yaml.dump(config)
    
    # Log configuration
    print_info("Using configuration:")
    print(yaml_str)
    
    try:
        # Send configuration to gateway
        endpoint = f"http://{args.gateway_ip}:{args.gateway_port}/api/modbus/configure"
        print_info(f"Sending configuration to {endpoint}...")
        
        response = requests.post(
            endpoint,
            data=yaml_str,
            headers={"Content-Type": "application/x-yaml"},
            timeout=5
        )
        
        if response.status_code == 200:
            print_success(f"Configuration sent successfully: {response.status_code}")
            print_info("Response:")
            print(json.dumps(response.json(), indent=2))
        else:
            print_error(f"Failed to send configuration: {response.status_code}")
            print_error(f"Response: {response.text}")
            return
        
        # Wait for gateway to process configuration
        print_info("Waiting for gateway to process configuration...")
        time.sleep(2)
        
        # Test reading value
        if args.operation in ["read", "monitor"]:
            endpoint = f"http://{args.gateway_ip}:{args.gateway_port}/api/modbus/values/{args.slave_name}"
            
            try:
                if args.operation == "monitor":
                    print_info(f"Monitoring {args.slave_name}. Press Ctrl+C to stop...")
                    
                    try:
                        while True:
                            response = requests.get(endpoint, timeout=5)
                            
                            if response.status_code == 200:
                                data = response.json()
                                if data.get("success"):
                                    print(f"{args.slave_name}: {data.get('value')}")
                                else:
                                    print(f"Error: {data.get('error')}")
                            else:
                                print(f"Error: {response.status_code} - {response.text}")
                            
                            time.sleep(args.scan_rate)
                    except KeyboardInterrupt:
                        print_info("Monitoring stopped")
                else:
                    response = requests.get(endpoint, timeout=5)
                    
                    if response.status_code == 200:
                        print_success("Value read successfully")
                        print_info("Response:")
                        print(json.dumps(response.json(), indent=2))
                    else:
                        print_error(f"Failed to read value: {response.status_code}")
                        print_error(f"Response: {response.text}")
            
            except requests.exceptions.RequestException as e:
                print_error(f"Error communicating with gateway: {e}")
        
        # Test writing value
        elif args.operation == "write":
            if args.value is None:
                print_error("No value provided for write operation")
                return
            
            endpoint = f"http://{args.gateway_ip}:{args.gateway_port}/api/modbus/write/{args.slave_name}"
            data = {"value": args.value}
            
            try:
                response = requests.post(
                    endpoint,
                    json=data,
                    headers={"Content-Type": "application/json"},
                    timeout=5
                )
                
                if response.status_code == 200:
                    print_success("Value written successfully")
                    print_info("Response:")
                    print(json.dumps(response.json(), indent=2))
                else:
                    print_error(f"Failed to write value: {response.status_code}")
                    print_error(f"Response: {response.text}")
            
            except requests.exceptions.RequestException as e:
                print_error(f"Error communicating with gateway: {e}")
    
    except requests.exceptions.RequestException as e:
        print_error(f"Error communicating with gateway: {e}")
    except Exception as e:
        print_error(f"Error: {e}")

def generate_yaml_config(args):
    """Generate a YAML configuration file based on command-line arguments"""
    config = {
        "modbus": {
            "master_config": {
                "max_users": args.max_users
            },
            "slaves": [
                {
                    "slave_name": args.slave_name,
                    "ip_address": args.slave_ip,
                    "port": args.slave_port,
                    "slave_id": args.slave_id,
                    "datatype": args.datatype,
                    "conversion": args.conversion,
                    "address": args.address,
                    "start_bit": args.start_bit,
                    "length_bit": args.length_bit,
                    "read_write_type": "read_write",
                    "scan_rate": args.scan_rate,
                    "scaling_type": args.scaling_type,
                    "formula": args.formula,
                    "scale": args.scale,
                    "offset": args.offset,
                    "clamp_to_span_low": args.clamp_to_span_low,
                    "clamp_to_span_high": args.clamp_to_span_high,
                    "clamp_to_zero": args.clamp_to_zero
                }
            ]
        }
    }
    
    # Convert to YAML
    yaml_str = yaml.dump(config, default_flow_style=False)
    
    # Save to file
    output_file = args.output or "modbus_config.yaml"
    with open(output_file, "w") as f:
        f.write(yaml_str)
    
    print_success(f"YAML configuration saved to {output_file}")
    print_info("Configuration:")
    print(yaml_str)

def parse_arguments():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(description='Modbus Client for testing')
    
    # Mode selection
    parser.add_argument('--mode', choices=['direct', 'gateway', 'generate'], default='direct',
                        help='Mode of operation: direct=test slave directly, gateway=use gateway API, generate=generate YAML config')
    
    # Common arguments
    parser.add_argument('--slave-name', default='TestSlave',
                        help='Name of the slave device (default: TestSlave)')
    parser.add_argument('--slave-ip', default='192.168.47.100',
                        help='IP address of the Modbus slave (default: 192.168.47.100)')
    parser.add_argument('--slave-port', type=int, default=502,
                        help='Port of the Modbus slave (default: 502)')
    parser.add_argument('--slave-id', type=int, default=1,
                        help='Modbus unit ID (default: 1)')
    parser.add_argument('--operation', choices=['read', 'write', 'monitor'], default='read',
                        help='Operation to perform (default: read)')
    parser.add_argument('--address', type=int, default=40001,
                        help='Modbus address to read/write (default: 40001)')
    parser.add_argument('--datatype', choices=['analog', 'discrete'], default='analog',
                        help='Data type (default: analog)')
    parser.add_argument('--conversion', default='FLOAT, Big Endian, Swap Word (CDAB)',
                        help='Conversion format (default: FLOAT, Big Endian, Swap Word (CDAB))')
    parser.add_argument('--value', type=str,
                        help='Value to write (required for write operation)')
    parser.add_argument('--scan-rate', type=int, default=1,
                        help='Scan rate in seconds for monitoring (default: 1)')
    
    # Arguments for gateway mode
    parser.add_argument('--gateway-ip', default='192.168.47.190',
                        help='IP address of the gateway (default: 192.168.47.190)')
    parser.add_argument('--gateway-port', type=int, default=5000,
                        help='Port of the gateway API (default: 5000)')
    
    # Advanced arguments
    parser.add_argument('--start-bit', type=int, default=0,
                        help='Start bit (0-15) (default: 0)')
    parser.add_argument('--length-bit', type=int, default=16,
                        help='Length in bits (1-64) (default: 16)')
    parser.add_argument('--scaling-type', default='',
                        help='Scaling type (default: none)')
    parser.add_argument('--formula', default='',
                        help='Scaling formula (default: none)')
    parser.add_argument('--scale', type=float, default=0,
                        help='Scale factor (default: 0)')
    parser.add_argument('--offset', type=float, default=0,
                        help='Offset value (default: 0)')
    parser.add_argument('--clamp-to-span-low', action='store_true',
                        help='Clamp to span low')
    parser.add_argument('--clamp-to-span-high', action='store_true',
                        help='Clamp to span high')
    parser.add_argument('--clamp-to-zero', action='store_true',
                        help='Clamp to zero if out of range')
    parser.add_argument('--max-users', type=int, default=10,
                        help='Maximum number of users when used as a client (default: 10)')
    
    # Arguments for generate mode
    parser.add_argument('--output', type=str,
                        help='Output file for generated YAML (default: modbus_config.yaml)')
    
    # Convert value to appropriate type if provided
    args = parser.parse_args()
    
    if args.value:
        # Try to convert value to appropriate type
        if args.datatype.lower() == 'discrete':
            # Convert to boolean
            if args.value.lower() in ['true', '1', 'yes', 'y']:
                args.value = True
            else:
                args.value = False
        elif "float" in args.conversion.lower():
            # Convert to float
            try:
                args.value = float(args.value)
            except ValueError:
                print_error(f"Invalid float value: {args.value}")
                sys.exit(1)
        else:
            # Convert to integer
            try:
                args.value = int(args.value)
            except ValueError:
                print_error(f"Invalid integer value: {args.value}")
                sys.exit(1)
    
    return args

def main():
    """Main function"""
    args = parse_arguments()
    
    print_separator()
    print_info("Modbus Client for Testing")
    print_separator()
    
    # Execute appropriate mode
    if args.mode == 'direct':
        test_direct_modbus(args)
    elif args.mode == 'gateway':
        test_gateway_api(args)
    elif args.mode == 'generate':
        generate_yaml_config(args)
    
    print_separator()
    print_success("Done")

if __name__ == "__main__":
    main()
