#!/usr/bin/env python3
import time
import random
import argparse
import threading
import math
import logging
# Updated imports for pymodbus 3.5.4
from pymodbus.client import ModbusTcpClient
from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext, ModbusSlaveContext
from pymodbus.payload import BinaryPayloadBuilder, BinaryPayloadDecoder
from pymodbus.constants import Endian

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global variables - MODIFY THESE TO MATCH YOUR GATEWAY CONFIG
GATEWAY_IP = "192.168.1.100"  # Replace with your gateway's IP
GATEWAY_PORT = 502  # Default Modbus port
SIMULATOR_IP = "0.0.0.0"  # Listen on all interfaces
SIMULATOR_PORT = 503  # Use a different port for simulator server
UNIT_ID = 1
SIMULATE_VALUES = True
UPDATE_INTERVAL = 1.0  # seconds

class ModbusSimulator:
    def __init__(self, gateway_ip, gateway_port, simulator_ip, simulator_port, unit_id):
        self.gateway_ip = gateway_ip
        self.gateway_port = gateway_port
        self.simulator_ip = simulator_ip
        self.simulator_port = simulator_port
        self.unit_id = unit_id
        
        # Client for connecting to gateway's slave server
        self.client = None
        
        # Server for gateway's master to connect to
        self.server = None
        self.server_context = None
        self.server_thread = None
        
        # Value update thread
        self.update_thread = None
        self.running = False
        
        # Track the values we're simulating
        self.simulated_values = {
            "current_amp": 0.0,
            "voltage": 220.0,
            "temperature": 25.0,
            "power_factor": 0.95,
            "frequency": 50.0
        }
        
        # Register mappings
        self.register_map = {
            "current_amp": 43913,  # As in your example
            "voltage": 43915,
            "temperature": 43917,
            "power_factor": 43919,
            "frequency": 43921
        }
    
    def connect_to_gateway(self):
        """Connect to the gateway as a client"""
        try:
            logger.info(f"Connecting to gateway at {self.gateway_ip}:{self.gateway_port}")
            self.client = ModbusTcpClient(self.gateway_ip, port=self.gateway_port)
            connected = self.client.connect()
            if connected:
                logger.info("Successfully connected to gateway")
            else:
                logger.error("Failed to connect to gateway")
            return connected
        except Exception as e:
            logger.error(f"Error connecting to gateway: {str(e)}")
            return False
    
    def disconnect_from_gateway(self):
        """Disconnect from the gateway"""
        if self.client:
            self.client.close()
            logger.info("Disconnected from gateway")
    
    def setup_server(self):
        """Setup the Modbus slave server"""
        # Setup datastore
        # Coils (0xxxxx) - Boolean read/write - Start at address 0
        coils = ModbusSequentialDataBlock(0, [False] * 10000)
        
        # Discrete Inputs (1xxxxx) - Boolean read-only - Start at address 0
        discrete_inputs = ModbusSequentialDataBlock(0, [False] * 10000)
        
        # Input Registers (3xxxxx) - 16-bit read-only - Start at address 0
        input_registers = ModbusSequentialDataBlock(0, [0] * 10000)
        
        # Holding Registers (4xxxxx) - 16-bit read/write - Start at address 0
        holding_registers = ModbusSequentialDataBlock(0, [0] * 10000)
        
        # Set initial values for demonstration
        # Current (43913 = 43913-40001 = 3912 in zero-based)
        self._update_float_in_registers(holding_registers, 3912, self.simulated_values["current_amp"], "CDAB")
        
        # Voltage
        self._update_float_in_registers(holding_registers, 3914, self.simulated_values["voltage"], "CDAB")
        
        # Temperature
        self._update_float_in_registers(holding_registers, 3916, self.simulated_values["temperature"], "CDAB")
        
        # Power Factor
        self._update_float_in_registers(holding_registers, 3918, self.simulated_values["power_factor"], "CDAB")
        
        # Frequency
        self._update_float_in_registers(holding_registers, 3920, self.simulated_values["frequency"], "CDAB")
        
        # Create slave context
        slaves = {
            self.unit_id: ModbusSlaveContext(
                di=discrete_inputs,
                co=coils,
                hr=holding_registers,
                ir=input_registers
            )
        }
        
        # Create server context
        self.server_context = ModbusServerContext(slaves=slaves, single=False)
        
        logger.info(f"Slave server setup complete with unit ID {self.unit_id}")
    
    def _update_float_in_registers(self, block, address, value, byte_order="CDAB"):
        """Update a float value in a register block using specified byte order"""
        builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
        if byte_order == "ABCD":
            builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Big)
        elif byte_order == "CDAB":
            builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
        elif byte_order == "DCBA":
            builder = BinaryPayloadBuilder(byteorder=Endian.Little, wordorder=Endian.Big)
        elif byte_order == "BADC":
            builder = BinaryPayloadBuilder(byteorder=Endian.Little, wordorder=Endian.Little)
        
        builder.add_32bit_float(float(value))
        registers = builder.to_registers()
        block.setValues(address, registers)
    
    def _read_float_from_registers(self, registers, byte_order="CDAB"):
        """Read a float value from registers using specified byte order"""
        if byte_order == "ABCD":
            decoder = BinaryPayloadDecoder.fromRegisters(
                registers, byteorder=Endian.Big, wordorder=Endian.Big
            )
        elif byte_order == "CDAB":
            decoder = BinaryPayloadDecoder.fromRegisters(
                registers, byteorder=Endian.Big, wordorder=Endian.Little
            )
        elif byte_order == "DCBA":
            decoder = BinaryPayloadDecoder.fromRegisters(
                registers, byteorder=Endian.Little, wordorder=Endian.Big
            )
        elif byte_order == "BADC":
            decoder = BinaryPayloadDecoder.fromRegisters(
                registers, byteorder=Endian.Little, wordorder=Endian.Little
            )
        
        return decoder.decode_32bit_float()
    
    def start_server(self):
        """Start the Modbus slave server in a thread"""
        self.setup_server()
        
        def run_server():
            logger.info(f"Starting Modbus slave server on {self.simulator_ip}:{self.simulator_port}")
            try:
                StartTcpServer(
                    context=self.server_context,
                    address=(self.simulator_ip, self.simulator_port),
                    allow_reuse_address=True
                )
            except Exception as e:
                logger.error(f"Error in server thread: {str(e)}")
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        logger.info("Server thread started")
    
    def stop_server(self):
        """Stop the server thread (not easily possible with pymodbus)"""
        logger.info("Server shutdown requested - restart the script to stop the server")
    
    def update_simulated_values(self):
        """Update simulated values to simulate real-world changes"""
        if not self.running or not SIMULATE_VALUES:
            return
        
        # Simulate current (sine wave pattern between 0-10A with some noise)
        t = time.time()
        self.simulated_values["current_amp"] = 5 + 5 * math.sin(t / 10) + random.uniform(-0.2, 0.2)
        
        # Simulate voltage (normal around 220V with small fluctuations)
        self.simulated_values["voltage"] = 220 + random.uniform(-2, 2)
        
        # Simulate temperature (slowly rising then falling)
        self.simulated_values["temperature"] = 25 + 5 * math.sin(t / 100) + random.uniform(-0.1, 0.1)
        
        # Simulate power factor (relatively stable around 0.95)
        self.simulated_values["power_factor"] = 0.95 + random.uniform(-0.01, 0.01)
        
        # Simulate frequency (stable around 50Hz with tiny fluctuations)
        self.simulated_values["frequency"] = 50 + random.uniform(-0.1, 0.1)
        
        # Update values in server context if server is running
        if self.server_context:
            slave = self.server_context[self.unit_id]
            # Current
            self._update_float_in_registers(
                slave.store["h"], 
                self.register_map["current_amp"] - 40001, 
                self.simulated_values["current_amp"], 
                "CDAB"
            )
            # Voltage
            self._update_float_in_registers(
                slave.store["h"], 
                self.register_map["voltage"] - 40001, 
                self.simulated_values["voltage"], 
                "CDAB"
            )
            # Temperature
            self._update_float_in_registers(
                slave.store["h"], 
                self.register_map["temperature"] - 40001, 
                self.simulated_values["temperature"], 
                "CDAB"
            )
            # Power Factor
            self._update_float_in_registers(
                slave.store["h"], 
                self.register_map["power_factor"] - 40001, 
                self.simulated_values["power_factor"], 
                "CDAB"
            )
            # Frequency
            self._update_float_in_registers(
                slave.store["h"], 
                self.register_map["frequency"] - 40001, 
                self.simulated_values["frequency"], 
                "CDAB"
            )
        
        logger.debug(f"Updated simulated values: {self.simulated_values}")
    
    def start_value_updates(self):
        """Start the thread to update simulated values"""
        self.running = True
        
        def updater():
            while self.running:
                self.update_simulated_values()
                time.sleep(UPDATE_INTERVAL)
        
        self.update_thread = threading.Thread(target=updater, daemon=True)
        self.update_thread.start()
        logger.info("Value update thread started")
    
    def stop_value_updates(self):
        """Stop the thread to update simulated values"""
        self.running = False
        if self.update_thread:
            self.update_thread.join(2)
        logger.info("Value update thread stopped")
    
    def read_from_gateway(self, address, count=2, unit=None):
        """Read from gateway's Modbus slave server"""
        if not self.client or not self.client.connect():
            if not self.connect_to_gateway():
                return None
        
        unit_id = unit if unit is not None else self.unit_id
        
        try:
            # Determine register type based on address
            if 1 <= address <= 9999:  # Coils
                result = self.client.read_coils(address-1, 1, unit=unit_id)
                if not result.isError():
                    return result.bits[0]
            elif 10001 <= address <= 19999:  # Discrete Inputs
                result = self.client.read_discrete_inputs(address-10001, 1, unit=unit_id)
                if not result.isError():
                    return result.bits[0]
            elif 30001 <= address <= 39999:  # Input Registers
                result = self.client.read_input_registers(address-30001, count, unit=unit_id)
                if not result.isError():
                    if count >= 2:
                        return self._read_float_from_registers(result.registers, "CDAB")
                    return result.registers[0]
            elif 40001 <= address <= 49999:  # Holding Registers
                result = self.client.read_holding_registers(address-40001, count, unit=unit_id)
                if not result.isError():
                    if count >= 2:
                        return self._read_float_from_registers(result.registers, "CDAB")
                    return result.registers[0]
            
            logger.error(f"Error reading from address {address}")
            return None
        except Exception as e:
            logger.error(f"Error reading from gateway: {str(e)}")
            return None
    
    def write_to_gateway(self, address, value, unit=None):
        """Write to gateway's Modbus slave server"""
        if not self.client or not self.client.connect():
            if not self.connect_to_gateway():
                return False
        
        unit_id = unit if unit is not None else self.unit_id
        
        try:
            # Determine register type based on address
            if 1 <= address <= 9999:  # Coils
                result = self.client.write_coil(address-1, bool(value), unit=unit_id)
                return not result.isError()
            elif 40001 <= address <= 49999:  # Holding Registers
                if isinstance(value, float):
                    # Convert float to registers
                    builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
                    builder.add_32bit_float(value)
                    registers = builder.to_registers()
                    result = self.client.write_registers(address-40001, registers, unit=unit_id)
                else:
                    result = self.client.write_register(address-40001, int(value), unit=unit_id)
                return not result.isError()
            
            logger.error(f"Cannot write to address {address} (not writable or invalid)")
            return False
        except Exception as e:
            logger.error(f"Error writing to gateway: {str(e)}")
            return False
    
    def test_gateway(self):
        """Test reading and writing to gateway"""
        # Test reading the Current_Amp tag from gateway
        current_value = self.read_from_gateway(self.register_map["current_amp"], 2)
        if current_value is not None:
            logger.info(f"Current Amp reading from gateway: {current_value:.2f}A")
        else:
            logger.error("Failed to read Current Amp from gateway")
        
        # Test writing to the Current_Amp tag on gateway
        test_value = random.uniform(0, 1000)
        logger.info(f"Writing test value to Current Amp: {test_value:.2f}A")
        if self.write_to_gateway(self.register_map["current_amp"], test_value):
            logger.info("Write successful")
            
            # Read back to confirm
            read_back = self.read_from_gateway(self.register_map["current_amp"], 2)
            if read_back is not None:
                logger.info(f"Read back value: {read_back:.2f}A")
                if abs(read_back - test_value) < 0.1:
                    logger.info("Values match! Gateway functioning correctly")
                else:
                    logger.warning(f"Values don't match! Expected: {test_value:.2f}, Got: {read_back:.2f}")
        else:
            logger.error("Failed to write to gateway")
    
    def run_monitor_loop(self):
        """Run a continuous monitoring loop for all values"""
        try:
            while True:
                logger.info("\n---- Current Values ----")
                for name, address in self.register_map.items():
                    value = self.read_from_gateway(address, 2)
                    if value is not None:
                        logger.info(f"{name}: {value:.2f}")
                    else:
                        logger.error(f"Failed to read {name}")
                
                logger.info("Press Ctrl+C to exit...")
                time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Monitor loop stopped by user")

