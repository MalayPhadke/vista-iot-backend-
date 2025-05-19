#!/usr/bin/env python3
import csv
import os
import socket
import threading
import time
# Updated imports for pymodbus 3.5.4
from pymodbus.client import ModbusTcpClient, ModbusSerialClient
from pymodbus.server import StartTcpServer, StartSerialServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext, ModbusSlaveContext
import pymodbus.exceptions

# Data types and conversion formats
DATA_TYPES = {
    "Analog": {
        "FLOAT": {
            "Big Endian": {"Normal": "ABCD", "Swap Word": "CDAB"},
            "Little Endian": {"Normal": "DCBA", "Swap Word": "BADC"}
        },
        "INT16": {"size": 16},
        "INT32": {"size": 32},
        "UINT16": {"size": 16},
        "UINT32": {"size": 32}
    },
    "Digital": {
        "BOOL": {"size": 1}
    }
}

# Global configuration
MODBUS_CONFIG = {
    "address_ranges": [],  # Example: [{"start": 40001, "end": 40100}, {"start": 30001, "end": 30050}]
    "ip": "0.0.0.0",
    "port": 502,
    "unit_ids": [1],  # Default unit ID
    "scan_rate": 1,  # Default scan rate in seconds
    "mode": "both"  # 'master', 'slave', or 'both'
}

# CSV file path for tag storage
TAG_CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modbus_tags.csv")

# CSV Headers
TAG_CSV_HEADERS = [
    "Name", "Data_Type", "Conversion", "Address", "Start_Bit", "Length_Bit",
    "Span_High", "Span_Low", "Default_Value", "Scan_Rate", "Read_Write",
    "Description", "Scaling_Type", "Formula", "Scale", "Offset",
    "Clamp_to_Span", "Clamp_High", "Clamp_Low", "Clamp_to_Zero"
]

