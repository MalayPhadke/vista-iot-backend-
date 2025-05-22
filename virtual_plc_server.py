# virtual_plc_server.py
import asyncio
import logging
import os
import subprocess
import sys 
from typing import Dict, Optional, List, Any
import datetime
from asyncua import Server, ua
from asyncua.ua import SecurityPolicyType 
from asyncua.server.user_managers import UserManager
from asyncua.server.history_sql import HistorySQLite

# Setup logger
_logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s') # Configured in __main__

# Basic user manager for authentication
class SimpleUserManager(UserManager):
    def __init__(self, username_password_map):
        super().__init__()
        self.username_password_map = username_password_map

    async def check_user_token(self, user_name, user_password, user_certificate=None):
        if user_name in self.username_password_map and self.username_password_map[user_name] == user_password:
            _logger.info(f"User {user_name} authenticated successfully.")
            return True
        _logger.warning(f"Failed authentication for user: {user_name}")
        return False

async def run_virtual_plc_server(
    plc_name: str, 
    url: str, 
    namespace_uri: str, 
    variables_config: List[Dict[str, Any]], 
    enable_history: bool = False, 
    username: Optional[str] = None, 
    password: Optional[str] = None,
    security_policy: Optional[str] = None, # e.g., "Basic256Sha256"
    security_mode: Optional[str] = None,   # e.g., "Sign", "SignAndEncrypt"
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None
):
    _logger.info(f"Starting Virtual PLC Server: {plc_name} at {url}")
    server = Server()
    await server.init()

    # DEBUG: Check available server methods for security configuration
    _logger.info(f"DEBUG SERVER METHODS for {plc_name}: Available attributes on server object: dir(server) partially shown for brevity if too long")
    # To avoid excessively long logs, let's check for specific ones:
    _logger.info(f"DEBUG SERVER METHODS for {plc_name}: hasattr(server, 'set_security_policies'): {hasattr(server, 'set_security_policies')}")
    _logger.info(f"DEBUG SERVER METHODS for {plc_name}: hasattr(server, 'set_security_policy'): {hasattr(server, 'set_security_policy')}") # Singular
    _logger.info(f"DEBUG SERVER METHODS for {plc_name}: hasattr(server, 'set_security'): {hasattr(server, 'set_security')}") # Generic method often used for endpoints
    _logger.info(f"DEBUG SERVER METHODS for {plc_name}: type(server): {type(server)}")

    server.set_endpoint(url)
    server.set_server_name(f"VirtualOPCUAPLC_{plc_name}")
    server.set_application_uri(f"urn:virtualplc:{plc_name.replace(' ', '_')}") # Required for security

    # Setup namespace
    idx = await server.register_namespace(namespace_uri)
    _logger.info(f"Virtual PLC '{plc_name}' namespace registered at index: {idx}")
    
    history_successfully_enabled = False
    if enable_history:
        _logger.info(f"Attempting to enable history for {plc_name}...")
        try:
            db_path = f"{plc_name.replace(' ', '_')}_history.sqlite"
            # Ensure aiosqlite is available
            try:
                import aiosqlite
                _logger.info(f"aiosqlite imported successfully for {plc_name} history.")
            except ImportError:
                _logger.error(f"aiosqlite library not found for {plc_name}. History will be disabled. Please install aiosqlite.")
                raise
            
            history_backend = HistorySQLite(db_path)
            # The init method of HistorySQLite is async and needs to be awaited.
            if hasattr(history_backend, 'init') and asyncio.iscoroutinefunction(history_backend.init):
                 _logger.info(f"Explicitly calling await history_backend.init() for {plc_name}")
                 await history_backend.init() # Corrected: Call without arguments
            else:
                 _logger.info(f"History backend for {plc_name} does not have an explicit async init or it's not a coroutine function, or init is not async.")

            server.iserver.history_manager.set_storage(history_backend)
            _logger.info(f"History storage backend (SQLite at {db_path}) set for {plc_name}.")
            history_successfully_enabled = True
        except Exception as e_hist_storage:
            _logger.error(f"Failed to set history storage for {plc_name}: {e_hist_storage}. History will be disabled.")
            history_successfully_enabled = False
    
    # Setup authentication if needed
    if username and password:
        user_manager = SimpleUserManager({username: password})
        server.user_manager = user_manager
        _logger.info(f"User authentication enabled for {plc_name} with user {username}")
    
    # Setup security policies
    policies_to_set = [SecurityPolicyType.NoSecurity] # Default to NoSecurity

    if security_policy and security_policy.lower() != "none" and security_policy.lower() != "nosecurity":
        if not (cert_path and key_path and os.path.exists(cert_path) and os.path.exists(key_path)):
            _logger.error(f"Security policy '{security_policy}' requested for {plc_name}, but certificate/key paths are invalid or files missing: Cert='{cert_path}', Key='{key_path}'.")
            _logger.warning(f"Falling back to NoSecurity for {plc_name}.")
        else:
            try:
                await server.load_certificate(cert_path)
                await server.load_private_key(key_path)
                _logger.info(f"Certificates loaded successfully for {plc_name} for policy {security_policy}.")
                
                # Construct the full enum member name, e.g., Basic256Sha256_SignAndEncrypt
                full_policy_name = security_policy
                if security_mode and security_mode.lower() != "none":
                    # Append mode, ensuring typical OPC UA naming (e.g., _Sign, _SignAndEncrypt)
                    mode_suffix = "_" + security_mode.replace("And", "_And_") # Basic256_Sign, Basic256_Sign_And_Encrypt - adjust as per actual enum names
                    # A common pattern is just Policy_Mode, e.g. Basic256Sha256_Sign
                    # Let's assume simpler concatenation for now, like PolicyName_ModeName
                    # Example: Basic256Sha256_Sign, Basic256Sha256_SignAndEncrypt
                    # The exact enum names in SecurityPolicyType matter here.
                    # For example, SecurityPolicyType.Basic256Sha256_Sign, SecurityPolicyType.Basic256Sha256_SignAndEncrypt
                    full_policy_name = f"{security_policy}_{security_mode}"
                
                selected_policy_enum = getattr(SecurityPolicyType, full_policy_name, None)
                
                if selected_policy_enum and selected_policy_enum != SecurityPolicyType.NoSecurity:
                    policies_to_set = [selected_policy_enum, SecurityPolicyType.NoSecurity] # Offer both secure and insecure
                    _logger.info(f"Configured security policy for {plc_name}: {selected_policy_enum.name}")
                elif selected_policy_enum == SecurityPolicyType.NoSecurity:
                    _logger.info(f"Security policy configured as '{full_policy_name}' which resolved to NoSecurity for {plc_name}.")
                    policies_to_set = [SecurityPolicyType.NoSecurity]
                else:
                    _logger.error(f"Unknown or unsupported security policy string: '{full_policy_name}' (from {security_policy} and {security_mode}) for {plc_name}. Falling back to NoSecurity.")
                    policies_to_set = [SecurityPolicyType.NoSecurity]

            except Exception as e_cert_load:
                _logger.error(f"Failed to load certificates or configure policy for {plc_name} ({security_policy}): {e_cert_load}. Falling back to NoSecurity.")
                policies_to_set = [SecurityPolicyType.NoSecurity]
    else:
        _logger.info(f"No specific security policy requested or 'NoSecurity' configured for {plc_name}. Using NoSecurity.")
        policies_to_set = [SecurityPolicyType.NoSecurity]

    if not hasattr(server, 'set_security_policies'):
        _logger.critical(f"CRITICAL: Server object for {plc_name} does not have 'set_security_policies' method. OPC UA security cannot be configured. Please check your asyncua library version.")
    else:
        try:
            await server.set_security_policies(policies_to_set)
            policy_names = [p.name for p in policies_to_set]
            _logger.info(f"Successfully applied security policies {policy_names} to {plc_name}.")
        except Exception as e_set_policy:
            _logger.error(f"Error setting security policies {policy_names} for {plc_name}: {e_set_policy}")
            _logger.warning(f"Attempting to fall back to only NoSecurity for {plc_name}.")
            try:
                await server.set_security_policies([SecurityPolicyType.NoSecurity])
                _logger.info(f"Successfully fell back to NoSecurity policy for {plc_name}.")
            except Exception as e_fallback_policy:
                _logger.error(f"Failed to fall back to NoSecurity policy for {plc_name}: {e_fallback_policy}. Server may not start correctly with desired security.")

    # Create a folder to organize our PLC variables
    plc_folder = await server.nodes.objects.add_folder(
        ua.NodeId(f"{plc_name}Variables", idx),
        ua.QualifiedName(f"{plc_name}Variables", idx)
    )
    _logger.info(f"Created folder for {plc_name} variables")
    
    # Add variables to the address space
    simulated_nodes = {}
    for variable_config in variables_config:
        node_id_suffix = variable_config["node_id"]
        var_type = variable_config["type"]
        
        # Create a NodeId and BrowseName for the variable
        node_id = ua.NodeId(node_id_suffix, idx)
        browse_name = ua.QualifiedName(node_id_suffix, idx)
        display_name = ua.LocalizedText(node_id_suffix)
        
        # Define initial value based on data type
        initial_value = None
        if var_type == ua.VariantType.Double: initial_value = 0.0
        elif var_type == ua.VariantType.Int32: initial_value = 0
        elif var_type == ua.VariantType.UInt32: initial_value = 0
        elif var_type == ua.VariantType.Int16: initial_value = 0
        elif var_type == ua.VariantType.UInt16: initial_value = 0
        elif var_type == ua.VariantType.Float: initial_value = 0.0
        elif var_type == ua.VariantType.Byte: initial_value = 0
        elif var_type == ua.VariantType.SByte: initial_value = 0
        elif var_type == ua.VariantType.DateTime: initial_value = datetime.datetime.now()
        elif var_type == ua.VariantType.Boolean: initial_value = False
        elif var_type == ua.VariantType.String: initial_value = ""
        else: initial_value = None
        
        # Add variable to our folder
        variable_node = await plc_folder.add_variable(
            node_id, 
            browse_name, 
            initial_value,
            varianttype=var_type
        )
        
        # Set Description attribute (DisplayName is set by add_variable via bname)
        await variable_node.write_attribute(ua.AttributeIds.Description, 
                                          ua.DataValue(ua.LocalizedText(f"Simulated {node_id_suffix} for {plc_name}")))
        
        # Make it writable
        await variable_node.set_writable()
        
        # Enable history for this variable if requested
        if history_successfully_enabled:
            try:
                await server.historize_node_data_change(variable_node, period=None, count=100)
                _logger.info(f"Enabled history for {node_id_suffix} in {plc_name}")
            except Exception as e_historize_var:
                _logger.error(f"Failed to historize variable '{node_id_suffix}' in {plc_name}: {e_historize_var}")
        elif enable_history:
            _logger.warning(f"Skipping historization for variable '{node_id_suffix}' in {plc_name} due to earlier history storage setup failure.")
        
        # Store node for later updates
        simulated_nodes[node_id_suffix] = variable_node
        _logger.info(f"Added variable '{node_id_suffix}' to {plc_name}")
    
    _logger.info(f"Starting Virtual PLC Server '{plc_name}' on {url}")
    
    # Start server and run simulation loop
    async with server:
        counter_val = 0
        while True:
            await asyncio.sleep(1)
            # Simulate data changes for each node
            for node_suffix, node_obj in simulated_nodes.items():
                try:
                    if node_suffix == "SimulatedAnalogValue":
                        new_val = await node_obj.get_value() + 0.5
                        await node_obj.write_value(new_val) # Assuming Double, cast if necessary
                        _logger.debug(f"[{plc_name}] {node_suffix} = {new_val:.1f}")
                    elif node_suffix == "SimulatedCounter":
                        counter_val += 1
                        await node_obj.write_value(ua.Int32(counter_val)) # Explicitly cast to Int32
                        _logger.debug(f"[{plc_name}] {node_suffix} = {counter_val}")
                    elif node_suffix == "SimulatedBoolean":
                        current_bool = await node_obj.get_value()
                        await node_obj.write_value(not current_bool)
                        _logger.debug(f"[{plc_name}] {node_suffix} = {not current_bool}")
                    elif node_suffix == "SimulatedString":
                        await node_obj.write_value(f"String_{counter_val % 10}")
                        _logger.debug(f"[{plc_name}] {node_suffix} = String_{counter_val % 10}")
                    elif node_suffix == "SimulatedDateTime":
                        await node_obj.write_value(datetime.datetime.now())
                        _logger.debug(f"[{plc_name}] {node_suffix} = {datetime.datetime.now()}")
                    elif node_suffix == "SimulatedByte":
                        await node_obj.write_value(ua.Byte(counter_val % 256))
                        _logger.debug(f"[{plc_name}] {node_suffix} = {counter_val % 256}")
                    elif node_suffix == "SimulatedSByte":
                        await node_obj.write_value(ua.SByte(counter_val % 128))
                        _logger.debug(f"[{plc_name}] {node_suffix} = {counter_val % 128}")
                    elif node_suffix == "SimulatedInt16":
                        await node_obj.write_value(ua.Int16(counter_val % 32768))
                        _logger.debug(f"[{plc_name}] {node_suffix} = {counter_val % 32768}")
                    elif node_suffix == "SimulatedUInt16":
                        await node_obj.write_value(ua.UInt16(counter_val % 65536))
                        _logger.debug(f"[{plc_name}] {node_suffix} = {counter_val % 65536}")
                    elif node_suffix == "SimulatedInt32":
                        await node_obj.write_value(ua.Int32(counter_val % 2147483648))
                        _logger.debug(f"[{plc_name}] {node_suffix} = {counter_val % 2147483648}")
                    elif node_suffix == "SimulatedUInt32":
                        await node_obj.write_value(ua.UInt32(counter_val % 4294967296))
                        _logger.debug(f"[{plc_name}] {node_suffix} = {counter_val % 4294967296}")
                    elif node_suffix == "SimulatedFloat":
                        await node_obj.write_value(ua.Float(counter_val % 1000))
                        _logger.debug(f"[{plc_name}] {node_suffix} = {counter_val % 1000}")
                    elif node_suffix == "SimulatedDouble":
                        await node_obj.write_value(ua.Double(counter_val % 1000.0))
                        _logger.debug(f"[{plc_name}] {node_suffix} = {counter_val % 1000.0}")
                except Exception as e:
                    _logger.error(f"Error updating {node_suffix} in {plc_name}: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # PLC 1 Configuration
    plc1_name = "Virtual_PLC_1"
    plc1_port = 4841
    plc1_url = f"opc.tcp://0.0.0.0:{plc1_port}/virtualplc/server/"
    plc1_namespace_uri = "http://virtualplc.io/plc1"
    plc1_variables_config = [
        {"node_id": "SimulatedAnalogValue", "type": ua.VariantType.Double},
        {"node_id": "SimulatedBoolean", "type": ua.VariantType.Boolean},
        # {"node_id": "SimulatedByte", "type": ua.VariantType.Byte},
        # {"node_id": "SimulatedDouble", "type": ua.VariantType.Double},
        # {"node_id": "SimulatedFloat", "type": ua.VariantType.Float},
        # {"node_id": "SimulatedInt16", "type": ua.VariantType.Int16},
        # {"node_id": "SimulatedSByte", "type": ua.VariantType.SByte},
        # {"node_id": "SimulatedString", "type": ua.VariantType.String},
        # {"node_id": "SimulatedUInt16", "type": ua.VariantType.UInt16},
        # {"node_id": "SimulatedUInt32", "type": ua.VariantType.UInt32}
    ]
    
    # PLC 2 Configuration
    plc2_name = "Virtual_PLC_2"
    plc2_port = 4842
    plc2_url = f"opc.tcp://0.0.0.0:{plc2_port}/virtualplc/server/"
    plc2_namespace_uri = "http://virtualplc.io/plc2"
    plc2_variables_config = [
        {"node_id": "SimulatedCounter", "type": ua.VariantType.Int32},
        {"node_id": "SimulatedString", "type": ua.VariantType.String}
    ]
    plc2_username = "user"
    plc2_password = "password"
    plc2_security_mode = "SignAndEncrypt" # This informs client, server policy is set by policy string
    plc2_security_policy = "Basic256Sha256" # Base policy name
    
    # Certificate paths for PLC 2
    cert_dir = "certs"
    private_dir = os.path.join(cert_dir, "private")
    plc2_cert_path = os.path.join(cert_dir, f"{plc2_name.lower()}_certificate.der")
    plc2_key_path = os.path.join(private_dir, f"{plc2_name.lower()}_private_key.pem")
    
    # Create certificate directories if they don't exist
    os.makedirs(cert_dir, exist_ok=True)
    os.makedirs(private_dir, exist_ok=True)
    
    # Generate certificates if they don't exist
    if not (os.path.exists(plc2_cert_path) and os.path.exists(plc2_key_path)):
        _logger.warning(f"Certificates for {plc2_name} not found. Generating new certificates using OpenSSL.")
        try:
            import subprocess
            # Generate private key
            subprocess.run(["openssl", "genrsa", "-out", plc2_key_path, "2048"], check=True, capture_output=True)
            
            # Generate self-signed certificate (DER format as used before)
            subject = f"/CN={plc2_name}/O=VirtualPLC/C=US/ST=California/L=CityName"
            subprocess.run([
                "openssl", "req", "-new", "-x509", "-key", plc2_key_path, 
                "-out", plc2_cert_path, "-days", "365", 
                "-subj", subject,
                "-outform", "DER"  # Output in DER format
            ], check=True, capture_output=True)
            
            # Set appropriate permissions for the private key
            os.chmod(plc2_key_path, 0o600)
            _logger.info(f"Generated certificates for {plc2_name} using OpenSSL.")
        except subprocess.CalledProcessError as e:
            _logger.error(f"OpenSSL command failed for {plc2_name}: {e}")
            _logger.error(f"stdout: {e.stdout.decode() if e.stdout else 'N/A'}")
            _logger.error(f"stderr: {e.stderr.decode() if e.stderr else 'N/A'}")
            sys.exit(1)
        except Exception as e:
            _logger.error(f"Failed to generate certificates for {plc2_name}: {e}")
            import traceback
            _logger.error(traceback.format_exc())
            sys.exit(1)

    # Run servers concurrently
    async def run_all_plcs():
        try:
            await asyncio.gather(
                run_virtual_plc_server(
                    plc_name=plc1_name, 
                    url=plc1_url, 
                    namespace_uri=plc1_namespace_uri, 
                    variables_config=plc1_variables_config,
                    enable_history=True
                ),
                run_virtual_plc_server(
                    plc_name=plc2_name, 
                    url=plc2_url, 
                    namespace_uri=plc2_namespace_uri, 
                    variables_config=plc2_variables_config,
                    username=plc2_username, 
                    password=plc2_password,
                    security_policy=plc2_security_policy,
                    security_mode=plc2_security_mode,
                    cert_path=plc2_cert_path, 
                    key_path=plc2_key_path,
                    enable_history=True
                )
            )
        except Exception as e:
            _logger.error(f"Error running PLCs: {e}")
            import traceback
            _logger.error(traceback.format_exc())

    asyncio.run(run_all_plcs())