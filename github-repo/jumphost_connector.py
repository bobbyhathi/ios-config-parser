"""
SSH connectivity helpers: connects directly to a device, or via an
intermediate jumphost using Paramiko port-forwarding + Netmiko.
"""
import socket

from netmiko import ConnectHandler
from paramiko import SSHClient, AutoAddPolicy


class JumphostConnector:
    def __init__(self, config_parser):
        self.parser = config_parser
        self.ssh_timeout = 30  # Increased timeout
        self.banner_timeout = 60  # Banner timeout
        
    def connect_via_jumphost(self, device_name):
        """SSH to device via jumphost using Paramiko port forwarding with enhanced error handling"""
        if device_name not in self.parser.devices:
            raise ValueError(f"Device {device_name} not found")
        
        device = self.parser.devices[device_name]
        jumphost_name = device.get("jumphost")
        
        if not jumphost_name:
            # Direct connection if no jumphost specified
            self.parser.log(f"Connecting directly to {device_name}")
            return self._direct_connect(device)
        
        if jumphost_name not in self.parser.jumphosts:
            raise ValueError(f"Jumphost {jumphost_name} not found")
        
        jumphost = self.parser.jumphosts[jumphost_name]
        self.parser.log(f"Connecting to {device_name} via jumphost {jumphost_name}")
        
        try:
            # Step 1: Connect to jumphost with enhanced timeout
            ssh_jump = SSHClient()
            ssh_jump.set_missing_host_key_policy(AutoAddPolicy())
            
            connect_args = {
                'hostname': jumphost['host'],
                'username': jumphost['username'],
                'port': jumphost.get('port', 22),
                'timeout': self.ssh_timeout,
                'banner_timeout': self.banner_timeout
            }
            
            if 'password' in jumphost:
                connect_args['password'] = jumphost['password']
            if 'key_file' in jumphost:
                connect_args['key_filename'] = jumphost['key_file']
            
            self.parser.log(f"Connecting to jumphost {jumphost_name} at {jumphost['host']}:{jumphost.get('port', 22)}")
            ssh_jump.connect(**connect_args)
            self.parser.log("Successfully connected to jumphost")
            
            # Step 2: Create port forward
            transport = ssh_jump.get_transport()
            dest_addr = (device['host'], device.get('port', 22))
            local_port = 10022  # Arbitrary local port
            
            self.parser.log(f"Creating port forward from localhost:{local_port} to {device['host']}:{device.get('port', 22)}")
            channel = transport.open_channel("direct-tcpip", dest_addr, ("127.0.0.1", local_port))
            
            # Step 3: Connect through tunnel
            device_params = {
                'device_type': device['device_type'],
                'host': '127.0.0.1',
                'port': local_port,
                'username': device['username'],
                'password': device.get('password'),
                'secret': device.get('secret'),
                'sock': channel,
                'timeout': self.ssh_timeout,
                'session_timeout': self.ssh_timeout,
                'keepalive': 30  # Send keepalive every 30 seconds
            }
            
            self.parser.log(f"Connecting to device through tunnel on port {local_port}")
            connection = ConnectHandler(**device_params)
            self.parser.log("Successfully connected to device via jumphost")
            
            return connection
            
        except Exception as e:
            self.parser.log(f"Failed to connect via jumphost: {str(e)}")
            # Clean up any open connections
            try:
                if 'ssh_jump' in locals() and ssh_jump:
                    ssh_jump.close()
            except:
                pass
            raise
    
    def _direct_connect(self, device):
        """Direct connection to device with enhanced error handling"""
        try:
            self.parser.log(f"Attempting direct connection to {device['host']}:{device.get('port', 22)}")
            
            connect_args = {
                'device_type': device['device_type'],
                'host': device['host'],
                'port': device.get('port', 22),
                'username': device['username'],
                'timeout': self.ssh_timeout,
                'session_timeout': self.ssh_timeout
            }
            
            if 'password' in device:
                connect_args['password'] = device['password']
            if 'secret' in device:
                connect_args['secret'] = device['secret']
            if 'key_file' in device:
                connect_args['use_keys'] = True
                connect_args['key_file'] = device['key_file']
            
            # Add additional connection parameters for better reliability
            connect_args['global_delay_factor'] = 2
            connect_args['fast_cli'] = False
            
            # Add keepalive to prevent connection timeout
            connect_args['keepalive'] = 30  # Send keepalive every 30 seconds
            connect_args['session_timeout'] = 3600  # 1 hour session timeout
            connect_args['timeout'] = 120  # 2 minute command timeout
            
            self.parser.log(f"Connection parameters: { {k: v for k, v in connect_args.items() if k not in ['password', 'secret']} }")
            
            connection = ConnectHandler(**connect_args)
            self.parser.log("Direct connection successful")
            return connection
            
        except Exception as e:
            self.parser.log(f"Direct connection failed: {str(e)}")
            raise
    
    def test_connection(self, device_name):
        """Test SSH connection without full configuration retrieval"""
        try:
            if device_name not in self.parser.devices:
                return False, f"Device {device_name} not found"
            
            device = self.parser.devices[device_name]
            jumphost_name = device.get("jumphost")
            
            if jumphost_name:
                # Test jumphost connection
                if jumphost_name not in self.parser.jumphosts:
                    return False, f"Jumphost {jumphost_name} not found"
                
                jumphost = self.parser.jumphosts[jumphost_name]
                
                # Test jumphost connectivity
                ssh_jump = SSHClient()
                ssh_jump.set_missing_host_key_policy(AutoAddPolicy())
                
                connect_args = {
                    'hostname': jumphost['host'],
                    'username': jumphost['username'],
                    'port': jumphost.get('port', 22),
                    'timeout': 10,  # Shorter timeout for testing
                    'banner_timeout': 15
                }
                
                if 'password' in jumphost:
                    connect_args['password'] = jumphost['password']
                if 'key_file' in jumphost:
                    connect_args['key_filename'] = jumphost['key_file']
                
                ssh_jump.connect(**connect_args)
                ssh_jump.close()
                
                return True, f"Jumphost {jumphost_name} is reachable"
            
            else:
                # Test direct connection
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10)
                result = sock.connect_ex((device['host'], device.get('port', 22)))
                sock.close()
                
                if result == 0:
                    return True, f"Device {device_name} is reachable"
                else:
                    return False, f"Device {device_name} is not reachable (port {device.get('port', 22)})"
                    
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"
