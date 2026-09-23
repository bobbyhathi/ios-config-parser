"""
Parses live-device BGP status output (per-VRF neighbor state, AS,
prefix counts) for the BGP Status tab.
"""
import re


class BGPManager:
    def __init__(self, config_parser):
        self.parser = config_parser
        
    def parse_bgp_status(self, bgp_output):
        """Parse BGP summary output for a single VRF"""
        bgp_data = []
        lines = bgp_output.splitlines()
        
        # Skip until we find the header
        header_found = False
        header_line = -1
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            # Look for header line - more robust matching
            if ('Neighbor' in line and 'AS' in line and 
                'Up/Down' in line and 'State/PfxRcd' in line):
                header_found = True
                header_line = i
                break
    
        if not header_found:
            # Check for common error messages
            if "% BGP not active" in bgp_output:
                return {"error": "BGP not active for this VRF"}
            if "% Invalid input" in bgp_output:
                return {"error": "Command not supported"}
            return {"error": "Could not find BGP header in output"}
        
        # Process neighbor lines after header
        for line in lines[header_line+1:]:
            line = line.strip()
            if not line:
                continue
                
            # Skip lines that are clearly not neighbor entries
            if line.startswith('*') or line.startswith('Total'):
                continue
                
            parts = line.split()
        
            # More robust parsing that handles different output formats
            try:
                # Basic validation - first part should be an IP address
                if not re.match(r'^\d+\.\d+\.\d+\.\d+', parts[0]):
                    continue
                    
                neighbor = parts[0]
                remote_as = parts[2]
                
                # State/PfxRcd is typically the last field
                state_pfx = parts[-1]
                
                # Uptime is typically the second-to-last field
                uptime = parts[-2] if len(parts) >= 6 else ''
                
                # Determine if state_pfx is a state or prefix count
                if state_pfx.isdigit():
                    state = 'Established'
                    prefixes = state_pfx
                else:
                    state = state_pfx
                    prefixes = '0'
                
                # Additional field for BGP version if available
                version = parts[1] if len(parts) > 2 else ''
                
                bgp_data.append({
                    'neighbor': neighbor,
                    'version': version,
                    'remote_as': remote_as,
                    'state': state,
                    'prefixes': prefixes,
                    'uptime': uptime,
                    'raw_line': line  # For debugging
                })
                
            except (IndexError, ValueError) as e:
                # Skip malformed lines but log them for debugging
                continue
        
        # If we found no peers but output exists, return the raw output for debugging
        if not bgp_data and bgp_output.strip():
            return {"error": "No peers found", "raw_output": bgp_output}
        
        return bgp_data
