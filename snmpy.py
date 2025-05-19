#!/usr/bin/env python3

def build_snmpv1_command(operation, config):
    """Build SNMP v1 command based on the provided configuration"""
    if not config.get("target", {}).get("host"):
        raise ValueError("Missing target host in configuration")
    
    cmd = [f"snmp{operation}", "-v1"]
    
    # Add community string
    if "community" not in config.get("authentication", {}).get("version1", {}):
        raise ValueError("Missing community string for SNMPv1")
    
    community = config["authentication"]["version1"]["community"]
    cmd.extend(["-c", community])
    
    # Add host
    host = config["target"]["host"]
    port = config["target"].get("port", 161)
    target = f"{host}:{port}"
    
    # Add OID
    if "oid" not in config:
        raise ValueError("Missing OID in configuration")
    
    cmd.append(target)
    cmd.append(config["oid"])
    
    # Add type and value for set operations
    if operation == "set":
        if "type" not in config or "value" not in config:
            raise ValueError("Missing type or value for SNMP set operation")
        cmd.append(config["type"])
        cmd.append(config["value"])
    
    return cmd

def build_snmpv2c_command(operation, config):
    """Build SNMP v2c command based on the provided configuration"""
    if not config.get("target", {}).get("host"):
        raise ValueError("Missing target host in configuration")
    
    cmd = [f"snmp{operation}", "-v2c"]
    
    # Add community string
    if "community" not in config.get("authentication", {}).get("version2c", {}):
        raise ValueError("Missing community string for SNMPv2c")
    
    community = config["authentication"]["version2c"]["community"]
    cmd.extend(["-c", community])
    
    # Add host
    host = config["target"]["host"]
    port = config["target"].get("port", 161)
    target = f"{host}:{port}"
    
    # Add OID
    if "oid" not in config:
        raise ValueError("Missing OID in configuration")
    
    cmd.append(target)
    cmd.append(config["oid"])
    
    # Add type and value for set operations
    if operation == "set":
        if "type" not in config or "value" not in config:
            raise ValueError("Missing type or value for SNMP set operation")
        cmd.append(config["type"])
        cmd.append(config["value"])
    
    return cmd

def build_snmpv3_command(operation, config):
    """Build SNMP v3 command based on the provided configuration"""
    if not config.get("target", {}).get("host"):
        raise ValueError("Missing target host in configuration")
    
    cmd = [f"snmp{operation}", "-v3"]
    
    v3_auth = config.get("authentication", {}).get("version3", {})
    if not v3_auth.get("username"):
        raise ValueError("Missing username for SNMPv3")
    
    # Add username
    cmd.extend(["-u", v3_auth["username"]])
    
    # Add security level
    level = v3_auth.get("level", "noAuthNoPriv")
    cmd.extend(["-l", level])
    
    # Add authentication protocol and passphrase if needed
    if level in ["authNoPriv", "authPriv"]:
        if not v3_auth.get("auth_protocol") or not v3_auth.get("auth_passphrase"):
            raise ValueError("Missing authentication protocol or passphrase for SNMPv3")
        
        auth_protocol = v3_auth["auth_protocol"]
        auth_passphrase = v3_auth["auth_passphrase"]
        
        cmd.extend(["-a", auth_protocol])
        cmd.extend(["-A", auth_passphrase])
    
    # Add privacy protocol and passphrase if needed
    if level == "authPriv":
        if not v3_auth.get("priv_protocol") or not v3_auth.get("priv_passphrase"):
            raise ValueError("Missing privacy protocol or passphrase for SNMPv3")
        
        priv_protocol = v3_auth["priv_protocol"]
        priv_passphrase = v3_auth["priv_passphrase"]
        
        cmd.extend(["-x", priv_protocol])
        cmd.extend(["-X", priv_passphrase])
    
    # Add host
    host = config["target"]["host"]
    port = config["target"].get("port", 161)
    target = f"{host}:{port}"
    
    # Add OID
    if "oid" not in config:
        raise ValueError("Missing OID in configuration")
    
    cmd.append(target)
    cmd.append(config["oid"])
    
    # Add type and value for set operations
    if operation == "set":
        if "type" not in config or "value" not in config:
            raise ValueError("Missing type or value for SNMP set operation")
        cmd.append(config["type"])
        cmd.append(config["value"])
    
    return cmd
