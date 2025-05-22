#!/usr/bin/env python3
# opcua_gateway_client.py - OPC UA client for IoT gateway to connect to virtual PLCs

import asyncio
import logging
import os
import ssl
import subprocess
import yaml
from asyncua import Client, ua
from asyncua.crypto.security_policies import SecurityPolicyType
from asyncua.ua.uaprotocol_auto import MessageSecurityMode
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
import csv
# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Maps for converting security strings from config to enums
SECURITY_POLICY_MAP = {
    "NoSecurity": SecurityPolicyType.NoSecurity,
    "Basic256": SecurityPolicyType.Basic256_Sign,
    "Basic128Rsa15": SecurityPolicyType.Basic128Rsa15_Sign,
    "Basic256Sha256": SecurityPolicyType.Basic256Sha256_Sign,
    # Add others if used, e.g., Aes128_Sha256_RsaOaep
}

MESSAGE_SECURITY_MODE_MAP = {
    "None": MessageSecurityMode.None_,
    "Sign": MessageSecurityMode.Sign,
    "SignAndEncrypt": MessageSecurityMode.SignAndEncrypt,
}

# CSV Writing Helper
def write_data_to_csv(filename: str, data_row: list, header: Optional[list] = None):
    file_exists = os.path.isfile(filename)
    try:
        with open(filename, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            if not file_exists and header:
                writer.writerow(header)
            writer.writerow(data_row)
    except IOError as e:
        logger.error(f"IOError writing to CSV {filename}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error writing to CSV {filename}: {e}")


class OPCUAGatewayClient:
    """
    OPC UA client that connects to virtual PLC servers, reads their values,
    and can relay this data to other systems (SCADA, cloud, etc.)
    """
    def __init__(self, config_file: str = "opcua_client_config.yaml"):
        """
        Initialize the OPC UA gateway client
        
        Args:
            config_file: Path to the configuration YAML file
        """
        self.config_file = config_file
        self.config = None
        self.plc_clients = {}  # Dictionary to hold client connections
        self.subscriptions = {}  # To store active subscriptions
        self.cached_values = {}  # To store latest values
        self.csv_log_file = "plc_data_log.csv"
        self.log_interval = 10

    async def load_config(self):
        """Load configuration from YAML file"""
        try:
            with open(self.config_file, 'r') as f:
                self.config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            return False
    
    async def connect_to_plc(self, plc_name: str, plc_config: dict, client_certs_base_dir="certs/client_certs"):
        """
        Connect to a PLC OPC UA server
        
        Args:
            plc_name: Name identifier for the PLC
            plc_config: Configuration dictionary for the PLC
            client_certs_base_dir: Base directory for client certificates
            
        Returns:
            Client object if connection successful, None otherwise
        """
        url = plc_config['url']
        client = Client(url=url)
        logger.info(f"Connecting to PLC '{plc_name}' at {url}")

        try:
            security_settings_str = plc_config.get("security")
            user_settings = plc_config.get("user_settings")

            if user_settings:
                client.set_user(user_settings.get("username"))
                client.set_password(user_settings.get("password"))
                logger.info(f"Set user/password for {plc_name}")

            if security_settings_str:
                logger.info(f"Configuring security for {plc_name} with settings: {security_settings_str}")
                try:
                    policy_str, mode_str = map(str.strip, security_settings_str.split(','))
                except ValueError:
                    logger.error(f"Invalid security string format '{security_settings_str}' for {plc_name}. Expected 'Policy,Mode'.")
                    return None

                policy_enum = SECURITY_POLICY_MAP.get(policy_str)
                mode_enum = MESSAGE_SECURITY_MODE_MAP.get(mode_str)

                if policy_enum is None:
                    logger.error(f"Unknown security policy string: '{policy_str}' for {plc_name}. Available: {list(SECURITY_POLICY_MAP.keys())}")
                    return None
                if mode_enum is None:
                    logger.error(f"Unknown message security mode string: '{mode_str}' for {plc_name}. Available: {list(MESSAGE_SECURITY_MODE_MAP.keys())}")
                    return None

                if policy_enum != SecurityPolicyType.NoSecurity:
                    client_cert_path = plc_config.get("client_cert_path", os.path.join(client_certs_base_dir, f"client_cert_{plc_name}.pem"))
                    client_key_path = plc_config.get("client_key_path", os.path.join(client_certs_base_dir, f"client_key_{plc_name}.pem"))
                    server_cert_path = plc_config.get("server_cert_path")

                    os.makedirs(os.path.dirname(client_cert_path), exist_ok=True)

                    key_was_auto_generated = False
                    if not (os.path.exists(client_cert_path) and os.path.exists(client_key_path)):
                        logger.info(f"Client certificate/key for {plc_name} not found at {client_cert_path}/{client_key_path}. Generating new ones...")
                        try:
                            # Generate private key
                            subprocess.run(["openssl", "genrsa", "-out", client_key_path, "2048"], check=True, capture_output=True, text=True)
                            # Generate CSR
                            csr_path = os.path.join(os.path.dirname(client_cert_path), f"client_csr_{plc_name}.csr")
                            subject = f"/CN=OPCUAGatewayClientFor{plc_name}/O=MyClientOrg/C=US"
                            subprocess.run([
                                "openssl", "req", "-new", "-key", client_key_path,
                                "-out", csr_path, "-subj", subject
                            ], check=True, capture_output=True, text=True)
                            # Generate self-signed certificate
                            subprocess.run([
                                "openssl", "x509", "-req", "-days", "365", "-in", csr_path,
                                "-signkey", client_key_path, "-out", client_cert_path
                            ], check=True, capture_output=True, text=True)
                            os.chmod(client_key_path, 0o600)
                            logger.info(f"Generated client certificate and key for {plc_name} at {client_cert_path} and {client_key_path}")
                            key_was_auto_generated = True
                        except subprocess.CalledProcessError as e:
                            logger.error(f"Failed to generate client cert/key for {plc_name}: {e.stderr}")
                            return None
                        except Exception as e_gen:
                            logger.error(f"An unexpected error occurred during client cert/key generation for {plc_name}: {e_gen}")
                            return None

                    if not server_cert_path or not os.path.exists(server_cert_path):
                        logger.error(f"Server certificate path for {plc_name} ('{server_cert_path}') is missing or invalid. Required for secure policy {policy_str}.")
                        return None
                    
                    password_for_set_security = None
                    if key_was_auto_generated:
                        logger.info(f"Client key for {plc_name} was auto-generated (unencrypted). Ignoring any configured password for this connection attempt.")
                    else:
                        password_for_set_security = plc_config.get("client_key_password")

                    logger.info(f"Setting security for {plc_name}: Policy={policy_str}, Mode={mode_str}, ClientCert={client_cert_path}, ServerCert={server_cert_path}")
                    await client.set_security(
                        policy_enum,
                        client_cert_path,
                        client_key_path,
                        password_for_set_security,
                        server_cert_path,
                        mode=mode_enum
                    )
                else: # Explicitly configured NoSecurity
                    logger.info(f"Setting security for {plc_name} to NoSecurity as per configuration.")
                    await client.set_security(
                        SecurityPolicyType.NoSecurity,
                        None, None, None, # cert, key, key_password
                        mode=MessageSecurityMode.None_
                    )
            else:
                logger.info(f"No security settings in config for {plc_name}. Defaulting to NoSecurity.")
                # Client defaults to NoSecurity if set_security is not called, or we can be explicit:
                # await client.set_security(SecurityPolicyType.NoSecurity, None, None, None, mode=MessageSecurityMode.None_)

            await client.connect()
            logger.info(f"Successfully connected to PLC '{plc_name}'.")
            self.plc_clients[plc_name] = client
            return client
            
        except Exception as e:
            logger.error(f"Failed to connect to {plc_name} at {url}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def disconnect_from_plc(self, plc_name: str):
        """Disconnect from a PLC"""
        if plc_name in self.plc_clients:
            try:
                await self.plc_clients[plc_name].disconnect()
                logger.info(f"Disconnected from {plc_name}")
            except Exception as e:
                logger.error(f"Error disconnecting from {plc_name}: {e}")
            finally:
                self.plc_clients[plc_name] = None
    
    async def disconnect_all(self):
        """Disconnect from all PLCs"""
        for plc_name in list(self.plc_clients.keys()):
            await self.disconnect_from_plc(plc_name)
    
    async def browse_nodes(self, plc_name: str, node_id: str = "i=85") -> List[Dict[str, Any]]:
        """
        Browse nodes from a specific PLC starting from the specified node
        
        Args:
            plc_name: Name of the PLC to browse
            node_id: Starting node ID (default: Objects folder)
            
        Returns:
            List of dictionaries containing node information
        """
        if plc_name not in self.plc_clients:
            logger.error(f"No connection to {plc_name}")
            return []
        
        client = self.plc_clients[plc_name]
        result = []
        
        try:
            # Get the starting node
            node = client.get_node(node_id)
            
            # Get the children of the node
            children = await node.get_children()
            
            # Process each child
            for child in children:
                try:
                    browse_name = await child.read_browse_name()
                    display_name = await child.read_display_name()
                    node_class = await child.read_node_class()
                    
                    # Add to results
                    result.append({
                        "node_id": str(child.nodeid),
                        "browse_name": str(browse_name),
                        "display_name": display_name.Text,
                        "node_class": str(node_class)
                    })
                    
                except Exception as e:
                    logger.warning(f"Error processing node {child.nodeid}: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error browsing nodes for {plc_name}: {e}")
            return []
    
    async def read_node_value(self, plc_name: str, node_id: str) -> Optional[Any]:
        """
        Read a value from a specific node
        
        Args:
            plc_name: Name of the PLC
            node_id: Node ID to read
            
        Returns:
            Value of the node or None if error
        """
        if plc_name not in self.plc_clients:
            logger.error(f"No connection to {plc_name}")
            return None
        
        client = self.plc_clients[plc_name]
        
        try:
            node = client.get_node(node_id)
            value = await node.read_value()
            
            # Cache the value
            if plc_name not in self.cached_values:
                self.cached_values[plc_name] = {}
            self.cached_values[plc_name][node_id] = value
            
            return value
            
        except Exception as e:
            logger.error(f"Error reading node {node_id} from {plc_name}: {e}")
            return None
    
    async def write_node_value(self, plc_name: str, node_id: str, value: Any) -> bool:
        """
        Write a value to a specific node
        
        Args:
            plc_name: Name of the PLC
            node_id: Node ID to write
            value: Value to write
            
        Returns:
            True if successful, False otherwise
        """
        if plc_name not in self.plc_clients:
            logger.error(f"No connection to {plc_name}")
            return False
        
        client = self.plc_clients[plc_name]
        
        try:
            node = client.get_node(node_id)
            await node.write_value(value)
            
            # Update cached value
            if plc_name not in self.cached_values:
                self.cached_values[plc_name] = {}
            self.cached_values[plc_name][node_id] = value
            
            logger.info(f"Wrote value {value} to {node_id} on {plc_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error writing to node {node_id} on {plc_name}: {e}")
            return False
    
    async def subscribe_to_node(self, plc_name: str, node_id: str, callback: Callable) -> bool:
        """
        Subscribe to changes in a specific node
        
        Args:
            plc_name: Name of the PLC
            node_id: Node ID to subscribe to
            callback: Callback function to call when value changes
            
        Returns:
            True if subscription set up successfully, False otherwise
        """
        if plc_name not in self.plc_clients:
            logger.error(f"No connection to {plc_name}")
            return False
        
        client = self.plc_clients[plc_name]
        
        # Create a key for this subscription
        sub_key = f"{plc_name}:{node_id}"
        
        try:
            # Create subscription handler
            handler = SubHandler(callback, node_id, plc_name)
            
            # Create subscription
            subscription = await client.create_subscription(500, handler)
            
            # Subscribe to node
            node = client.get_node(node_id)
            await subscription.subscribe_data_change(node)
            
            # Store subscription for later management
            if sub_key in self.subscriptions:
                # Clean up old subscription
                old_sub = self.subscriptions[sub_key]
                await old_sub.delete()
                
            self.subscriptions[sub_key] = subscription
            
            logger.info(f"Subscribed to {node_id} on {plc_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to subscribe to {node_id} on {plc_name}: {e}")
            return False
    
    async def unsubscribe_from_node(self, plc_name: str, node_id: str) -> bool:
        """
        Unsubscribe from changes in a specific node
        
        Args:
            plc_name: Name of the PLC
            node_id: Node ID to unsubscribe from
            
        Returns:
            True if unsubscribed successfully, False otherwise
        """
        sub_key = f"{plc_name}:{node_id}"
        
        if sub_key in self.subscriptions:
            try:
                subscription = self.subscriptions[sub_key]
                await subscription.delete()
                del self.subscriptions[sub_key]
                logger.info(f"Unsubscribed from {node_id} on {plc_name}")
                return True
            except Exception as e:
                logger.error(f"Error unsubscribing from {node_id} on {plc_name}: {e}")
                return False
        else:
            logger.warning(f"No subscription found for {node_id} on {plc_name}")
            return False
            
    async def unsubscribe_all(self):
        """Unsubscribe from all nodes"""
        for sub_key in list(self.subscriptions.keys()):
            try:
                subscription = self.subscriptions[sub_key]
                await subscription.delete()
                logger.info(f"Unsubscribed from {sub_key}")
            except Exception as e:
                logger.error(f"Error unsubscribing from {sub_key}: {e}")
            finally:
                del self.subscriptions[sub_key]

# Subscription handler for data change notifications
class SubHandler:
    """Subscription Handler for OPC UA data changes"""
    
    def __init__(self, callback, node_id, plc_name):
        self.callback = callback
        self.node_id = node_id
        self.plc_name = plc_name
        
    async def datachange_notification(self, node, val, data):
        """Called when a subscribed node's value changes"""
        await self.callback(self.plc_name, self.node_id, val)

async def main():
    opcua_gw_client = OPCUAGatewayClient(config_file="opcua_client_config.yaml")
    if not await opcua_gw_client.load_config(): # Added await here
        logger.error("Failed to load client configuration. Exiting.")
        return

    # Get log file and interval from OPCUAGatewayClient instance
    # These should be initialized in OPCUAGatewayClient.__init__ (e.g., from config or defaults)
    csv_log_file = getattr(opcua_gw_client, 'csv_log_file', "plc_data_log.csv")
    log_interval_seconds = getattr(opcua_gw_client, 'log_interval', 10)
    csv_header = ["Timestamp", "PLCName", "NodeID", "Value", "SourceTimestamp", "StatusCode"]

    # Initial connection attempts to all configured PLCs
    for plc_name_init, plc_config_init in opcua_gw_client.config.get('plcs', {}).items():
        if plc_name_init not in opcua_gw_client.plc_clients or opcua_gw_client.plc_clients.get(plc_name_init) is None:
            logger.info(f"Attempting initial connection to {plc_name_init}...")
            await opcua_gw_client.connect_to_plc(plc_name_init, plc_config_init)
    
    if not any(opcua_gw_client.plc_clients.values()):
        logger.warning("No PLCs could be connected initially. Gateway will attempt to connect in the main loop.")

    logger.info(f"Starting data logging to {csv_log_file} every {log_interval_seconds} seconds.")
    logger.info("Press Ctrl+C to stop.")

    try:
        while True:
            active_plc_in_current_cycle = False
            for plc_name, plc_asyncua_client in list(opcua_gw_client.plc_clients.items()): # Iterate over connected/attempted PLCs
                if plc_asyncua_client is None: # Connection might have failed or been closed
                    continue
                
                active_plc_in_current_cycle = True
                current_plc_config = opcua_gw_client.config['plcs'].get(plc_name)
                if not current_plc_config:
                    logger.warning(f"Configuration for {plc_name} not found during logging. Skipping.")
                    continue
                
                variables_to_monitor = current_plc_config.get('variables_to_monitor', [])
                if not variables_to_monitor:
                    continue # No variables specified for this PLC
                
                for node_id_str in variables_to_monitor:
                    try:
                        node = plc_asyncua_client.get_node(node_id_str)
                        data_value = await node.read_data_value()
                        
                        current_time_iso = datetime.now().isoformat()
                        value = data_value.Value.Value if data_value.Value is not None else None
                        source_timestamp_iso = data_value.SourceTimestamp.isoformat() if data_value.SourceTimestamp else None
                        status_code_name = data_value.StatusCode.name
                        
                        data_row = [current_time_iso, plc_name, node_id_str, value, source_timestamp_iso, status_code_name]
                        write_data_to_csv(csv_log_file, data_row, csv_header)

                    except ua.UaStatusCodeError as e:
                        logger.error(f"Error reading node {node_id_str} from {plc_name}: {e} (Status: {e.code.name})")
                        # Basic disconnect & mark for reconnect logic
                        if e.code in [ua.StatusCodes.BadSessionIdInvalid, 
                                      ua.StatusCodes.BadSecureChannelIdInvalid,
                                      ua.StatusCodes.BadConnectionClosed,
                                      ua.StatusCodes.BadTimeout]:
                            logger.warning(f"Connection issue with {plc_name} (Reason: {e.code.name}). Marking for reconnect.")
                            await opcua_gw_client.disconnect_from_plc(plc_name) # disconnect_plc should set client to None in self.plc_clients
                    except AttributeError as e:
                        logger.error(f"Attribute error processing node {node_id_str} for {plc_name}: {e}. PLC might be disconnected.")
                    except Exception as e:
                        logger.error(f"Unexpected error processing node {node_id_str} from {plc_name}: {e}")
            
            # Reconnection logic for PLCs that are marked as disconnected (None in plc_clients)
            configured_plcs = opcua_gw_client.config.get('plcs', {})
            if configured_plcs:
                for plc_name_rc, plc_config_rc in configured_plcs.items():
                    if plc_name_rc not in opcua_gw_client.plc_clients or opcua_gw_client.plc_clients.get(plc_name_rc) is None:
                        logger.info(f"Attempting to reconnect to disconnected PLC: {plc_name_rc}...")
                        await opcua_gw_client.connect_to_plc(plc_name_rc, plc_config_rc)
            
            await asyncio.sleep(log_interval_seconds)

    except KeyboardInterrupt:
        logger.info("Client shutting down due to KeyboardInterrupt...")
    finally:
        logger.info("Disconnecting from all PLCs...")
        await opcua_gw_client.disconnect_all()
        logger.info("All PLC connections closed and client shut down.")

if __name__ == "__main__":
    asyncio.run(main())
