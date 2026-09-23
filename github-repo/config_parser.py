"""
Core Cisco IOS configuration parsing primitives: pulls raw text blocks
(NAT pools, IP SLA, tracking objects, crypto blocks, etc.) out of a running
config and provides shared helpers used by VRFManager, VPNMonitor and
BGPManager.
"""
import re
from collections import defaultdict
from datetime import datetime


class ConfigParser:
    def __init__(self, gui_callback=None, debug_mode=False):
        self.gui_callback = gui_callback
        self.debug_mode = debug_mode
        self.reset_data_structures()
        
#    def log(self, message):
#        if self.gui_callback:
#            self.gui_callback(message)
#        else:
#            print(message)

    def log(self, message, debug_level=False):
        """Log message with optional debug level filtering"""
        # If this is a debug message and debug mode is off, skip it
        if debug_level and not self.debug_mode:
            return
            
        if self.gui_callback:
            self.gui_callback(message)
        else:
            print(message)
            
    def reset_data_structures(self):
        """Reset all parsing data structures"""
        self.vrfs = defaultdict(lambda: {
        'definition': [], 'interfaces': [], 'nat': [], 'nat_outside': [],
        'nat_inside_dynamic': [], 'nat_inside_dynamic2': [], 'nat_pool': [], 
        'acl_extended': set(), 'static_routes': [], 'bgp': [], 'route_maps': set(), 
        'prefix_lists': set(), 'acls': defaultdict(list), 'ext_acls': defaultdict(list), 
        'ip_sla': [], 'tracking': [], 
        'ikev2': {'keyring': [], 'policy': [], 'profile': [], 'proposal': []},
        'ipsec': {'profile': [], 'transform_set': []}, 'tunnel_interfaces': []
        })
        self.route_maps = defaultdict(list)
        self.prefix_lists = defaultdict(list)
        self.ikev2_keyring = []
        self.ikev2_policy = []
        self.ikev2_profile = []
        self.ikev2_proposal = []
        self.ipsec_profile = []
        self.ipsec_transform_set = []
        self.acls = []
        self.ext_acls = []
        self.nat_pool = defaultdict(list)
        self.ip_sla = {}
        self.tracking = {}
        
    def extract_block(self, start_index, lines):
        """Extract a configuration block"""
        block = [lines[start_index]]
        i = start_index + 1
        while i < len(lines) and (lines[i].startswith(' ') or lines[i].strip() in ('!', '')):
            block.append(lines[i])
            i += 1
        return block, i
        
    def _extract_blocks_by_prefix(self, lines, prefix):
        """A helper to extract configuration blocks starting with a given prefix."""
        blocks = []
        i = 0
        while i < len(lines):
            if lines[i].strip().startswith(prefix):
                block, i = self.extract_block(i, lines)
                blocks.append(block)
            else:
                i += 1
        return blocks

    def get_config_last_change_date(self, config_lines):
        """Extract last config change timestamp"""
        if not config_lines:
            return None
        for line in reversed(config_lines):
            if "Last configuration change" in line:
                try:
                    date_part = line.split(" at ")[1].split(" by ")[0]
                    try:
                        dt = datetime.strptime(date_part, "%H:%M:%S %Z %a %b %d %Y")
                    except ValueError:
                        dt = datetime.strptime(date_part, "%H:%M:%S %a %b %d %Y")
                    return dt.strftime("%Y-%m-%d_%H-%M-%S")
                except Exception as e:
                    self.log(f"Warning: Could not parse timestamp: {str(e)}")
                    return None
        return None

    def format_config_for_output(self, config_lines):
        """Format configuration lines for file output with proper Cisco formatting."""
        formatted_lines = []
        indent_level = 0
        
        increase_indent_keywords = [
            'router bgp', 'address-family', 'vrf definition', 'interface', 
            'route-map', 'crypto ikev2', 'crypto ipsec', 'ip access-list',
            'ip sla', 'track'
        ]
        
        decrease_indent_keywords = ['exit-address-family', 'exit-vrf', 'exit']

        for line in config_lines:
            if not isinstance(line, str):
                continue

            stripped_line = line.strip()
            if not stripped_line:
                formatted_lines.append('')
                continue

            if any(stripped_line.startswith(keyword) for keyword in decrease_indent_keywords):
                indent_level = max(0, indent_level - 1)

            formatted_lines.append(('  ' * indent_level) + stripped_line)

            if any(stripped_line.startswith(keyword) for keyword in increase_indent_keywords):
                indent_level += 1
                
        return formatted_lines

    def extract_nat_pool(self, lines):
        nat_pools = defaultdict(list)
        current_pool = None
        for line in lines:
            if line.strip().startswith('ip nat pool '):
                current_pool = line.strip().split()[3]
                nat_pools[current_pool].append(line)
            elif current_pool and (line.startswith(' ') or line.strip() in ('!', '')):
                nat_pools[current_pool].append(line)
            else:
                current_pool = None
        return nat_pools

    def extract_ip_sla(self, lines):
        sla_entries = {}
        i = 0
        while i < len(lines):
            if lines[i].strip().startswith('ip sla '):
                sla_num = lines[i].strip().split()[2]
                block, i = self.extract_block(i, lines)
                sla_entries[sla_num] = {
                    'config': block,
                    'vrf': None
                }
                for line in block:
                    vrf_match = re.search(r'vrf (\S+)', line)
                    if vrf_match:
                        sla_entries[sla_num]['vrf'] = vrf_match.group(1)
                        break
            else:
                i += 1
        return sla_entries

    def extract_tracking(self, lines):
        tracking_entries = {}
        i = 0
        while i < len(lines):
            if lines[i].strip().startswith('track '):
                track_num = lines[i].strip().split()[1]
                block, i = self.extract_block(i, lines)
                tracking_entries[track_num] = {
                    'config': block,
                    'sla_num': None,
                    'vrf': None,  # Add VRF tracking
                    'type': None  # Add type (sla or ip_route)
                }
                for line in block:
                    # Check for SLA-based tracking
                    sla_match = re.search(r'ip sla (\d+)', line)
                    if sla_match:
                        tracking_entries[track_num]['sla_num'] = sla_match.group(1)
                        tracking_entries[track_num]['type'] = 'sla'
                        break
                    # Check for IP route reachability tracking with VRF
                    route_match = re.search(r'ip route .* reachability', line)
                    if route_match:
                        tracking_entries[track_num]['type'] = 'ip_route'
                    # Extract VRF from tracking configuration
                    vrf_match = re.search(r'ip vrf (\S+)', line)
                    if vrf_match:
                        tracking_entries[track_num]['vrf'] = vrf_match.group(1)
            else:
                i += 1
        return tracking_entries
