#!/usr/bin/env python3
"""
Modbus Master Module for IoT Gateway

This module implements a Modbus master to communicate with Modbus slaves.
It reads configuration from a YAML file and stores tag definitions in a CSV file.
Supports comprehensive data type conversions and scaling methods.
"""
####multiple addresses from the same slave in order or not in order reading in bulk
####


import csv
import os
import yaml
import time
import math
import struct
import logging
import threading
from pymodbus.client.sync import ModbusTcpClient, ModbusSerialClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder, BinaryPayloadBuilder
from pymodbus.exceptions import ModbusException

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Path for CSV storage
CSV_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modbus_tags.csv")

# CSV Headers - based on required arguments
CSV_HEADERS = [
    "slave_name", "ip_address", "port", "slave_id", "datatype", "conversion",
    "address", "start_bit", "length_bit", "read_write_type", "scan_rate",
    "scaling_type", "formula", "scale", "offset", "clamp_to_span_low",
    "clamp_to_span_high", "clamp_to_zero", "max_users", "span_high", "span_low",
    "input_high", "input_low"
]

# Default values for optional parameters
DEFAULT_VALUES = {
    "port": 502,
    "slave_id": 1,
    "start_bit": 0,
    "length_bit": 16,
    "read_write_type": "read_write",
    "scan_rate": 1,
    "scaling_type": "No Scale",
    "formula": "",
    "scale": 0,
    "offset": 0,
    "clamp_to_span_low": False,
    "clamp_to_span_high": False,
    "clamp_to_zero": False,
    "max_users": 10,
    "conversion": "FLOAT, Big Endian (ABCD)",
    "span_high": 100.0,
    "span_low": 0.0,
    "input_high": 100.0,
    "input_low": 0.0
}

# Supported data conversion types
DATA_CONVERSIONS = {
    # INT64 types
    "INT64, Little Endian, Swap Byte (GHEFCDAB)": {"byte_order": "little", "word_order": "little", "size": 4, "type": "int64"},
    "INT64, Big Endian, Swap Byte (BADCFEHG)": {"byte_order": "big", "word_order": "little", "size": 4, "type": "int64"},  
    "INT64, Little Endian (HGFEDCBA)": {"byte_order": "little", "word_order": "big", "size": 4, "type": "int64"},
    "INT64, Big Endian (ABCDEFGH)": {"byte_order": "big", "word_order": "big", "size": 4, "type": "int64"},
    
    # UINT64 types
    "UINT64, Big Endian (ABCDEFGH)": {"byte_order": "big", "word_order": "big", "size": 4, "type": "uint64"},
    "UINT64, Little Endian (HGFEDCBA)": {"byte_order": "little", "word_order": "big", "size": 4, "type": "uint64"},
    "UINT64, Big Endian, Swap Byte (BADCFEHG)": {"byte_order": "big", "word_order": "little", "size": 4, "type": "uint64"},
    "UINT64, Little Endian, Swap Byte (GHEFCDAB)": {"byte_order": "little", "word_order": "little", "size": 4, "type": "uint64"},
    
    # UINT types
    "UINT, Big Endian (ABCD)": {"byte_order": "big", "word_order": "big", "size": 2, "type": "uint32"},
    "UINT, Big Endian, Swap Word (CDAB)": {"byte_order": "big", "word_order": "little", "size": 2, "type": "uint32"},
    "UINT, Packed BCD, Big Endian (ABCD)": {"byte_order": "big", "word_order": "big", "size": 2, "type": "bcd_uint32"},
    "UINT, Packed BCD, Big Endian, Swap Word (CDAB)": {"byte_order": "big", "word_order": "little", "size": 2, "type": "bcd_uint32"},
    "UINT, Little Endian (DCBA)": {"byte_order": "little", "word_order": "big", "size": 2, "type": "uint32"},
    
    # INT types
    "INT, Big Endian (ABCD)": {"byte_order": "big", "word_order": "big", "size": 2, "type": "int32"},
    "INT, Big Endian, Swap Word (CDAB)": {"byte_order": "big", "word_order": "little", "size": 2, "type": "int32"},
    "INT, Little Endian (DCBA)": {"byte_order": "little", "word_order": "big", "size": 2, "type": "int32"},
    "INT, Text to Number": {"byte_order": "big", "word_order": "big", "size": 2, "type": "text_to_num"},
    
    # Special types
    "UINT32, Modicon Double Precision (reg1*10000+reg2)": {"byte_order": "big", "word_order": "big", "size": 2, "type": "modicon"},
    
    # Float types
    "FLOAT, Big Endian (ABCD)": {"byte_order": "big", "word_order": "big", "size": 2, "type": "float32"},
    "FLOAT, Big Endian, Swap Word (CDAB)": {"byte_order": "big", "word_order": "little", "size": 2, "type": "float32"},
    "FLOAT, Little Endian, Swap Word (BADC)": {"byte_order": "little", "word_order": "little", "size": 2, "type": "float32"},
    "FLOAT, Little Endian (DCBA)": {"byte_order": "little", "word_order": "big", "size": 2, "type": "float32"},
    
    # Double types
    "DOUBLE, Big Endian (ABCDEFGH)": {"byte_order": "big", "word_order": "big", "size": 4, "type": "float64"},
    "DOUBLE, Little Endian (HGFEDCBA)": {"byte_order": "little", "word_order": "big", "size": 4, "type": "float64"}
}

