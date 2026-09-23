"""
Parses live-device 'show crypto session'/'show crypto ipsec sa' style
command output into structured VPN tunnel status and traffic-flow data.
"""
import re


class VPNMonitor:
    VPN_STATUS_COMMANDS = [
        'show crypto session brief',
        'show interface description',
        'show crypto ipsec sa'
    ]

    def __init__(self, config_parser):
        self.parser = config_parser
        
    def _parse_crypto_session_brief(self, output):
        """Parse the brief crypto session output in the specific format"""
        sessions = []
        current_vrf = None
        
        for line in output.splitlines():
            # Skip header lines
            if 'Status:' in line or 'Peer' in line or not line.strip():
                continue
                
            # Check for VRF line
            if 'ivrf =' in line:
                current_vrf = line.split('=')[1].strip()
                if current_vrf == '(none)':
                    current_vrf = 'global'
                continue
                
            # Parse session lines
            parts = line.split()
            if len(parts) >= 5:  # Minimum: Peer, I/F, Uptime, Status
                interface = parts[1]
                sessions.append({
                    'vrf': current_vrf,
                    'peer': parts[0],
                    'interface': interface,
                    'uptime': parts[-2],
                    'status': parts[-1],
                    'tunnel_id': interface[2:] if interface.startswith('Tu') and interface[2:].isdigit() else None
                })
        
        return sessions


    def _parse_crypto_ipsec_sa(self, output):
        """Parse the output of 'show crypto ipsec sa'."""
        self.parser.log("--- Parsing 'show crypto ipsec sa' output ---")
        
        # Try the main parser first
        sessions = self._parse_crypto_ipsec_sa_main(output)
        
        # If main parser found nothing, try fallback
        if not sessions:
            self.parser.log("Main parser found no sessions, trying fallback...")
            sessions = self._parse_crypto_ipsec_sa_fallback(output)
        
        self.parser.log(f"--- Finished parsing 'show crypto ipsec sa'. Found {len(sessions)} sessions. ---")
        
        return sessions


    def _parse_crypto_ipsec_sa_main(self, output):
        """Parse the output of 'show crypto ipsec sa'."""
        self.parser.log("--- Parsing 'show crypto ipsec sa' output ---")
        
        sessions = []
        current_interface = None
        session_data = {}
        in_session = False
    
        # Split into lines and process
        lines = output.splitlines()
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines and some headers
            if not line or line.startswith('interface:') and ':' not in line[10:]:
                continue
                
            if line.startswith('interface:'):
                # If we have a previous session, add it
                if session_data and current_interface:
                    session_data['interface'] = current_interface
                    sessions.append(session_data)
                    
                # Start new session
                current_interface = line.split(':')[1].strip()
                session_data = {'interface': current_interface}
                in_session = True
                
            elif in_session and 'local ident' in line:
                try:
                    # Extract local ident - handle different formats
                    if '): (' in line:
                        session_data['local_ident'] = line.split('): (')[1].split(')')[0]
                    elif ': ' in line:
                        session_data['local_ident'] = line.split(': ')[1]
                    else:
                        session_data['local_ident'] = line
                except (IndexError, ValueError):
                    session_data['local_ident'] = 'Error parsing'
                    
            elif in_session and 'remote ident' in line:
                try:
                    # Extract remote ident - handle different formats
                    if '): (' in line:
                        session_data['remote_ident'] = line.split('): (')[1].split(')')[0]
                    elif ': ' in line:
                        session_data['remote_ident'] = line.split(': ')[1]
                    else:
                        session_data['remote_ident'] = line
                except (IndexError, ValueError):
                    session_data['remote_ident'] = 'Error parsing'
                    
            elif in_session and line.startswith('current_peer'):
                try:
                    session_data['peer'] = line.split()[1]
                except (IndexError, ValueError):
                    session_data['peer'] = 'Error parsing'
                    
            elif in_session and '#pkts encaps:' in line:
                try:
                    parts = line.split(',')
                    for part in parts:
                        part = part.strip()
                        if 'encaps:' in part:
                            session_data['pkts_encaps'] = part.split(':')[1].strip()
                        elif 'encrypt:' in part:
                            session_data['pkts_encrypt'] = part.split(':')[1].strip()
                except (ValueError, IndexError):
                    session_data['pkts_encaps'] = 'Error'
                    session_data['pkts_encrypt'] = 'Error'
                    
            elif in_session and '#pkts decaps:' in line:
                try:
                    parts = line.split(',')
                    for part in parts:
                        part = part.strip()
                        if 'decaps:' in part:
                            session_data['pkts_decaps'] = part.split(':')[1].strip()
                        elif 'decrypt:' in part:
                            session_data['pkts_decrypt'] = part.split(':')[1].strip()
                except (ValueError, IndexError):
                    session_data['pkts_decaps'] = 'Error'
                    session_data['pkts_decrypt'] = 'Error'
                    
            elif in_session and line.startswith('#'):
                # This might be the end of a session block
                pass
                
        # Add the last session if exists
        if session_data and current_interface:
            session_data['interface'] = current_interface
            sessions.append(session_data)
        
        self.parser.log(f"--- Finished parsing 'show crypto ipsec sa'. Found {len(sessions)} sessions. ---")
        return sessions
    
    
    def _parse_crypto_ipsec_sa_fallback(self, output):
        """Alternative parsing method for 'show crypto ipsec sa' output"""
        self.parser.log("--- Using fallback parser for 'show crypto ipsec sa' ---")
        
        sessions = []
        current_session = {}
        
        # Split into sections by interface
        sections = re.split(r'(?=^interface:)', output, flags=re.MULTILINE)
        
        for section in sections:
            if not section.strip():
                continue
                
            lines = section.splitlines()
            if not lines:
                continue
                
            # First line should be interface
            if lines[0].startswith('interface:'):
                interface = lines[0].split(':')[1].strip()
                current_session = {'interface': interface}
                
                # Parse the rest of the section
                for line in lines[1:]:
                    line = line.strip()
                    if 'local ident' in line:
                        current_session['local_ident'] = line
                    elif 'remote ident' in line:
                        current_session['remote_ident'] = line
                    elif 'current_peer' in line:
                        try:
                            current_session['peer'] = line.split()[1]
                        except:
                            current_session['peer'] = 'Unknown'
                    elif 'pkts encaps' in line or 'pkts encrypt' in line or 'pkts decaps' in line or 'pkts decrypt' in line:
                        # Extract packet counts
                        numbers = re.findall(r'\d+', line)
                        if numbers:
                            if 'encaps' in line:
                                current_session['pkts_encaps'] = numbers[0]
                            if 'encrypt' in line:
                                current_session['pkts_encrypt'] = numbers[0] if len(numbers) > 1 else numbers[0]
                            if 'decaps' in line:
                                current_session['pkts_decaps'] = numbers[0] if len(numbers) > 2 else numbers[0]
                            if 'decrypt' in line:
                                current_session['pkts_decrypt'] = numbers[-1]
                
                sessions.append(current_session)
        
        self.parser.log(f"Fallback parser found {len(sessions)} sessions")
        return sessions


    def _parse_interface_descriptions(self, output):
        """Parse interface descriptions into a dictionary {interface: description}"""
        descriptions = {}
        
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
                
            # Match interface line and capture just the description (ignoring protocol/status)
            # Example formats:
            # "Tunnel1          admin down down         VPN to Datacenter A"
            # "GigabitEthernet0/1 up             up       LAN Connection"
            match = re.match(r'^\S+\s+(?:\S+\s+\S+\s+)?(.+)$', line)
            if match:
                interface = line.split()[0]  # First word is always interface name
                description = match.group(1).strip()
                descriptions[interface] = description
                
                # Add alternative forms for tunnel interfaces
                if interface.startswith('Tu') and interface[2:].isdigit():
                    descriptions[f"Tunnel{interface[2:]}"] = description
                elif interface.startswith('Tunnel') and interface[6:].isdigit():
                    descriptions[f"Tu{interface[6:]}"] = description
        
        return descriptions


    def parse_vpn_status(self, command, output):
        """Parse VPN status command outputs"""
        if 'show crypto session brief' in command:
            return self._parse_crypto_session_brief(output)
        elif 'show interface description' in command:
            return self._parse_interface_descriptions(output)
        elif 'show crypto ipsec sa' in command:
            # Try both parsing methods
            parsed = self._parse_crypto_ipsec_sa(output)
            if not parsed:
                self.parser.log("Primary IPSec SA parser failed, trying alternative approaches")
            return parsed
        else:
            return output  # Return raw output for other commands


    def get_vpn_traffic_flow(self):
        """
        Get VPN traffic flow (IPSec SAs) and enrich with VRF and description information.
        """
        self.parser.log("--- Starting VPN traffic flow analysis ---")
        
        # Check if we have the necessary data - look in the main parser instance
        if not hasattr(self.parser, 'last_vpn_status') or not self.parser.last_vpn_status:
            self.parser.log("No VPN status data available for traffic flow")
            return []
        
        traffic_data = []
        interface_descriptions = {}
        
        # Extract data from the last_vpn_status dictionary
        self.parser.log(f"Available VPN status keys: {list(self.parser.last_vpn_status.keys())}")
        
        for cmd, data in self.parser.last_vpn_status.items():
            # FIX: Use exact match instead of substring search
            if cmd == 'show crypto ipsec sa' and isinstance(data, list):
                self.parser.log(f"Found crypto ipsec sa data: {len(data)} sessions")
                traffic_data = data
            elif cmd == 'show interface description' and isinstance(data, dict):
                self.parser.log(f"Found interface descriptions: {len(data)} interfaces")
                interface_descriptions = data
        
        if not traffic_data:
            self.parser.log("No IPSec traffic data found")
            return []
        
        self.parser.log(f"Found {len(traffic_data)} traffic sessions")
        
        # Debug: Log the first session to see its structure
        if traffic_data:
            self.parser.log(f"First session structure: {traffic_data[0]}")
        
        # Create an interface-to-VRF mapping from the actual config (more reliable)
        iface_to_vrf = {}
        for vrf, data in self.parser.vrfs.items():
            for iface_block in data.get('interfaces', []):
                if iface_block:
                    iface_name = iface_block[0].strip().split()[1]
                    iface_to_vrf[iface_name] = vrf
                    # Handle tunnel interface variations
                    if iface_name.startswith('Tu') and iface_name[2:].isdigit():
                        iface_to_vrf[f"Tunnel{iface_name[2:]}"] = vrf
                    elif iface_name.startswith('Tunnel') and iface_name[6:].isdigit():
                        iface_to_vrf[f"Tu{iface_name[6:]}"] = vrf
        
        # Enrich SA data with VRF and description
        enriched_traffic_data = []
        for session in traffic_data:
            iface = session.get('interface')
            
            # Add VRF (prefer the one from the session if available, otherwise from config)
            vrf = session.get('vrf') or iface_to_vrf.get(iface, 'global')
            session['vrf'] = vrf
            
            # Add description
            description = interface_descriptions.get(iface, 'N/A')
            session['description'] = description
            
            # Ensure all required fields are present
            session.setdefault('peer', 'Unknown')
            session.setdefault('local_ident', 'N/A')
            session.setdefault('remote_ident', 'N/A')
            session.setdefault('pkts_encrypt', 'N/A')
            session.setdefault('pkts_decrypt', 'N/A')
            
            enriched_traffic_data.append(session)
            
        self.parser.log(f"Enriched {len(enriched_traffic_data)} traffic sessions")
        
        # Debug: Log the first enriched session
        if enriched_traffic_data:
            self.parser.log(f"First enriched session: {enriched_traffic_data[0]}")
        
        return enriched_traffic_data


    def get_active_vpn_sessions(self):
        """Return a list of active VPN sessions."""
        if not hasattr(self.parser, 'last_vpn_status') or not self.parser.last_vpn_status:
            return []

        active_sessions = []
        
        for cmd, data in self.parser.last_vpn_status.items():
            if 'show crypto session brief' in cmd and isinstance(data, list):
                for session in data:
                    status = session.get('status', '').upper()
                    if 'UA' in status or 'A-' in status:
                        active_sessions.append(session)
        return active_sessions
