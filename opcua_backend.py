# main.py
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select, delete
import logging
import asyncio
import os
import bcrypt
import yaml # pip install PyYAML
import io # For in-memory file operations for export
import subprocess
import sys
import signal
import time
from contextlib import asynccontextmanager
from pydantic import BaseModel # Moved Pydantic import earlier

from models import create_db_and_tables, ServerConfig, OpcUaNode, engine
from typing import List, Dict, Any, Optional

_logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

running_opcua_subprocesses = []

# Global list to keep track of running OPC UA related subprocesses

# Database session dependency
def get_db():
    with Session(engine) as session:
        yield session

# New functions for OPC UA components management

def write_opcua_client_config(config_data: dict, output_path: str):
    """Writes the OPC UA client configuration to a YAML file."""
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            yaml.dump(config_data, f, sort_keys=False)
        _logger.info(f"OPC UA client configuration written to {output_path}")
        return True
    except Exception as e:
        _logger.error(f"Failed to write OPC UA client configuration to {output_path}: {e}")
        return False

def start_opcua_gateway_client(client_settings: dict):
    """Starts the opcua_gateway_client.py script as a subprocess."""
    if not client_settings.get("enabled", False):
        _logger.info("OPC UA Gateway Client is disabled in configuration.")
        return None

    script_path = client_settings.get("script_path")
    config_output_path = client_settings.get("config_output_path")
    client_data_for_config_file = client_settings.get("data")

    if not all([script_path, config_output_path, client_data_for_config_file]):
        _logger.error("Missing critical settings for OPC UA Gateway Client (script_path, config_output_path, or data).")
        return None

    if not os.path.exists(script_path):
        _logger.error(f"OPC UA Gateway Client script not found at {script_path}")
        return None

    if not write_opcua_client_config(client_data_for_config_file, config_output_path):
        _logger.error("Failed to generate OPC UA client config file. Client will not start.")
        return None
    
    try:
        _logger.info(f"Starting OPC UA Gateway Client: {script_path}")
        process = subprocess.Popen([sys.executable, script_path], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
        running_opcua_subprocesses.append(process)
        _logger.info(f"OPC UA Gateway Client started with PID: {process.pid}")
        return process
    except Exception as e:
        _logger.error(f"Failed to start OPC UA Gateway Client: {e}")
        return None

def start_opcua_csv_data_server(server_settings: dict):
    """Starts the opcua_csv_data_server.py script as a subprocess."""
    if not server_settings.get("enabled", False):
        _logger.info("OPC UA CSV Data Server is disabled in configuration.")
        return None

    script_path = server_settings.get("script_path")
    if not script_path or not os.path.exists(script_path):
        _logger.error(f"OPC UA CSV Data Server script not found at {script_path or 'Not specified'}")
        return None

    cmd = [sys.executable, script_path]
    if server_settings.get("url"):
        cmd.extend(["--url", server_settings["url"]])
    if server_settings.get("namespace_uri"):
        cmd.extend(["--ns_uri", server_settings["namespace_uri"]])
    if server_settings.get("csv_file_path"):
        cmd.extend(["--csv_file", server_settings["csv_file_path"]])
    if server_settings.get("update_interval_seconds"):
        cmd.extend(["--interval", str(server_settings["update_interval_seconds"])])
    if server_settings.get("log_level"):
        cmd.extend(["--log_level", server_settings["log_level"]])

    try:
        _logger.info(f"Starting OPC UA CSV Data Server: {' '.join(cmd)}")
        process = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
        running_opcua_subprocesses.append(process)
        _logger.info(f"OPC UA CSV Data Server started with PID: {process.pid}")
        return process
    except Exception as e:
        _logger.error(f"Failed to start OPC UA CSV Data Server: {e}")
        return None

def shutdown_opcua_subprocesses():
    _logger.info("Shutting down OPC UA subprocesses...")
    for process in running_opcua_subprocesses:
        if process.poll() is None: # Check if process is still running
            _logger.info(f"Terminating process {process.pid}...")
            if os.name == 'nt':
                process.send_signal(signal.CTRL_BREAK_EVENT) # For Windows, to allow graceful shutdown if handled
            else:
                process.terminate() # SIGTERM
            try:
                process.wait(timeout=10) # Wait for graceful termination
                _logger.info(f"Process {process.pid} terminated gracefully.")
            except subprocess.TimeoutExpired:
                _logger.warning(f"Process {process.pid} did not terminate gracefully, killing.")
                process.kill()
                _logger.info(f"Process {process.pid} killed.")
            except Exception as e:
                 _logger.error(f"Error during termination of {process.pid}: {e}")
    running_opcua_subprocesses.clear()
    _logger.info("OPC UA subprocess shutdown complete.")

class GatewayClientConfigData(BaseModel):
    plcs: Dict[str, Any] 
    # Optional: Add other fields if opcua_gateway_client.py expects them directly in its config file
    # csv_log_file: Optional[str] = None
    # log_interval: Optional[int] = None

class GatewayClientSettings(BaseModel):
    enabled: bool = True
    script_path: str
    config_output_path: str # Path where the client's specific config will be written
    data: GatewayClientConfigData

class CsvDataServerSettings(BaseModel):
    enabled: bool = True
    script_path: str
    url: str
    namespace_uri: str
    csv_file_path: str # Must match the output of opcua_gateway_client.py
    update_interval_seconds: int = 10
    log_level: str = "INFO"

class OpcUaComponentsStartRequest(BaseModel):
    gateway_client_settings: Optional[GatewayClientSettings] = None
    csv_data_server_settings: Optional[CsvDataServerSettings] = None

async def _start_csv_server_with_delay_logic(csv_server_settings_dict: dict, gateway_client_was_started: bool):
    """Helper async function to handle delayed start of CSV server."""
    csv_file_path = csv_server_settings_dict.get("csv_file_path")

    if not csv_file_path:
        _logger.error("CSV file path not specified in csv_data_server_settings. Cannot start OPC UA CSV Data Server.")
        return False
    
    if not gateway_client_was_started:
        _logger.warning("OPC UA Gateway Client was not started or failed to start. OPC UA CSV Data Server will not be started as it may depend on the client's output CSV.")
        # Depending on requirements, we might still try to start it if the CSV file could exist independently.
        # For now, let's assume dependency.
        return False

    _logger.info(f"Waiting for OPC UA Gateway Client to create/populate CSV file: {csv_file_path}")
    csv_ready = False
    max_wait_time_seconds = csv_server_settings_dict.get("wait_for_csv_timeout", 30)  # Allow timeout to be configurable
    check_interval_seconds = 2
    wait_time_elapsed = 0
    
    while wait_time_elapsed < max_wait_time_seconds:
        if os.path.exists(csv_file_path) and os.path.getsize(csv_file_path) > 0:
            _logger.info(f"CSV file {csv_file_path} is ready.")
            csv_ready = True
            break
        _logger.info(f"CSV file {csv_file_path} not ready yet. Waiting {check_interval_seconds}s... ({wait_time_elapsed}/{max_wait_time_seconds}s)")
        await asyncio.sleep(check_interval_seconds)
        wait_time_elapsed += check_interval_seconds
    
    if csv_ready:
        start_opcua_csv_data_server(csv_server_settings_dict)
        return True
    else:
        _logger.error(f"CSV file {csv_file_path} was not ready after {max_wait_time_seconds} seconds. OPC UA CSV Data Server will not be started.")
        return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    _logger.info("FastAPI application startup (lifespan)...")
    create_db_and_tables() 
    _logger.info("FastAPI application startup sequence complete (lifespan). OPC UA components will NOT be started automatically.")
    
    yield # FastAPI app runs here
    
    # Shutdown logic
    _logger.info("FastAPI application shutdown (lifespan)...")
    shutdown_opcua_subprocesses() # This will stop any components started via the API
    _logger.info("FastAPI application shutdown complete (lifespan).")

app = FastAPI(
    title="Vista OPC UA Backend",
    description="FastAPI application for OPC UA Gateway configuration and data management. OPC UA components are started via API.",
    lifespan=lifespan
)

# Database session dependency
def get_db():
    with Session(engine) as session:
        yield session

# --- Server Configuration API Endpoints ---
@app.get("/api/config", response_model=ServerConfig)
async def get_server_config(db: Session = Depends(get_db)):
    config = db.exec(select(ServerConfig)).first()
    if not config:
        raise HTTPException(status_code=404, detail="Server configuration not found.")
    return config

@app.put("/api/config", response_model=ServerConfig)
async def update_server_config(updated_config: ServerConfig, db: Session = Depends(get_db)):
    db_config = db.exec(select(ServerConfig)).first()
    if not db_config:
        raise HTTPException(status_code=404, detail="Server configuration not found.")

    # Update database object by copying fields from updated_config
    # Use model_dump to handle Optional fields correctly
    update_data = updated_config.model_dump(exclude_unset=True)

    # Handle password hashing if method is Username/Password and password field is provided
    if update_data.get("user_account_control_method") == "Username/Password" and "password_hash" in update_data and update_data["password_hash"]:
        # Only hash if it doesn't look like an already hashed password
        if not str(update_data["password_hash"]).startswith('$2b$'):
            db_config.set_password(update_data["password_hash"])
        else:
            db_config.password_hash = update_data["password_hash"] # Assume it's already hashed
    elif update_data.get("user_account_control_method") == "Anonymous":
        db_config.username = None
        db_config.password_hash = None
    
    # Apply other updates
    for key, value in update_data.items():
        if key not in ["id", "password_hash"]: # 'id' is primary key, password_hash handled above
            setattr(db_config, key, value)

    db.add(db_config)
    db.commit()
    db.refresh(db_config)

    return db_config

@app.post("/api/server/start", status_code=status.HTTP_200_OK)
async def start_server(db: Session = Depends(get_db)):
    config = db.exec(select(ServerConfig)).first()
    if not config:
        raise HTTPException(status_code=404, detail="Server configuration not found.")
    
    # Update config in DB to enable service
    config.enable_service = True
    db.add(config)
    db.commit()
    db.refresh(config)

    return {"message": "OPC UA Server started."}

@app.post("/api/server/stop", status_code=status.HTTP_200_OK)
async def stop_server(db: Session = Depends(get_db)):
    config = db.exec(select(ServerConfig)).first()
    if not config:
        raise HTTPException(status_code=404, detail="Server configuration not found.")

    # Update config in DB to disable service
    config.enable_service = False
    db.add(config)
    db.commit()
    db.refresh(config)

    return {"message": "OPC UA Server stopped."}

# --- Node Management API Endpoints ---
@app.get("/api/nodes", response_model=List[OpcUaNode])
async def get_all_nodes(db: Session = Depends(get_db)):
    nodes = db.exec(select(OpcUaNode)).all()
    return nodes

@app.get("/api/nodes/{node_id_from_url}", response_model=OpcUaNode)
async def get_node_by_id(node_id_from_url: str, db: Session = Depends(get_db)):
    node = db.exec(select(OpcUaNode).where(OpcUaNode.node_id == node_id_from_url)).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found.")
    return node

@app.post("/api/nodes", response_model=OpcUaNode, status_code=status.HTTP_201_CREATED)
async def create_node(node: OpcUaNode, db: Session = Depends(get_db)):
    # Check if node_id already exists to prevent integrity errors
    existing_node = db.exec(select(OpcUaNode).where(OpcUaNode.node_id == node.node_id)).first()
    if existing_node:
        raise HTTPException(status_code=400, detail=f"Node with Node ID '{node.node_id}' already exists.")

    try:
        db.add(node)
        db.commit()
        db.refresh(node)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="A database integrity error occurred, possibly duplicate Node ID.")

    return node

