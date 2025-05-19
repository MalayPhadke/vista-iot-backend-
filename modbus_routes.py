#!/usr/bin/env python3
"""
Modbus Routes Module for IoT Gateway

This module provides Flask routes to configure and use the Modbus master functionality.
"""

import os
import yaml
import json
import csv
from flask import request, jsonify, send_file
from io import StringIO
from modbus_master import ModbusMaster, CSV_HEADERS

# Global ModbusMaster instance
MODBUS_MASTER = None

def register_modbus_routes(app):
    """Register Modbus routes with the Flask app"""
    
    @app.route('/api/modbus/configure', methods=['POST'])
    def modbus_configure():
        """
        Configure the Modbus master
        Expects a YAML or JSON payload with configuration
        """
        global MODBUS_MASTER
        
        try:
            # Parse request data
            if request.content_type == 'application/x-yaml' or request.content_type == 'text/yaml':
                config = yaml.safe_load(request.data)
            elif request.content_type == 'application/json':
                config = request.json
            else:
                return jsonify({
                    "error": "Content-Type must be application/x-yaml, text/yaml, or application/json"
                }), 400
            
            # Create a new ModbusMaster with the configuration
            MODBUS_MASTER = ModbusMaster(config)
            
            # Connect to all slaves
            MODBUS_MASTER.connect_all()
            
            # Start scanning
            MODBUS_MASTER.start_scanning()
            
            return jsonify({
                "success": True,
                "message": "Modbus master configured and started",
                "slave_count": len(MODBUS_MASTER.tags)
            })
        
        except Exception as e:
            return jsonify({
                "error": f"Error configuring Modbus master: {str(e)}"
            }), 500
    
    @app.route('/api/modbus/status', methods=['GET'])
    def modbus_status():
        """Get the status of the Modbus master"""
        global MODBUS_MASTER
        
        if not MODBUS_MASTER:
            return jsonify({
                "error": "Modbus master not configured"
            }), 404
        
        try:
            # Get status information
            status = {
                "running": MODBUS_MASTER.running,
                "slave_count": len(MODBUS_MASTER.tags),
                "slaves": list(MODBUS_MASTER.tags.keys())
            }
            
            return jsonify({
                "success": True,
                "status": status
            })
        
        except Exception as e:
            return jsonify({
                "error": f"Error getting Modbus status: {str(e)}"
            }), 500
    
    @app.route('/api/modbus/stop', methods=['POST'])
    def modbus_stop():
        """Stop the Modbus master"""
        global MODBUS_MASTER
        
        if not MODBUS_MASTER:
            return jsonify({
                "error": "Modbus master not configured"
            }), 404
        
        try:
            # Stop scanning
            MODBUS_MASTER.stop_scanning()
            
            # Disconnect from all slaves
            MODBUS_MASTER.disconnect_all()
            
            return jsonify({
                "success": True,
                "message": "Modbus master stopped"
            })
        
        except Exception as e:
            return jsonify({
                "error": f"Error stopping Modbus master: {str(e)}"
            }), 500
    
    @app.route('/api/modbus/slaves', methods=['GET'])
    def get_modbus_slaves():
        """Get all configured Modbus slaves"""
        global MODBUS_MASTER
        
        if not MODBUS_MASTER:
            return jsonify({
                "error": "Modbus master not configured"
            }), 404
        
        try:
            return jsonify({
                "success": True,
                "slaves": MODBUS_MASTER.tags
            })
        
        except Exception as e:
            return jsonify({
                "error": f"Error getting Modbus slaves: {str(e)}"
            }), 500
    
    @app.route('/api/modbus/slaves/<slave_name>', methods=['GET'])
    def get_modbus_slave(slave_name):
        """Get a specific Modbus slave by name"""
        global MODBUS_MASTER
        
        if not MODBUS_MASTER:
            return jsonify({
                "error": "Modbus master not configured"
            }), 404
        
        try:
            # Check if slave exists
            if slave_name not in MODBUS_MASTER.tags:
                return jsonify({
                    "error": f"Slave not found: {slave_name}"
                }), 404
            
            return jsonify({
                "success": True,
                "slave": MODBUS_MASTER.tags[slave_name]
            })
        
        except Exception as e:
            return jsonify({
                "error": f"Error getting Modbus slave: {str(e)}"
            }), 500
    
    @app.route('/api/modbus/values', methods=['GET'])
    def get_modbus_values():
        """Get all Modbus tag values"""
        global MODBUS_MASTER
        
        if not MODBUS_MASTER:
            return jsonify({
                "error": "Modbus master not configured"
            }), 404
        
        try:
            return jsonify({
                "success": True,
                "values": MODBUS_MASTER.get_all_tag_values()
            })
        
        except Exception as e:
            return jsonify({
                "error": f"Error getting Modbus values: {str(e)}"
            }), 500
    
    @app.route('/api/modbus/values/<slave_name>', methods=['GET'])
    def get_modbus_value(slave_name):
        """Get a specific Modbus tag value by slave name"""
        global MODBUS_MASTER
        
        if not MODBUS_MASTER:
            return jsonify({
                "error": "Modbus master not configured"
            }), 404
        
        try:
            # Check if slave exists
            if slave_name not in MODBUS_MASTER.tags:
                return jsonify({
                    "error": f"Slave not found: {slave_name}"
                }), 404
            
            value = MODBUS_MASTER.get_tag_value(slave_name)
            
            return jsonify({
                "success": True,
                "slave_name": slave_name,
                "value": value
            })
        
        except Exception as e:
            return jsonify({
                "error": f"Error getting Modbus value: {str(e)}"
            }), 500
    
    @app.route('/api/modbus/write/<slave_name>', methods=['POST'])
    def write_modbus_value(slave_name):
        """Write a value to a Modbus slave"""
        global MODBUS_MASTER
        
        if not MODBUS_MASTER:
            return jsonify({
                "error": "Modbus master not configured"
            }), 404
        
        try:
            # Check if slave exists
            if slave_name not in MODBUS_MASTER.tags:
                return jsonify({
                    "error": f"Slave not found: {slave_name}"
                }), 404
            
            # Parse request data
            if request.content_type == 'application/x-yaml' or request.content_type == 'text/yaml':
                data = yaml.safe_load(request.data)
            elif request.content_type == 'application/json':
                data = request.json
            else:
                return jsonify({
                    "error": "Content-Type must be application/x-yaml, text/yaml, or application/json"
                }), 400
            
            # Check for required fields
            if 'value' not in data:
                return jsonify({
                    "error": "Missing required field: value"
                }), 400
            
            # Get slave configuration
            slave_config = MODBUS_MASTER.tags[slave_name]
            
            # Write the value
            success = MODBUS_MASTER.write_data(
                slave_name=slave_name,
                address=int(slave_config['address']),
                value=data['value'],
                unit=int(slave_config['slave_id']),
                datatype=slave_config['datatype'],
                conversion=slave_config['conversion']
            )
            
            if success:
                return jsonify({
                    "success": True,
                    "message": f"Value written to {slave_name}"
                })
            else:
                return jsonify({
                    "error": f"Failed to write value to {slave_name}"
                }), 500
        
        except Exception as e:
            return jsonify({
                "error": f"Error writing Modbus value: {str(e)}"
            }), 500
    
    @app.route('/api/modbus/add-slave', methods=['POST'])
    def add_modbus_slave():
        """Add a new Modbus slave"""
        global MODBUS_MASTER
        
        if not MODBUS_MASTER:
            # Create a new ModbusMaster if it doesn't exist
            MODBUS_MASTER = ModbusMaster()
        
        try:
            # Parse request data
            if request.content_type == 'application/x-yaml' or request.content_type == 'text/yaml':
                slave_config = yaml.safe_load(request.data)
            elif request.content_type == 'application/json':
                slave_config = request.json
            else:
                return jsonify({
                    "error": "Content-Type must be application/x-yaml, text/yaml, or application/json"
                }), 400
            
            # Check for required fields
            required_fields = ['slave_name', 'ip_address']
            for field in required_fields:
                if field not in slave_config:
                    return jsonify({
                        "error": f"Missing required field: {field}"
                    }), 400
            
            # Process the slave configuration
            MODBUS_MASTER._process_slave_config(slave_config)
            
            return jsonify({
                "success": True,
                "message": f"Slave {slave_config['slave_name']} added"
            })
        
        except Exception as e:
            return jsonify({
                "error": f"Error adding Modbus slave: {str(e)}"
            }), 500
    
    @app.route('/api/modbus/remove-slave/<slave_name>', methods=['DELETE'])
    def remove_modbus_slave(slave_name):
        """Remove a Modbus slave"""
        global MODBUS_MASTER
        
        if not MODBUS_MASTER:
            return jsonify({
                "error": "Modbus master not configured"
            }), 404
        
        try:
            # Check if slave exists
            if slave_name not in MODBUS_MASTER.tags:
                return jsonify({
                    "error": f"Slave not found: {slave_name}"
                }), 404
            
            # Disconnect client if it exists
            if slave_name in MODBUS_MASTER.clients:
                MODBUS_MASTER.clients[slave_name].close()
                del MODBUS_MASTER.clients[slave_name]
            
            # Remove from tags
            del MODBUS_MASTER.tags[slave_name]
            
            # Save to CSV
            MODBUS_MASTER._save_to_csv()
            
            return jsonify({
                "success": True,
                "message": f"Slave {slave_name} removed"
            })
        
        except Exception as e:
            return jsonify({
                "error": f"Error removing Modbus slave: {str(e)}"
            }), 500
    
    @app.route('/api/modbus/export-csv', methods=['GET'])
    def export_modbus_csv():
        """Export Modbus configuration as CSV"""
        global MODBUS_MASTER
        
        if not MODBUS_MASTER:
            return jsonify({
                "error": "Modbus master not configured"
            }), 404
        
        try:
            # Create a CSV string
            csv_output = StringIO()
            writer = csv.DictWriter(csv_output, fieldnames=CSV_HEADERS)
            writer.writeheader()
            
            for slave_name, tag in MODBUS_MASTER.tags.items():
                writer.writerow(tag)
            
            # Return as a file download
            csv_output.seek(0)
            
            return csv_output.getvalue(), 200, {
                'Content-Type': 'text/csv',
                'Content-Disposition': 'attachment; filename=modbus_config.csv'
            }
        
        except Exception as e:
            return jsonify({
                "error": f"Error exporting CSV: {str(e)}"
            }), 500
    
    @app.route('/api/modbus/import-csv', methods=['POST'])
    def import_modbus_csv():
        """Import Modbus configuration from CSV"""
        global MODBUS_MASTER
        
        try:
            # Check if file was uploaded
            if 'file' not in request.files:
                return jsonify({
                    "error": "No file part in the request"
                }), 400
            
            file = request.files['file']
            
            if file.filename == '':
                return jsonify({
                    "error": "No file selected"
                }), 400
            
            if not file.filename.endswith('.csv'):
                return jsonify({
                    "error": "File must be CSV format"
                }), 400
            
            # Create a new ModbusMaster if it doesn't exist
            if not MODBUS_MASTER:
                MODBUS_MASTER = ModbusMaster()
            
            # Read CSV file
            csv_content = file.read().decode('utf-8')
            csv_file = StringIO(csv_content)
            reader = csv.DictReader(csv_file)
            
            # Process each row as a slave configuration
            for row in reader:
                MODBUS_MASTER._process_slave_config(row)
            
            # Connect to all slaves
            MODBUS_MASTER.connect_all()
            
            # Start scanning if not already running
            if not MODBUS_MASTER.running:
                MODBUS_MASTER.start_scanning()
            
            return jsonify({
                "success": True,
                "message": f"Imported {len(MODBUS_MASTER.tags)} slaves from CSV"
            })
        
        except Exception as e:
            return jsonify({
                "error": f"Error importing CSV: {str(e)}"
            }), 500
