import asyncio
import logging
import csv
from datetime import datetime
import os
from asyncua import Server, ua
from asyncua.common.methods import uamethod
import argparse
import re
from typing import Optional

# Basic logging setup
_logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class CsvDataPublisher:
    def __init__(self, server_url, namespace_uri, csv_file_path, update_interval_seconds):
        self.server_url = server_url
        self.namespace_uri = namespace_uri
        self.csv_file_path = csv_file_path
        self.update_interval = update_interval_seconds
        self.server = Server()
        self.idx = 0 # Namespace index
        self.nodes_cache = {} # To keep track of created nodes: {plc_name: {node_id_csv: {col_name: node}}}
        self.last_known_row_count = 0
        self.objects_node = None

    async def setup_server(self):
        _logger.info(f"Setting up CSV Data OPC UA Server at {self.server_url}")
        await self.server.init()
        self.server.set_endpoint(self.server_url)
        self.server.set_server_name("OPC UA CSV Data Publisher")
        # Security policies (can be configured further if needed)
        self.server.set_security_policy([
            ua.SecurityPolicyType.NoSecurity,
            # ua.SecurityPolicyType.Basic256Sha256_Sign,
            # ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt
        ])
        # self.server.set_security_IDs(["Anonymous"]) # Add user manager for authenticated access

        self.idx = await self.server.register_namespace(self.namespace_uri)
        _logger.info(f"Namespace '{self.namespace_uri}' registered with index {self.idx}")
        self.objects_node = self.server.nodes.objects

    async def read_and_update_nodes(self):
        if not os.path.exists(self.csv_file_path) or os.path.getsize(self.csv_file_path) == 0:
            _logger.info(f"CSV file {self.csv_file_path} not found or is empty. Skipping update cycle.")
            return

        try:
            with open(self.csv_file_path, 'r', newline='', encoding='utf-8') as csvfile:
                reader = list(csv.DictReader(csvfile))
        except Exception as e:
            _logger.error(f"Error reading CSV file {self.csv_file_path}: {e}")
            return
        
        _logger.info(f"Processing {len(reader)} rows from CSV.")

        # Group data by PLC name first
        plc_data_map = {}
        for row_index, row in enumerate(reader):
            try:
                timestamp_str = row['Timestamp'].strip()
                plc_name = row['PLCName'].strip() # Corrected column name and added strip()
                variable_name = row['NodeID'].strip() # Corrected column name, using NodeID as variable_name, and added strip()
                value_str = row['Value'].strip()
                # 'Data Type' is not in plc_data_log.csv. We'll infer it or default later.
                # status_code_str = row['StatusCode'].strip() # Available, but not directly used for node creation type
            except KeyError as e:
                _logger.error(f"CSV row {row_index + 2} is missing expected column: {e}. Row content: {row}. Ensure CSV has 'Timestamp', 'PLCName', 'NodeID', 'Value'.")
                continue

            if plc_name not in plc_data_map:
                plc_data_map[plc_name] = []
            plc_data_map[plc_name].append((timestamp_str, variable_name, value_str, row_index))

        for plc_name, data_points in plc_data_map.items():
            plc_folder = None # Initialize plc_folder for each PLC
            try:
                _logger.debug(f"Processing PLC: {plc_name}")
                # Get or create PLC folder under Objects node
                try:
                    plc_folder_node_id_str = f"{self.idx}:{plc_name}"
                    _logger.debug(f"Attempting to get folder for PLC: '{plc_name}' using browse name '{plc_folder_node_id_str}' under parent {self.objects_node}")
                    plc_folder = await self.objects_node.get_child(plc_folder_node_id_str)
                    _logger.info(f"Found existing folder for PLC: {plc_name} (Node: {plc_folder})")
                except ua.UaStatusCodeError as e_get_folder:
                    actual_code = e_get_folder.code
                    _logger.warning(f"ENTERED UaStatusCodeError block for PLC folder '{plc_name}'. Actual Error Code: {actual_code} (0x{actual_code:X}), Msg: {getattr(e_get_folder, 'msg', str(e_get_folder))}")
                    
                    # Direct integer comparison
                    is_bad_not_found = (actual_code == ua.StatusCodes.BadNotFound)
                    is_bad_no_match = (actual_code == ua.StatusCodes.BadNoMatch)
                    
                    _logger.info(f"DEBUG: actual_code = {actual_code} (type: {type(actual_code)}) | ua.StatusCodes.BadNotFound = {ua.StatusCodes.BadNotFound} | ua.StatusCodes.BadNoMatch = {ua.StatusCodes.BadNoMatch}")
                    _logger.info(f"DEBUG: Comparison results: is_bad_not_found = {is_bad_not_found}, is_bad_no_match = {is_bad_no_match}")

                    if is_bad_not_found or is_bad_no_match:
                        _logger.info(f"CONDITION TRUE: Folder for PLC '{plc_name}' not found (Actual Code: 0x{actual_code:X}). Attempting to create it...")
                        try:
                            plc_folder = await self.objects_node.add_folder(self.idx, plc_name)
                            # Check if add_folder returned a node or a status code
                            if not isinstance(plc_folder, ua.Node):
                                _logger.error(f"Failed to create folder for PLC '{plc_name}'. add_folder returned {plc_folder} instead of a Node. Skipping this PLC.")
                                continue
                            _logger.info(f"Successfully created folder for PLC: {plc_name} (Node: {plc_folder})")
                        except Exception as e_add_folder:
                            _logger.error(f"Exception during add_folder for PLC '{plc_name}': {e_add_folder}. Skipping this PLC.")
                            continue
                    else:
                        # Safer logging for unhandled status codes
                        status_code_val = getattr(e_get_folder, 'code', 'UnknownCode')
                        status_code_name = getattr(e_get_folder, 'name', 'UnknownName') # Try to get name safely
                        status_code_msg = getattr(e_get_folder, 'msg', str(e_get_folder)) # Get msg safely
                        _logger.error(f"CONDITION FALSE: OPC UA error (unhandled status code {status_code_name} [0x{status_code_val:X}]) getting PLC folder '{plc_name}': {status_code_msg}. Skipping this PLC.")
                        continue
                except Exception as e_generic_get_folder:
                    _logger.error(f"Generic error getting PLC folder '{plc_name}': {e_generic_get_folder}. Skipping this PLC.")
                    continue # Skip to the next PLC

                if plc_folder is None:
                    _logger.error(f"PLC folder for '{plc_name}' is None after get/create attempts. Cannot add variables. Skipping this PLC.")
                    continue # Skip to the next PLC

                # Process all data points for this PLC
                for timestamp_str, variable_name, value_str, row_idx in data_points:
                    # Sanitize variable_name to be a valid OPC UA node name if necessary
                    # For now, assume variable_name is valid.
                    variable_node = None
                    try:
                        # Try to get the variable node
                        var_node_id_str = f"{self.idx}:{variable_name}" # Variables are directly under PLC folder with server's namespace
                        _logger.debug(f"Attempting to get variable '{variable_name}' under folder '{plc_name}' (Node: {plc_folder})")
                        variable_node = await plc_folder.get_child(var_node_id_str)
                        _logger.debug(f"Found existing variable node '{variable_name}' for PLC '{plc_name}'.")
                    except ua.UaStatusCodeError as e_get_var:
                        actual_var_code = e_get_var.code
                        if actual_var_code == ua.StatusCodes.BadNotFound or actual_var_code == ua.StatusCodes.BadNoMatch:
                            _logger.debug(f"Variable node '{variable_name}' not found for PLC '{plc_name}'. Creating it...")
                            # Determine initial value and data type for creation
                            try:
                                # Pass only value_str to _parse_value_and_type, as data_type_str is not available from CSV
                                initial_val, ua_data_type = self._parse_value_and_type(value_str)
                                if ua_data_type is None: # Parsing failed or type couldn't be determined
                                    _logger.error(f"Skipping variable '{variable_name}' for PLC '{plc_name}' due to data type parsing error/inability to determine type from value '{value_str}' (CSV row {row_idx + 2}).")
                                    continue # Skip this variable
                                
                                variable_node = await plc_folder.add_variable(self.idx, variable_name, initial_val, datatype=ua_data_type)
                                await variable_node.set_writable(True) # Make it writable by default
                                _logger.info(f"Created variable '{variable_name}' for PLC '{plc_name}' with initial value '{initial_val}'.")
                            except Exception as e_add_var:
                                _logger.error(f"Error creating variable node '{variable_name}' for PLC '{plc_name}': {e_add_var}. CSV row {row_idx + 2}.")
                                continue # Skip this variable
                        else:
                            # Safer logging for unhandled status codes
                            status_code_val = getattr(e_get_var, 'code', 'UnknownCode')
                            status_code_name = getattr(e_get_var, 'name', 'UnknownName') # Try to get name safely
                            status_code_msg = getattr(e_get_var, 'msg', str(e_get_var)) # Get msg safely
                            _logger.error(f"OPC UA error (unhandled status code {status_code_name} [0x{status_code_val:X}]) getting variable '{variable_name}' for PLC '{plc_name}': {status_code_msg}. CSV row {row_idx + 2}.")
                            continue # Skip this variable
                    except Exception as e_generic_get_var:
                        _logger.error(f"Generic error getting variable '{variable_name}' for PLC '{plc_name}': {e_generic_get_var}. CSV row {row_idx + 2}.")
                        continue # Skip this variable

                    if variable_node is None:
                        _logger.error(f"Variable node '{variable_name}' for PLC '{plc_name}' is None after get/create attempts. Skipping update. CSV row {row_idx + 2}.")
                        continue # Skip this variable

                    # Update the variable's value
                    try:
                        # Pass only value_str to _parse_value_and_type
                        current_val, ua_data_type_ignored = self._parse_value_and_type(value_str)
                        if current_val is not None: # If parsing was successful
                            await variable_node.write_value(current_val)
                            _logger.debug(f"Updated variable '{plc_name}/{variable_name}' to '{current_val}'.")
                        else:
                            _logger.warning(f"Could not parse value for '{plc_name}/{variable_name}' from CSV row {row_idx + 2} ('{value_str}'). Skipping update for this row.")
                    except Exception as e_write_val:
                        _logger.error(f"Error writing value to variable '{plc_name}/{variable_name}': {e_write_val}. CSV row {row_idx + 2}.")
            
            except Exception as e_outer_plc:
                if isinstance(e_outer_plc, ua.StatusCode):
                    _logger.error(f"Outer loop error processing PLC {plc_name}: OPC UA StatusCode {e_outer_plc.name} (0x{e_outer_plc.value:X}) was raised directly. This PLC's data points may not have been processed.")
                elif hasattr(e_outer_plc, 'name') and hasattr(e_outer_plc, 'code'): # Likely a UaStatusCodeError
                    _logger.error(f"Outer loop error processing PLC {plc_name}: {e_outer_plc.name} (0x{e_outer_plc.code:X}) - {getattr(e_outer_plc, 'msg', str(e_outer_plc))}. This PLC's data points may not have been processed.")
                else:
                    _logger.error(f"Outer loop error processing PLC {plc_name}: {type(e_outer_plc).__name__} - {str(e_outer_plc)}. This PLC's data points may not have been processed.")
                # import traceback # Uncomment for full stack trace if needed
                # _logger.error(traceback.format_exc())
                continue

    async def start(self):
        await self.setup_server()
        async with self.server:
            _logger.info("OPC UA CSV Data Publisher Server started.")
            while True:
                await self.read_and_update_nodes()
                await asyncio.sleep(self.update_interval)

    def _parse_value_and_type(self, value_str: str, data_type_str: Optional[str] = None):
        """Parses the value string and determines the UA data type.
           If data_type_str is provided, it's used as a hint but inference from value_str takes precedence for robustness.
           Now primarily infers from value_str as 'Data Type' column is not in plc_data_log.csv.
        """
        value_str = value_str.strip()
        
        # Try boolean
        if value_str.lower() == 'true':
            return True, ua.VariantType.Boolean
        if value_str.lower() == 'false':
            return False, ua.VariantType.Boolean
        
        # Try integer
        try:
            return int(value_str), ua.VariantType.Int64 # Defaulting to Int64, can be Int32 etc.
        except ValueError:
            pass
        
        # Try float/double
        try:
            return float(value_str), ua.VariantType.Double # Defaulting to Double
        except ValueError:
            pass
            
        # Try to parse as datetime if it matches ISO format (or other common formats)
        # This is a basic check; a more robust parser might be needed for various datetime strings.
        try:
            # Example check for ISO-like format (YYYY-MM-DDTHH:MM:SS...)
            if 'T' in value_str and (value_str.count(':') >= 2):
                dt_obj = datetime.fromisoformat(value_str.replace('Z', '+00:00')) # Handle Z for UTC
                return dt_obj, ua.VariantType.DateTime
        except ValueError:
            pass # Not a recognized datetime format

        # Default to String if no other type matches
        _logger.debug(f"Could not infer specific data type for value '{value_str}'. Defaulting to String.")
        return value_str, ua.VariantType.String

async def main():
    parser = argparse.ArgumentParser(description="OPC UA CSV Data Publisher Server")
    parser.add_argument("--url", default="opc.tcp://0.0.0.0:4850/csv_data_server/", help="OPC UA server URL")
    parser.add_argument("--ns_uri", default="http://mycompany.com/csv_data_server", help="OPC UA namespace URI")
    parser.add_argument("--csv_file", default="/home/malay/vista-iot-backend-/plc_data_log.csv", help="Path to the CSV data log file")
    parser.add_argument("--interval", type=int, default=10, help="Update interval in seconds to check CSV file")
    parser.add_argument("--log_level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Logging level")
    
    args = parser.parse_args()

    # Update logger level based on args
    logging.getLogger().setLevel(args.log_level.upper())
    _logger.setLevel(args.log_level.upper())
    
    publisher = CsvDataPublisher(
        server_url=args.url,
        namespace_uri=args.ns_uri,
        csv_file_path=args.csv_file,
        update_interval_seconds=args.interval
    )
    await publisher.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _logger.info("OPC UA CSV Data Publisher Server shutting down.")