class ModbusTagManager:
    def __init__(self, csv_file=TAG_CSV_FILE):
        self.csv_file = csv_file
        self.tags = {}
        self.load_tags()
        
    def load_tags(self):
        """Load tags from CSV file"""
        if not os.path.exists(self.csv_file):
            self._create_csv_file()
            return
        
        try:
            with open(self.csv_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.tags[row['Name']] = row
        except Exception as e:
            print(f"Error loading tags: {str(e)}")
    
    def _create_csv_file(self):
        """Create a new CSV file with headers"""
        try:
            with open(self.csv_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=TAG_CSV_HEADERS)
                writer.writeheader()
        except Exception as e:
            print(f"Error creating CSV file: {str(e)}")
    
    def save_tags(self):
        """Save all tags to CSV file"""
        try:
            with open(self.csv_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=TAG_CSV_HEADERS)
                writer.writeheader()
                for tag in self.tags.values():
                    writer.writerow(tag)
            return True
        except Exception as e:
            print(f"Error saving tags: {str(e)}")
            return False
    
    def add_tag(self, tag_data):
        """Add a new tag or update existing tag"""
        # Validate required fields
        required_fields = ["Name", "Data_Type", "Address"]
        for field in required_fields:
            if field not in tag_data or not tag_data[field]:
                raise ValueError(f"Missing required field: {field}")
        
        # Set default values for optional fields
        tag_data.setdefault("Start_Bit", "0")
        tag_data.setdefault("Length_Bit", "16")  # Default to 16-bit
        tag_data.setdefault("Span_High", "100")
        tag_data.setdefault("Span_Low", "0")
        tag_data.setdefault("Default_Value", "0.0")
        tag_data.setdefault("Scan_Rate", "1")
        tag_data.setdefault("Read_Write", "Read Write")
        tag_data.setdefault("Scaling_Type", "No Scale")
        tag_data.setdefault("Scale", "0")
        tag_data.setdefault("Offset", "0")
        tag_data.setdefault("Clamp_to_Span", "False")
        tag_data.setdefault("Clamp_High", "False")
        tag_data.setdefault("Clamp_Low", "False")
        tag_data.setdefault("Clamp_to_Zero", "False")
        
        # Add or update tag
        self.tags[tag_data["Name"]] = tag_data
        
        # Save to CSV
        return self.save_tags()
    
    def get_tag(self, tag_name):
        """Get a tag by name"""
        return self.tags.get(tag_name)
    
    def get_all_tags(self):
        """Get all tags"""
        return list(self.tags.values())
    
    def delete_tag(self, tag_name):
        """Delete a tag by name"""
        if tag_name in self.tags:
            del self.tags[tag_name]
            return self.save_tags()
        return False

class ModbusMaster:
    def __init__(self, ip="localhost", port=502, unit_id=1):
        self.ip = ip
        self.port = port
        self.unit_id = unit_id
        self.client = None
        self.connected = False
        self.tag_manager = ModbusTagManager()
        self.values = {}  # To store the latest values
        self.running = False
        self.thread = None
    
    def connect(self):
        """Connect to Modbus slave"""
        try:
            self.client = ModbusTcpClient(self.ip, port=self.port)
            self.connected = self.client.connect()
            return self.connected
        except Exception as e:
            print(f"Connection error: {str(e)}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from Modbus slave"""
        if self.client:
            self.client.close()
        self.connected = False
    
    def read_value(self, address, data_type="Analog", conversion="FLOAT, Big Endian, Normal"):
        """Read a value from a Modbus register"""
        if not self.connected:
            if not self.connect():
                return None
        
        try:
            # Determine register type based on address
            if 1 <= address <= 9999:  # Coils
                result = self.client.read_coils(address-1, 1, unit=self.unit_id)
                if not result.isError():
                    return result.bits[0]
            elif 10001 <= address <= 19999:  # Discrete Inputs
                result = self.client.read_discrete_inputs(address-10001, 1, unit=self.unit_id)
                if not result.isError():
                    return result.bits[0]
            elif 30001 <= address <= 39999:  # Input Registers
                count = 2 if "FLOAT" in data_type or "INT32" in data_type else 1
                result = self.client.read_input_registers(address-30001, count, unit=self.unit_id)
                if not result.isError():
                    return self._process_value(result.registers, data_type, conversion)
            elif 40001 <= address <= 49999:  # Holding Registers
                count = 2 if "FLOAT" in data_type or "INT32" in data_type else 1
                result = self.client.read_holding_registers(address-40001, count, unit=self.unit_id)
                if not result.isError():
                    return self._process_value(result.registers, data_type, conversion)
            
            return None
        except Exception as e:
            print(f"Error reading address {address}: {str(e)}")
            return None
    
    def write_value(self, address, value, data_type="Analog", conversion="FLOAT, Big Endian, Normal"):
        """Write a value to a Modbus register"""
        if not self.connected:
            if not self.connect():
                return False
        
        try:
            # Determine register type based on address
            if 1 <= address <= 9999:  # Coils
                result = self.client.write_coil(address-1, bool(value), unit=self.unit_id)
                return not result.isError()
            elif 40001 <= address <= 49999:  # Holding Registers
                if "FLOAT" in data_type or "INT32" in data_type:
                    # Convert to registers based on conversion type
                    registers = self._value_to_registers(value, data_type, conversion)
                    result = self.client.write_registers(address-40001, registers, unit=self.unit_id)
                else:
                    result = self.client.write_register(address-40001, int(value), unit=self.unit_id)
                return not result.isError()
            
            return False
        except Exception as e:
            print(f"Error writing to address {address}: {str(e)}")
            return False
    
    def _process_value(self, registers, data_type, conversion):
        """Process registers based on data type and conversion"""
        # Simplified implementation - would need more detailed conversion logic
        # in a full implementation based on endianness and word swapping
        if "FLOAT" in data_type:
            if len(registers) >= 2:
                # This is a simplified implementation - real code would handle
                # byte order and word swapping based on the conversion parameter
                import struct
                
                # ABCD - Big Endian, Normal
                if "Big Endian, Normal" in conversion:
                    bytes_val = struct.pack('>HH', registers[0], registers[1])
                # CDAB - Big Endian, Swap Word
                elif "Big Endian, Swap Word" in conversion:
                    bytes_val = struct.pack('>HH', registers[1], registers[0])
                # DCBA - Little Endian, Normal
                elif "Little Endian, Normal" in conversion:
                    bytes_val = struct.pack('<HH', registers[1], registers[0])
                # BADC - Little Endian, Swap Word
                elif "Little Endian, Swap Word" in conversion:
                    bytes_val = struct.pack('<HH', registers[0], registers[1])
                else:
                    # Default to Big Endian
                    bytes_val = struct.pack('>HH', registers[0], registers[1])
                
                value = struct.unpack('>f', bytes_val)[0]
                return value
            return float(registers[0])
        elif "INT32" in data_type:
            if len(registers) >= 2:
                return (registers[0] << 16) + registers[1]
            return registers[0]
        elif "UINT32" in data_type:
            if len(registers) >= 2:
                return (registers[0] << 16) + registers[1]
            return registers[0]
        else:
            return registers[0]
    
    def _value_to_registers(self, value, data_type, conversion):
        """Convert a value to registers based on data type and conversion"""
        # Simplified implementation
        if "FLOAT" in data_type:
            import struct
            bytes_val = struct.pack('>f', float(value))
            
            # ABCD - Big Endian, Normal
            if "Big Endian, Normal" in conversion:
                registers = struct.unpack('>HH', bytes_val)
            # CDAB - Big Endian, Swap Word
            elif "Big Endian, Swap Word" in conversion:
                high, low = struct.unpack('>HH', bytes_val)
                registers = [low, high]
            # DCBA - Little Endian, Normal
            elif "Little Endian, Normal" in conversion:
                registers = list(reversed(struct.unpack('<HH', bytes_val)))
            # BADC - Little Endian, Swap Word
            elif "Little Endian, Swap Word" in conversion:
                low, high = struct.unpack('<HH', bytes_val)
                registers = [low, high]
            else:
                # Default to Big Endian
                registers = struct.unpack('>HH', bytes_val)
            
            return list(registers)
        elif "INT32" in data_type or "UINT32" in data_type:
            value = int(value)
            return [(value >> 16) & 0xFFFF, value & 0xFFFF]
        else:
            return [int(value)]
    
    def start_scanning(self):
        """Start scanning all configured tags"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._scan_loop)
        self.thread.daemon = True
        self.thread.start()
    
    def stop_scanning(self):
        """Stop scanning tags"""
        self.running = False
        if self.thread:
            self.thread.join(2)
            self.thread = None
    
    def _scan_loop(self):
        """Main scanning loop"""
        while self.running:
            # Get all tags
            tags = self.tag_manager.get_all_tags()
            
            # Group tags by scan rate
            scan_groups = {}
            for tag in tags:
                scan_rate = int(tag.get("Scan_Rate", 1))
                if scan_rate not in scan_groups:
                    scan_groups[scan_rate] = []
                scan_groups[scan_rate].append(tag)
            
            # Process each scan group
            for scan_rate, tags in scan_groups.items():
                for tag in tags:
                    address = int(tag.get("Address", 0))
                    data_type = tag.get("Data_Type", "Analog")
                    conversion = tag.get("Conversion", "FLOAT, Big Endian, Normal")
                    
                    # Read the value
                    value = self.read_value(address, data_type, conversion)
                    
                    # Store the value
                    if value is not None:
                        self.values[tag["Name"]] = value
                
                # Sleep for the scan rate
                time.sleep(scan_rate)

class ModbusSlave:
    def __init__(self, ip="0.0.0.0", port=502, unit_id=1):
        self.ip = ip
        self.port = port
        self.unit_id = unit_id
        self.server = None
        self.tag_manager = ModbusTagManager()
        self.context = None
        self.running = False
        self.thread = None
    
    def setup_datastore(self):
        """Setup the datastore using configured tags"""
        # Create data blocks for each register type
        coils = ModbusSequentialDataBlock(0, [False] * 10000)
        discrete_inputs = ModbusSequentialDataBlock(0, [False] * 10000)
        input_registers = ModbusSequentialDataBlock(0, [0] * 10000)
        holding_registers = ModbusSequentialDataBlock(0, [0] * 10000)
        
        # Load initial values from tags
        tags = self.tag_manager.get_all_tags()
        for tag in tags:
            address = int(tag.get("Address", 0))
            default_value = float(tag.get("Default_Value", 0.0))
            
            # Set initial values based on register type
            if 1 <= address <= 9999:  # Coils
                coils.setValues(address-1, [bool(default_value)])
            elif 10001 <= address <= 19999:  # Discrete Inputs
                discrete_inputs.setValues(address-10001, [bool(default_value)])
            elif 30001 <= address <= 39999:  # Input Registers
                input_registers.setValues(address-30001, [int(default_value)])
            elif 40001 <= address <= 49999:  # Holding Registers
                holding_registers.setValues(address-40001, [int(default_value)])
        
        # Create slave context
        slaves = {
            self.unit_id: ModbusSlaveContext(
                di=discrete_inputs,
                co=coils,
                hr=holding_registers,
                ir=input_registers
            )
        }
        
        # Create modbus server context
        self.context = ModbusServerContext(slaves=slaves, single=False)
    
    def start(self):
        """Start the Modbus slave server"""
        if self.running:
            return
        
        self.setup_datastore()
        self.running = True
        self.thread = threading.Thread(target=self._start_server)
        self.thread.daemon = True
        self.thread.start()
    
    def stop(self):
        """Stop the Modbus slave server"""
        self.running = False
        if self.server:
            self.server.shutdown()
        if self.thread:
            self.thread.join(2)
            self.thread = None
    
    def _start_server(self):
        """Start the server in a thread"""
        try:
            self.server = StartTcpServer(
                context=self.context,
                address=(self.ip, self.port),
                allow_reuse_address=True
            )
        except Exception as e:
            print(f"Error starting Modbus slave server: {str(e)}")
            self.running = False

def parse_address_ranges(address_ranges_str):
    """Parse address ranges from string like '40001-40100,30001-30050'"""
    ranges = []
    if not address_ranges_str:
        return ranges
    
    parts = address_ranges_str.split(',')
    for part in parts:
        part = part.strip()
        if '-' in part:
            start, end = part.split('-')
            try:
                start = int(start.strip())
                end = int(end.strip())
                ranges.append({"start": start, "end": end})
            except ValueError:
                continue
        else:
            try:
                addr = int(part)
                ranges.append({"start": addr, "end": addr})
            except ValueError:
                continue
    
    return ranges

def parse_unit_ids(unit_ids_str):
    """Parse unit IDs from string like '1,2,3'"""
    unit_ids = []
    if not unit_ids_str:
        return [1]  # Default to unit ID 1
    
    parts = unit_ids_str.split(',')
    for part in parts:
        try:
            unit_id = int(part.strip())
            if 0 <= unit_id <= 255:
                unit_ids.append(unit_id)
        except ValueError:
            continue
    
    if not unit_ids:
        return [1]  # Default to unit ID 1
    
    return unit_ids

def configure_modbus(address_ranges_str, ip, port, unit_ids_str, mode="both"):
    """Configure the Modbus system"""
    global MODBUS_CONFIG
    
    # Parse address ranges
    MODBUS_CONFIG["address_ranges"] = parse_address_ranges(address_ranges_str)
    
    # Set IP and port
    MODBUS_CONFIG["ip"] = ip
    try:
        port = int(port)
        MODBUS_CONFIG["port"] = port
    except ValueError:
        MODBUS_CONFIG["port"] = 502  # Default port
    
    # Parse unit IDs
    MODBUS_CONFIG["unit_ids"] = parse_unit_ids(unit_ids_str)
    
    # Set mode
    if mode in ["master", "slave", "both"]:
        MODBUS_CONFIG["mode"] = mode
    else:
        MODBUS_CONFIG["mode"] = "both"
    
    return MODBUS_CONFIG

def start_modbus_system():
    """Start the Modbus system based on configuration"""
    master = None
    slave = None
    
    # Start master if configured
    if MODBUS_CONFIG["mode"] in ["master", "both"]:
        master = ModbusMaster(
            ip=MODBUS_CONFIG["ip"],
            port=MODBUS_CONFIG["port"],
            unit_id=MODBUS_CONFIG["unit_ids"][0]
        )
        master.start_scanning()
    
    # Start slave if configured
    if MODBUS_CONFIG["mode"] in ["slave", "both"]:
        slave = ModbusSlave(
            ip="0.0.0.0",  # Bind to all interfaces
            port=MODBUS_CONFIG["port"],
            unit_id=MODBUS_CONFIG["unit_ids"][0]
        )
        slave.start()
    
    return {"master": master, "slave": slave}

def stop_modbus_system(system):
    """Stop the Modbus system"""
    if system.get("master"):
        system["master"].stop_scanning()
    
    if system.get("slave"):
        system["slave"].stop()

# Helper function to create a tag from data
def create_tag_from_data(name, data_type, conversion, address, start_bit="0", length_bit="32",
                        span_high="1000", span_low="0", default_value="0.0", scan_rate="1",
                        read_write="Read Write", description="", scaling_type="No Scale",
                        formula="", scale="0", offset="0", clamp_to_span="False", clamp_high="False",
                        clamp_low="False", clamp_to_zero="False"):
    """Create a tag from provided data"""
    tag_manager = ModbusTagManager()
    
    tag_data = {
        "Name": name,
        "Data_Type": data_type,
        "Conversion": conversion,
        "Address": str(address),
        "Start_Bit": str(start_bit),
        "Length_Bit": str(length_bit),
        "Span_High": str(span_high),
        "Span_Low": str(span_low),
        "Default_Value": str(default_value),
        "Scan_Rate": str(scan_rate),
        "Read_Write": read_write,
        "Description": description,
        "Scaling_Type": scaling_type,
        "Formula": formula,
        "Scale": str(scale),
        "Offset": str(offset),
        "Clamp_to_Span": str(clamp_to_span),
        "Clamp_High": str(clamp_high),
        "Clamp_Low": str(clamp_low),
        "Clamp_to_Zero": str(clamp_to_zero)
    }
    
    return tag_manager.add_tag(tag_data)
