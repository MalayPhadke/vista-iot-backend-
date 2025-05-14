#!/usr/bin/env python3
import unittest
import yaml
import json
from app import app
from unittest.mock import patch

class TestSNMPServer(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
    
    @patch('app.execute_snmp_command')
    def test_snmpv1_get(self, mock_execute):
        # Set up mock
        mock_execute.return_value = {
            "success": True,
            "output": "SNMPv1-MIB::sysDescr.0 = STRING: Test System Description",
            "command": "snmpget -v1 -c public 192.168.1.1:161 1.3.6.1.2.1.1.1.0"
        }
        
        # Test data
        test_yaml = """
        protocols:
          snmp:
            operation: get
            version: 1
            target:
              host: 192.168.1.1
              port: 161
            authentication:
              version1:
                community: public
            oid: 1.3.6.1.2.1.1.1.0
        """
        
        # Make request
        response = self.client.post(
            '/api/snmp/v1',
            data=test_yaml,
            content_type='application/x-yaml'
        )
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['output'], "SNMPv1-MIB::sysDescr.0 = STRING: Test System Description")
    
    @patch('app.execute_snmp_command')
    def test_snmpv2c_walk(self, mock_execute):
        # Set up mock
        mock_execute.return_value = {
            "success": True,
            "output": "SNMPv2-MIB::sysDescr.0 = STRING: Test System Description\nSNMPv2-MIB::sysObjectID.0 = OID: NET-SNMP-MIB::netSnmpAgentOIDs.10",
            "command": "snmpwalk -v2c -c public 192.168.1.1:161 1.3.6.1.2.1.1"
        }
        
        # Test data
        test_yaml = """
        protocols:
          snmp:
            operation: walk
            version: 2c
            target:
              host: 192.168.1.1
              port: 161
            authentication:
              version2c:
                community: public
            oid: 1.3.6.1.2.1.1
        """
        
        # Make request
        response = self.client.post(
            '/api/snmp/v2c',
            data=test_yaml,
            content_type='application/x-yaml'
        )
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn("SNMPv2-MIB::sysDescr.0", data['output'])
    
    @patch('app.execute_snmp_command')
    def test_snmpv3_get(self, mock_execute):
        # Set up mock
        mock_execute.return_value = {
            "success": True,
            "output": "SNMPv2-MIB::sysDescr.0 = STRING: Test System Description",
            "command": "snmpget -v3 -u snmpuser -l authPriv -a SHA -A authpassword -x AES -X privpassword 192.168.1.1:161 1.3.6.1.2.1.1.1.0"
        }
        
        # Test data
        test_yaml = """
        protocols:
          snmp:
            operation: get
            version: 3
            target:
              host: 192.168.1.1
              port: 161
            authentication:
              version3:
                username: snmpuser
                level: authPriv
                auth_protocol: SHA
                auth_passphrase: authpassword
                privacy_protocol: AES
                privacy_passphrase: privpassword
            oid: 1.3.6.1.2.1.1.1.0
        """
        
        # Make request
        response = self.client.post(
            '/api/snmp/v3',
            data=test_yaml,
            content_type='application/x-yaml'
        )
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['output'], "SNMPv2-MIB::sysDescr.0 = STRING: Test System Description")
    
    @patch('app.execute_snmp_command')
    def test_snmpv2c_set(self, mock_execute):
        # Set up mock
        mock_execute.return_value = {
            "success": True,
            "output": "SNMPv2-MIB::sysContact.0 = STRING: contact@example.com",
            "command": "snmpset -v2c -c private 192.168.1.1:161 1.3.6.1.2.1.1.4.0 s contact@example.com"
        }
        
        # Test data
        test_yaml = """
        protocols:
          snmp:
            operation: set
            version: 2c
            target:
              host: 192.168.1.1
              port: 161
            authentication:
              version2c:
                community: private
            oid: 1.3.6.1.2.1.1.4.0
            type: s
            value: contact@example.com
        """
        
        # Make request
        response = self.client.post(
            '/api/snmp/v2c',
            data=test_yaml,
            content_type='application/x-yaml'
        )
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['output'], "SNMPv2-MIB::sysContact.0 = STRING: contact@example.com")
    
    def test_invalid_yaml(self):
        response = self.client.post(
            '/api/snmp/v1',
            data="invalid: yaml: - content",
            content_type='application/x-yaml'
        )
        
        self.assertNotEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("error", data)
        self.assertIn("Invalid YAML", data["error"])
    
    def test_missing_config(self):
        test_yaml = """
        protocols:
          other_protocol:
            something: else
        """
        
        response = self.client.post(
            '/api/snmp/v1',
            data=test_yaml,
            content_type='application/x-yaml'
        )
        
        self.assertNotEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("error", data)
        self.assertIn("Missing SNMP configuration", data["error"])

if __name__ == '__main__':
    unittest.main()