def parse_arguments():
    parser = argparse.ArgumentParser(description='Modbus Simulator for IoT Gateway Testing')
    
    parser.add_argument('--gateway-ip', type=str, default=GATEWAY_IP,
                        help=f'IP address of the gateway (default: {GATEWAY_IP})')
    parser.add_argument('--gateway-port', type=int, default=GATEWAY_PORT,
                        help=f'Port of the gateway Modbus server (default: {GATEWAY_PORT})')
    parser.add_argument('--simulator-ip', type=str, default=SIMULATOR_IP,
                        help=f'IP address for simulator to listen on (default: {SIMULATOR_IP})')
    parser.add_argument('--simulator-port', type=int, default=SIMULATOR_PORT,
                        help=f'Port for simulator server (default: {SIMULATOR_PORT})')
    parser.add_argument('--unit-id', type=int, default=UNIT_ID,
                        help=f'Modbus unit ID to use (default: {UNIT_ID})')
    parser.add_argument('--update-interval', type=float, default=UPDATE_INTERVAL,
                        help=f'Interval between value updates in seconds (default: {UPDATE_INTERVAL})')
    parser.add_argument('--no-simulate', action='store_true',
                        help='Do not simulate changing values')
    parser.add_argument('--mode', type=str, choices=['server', 'client', 'both', 'test', 'monitor'],
                        default='both', help='Mode to run in (server, client, both, test, or monitor)')
    
    return parser.parse_args()