# Supported scaling types
SCALING_TYPES = [
    "No Scale",
    "Scale 0-100% Input to Span",
    "Linear Scale, MX+B",
    "Scale Defined Input H/L to Span",
    "Scale 12-Bit Input to Span",
    "Scale 0-100% Square Root Input",
    "Square Root of (Input/(F2-F1)) to Span"
]

class ModbusMaster:
    """Modbus Master class to communicate with Modbus slaves"""
    
    def __init__(self, yaml_config=None):
        self.clients = {}  # Dictionary to store clients by slave_name
        self.tags = {}     # Dictionary to store tag configurations
        self.csv_file = CSV_FILE_PATH
        self.running = False
        self.scan_thread = None
        self.tag_values = {}  # Store latest values
        
        # Load configuration if provided
        if yaml_config:
            self.load_config_from_yaml(yaml_config)
    
    def load_config_from_yaml(self, yaml_config):
        """Load configuration from YAML string or file"""
        if isinstance(yaml_config, str):
            if os.path.isfile(yaml_config):
                # It's a file path
                with open(yaml_config, 'r') as f:
                    config = yaml.safe_load(f)
            else:
                # It's a YAML string
                config = yaml.safe_load(yaml_config)
        else:
            # It's already a dictionary
            config = yaml_config
        
        # Process configuration
        if "modbus" not in config:
            raise ValueError("Missing 'modbus' section in configuration")
        
        modbus_config = config["modbus"]
        
        # Process slave configurations
        for slave_config in modbus_config.get("slaves", []):
            self._process_slave_config(slave_config)
    
    def _process_slave_config(self, slave_config):
        """Process a single slave configuration"""
        # Check required fields
        required_fields = ["slave_name", "ip_address"]
        for field in required_fields:
            if field not in slave_config:
                raise ValueError(f"Missing required field '{field}' in slave configuration")
        
        # Set default values for optional fields
        for key, default_value in DEFAULT_VALUES.items():
            if key not in slave_config:
                slave_config[key] = default_value
        
        # Save tag configuration
        slave_name = slave_config["slave_name"]
        self.tags[slave_name] = slave_config
        
        # Save to CSV
        self._save_to_csv()
        
        # Create client if it doesn't exist
        if slave_name not in self.clients:
            self._create_client(slave_config)
    
    def _create_client(self, slave_config):
        """Create a Modbus client for a slave"""
        slave_name = slave_config["slave_name"]
        ip_address = slave_config["ip_address"]
        port = int(slave_config["port"])
        
        try:
            client = ModbusTcpClient(
                host=ip_address,
                port=port,
                timeout=3
            )
            self.clients[slave_name] = client
            logger.info(f"Created Modbus client for {slave_name} at {ip_address}:{port}")
            return True
        except Exception as e:
            logger.error(f"Error creating Modbus client for {slave_name}: {e}")
            return False
    
    def connect_all(self):
        """Connect to all configured slaves"""
        for slave_name, client in self.clients.items():
            try:
                connected = client.connect()
                if connected:
                    logger.info(f"Connected to Modbus slave: {slave_name}")
                else:
                    logger.warning(f"Failed to connect to Modbus slave: {slave_name}")
            except Exception as e:
                logger.error(f"Error connecting to Modbus slave {slave_name}: {e}")
    
    def disconnect_all(self):
        """Disconnect from all slaves"""
        for slave_name, client in self.clients.items():
            try:
                client.close()
                logger.info(f"Disconnected from Modbus slave: {slave_name}")
            except Exception as e:
                logger.error(f"Error disconnecting from Modbus slave {slave_name}: {e}")
    
    def _save_to_csv(self):
        """Save all tag configurations to CSV"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.csv_file), exist_ok=True)
            
            # Write to CSV
            with open(self.csv_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
                writer.writeheader()
                
                # Write each tag to CSV
                for slave_name, tag in self.tags.items():
                    # Ensure all fields are present
                    for header in CSV_HEADERS:
                        if header not in tag:
                            tag[header] = DEFAULT_VALUES.get(header, "")
                    
                    writer.writerow(tag)
            
            logger.info(f"Saved {len(self.tags)} tag configurations to {self.csv_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving to CSV: {e}")
            return False
    
    def load_from_csv(self):
        """Load tag configurations from CSV"""
        if not os.path.exists(self.csv_file):
            logger.warning(f"CSV file not found: {self.csv_file}")
            return False
        
        try:
            with open(self.csv_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                
                # Clear existing tags
                self.tags = {}
                
                # Read each row as a tag configuration
                for row in reader:
                    slave_name = row["slave_name"]
                    self.tags[slave_name] = row
                    
                    # Create client if it doesn't exist
                    if slave_name not in self.clients:
                        self._create_client(row)
            
            logger.info(f"Loaded {len(self.tags)} tag configurations from {self.csv_file}")
            return True
        except Exception as e:
            logger.error(f"Error loading from CSV: {e}")
            return False
    
    def read_data(self, slave_name, address, count=None, unit=None, datatype=None, conversion=None):
        """Read data from a Modbus slave and apply scaling"""
        if slave_name not in self.clients:
            logger.error(f"Unknown slave: {slave_name}")
            return None
        
        client = self.clients[slave_name]
        tag = self.tags.get(slave_name)
        
        # If tag exists, use its values for missing parameters
        if tag:
            if unit is None:
                unit = int(tag.get("slave_id", 1))
            if datatype is None:
                datatype = tag.get("datatype", "analog")
            if conversion is None:
                conversion = tag.get("conversion", "FLOAT, Big Endian (ABCD)")
        else:
            # Use defaults if tag doesn't exist
            unit = unit or 1
            datatype = datatype or "analog"
            conversion = conversion or "FLOAT, Big Endian (ABCD)"
        
        # Determine count based on conversion type if not specified
        if count is None:
            if conversion in DATA_CONVERSIONS:
                count = DATA_CONVERSIONS[conversion]["size"]
            else:
                count = 2 if "float" in conversion.lower() or "double" in conversion.lower() else 1
        
        # Check if client is connected
        if not client.is_socket_open():
            try:
                client.connect()
            except Exception as e:
                logger.error(f"Error connecting to {slave_name}: {e}")
                return None
        
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
                logger.error(f"Error reading from {slave_name} at address {address}: {result}")
                return None
            
            # Process the result based on datatype and conversion
            raw_value = self._process_read_result(result, datatype, conversion)
            
            # Apply scaling if tag exists and we have a valid raw value
            if tag and raw_value is not None:
                return self._apply_scaling(raw_value, tag)
            
            return raw_value
        
        except Exception as e:
            logger.error(f"Error reading from {slave_name} at address {address}: {e}")
            return None
    
    def write_data(self, slave_name, address, value, unit=1, datatype="analog", conversion=""):
        """Write data to a Modbus slave"""
        if slave_name not in self.clients:
            logger.error(f"Unknown slave: {slave_name}")
            return False
        
        client = self.clients[slave_name]
        
        # Check if client is connected
        if not client.is_socket_open():
            try:
                client.connect()
            except Exception as e:
                logger.error(f"Error connecting to {slave_name}: {e}")
                return False
        
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
                    if isinstance(value, float):
                        # Convert float to registers based on conversion
                        registers = self._convert_float_to_registers(value, conversion)
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
                logger.error(f"Error writing to {slave_name} at address {address}: {result}")
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"Error writing to {slave_name} at address {address}: {e}")
            return False
    
    def _process_read_result(self, result, datatype, conversion):
        """Process read result based on datatype and conversion"""
        # Handle discrete datatype
        if datatype.lower() == "discrete":
            return result.bits[0] if hasattr(result, 'bits') and result.bits else None
        
        # For analog data types, first check if we have registers
        if not (hasattr(result, 'registers') and result.registers):
            return None
            
        # Get the conversion specification from our dictionary
        conv_spec = DATA_CONVERSIONS.get(conversion)
        if not conv_spec:
            # Use default conversion if specified conversion not found
            logger.warning(f"Conversion '{conversion}' not found, using default")
            conv_spec = DATA_CONVERSIONS.get("FLOAT, Big Endian (ABCD)")
            
        registers = result.registers
        conv_type = conv_spec["type"]
        size = conv_spec["size"]
        
        # Make sure we have enough registers
        if len(registers) < size:
            logger.error(f"Not enough registers for conversion {conversion}, need {size}, got {len(registers)}")
            return None
            
        # Special handling for specific types
        if conv_type == "modicon":
            # Modicon Double Precision: reg1*10000+reg2
            if len(registers) >= 2:
                return registers[0] * 10000 + registers[1]
            return registers[0]
            
        elif conv_type == "text_to_num":
            # Convert text to number
            try:
                # Convert each register to ASCII char and join
                text = ''.join([chr((r >> 8) & 0xFF) + chr(r & 0xFF) for r in registers])
                # Strip null and non-printable chars and convert to float
                return float(''.join(c for c in text if c.isprintable()))
            except ValueError:
                return 0
                
        elif conv_type == "bcd_uint32":
            # BCD encoding: each 4-bit nibble represents a decimal digit
            result = 0
            for reg in registers:
                # Process each byte in the register
                for nibble_pos in range(3, -1, -1):  # Process 4 nibbles (2 bytes)
                    nibble = (reg >> (nibble_pos * 4)) & 0xF
                    if 0 <= nibble <= 9:  # Valid BCD digit
                        result = result * 10 + nibble
            return result
        
        # Use PyModbus decoder for standard types
        byte_order = Endian.Big if conv_spec["byte_order"] == "big" else Endian.Little
        word_order = Endian.Big if conv_spec["word_order"] == "big" else Endian.Little
        
        # Create decoder
        decoder = BinaryPayloadDecoder.fromRegisters(
            registers, 
            byteorder=byte_order,
            wordorder=word_order
        )
        
        # Decode based on type
        if conv_type == "int32":
            return decoder.decode_32bit_int()
        elif conv_type == "uint32":
            return decoder.decode_32bit_uint()
        elif conv_type == "int64":
            return decoder.decode_64bit_int()
        elif conv_type == "uint64":
            return decoder.decode_64bit_uint()
        elif conv_type == "float32":
            return decoder.decode_32bit_float()
        elif conv_type == "float64":
            return decoder.decode_64bit_float()
        
        # Default handling for registers if type wasn't processed
        if len(registers) == 1:
            return registers[0]
        return registers
        
    def _apply_scaling(self, raw_value, tag):
        """Apply scaling to a raw value based on tag configuration
        
        Scaling Types:
        1. No Scale - Raw register value (no conversion)
        2. Scale 0-100% Input to Span - Maps 0-100% input to defined Span Low/Span High
        3. Linear Scale, MX+B - Applies linear formula: Scaled_Value = (M * Raw_Value) + B
        4. Scale Defined Input H/L to Span - Maps custom input range to span
        5. Scale 12-Bit Input to Span - Converts 12-bit raw values (0-4095) to engineering units
        6. Scale 0-100% Square Root Input - For flow/pressure: Scaled_Value = √(Raw_Value) * (Span_High - Span_Low)
        7. Square Root of (Input/(F2-F1)) to Span - Advanced square root scaling with offset
        """
        # Make sure we have a valid value
        if raw_value is None:
            return None
            
        try:
            # Convert to float for calculations
            raw_value = float(raw_value)
            
            # Get scaling parameters from tag
            scaling_type = tag.get("scaling_type", "No Scale")
            span_high = float(tag.get("span_high", 100.0))
            span_low = float(tag.get("span_low", 0.0))
            scale = float(tag.get("scale", 1.0))  # M in MX+B
            offset = float(tag.get("offset", 0.0))  # B in MX+B
            input_high = float(tag.get("input_high", 100.0))
            input_low = float(tag.get("input_low", 0.0))
            formula = tag.get("formula", "")
            
            # Apply scaling based on type
            scaled_value = raw_value  # Default: no scaling
            
            if scaling_type == "No Scale":
                # No scaling, use raw value
                scaled_value = raw_value
                
            elif scaling_type == "Scale 0-100% Input to Span":
                # Map 0-100% input to span
                scaled_value = span_low + (raw_value / 100.0) * (span_high - span_low)
                
            elif scaling_type == "Linear Scale, MX+B":
                # Apply linear formula: Scaled_Value = (M * Raw_Value) + B
                scaled_value = (scale * raw_value) + offset
                
            elif scaling_type == "Scale Defined Input H/L to Span":
                # Map custom input range to span
                # Formula: (RawValue - InputLow) / (InputHigh - InputLow) * (SpanHigh - SpanLow) + SpanLow
                if input_high != input_low:  # Avoid division by zero
                    ratio = (raw_value - input_low) / (input_high - input_low)
                    scaled_value = span_low + ratio * (span_high - span_low)
                else:
                    scaled_value = raw_value
                    
            elif scaling_type == "Scale 12-Bit Input to Span":
                # Convert 12-bit values (0-4095) to engineering units
                if raw_value >= 0 and raw_value <= 4095:
                    scaled_value = span_low + (raw_value / 4095.0) * (span_high - span_low)
                else:
                    scaled_value = raw_value
                    
            elif scaling_type == "Scale 0-100% Square Root Input":
                # For flow/pressure: Scaled_Value = √(Raw_Value) * (Span_High - Span_Low)
                if raw_value >= 0:  # Can't take square root of negative
                    root_value = math.sqrt(raw_value / 100.0)  # Convert to 0-1 range first
                    scaled_value = span_low + root_value * (span_high - span_low)
                else:
                    scaled_value = span_low
                    
            elif scaling_type == "Square Root of (Input/(F2-F1)) to Span":
                # Advanced square root scaling with offset compensation
                # Assuming F2 and F1 are stored in input_high and input_low
                if input_high != input_low and raw_value >= 0:  # Avoid division by zero
                    ratio = raw_value / (input_high - input_low)
                    if ratio >= 0:  # Can't take square root of negative
                        root_value = math.sqrt(ratio)
                        scaled_value = span_low + root_value * (span_high - span_low)
                    else:
                        scaled_value = span_low
                else:
                    scaled_value = raw_value
            
            # Apply custom formula if provided (with caution!)
            if formula and formula.strip():
                try:
                    # Create a safe namespace with only essential math functions
                    safe_dict = {
                        'x': scaled_value,  # Use already scaled value as input
                        'math': math,
                        'abs': abs,
                        'min': min,
                        'max': max,
                        'round': round
                    }
                    # Evaluate formula with limited namespace
                    scaled_value = eval(formula, {"__builtins__": {}}, safe_dict)
                except Exception as e:
                    logger.error(f"Error evaluating custom formula: {e}")
            
            # Apply clamping if configured
            if tag.get("clamp_to_span_low", False) and scaled_value < span_low:
                scaled_value = span_low
                
            if tag.get("clamp_to_span_high", False) and scaled_value > span_high:
                scaled_value = span_high
                
            if tag.get("clamp_to_zero", False) and (scaled_value < span_low or scaled_value > span_high):
                scaled_value = 0.0
            
            return scaled_value
            
        except Exception as e:
            logger.error(f"Error applying scaling: {e}")
            return raw_value  # Return original value if scaling fails
    
    def _convert_float_to_registers(self, value, conversion):
        """Convert a float value to Modbus registers based on conversion string"""
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
        builder.add_32bit_float(float(value))
        
        # Get registers
        registers = builder.to_registers()
        
        # Swap if needed
        if "swap word" in conversion.lower():
            return [registers[1], registers[0]]
        
        return registers
    
    def start_scanning(self):
        """Start scanning all tags based on their scan rates"""
        if self.running:
            logger.warning("Scanning already running")
            return
        
        self.running = True
        self.scan_thread = threading.Thread(target=self._scan_loop)
        self.scan_thread.daemon = True
        self.scan_thread.start()
        logger.info("Started scanning tags")
    
    def stop_scanning(self):
        """Stop scanning tags"""
        self.running = False
        if self.scan_thread:
            self.scan_thread.join(timeout=2)
            self.scan_thread = None
        logger.info("Stopped scanning tags")
    
    def _scan_loop(self):
        """Main loop for scanning tags"""
        while self.running:
            scan_start = time.time()
            
            # Group tags by scan rate
            scan_groups = {}
            for slave_name, tag in self.tags.items():
                scan_rate = int(tag.get("scan_rate", 1))
                if scan_rate not in scan_groups:
                    scan_groups[scan_rate] = []
                scan_groups[scan_rate].append(tag)
            
            # Process each scan group
            for scan_rate, tags in scan_groups.items():
                # Check if it's time to scan this group
                if scan_start % scan_rate < 1:
                    for tag in tags:
                        slave_name = tag["slave_name"]
                        address = int(tag["address"])
                        unit = int(tag["slave_id"])
                        datatype = tag["datatype"]
                        conversion = tag["conversion"]
                        
                        # Read the tag
                        value = self.read_data(
                            slave_name=slave_name,
                            address=address,
                            unit=unit,
                            datatype=datatype,
                            conversion=conversion
                        )
                        
                        # Store the value
                        if value is not None:
                            self.tag_values[slave_name] = value
            
            # Sleep until next scan
            time.sleep(1)
    
    def get_tag_value(self, slave_name):
        """Get the latest value for a tag"""
        return self.tag_values.get(slave_name)
    
    def get_all_tag_values(self):
        """Get all tag values"""
        return self.tag_values

def load_yaml_config(yaml_file_or_string):
    """Load YAML configuration from a file or string"""
    try:
        # Check if it's a file path
        if os.path.isfile(yaml_file_or_string):
            with open(yaml_file_or_string, 'r') as f:
                config = yaml.safe_load(f)
        else:
            # It's a YAML string
            config = yaml.safe_load(yaml_file_or_string)
        
        return config
    except Exception as e:
        logger.error(f"Error loading YAML configuration: {e}")
        return None

def create_master_from_yaml(yaml_file_or_string):
    """Create a ModbusMaster instance from YAML configuration"""
    config = load_yaml_config(yaml_file_or_string)
    if not config:
        return None
    
    master = ModbusMaster(config)
    return master

def main():
    """Main function for standalone execution"""
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Modbus Master')
    parser.add_argument('--config', type=str, required=True,
                        help='Path to YAML configuration file')
    parser.add_argument('--connect', action='store_true',
                        help='Connect to all slaves and start scanning')
    
    args = parser.parse_args()
    
    # Create master from YAML
    master = create_master_from_yaml(args.config)
    if not master:
        logger.error("Failed to create Modbus master")
        return
    
    # Connect and start scanning if requested
    if args.connect:
        master.connect_all()
        master.start_scanning()
        
        try:
            # Keep running until Ctrl+C
            logger.info("Modbus master running. Press Ctrl+C to exit...")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopping Modbus master...")
        finally:
            master.stop_scanning()
            master.disconnect_all()

if __name__ == "__main__":
    main()
