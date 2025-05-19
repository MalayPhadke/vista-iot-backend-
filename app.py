#!/usr/bin/env python3
import os
from flask import Flask
from routes import register_routes
from modbus_routes import register_modbus_routes

app = Flask(__name__)

# Register all routes from routes.py
register_routes(app)

# Register Modbus routes
register_modbus_routes(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
