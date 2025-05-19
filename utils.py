#!/usr/bin/env python3
import subprocess

def execute_snmp_command(command):
    """
    Execute an SNMP command and return the result
    """
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True
        )
        return {
            "success": True,
            "output": result.stdout,
            "command": " ".join(command)
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": str(e),
            "stderr": e.stderr,
            "command": " ".join(command)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "command": " ".join(command) if command else "Unknown"
        }