@app.put("/api/nodes/{node_id_from_url}", response_model=OpcUaNode)
async def update_node(node_id_from_url: str, updated_node: OpcUaNode, db: Session = Depends(get_db)):
    db_node = db.exec(select(OpcUaNode).where(OpcUaNode.node_id == node_id_from_url)).first()
    if not db_node:
        raise HTTPException(status_code=404, detail="Node not found.")

    # Update database object by copying fields from updated_node
    update_data = updated_node.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key != "id": # 'id' is primary key, should not be updated
            setattr(db_node, key, value)

    db.add(db_node)
    db.commit()
    db.refresh(db_node)

    return db_node

@app.delete("/api/nodes/{node_id_from_url}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(node_id_from_url: str, db: Session = Depends(get_db)):
    db_node = db.exec(select(OpcUaNode).where(OpcUaNode.node_id == node_id_from_url)).first()
    if not db_node:
        raise HTTPException(status_code=404, detail="Node not found.")
    
    db.delete(db_node)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)

# --- Full Configuration Import/Export Endpoints ---
@app.post("/api/config/import_full", status_code=status.HTTP_200_OK)
async def import_full_config(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Imports full gateway configuration (server settings and nodes) from a YAML/JSON file.
    Existing configurations will be overwritten.
    """
    if not (file.filename.endswith('.yaml') or file.filename.endswith('.yml') or file.filename.endswith('.json')):
        raise HTTPException(status_code=400, detail="Only YAML or JSON files are supported for full config import.")
    
    content = await file.read()
    try:
        config_data = yaml.safe_load(content.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse config file: {e}")

    imported_server_config = None
    imported_nodes_count = 0
    errors = []

    # Process server_config
    server_config_data = config_data.get("server_config")
    if server_config_data:
        current_config = db.exec(select(ServerConfig)).first()
        if not current_config:
            current_config = ServerConfig()
            db.add(current_config)
            db.flush() # Ensure it has an ID if new
        
        # Manually update fields, excluding 'id' and handling password_hash
        for key, value in server_config_data.items():
            if key == "password_hash":
                if value and not str(value).startswith('$2b$'): # Only hash if it's not already hashed
                    current_config.set_password(value)
                elif value:
                    current_config.password_hash = value # Assume it's already hashed
                else: # if password_hash is null/empty
                    current_config.password_hash = None
            elif key != "id":
                setattr(current_config, key, value)
        
        db.add(current_config) # Add or update
        db.commit()
        db.refresh(current_config)
        imported_server_config = current_config
        _logger.info("Server config imported and updated.")
    else:
        _logger.warning("No 'server_config' found in the import file.")

    # Process opcua_nodes
    nodes_data = config_data.get("opcua_nodes", [])
    
    # Clear existing nodes for a clean import
    db.exec(delete(OpcUaNode))
    db.commit()
    
    for node_row in nodes_data:
        try:
            node = OpcUaNode(**node_row)
            db.add(node)
            db.commit() # Commit each node to ensure it gets an ID and is available for refresh
            db.refresh(node)
            imported_nodes_count += 1
        except Exception as e:
            errors.append(f"Error importing node row {node_row}: {e}")
            db.rollback() # Rollback the failed node creation

    _logger.info(f"Nodes imported: {imported_nodes_count}, errors: {len(errors)}")

    # After import, reinitialize/restart server and client managers
    if imported_server_config:
        # Update config in DB to enable service
        imported_server_config.enable_service = True
        db.add(imported_server_config)
        db.commit()
        db.refresh(imported_server_config)

    # Shutdown and restart external OPC UA subprocesses
    shutdown_opcua_subprocesses()
    if config_data.get("gateway_client_settings"):
        start_opcua_gateway_client(config_data["gateway_client_settings"])
    if config_data.get("csv_data_server_settings"):
        start_opcua_csv_data_server(config_data["csv_data_server_settings"])

    return {"message": "Full configuration import finished.", "imported_nodes": imported_nodes_count, "errors": errors}

@app.get("/api/config/export_full", status_code=status.HTTP_200_OK)
async def export_full_config(db: Session = Depends(get_db)):
    """Exports the full gateway configuration (server settings and nodes) as a YAML file."""
    server_config = db.exec(select(ServerConfig)).first()
    nodes = db.exec(select(OpcUaNode)).all()

    # Convert SQLModel instances to dict for YAML/JSON serialization
    export_data = {
        "server_config": server_config.model_dump() if server_config else {},
        "opcua_nodes": [node.model_dump() for node in nodes]
    }

    output = io.StringIO()
    # Use sort_keys=False to preserve order, better for human readability in YAML
    yaml.dump(export_data, output, sort_keys=False, default_flow_style=False, allow_unicode=True) 

    response = Response(content=output.getvalue(), media_type="application/x-yaml")
    response.headers["Content-Disposition"] = "attachment; filename=gateway_config.yaml"
    return response

# --- New API Endpoint to start OPC UA Components ---
@app.post("/api/opcua/control/start", status_code=status.HTTP_202_ACCEPTED)
async def api_start_opcua_components(config_request: OpcUaComponentsStartRequest):
    _logger.info("Received request to start OPC UA components.")

    # Stop any existing managed subprocesses first
    _logger.info("Shutting down any existing OPC UA subprocesses before starting new ones...")
    shutdown_opcua_subprocesses() 
    # Give a brief moment for processes to terminate if needed
    await asyncio.sleep(1) 

    gateway_client_started_successfully = False

    if config_request.gateway_client_settings:
        if config_request.gateway_client_settings.enabled:
            _logger.info("Attempting to start OPC UA Gateway Client based on provided configuration.")
            client_settings_dict = config_request.gateway_client_settings.model_dump()
            process = start_opcua_gateway_client(client_settings_dict)
            if process:
                gateway_client_started_successfully = True
        else:
            _logger.info("OPC UA Gateway Client is disabled in the request configuration.")
    else:
        _logger.info("No OPC UA Gateway Client settings provided in the request.")

    csv_server_started_successfully = False
    if config_request.csv_data_server_settings:
        if config_request.csv_data_server_settings.enabled:
            _logger.info("Attempting to start OPC UA CSV Data Server based on provided configuration.")
            csv_server_settings_dict = config_request.csv_data_server_settings.model_dump()
            # The helper function now takes gateway_client_was_started flag
            csv_server_started_successfully = await _start_csv_server_with_delay_logic(csv_server_settings_dict, gateway_client_started_successfully)
        else:
            _logger.info("OPC UA CSV Data Server is disabled in the request configuration.")
    else:
        _logger.info("No OPC UA CSV Data Server settings provided in the request.")

    if gateway_client_started_successfully or csv_server_started_successfully:
        return {"message": "OPC UA components start process initiated.", "gateway_client_started": gateway_client_started_successfully, "csv_data_server_started": csv_server_started_successfully}
    else:
        return {"message": "No OPC UA components were started. Check settings or logs.", "gateway_client_started": False, "csv_data_server_started": False}

# --- Static files and main execution block ---
# app.mount("/static", StaticFiles(directory="static"), name="static")
# @app.get("/")
# async def read_root():
#     return FileResponse('static/index.html')

if __name__ == "__main__":
    import uvicorn
    _logger.info("Starting Uvicorn server for OPC UA Backend...")
    uvicorn.run("opcua_backend:app", host="0.0.0.0", port=8000, reload=True)