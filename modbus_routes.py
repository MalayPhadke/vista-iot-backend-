#!/usr/bin/env python3
import yaml
import csv
import os
from flask import request, jsonify
from modbus import (
    ModbusTagManager, 
    configure_modbus, 
    start_modbus_system, 
    stop_modbus_system,
    create_tag_from_data
)

# Store active Modbus systems
ACTIVE_MODBUS_SYSTEMS = {}

def register_modbus_routes(app):
    """Register Modbus routes with the Flask app"""
    tag_manager = ModbusTagManager()
    
    @app.route('/api/modbus/configure', methods=['POST'])
    def modbus_configure():
        """
        Configure the Modbus system
        Expects a YAML or JSON payload with configuration
        """
        try:
            if request.content_type == 'application/x-yaml' or request.content_type == 'text/yaml':
                config = yaml.safe_load(request.data)
            elif request.content_type == 'application/json':
                config = request.json
            else:
                return jsonify({"error": "Content-Type must be application/x-yaml, text/yaml, or application/json"}), 400
            
            # Check for required configuration fields
            if not config:
                return jsonify({"error": "Empty configuration"}), 400
            
            # Get configuration parameters
            address_ranges = config.get("address_ranges", "")
            ip = config.get("ip", "0.0.0.0")
            port = config.get("port", 502)
            unit_ids = config.get("unit_ids", "1")
            mode = config.get("mode", "both")
            
            # Configure Modbus
            modbus_config = configure_modbus(
                address_ranges_str=address_ranges,
                ip=ip,
                port=port,
                unit_ids_str=unit_ids,
                mode=mode
            )
            
            # Stop existing system if any
            if 'default' in ACTIVE_MODBUS_SYSTEMS:
                stop_modbus_system(ACTIVE_MODBUS_SYSTEMS['default'])
            
            # Start new system
            system = start_modbus_system()
            ACTIVE_MODBUS_SYSTEMS['default'] = system
            
            return jsonify({
                "success": True,
                "message": f"Modbus configured in {mode} mode",
                "config": modbus_config
            })
            
        except yaml.YAMLError as e:
            return jsonify({"error": f"Invalid YAML: {str(e)}"}), 400
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": f"Unexpected error: {str(e)}"}), 500
    
    @app.route('/api/modbus/tags', methods=['GET'])
    def get_modbus_tags():
        """Get all defined Modbus tags"""
        try:
            tags = tag_manager.get_all_tags()
            return jsonify({
                "success": True,
                "count": len(tags),
                "tags": tags
            })
        except Exception as e:
            return jsonify({"error": f"Unexpected error: {str(e)}"}), 500
    
    @app.route('/api/modbus/tags/<tag_name>', methods=['GET'])
    def get_modbus_tag(tag_name):
        """Get a specific Modbus tag by name"""
        try:
            tag = tag_manager.get_tag(tag_name)
            if not tag:
                return jsonify({"error": f"Tag not found: {tag_name}"}), 404
            
            return jsonify({
                "success": True,
                "tag": tag
            })
        except Exception as e:
            return jsonify({"error": f"Unexpected error: {str(e)}"}), 500
    
    @app.route('/api/modbus/tags', methods=['POST'])
    def create_modbus_tag():
        """Create or update a Modbus tag"""
        try:
            if request.content_type == 'application/x-yaml' or request.content_type == 'text/yaml':
                data = yaml.safe_load(request.data)
            elif request.content_type == 'application/json':
                data = request.json
            else:
                return jsonify({"error": "Content-Type must be application/x-yaml, text/yaml, or application/json"}), 400
            
            # Check for required fields
            required_fields = ["Name", "Data_Type", "Address"]
            for field in required_fields:
                if field not in data:
                    return jsonify({"error": f"Missing required field: {field}"}), 400
            
            # Create tag using the provided data
            result = create_tag_from_data(
                name=data.get("Name"),
                data_type=data.get("Data_Type"),
                conversion=data.get("Conversion", "FLOAT, Big Endian, Swap Word (CDAB)"),
                address=data.get("Address"),
                start_bit=data.get("Start_Bit", "0"),
                length_bit=data.get("Length_Bit", "32"),
                span_high=data.get("Span_High", "1000"),
                span_low=data.get("Span_Low", "0"),
                default_value=data.get("Default_Value", "0.0"),
                scan_rate=data.get("Scan_Rate", "1"),
                read_write=data.get("Read_Write", "Read Write"),
                description=data.get("Description", ""),
                scaling_type=data.get("Scaling_Type", "No Scale"),
                formula=data.get("Formula", ""),
                scale=data.get("Scale", "0"),
                offset=data.get("Offset", "0"),
                clamp_to_span=data.get("Clamp_to_Span", "False"),
                clamp_high=data.get("Clamp_High", "False"),
                clamp_low=data.get("Clamp_Low", "False"),
                clamp_to_zero=data.get("Clamp_to_Zero", "False")
            )
            
            if result:
                return jsonify({
                    "success": True,
                    "message": f"Tag '{data['Name']}' created/updated successfully"
                })
            else:
                return jsonify({"error": "Failed to create/update tag"}), 500
            
        except yaml.YAMLError as e:
            return jsonify({"error": f"Invalid YAML: {str(e)}"}), 400
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": f"Unexpected error: {str(e)}"}), 500
    
    @app.route('/api/modbus/tags/<tag_name>', methods=['DELETE'])
    def delete_modbus_tag(tag_name):
        """Delete a Modbus tag"""
        try:
            result = tag_manager.delete_tag(tag_name)
            if result:
                return jsonify({
                    "success": True,
                    "message": f"Tag '{tag_name}' deleted successfully"
                })
            else:
                return jsonify({"error": f"Tag not found or could not be deleted: {tag_name}"}), 404
        except Exception as e:
            return jsonify({"error": f"Unexpected error: {str(e)}"}), 500
    
    @app.route('/api/modbus/export', methods=['GET'])
    def export_modbus_tags():
        """Export all Modbus tags to CSV"""
        try:
            tags = tag_manager.get_all_tags()
            
            if not tags:
                return jsonify({"message": "No tags to export"}), 404
            
            # Create a temporary CSV file
            temp_csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modbus_export.csv")
            with open(temp_csv_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=tag_manager.tags[list(tag_manager.tags.keys())[0]].keys())
                writer.writeheader()
                for tag in tags:
                    writer.writerow(tag)
            
            # Return the file content
            with open(temp_csv_path, 'r') as f:
                csv_content = f.read()
            
            # Clean up the temporary file
            os.remove(temp_csv_path)
            
            return csv_content, 200, {
                'Content-Type': 'text/csv',
                'Content-Disposition': 'attachment; filename=modbus_tags.csv'
            }
        except Exception as e:
            return jsonify({"error": f"Unexpected error: {str(e)}"}), 500
    
    @app.route('/api/modbus/import', methods=['POST'])
    def import_modbus_tags():
        """Import Modbus tags from CSV"""
        try:
            if 'file' not in request.files:
                return jsonify({"error": "No file provided"}), 400
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({"error": "No file selected"}), 400
            
            if not file.filename.endswith('.csv'):
                return jsonify({"error": "File must be CSV format"}), 400
            
            # Create a temporary file
            temp_csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modbus_import.csv")
            file.save(temp_csv_path)
            
            # Read the CSV and create tags
            imported_count = 0
            with open(temp_csv_path, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Create tag using row data
                    result = tag_manager.add_tag(row)
                    if result:
                        imported_count += 1
            
            # Clean up the temporary file
            os.remove(temp_csv_path)
            
            return jsonify({
                "success": True,
                "message": f"Successfully imported {imported_count} tags"
            })
        except Exception as e:
            return jsonify({"error": f"Unexpected error: {str(e)}"}), 500
    
    @app.route('/api/modbus/status', methods=['GET'])
    def modbus_status():
        """Get the status of the Modbus system"""
        try:
            status = {
                "master_running": False,
                "slave_running": False,
                "tag_count": len(tag_manager.get_all_tags())
            }
            
            if 'default' in ACTIVE_MODBUS_SYSTEMS:
                system = ACTIVE_MODBUS_SYSTEMS['default']
                if system.get("master"):
                    status["master_running"] = system["master"].running
                if system.get("slave"):
                    status["slave_running"] = system["slave"].running
            
            return jsonify({
                "success": True,
                "status": status
            })
        except Exception as e:
            return jsonify({"error": f"Unexpected error: {str(e)}"}), 500
    
    @app.route('/api/modbus/create-current-amp-sample', methods=['GET'])
    def create_current_amp_sample():
        """Create a sample Current_Amp tag as described in the requirements"""
        try:
            # Create the Current_Amp tag
            result = create_tag_from_data(
                name="Current_Amp",
                data_type="Analog",
                conversion="FLOAT, Big Endian, Swap Word (CDAB)",
                address="43913",
                start_bit="0",
                length_bit="32",
                span_high="1000",
                span_low="0",
                default_value="0.0",
                scan_rate="1",
                read_write="Read Write",
                description="Current measurement in Amperes",
                scaling_type="No Scale",
                formula="",
                scale="0",
                offset="0",
                clamp_to_span="False",
                clamp_high="False",
                clamp_low="False",
                clamp_to_zero="False"
            )
            
            if result:
                return jsonify({
                    "success": True,
                    "message": "Sample 'Current_Amp' tag created successfully"
                })
            else:
                return jsonify({"error": "Failed to create sample tag"}), 500
        except Exception as e:
            return jsonify({"error": f"Unexpected error: {str(e)}"}), 500