def main():
    args = parse_arguments()
    
    # Update global variables
    global GATEWAY_IP, GATEWAY_PORT, SIMULATOR_IP, SIMULATOR_PORT, UNIT_ID, SIMULATE_VALUES, UPDATE_INTERVAL
    GATEWAY_IP = args.gateway_ip
    GATEWAY_PORT = args.gateway_port
    SIMULATOR_IP = args.simulator_ip
    SIMULATOR_PORT = args.simulator_port
    UNIT_ID = args.unit_id
    SIMULATE_VALUES = not args.no_simulate
    UPDATE_INTERVAL = args.update_interval
    
    logger.info(f"Starting Modbus simulator in {args.mode} mode")
    logger.info(f"Gateway: {GATEWAY_IP}:{GATEWAY_PORT}, Simulator: {SIMULATOR_IP}:{SIMULATOR_PORT}, Unit ID: {UNIT_ID}")
    
    simulator = ModbusSimulator(GATEWAY_IP, GATEWAY_PORT, SIMULATOR_IP, SIMULATOR_PORT, UNIT_ID)
    
    try:
        # Run in server mode (act as slave for gateway's master to read from)
        if args.mode in ['server', 'both']:
            simulator.start_server()
            simulator.start_value_updates()
        
        # Run in client mode (connect to gateway's slave)
        if args.mode in ['client', 'both']:
            simulator.connect_to_gateway()
        
        # Run test mode (read/write to gateway)
        if args.mode == 'test':
            simulator.test_gateway()
        
        # Run monitor mode (continuously read values)
        if args.mode == 'monitor':
            simulator.run_monitor_loop()
        else:
            # Keep running in other modes
            logger.info("Simulator running. Press Ctrl+C to exit...")
            while True:
                time.sleep(1)
    
    except KeyboardInterrupt:
        logger.info("Shutting down simulator...")
    finally:
        simulator.disconnect_from_gateway()
        simulator.stop_value_updates()
        simulator.stop_server()

if __name__ == "__main__":
    main()
