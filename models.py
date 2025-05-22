# models.py
from typing import Optional, Dict, Any
from sqlmodel import Field, SQLModel, create_engine
import os
import bcrypt # For password hashing
import logging
from asyncua import ua # For VariantType reference

_logger = logging.getLogger(__name__)

# Helper to map string to VariantType (moved here for broader access if needed)
def get_variant_type(type_str: str) -> ua.VariantType:
    try:
        return getattr(ua.VariantType, type_str.upper())
    except AttributeError:
        _logger.warning(f"Unknown data type: {type_str}. Defaulting to String.")
        return ua.VariantType.String

class ServerConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    enable_service: bool = Field(default=True)
    port: int = Field(default=51210)
    max_clients: int = Field(default=4)
    user_account_control_method: str = Field(default="Anonymous") # "Anonymous", "Username/Password"
    username: Optional[str] = Field(default=None)
    password_hash: Optional[str] = Field(default=None) # Store hashed password

    node_id_namespace_uri: str = Field(default="http://yourcompany.com/opcua/gateway/")

    # Security Policy Configuration
    security_policy_none_enabled: bool = Field(default=True)
    security_policy_basic128rsa15_enabled: bool = Field(default=False)
    security_policy_basic256_enabled: bool = Field(default=False)
    security_policy_basic256sha256_enabled: bool = Field(default=False)
    message_security_mode: str = Field(default="None") # "None", "Sign", "Sign and Encrypt"

    # Certificate Paths
    server_cert_path: str = Field(default="certs/server/server_cert.pem")
    server_key_path: str = Field(default="certs/server/server_key.pem")
    ca_cert_dir: str = Field(default="certs/client_trusted") # Directory for trusted client certificates

    # Discovery Server Configuration
    enable_local_discovery_server: bool = Field(default=False)
    lds_server_url: Optional[str] = Field(default=None)
    registration_interval_seconds: int = Field(default=300)

    # Method to hash a password
    def set_password(self, password: str):
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Method to verify a password
    def verify_password(self, password: str) -> bool:
        if self.password_hash is None:
            return False
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

class OpcUaNode(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    node_id: str = Field(unique=True, index=True) # NodeId on the GATEWAY's server
    data_type: str # e.g., "Double", "Int32", "Boolean", "String"
    engineering_units: Optional[str] = None
    browse_name: str
    display_name: str
    description: Optional[str] = None

    # Source configuration for the gateway node
    source_type: str = Field(default="Internal", description="Source of data: 'Internal', 'OPC_UA_Client'")
    initial_value: Optional[str] = None # For 'Internal' nodes, stored as string

    # OPC UA Client specific configuration (if source_type is 'OPC_UA_Client')
    opcua_client_endpoint: Optional[str] = Field(default=None, description="Endpoint of the external OPC UA server (PLC)")
    opcua_client_source_node_id: Optional[str] = Field(default=None, description="Node ID on the external OPC UA server to read from")
    opcua_client_username: Optional[str] = Field(default=None)
    opcua_client_password: Optional[str] = Field(default=None) # Store as plain text or hash, depending on security model
    opcua_client_security_mode: Optional[str] = Field(default="None", description="e.g., 'None', 'Sign', 'SignAndEncrypt'")
    opcua_client_security_policy: Optional[str] = Field(default="None", description="e.g., 'None', 'Basic256Sha256'")


# Database engine setup
sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url, echo=False) # echo=True for SQL logs

def create_db_and_tables():
    """Creates database tables based on SQLModel definitions."""
    SQLModel.metadata.create_all(engine)

# Helper function to get initial value in correct type for OPC UA Server
def get_initial_value_typed(value_str: Optional[str], data_type_str: str) -> Any:
    if value_str is None:
        return None # Let asyncua handle default for None

    variant_type = get_variant_type(data_type_str)
    try:
        if variant_type == ua.VariantType.Double:
            return float(value_str)
        elif variant_type == ua.VariantType.Int32:
            return int(value_str)
        elif variant_type == ua.VariantType.Boolean:
            return value_str.lower() == 'true' or value_str == '1'
        elif variant_type == ua.VariantType.String:
            return str(value_str)
        # Add more conversions as needed
        return value_str # Fallback
    except (ValueError, TypeError) as e:
        _logger.error(f"Failed to convert initial value '{value_str}' to {data_type_str}: {e}. Returning original string.")
        return value_str