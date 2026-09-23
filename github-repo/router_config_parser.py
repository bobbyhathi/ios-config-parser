"""
RouterConfigParser: the non-GUI engine that ties ConfigParser, VRFManager,
VPNMonitor, BGPManager and JumphostConnector together. Can be used entirely
headlessly (no tkinter) -- see main.py / ui.py for the GUI front-end.
"""
import json
import os
import re
from datetime import datetime

from config_parser import ConfigParser
from vrf_manager import VRFManager
from vpn_monitor import VPNMonitor
from bgp_manager import BGPManager
from jumphost_connector import JumphostConnector


class RouterConfigParser:
    def __init__(self, config_file="devices.json", output_dir=None, gui_callback=None, debug_mode=False):
        self.config_file = config_file
        self.OUTPUT_DIR = output_dir or os.path.join(os.path.dirname(__file__), "vrf_outputs")
        self.gui_callback = gui_callback
        self.jumphosts = {}
        self.devices = {}
        self.last_config = None
        self.last_vpn_status = None
        self.last_bgp_status = None
        
        # Initialize component classes
        self.config_parser = ConfigParser(gui_callback, debug_mode)
        self.debug_mode = debug_mode
        self.vrf_manager = VRFManager(self.config_parser)
        self.vpn_monitor = VPNMonitor(self.config_parser)
        self.bgp_manager = BGPManager(self.config_parser)
        self.jumphost_connector = JumphostConnector(self.config_parser)
        
        self.reset_data_structures()
        self.load_config()

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
        self.config_parser.reset_data_structures()

    def load_config(self):
        """Load devices and jumphosts from config file"""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                self.jumphosts = config.get("jumphosts", {})
                self.devices = config.get("devices", {})
                self.config_parser.jumphosts = self.jumphosts
                self.config_parser.devices = self.devices
                self.log(f"Loaded {len(self.devices)} devices and {len(self.jumphosts)} jumphosts")
        except Exception as e:
            self.log(f"Error loading config: {str(e)}")

    def connect_via_jumphost(self, device_name):
        """SSH to device via jumphost using Paramiko port forwarding"""
        return self.jumphost_connector.connect_via_jumphost(device_name)

    def fetch_live_config(self, device_name):
        """Get running config and status from live device with enhanced error handling"""
        max_retries = 2
        retry_delay = 5  # seconds
        
        for attempt in range(max_retries):
            try:
                self.log(f"Attempt {attempt + 1}/{max_retries} to connect to {device_name}")
                
                # Test connection first
                if attempt == 0:  # Only test on first attempt
                    success, message = self.jumphost_connector.test_connection(device_name)
                    if not success:
                        self.log(f"Connection test failed: {message}")
                        if max_retries > 1:
                            self.log(f"Will retry in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                            continue
                        else:
                            raise ConnectionError(f"Connection test failed: {message}")
                
                connection = self.connect_via_jumphost(device_name)
                self.log(f"Connected to {device_name}, fetching config...")
                self.current_connection = connection
                
                # Get running config first with command timeout
                running_config = connection.send_command("show running-config", delay_factor=2, max_loops=3000)
                
                # Parse the config to identify VRFs first
                self.parse_configuration(running_config.splitlines(), preview_only=True)
                
                # Now get VPN status with individual timeouts - ONLY VALID COMMANDS
                vpn_status = {}
                for cmd in self.vpn_monitor.VPN_STATUS_COMMANDS:
                    try:
                        self.log(f"Executing command: {cmd}")
                        vpn_output = connection.send_command(cmd, delay_factor=2, max_loops=2000)
                        # Store only parsed output, no raw
                        parsed_output = self.vpn_monitor.parse_vpn_status(cmd, vpn_output)
                        vpn_status[cmd] = parsed_output
                    except Exception as e:
                        self.log(f"Failed to execute {cmd}: {str(e)}")
                        vpn_status[cmd] = f"Error: {str(e)}"
                
                # Store the VPN status
                self.last_vpn_status = vpn_status
        
                # Get BGP status for all VRFs now that we know what they are
                bgp_status = {}
                for vrf in self.config_parser.vrfs.keys():
                    try:
                        cmd = f"show ip bgp vpnv4 vrf {vrf} summary"
                        self.log(f"Executing BGP command for VRF {vrf}: {cmd}")
                        bgp_output = connection.send_command(cmd, delay_factor=2, max_loops=2000)
                        bgp_status[vrf] = self.bgp_manager.parse_bgp_status(bgp_output)
                    except Exception as e:
                        self.log(f"Failed to get BGP status for VRF {vrf}: {str(e)}")
                        bgp_status[vrf] = f"Error: {str(e)}"
        
                #Connection not closed as now we might use the same connection to run commands!
                #connection.disconnect()
            
                # Store the config and status
                self.last_config = running_config.splitlines()
                self.last_vpn_status = vpn_status
                self.config_parser.last_vpn_status = vpn_status
                self.last_bgp_status = bgp_status
                
                self.log(f"Successfully retrieved configuration from {device_name}")
                return self.last_config
                
            except Exception as e:
                self.log(f"Connection attempt {attempt + 1} failed: {str(e)}")
                
                # Clean up any lingering connections
                try:
                    if 'connection' in locals():
                        connection.disconnect()
                except:
                    pass
                
                if attempt == max_retries - 1:  # Last attempt
                    self.log(f"All connection attempts failed for {device_name}")
                    return None
                else:
                    self.log(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
        
        return None
    
    def refresh_status_data(self):
        """Refresh VPN and BGP status from existing connection without full reconnect"""
        if not self.current_connection:
            self.log("No active connection to refresh from")
            return False
        
        try:
            # Check if connection is still alive
            self.log("Checking connection health...")
            try:
                # Send a simple command to test connection
                self.current_connection.find_prompt()
                self.log("Connection is alive")
            except Exception as e:
                self.log(f"Connection appears to be closed: {str(e)}")
                self.log("ERROR: Socket is closed. Please reconnect using 'Get Config' button.")
                return False
            
            self.log("Refreshing status data from connected device...")
            
            # Re-fetch VPN status
            vpn_status = {}
            for cmd in self.vpn_monitor.VPN_STATUS_COMMANDS:
                try:
                    self.log(f"Executing command: {cmd}")
                    vpn_output = self.current_connection.send_command(cmd, delay_factor=2, max_loops=2000)
                    parsed_output = self.vpn_monitor.parse_vpn_status(cmd, vpn_output)
                    vpn_status[cmd] = parsed_output
                except Exception as e:
                    self.log(f"Failed to execute {cmd}: {str(e)}")
                    vpn_status[cmd] = f"Error: {str(e)}"
            
            # Store the updated VPN status
            self.last_vpn_status = vpn_status
            self.config_parser.last_vpn_status = vpn_status
            
            # Re-fetch BGP status for all VRFs
            bgp_status = {}
            for vrf in self.config_parser.vrfs.keys():
                try:
                    cmd = f"show ip bgp vpnv4 vrf {vrf} summary"
                    self.log(f"Executing BGP command for VRF {vrf}: {cmd}")
                    bgp_output = self.current_connection.send_command(cmd, delay_factor=2, max_loops=2000)
                    bgp_status[vrf] = self.bgp_manager.parse_bgp_status(bgp_output)
                except Exception as e:
                    self.log(f"Failed to get BGP status for VRF {vrf}: {str(e)}")
                    bgp_status[vrf] = f"Error: {str(e)}"
            
            # Store the updated BGP status
            self.last_bgp_status = bgp_status
            
            self.log("Status data refreshed successfully")
            return True
            
        except Exception as e:
            self.log(f"Error refreshing status data: {str(e)}")
            return False
    
    
    def parse_configuration(self, config_source, selected_vrf=None, preview_only=False, device_name=None):
        """Main parsing logic"""
        try:
            self.reset_data_structures()
            
            if isinstance(config_source, str):  # File path
                with open(config_source, 'r') as f:
                    config_lines = f.readlines()
                self.INPUT_FILE = config_source
                if not device_name:
                    device_name = os.path.basename(config_source)
            else:  # List of lines
                config_lines = config_source
                if not device_name:
                    device_name = "live_device"
            
            # Debug: Save the raw config for inspection
            if self.debug_mode:  # Only save debug config in debug mode
                debug_path = os.path.join(self.OUTPUT_DIR, "debug_config.txt")
                with open(debug_path, 'w') as f:
                    f.writelines(config_lines)
                self.log(f"Debug: Raw config saved to {debug_path}", debug_level=True)
    
            config_date = self.config_parser.get_config_last_change_date(config_lines)
            
            if not preview_only:
                os.makedirs(self.OUTPUT_DIR, exist_ok=True)
    
            # Extract global configurations
            self.config_parser.ikev2_keyring = self.config_parser._extract_blocks_by_prefix(config_lines, 'crypto ikev2 keyring ')
            self.config_parser.ikev2_policy = self.config_parser._extract_blocks_by_prefix(config_lines, 'crypto ikev2 policy ')
            self.config_parser.ikev2_profile = self.config_parser._extract_blocks_by_prefix(config_lines, 'crypto ikev2 profile ')
            self.config_parser.ikev2_proposal = self.config_parser._extract_blocks_by_prefix(config_lines, 'crypto ikev2 proposal ')
            self.config_parser.ipsec_profile = self.config_parser._extract_blocks_by_prefix(config_lines, 'crypto ipsec profile ')
            self.config_parser.ipsec_transform_set = self.config_parser._extract_blocks_by_prefix(config_lines, 'crypto ipsec transform-set ')
            self.config_parser.acls = self.config_parser._extract_blocks_by_prefix(config_lines, 'ip access-list standard')
            self.config_parser.ext_acls = self.config_parser._extract_blocks_by_prefix(config_lines, 'ip access-list extended')
            self.config_parser.nat_pool = self.config_parser.extract_nat_pool(config_lines)
            self.config_parser.ip_sla = self.config_parser.extract_ip_sla(config_lines)
            self.config_parser.tracking = self.config_parser.extract_tracking(config_lines)
    
            # DEBUG: Check if we can find route-maps manually (only in debug mode)
            if self.debug_mode:
                self.log("=== DEBUG: Searching for route-maps in config ===", debug_level=True)
                route_map_lines = [line for line in config_lines if line.strip().startswith('route-map ')]
                self.log(f"Found {len(route_map_lines)} route-map lines in config", debug_level=True)
                for line in route_map_lines[:5]:  # Show first 5
                    self.log(f"  Route-map line: {line.strip()}", debug_level=True)
            
            # Parse route-maps and prefix-lists FIRST
            self.log("=== Calling _parse_route_maps_and_prefix_lists ===", debug_level=True)
            self.vrf_manager._parse_route_maps_and_prefix_lists(config_lines)
            self.log(f"After parsing, found {len(self.config_parser.route_maps)} route-maps", debug_level=True)
    
            # Parse VRFs
            self.vrf_manager.parse_vrf_definitions(config_lines)
    
            # Parse interfaces
            self.vrf_manager.parse_interfaces(config_lines)
    
            # Parse BGP
            self.vrf_manager._parse_bgp(config_lines)                 
    
            # Parse NAT and static routes
            self.vrf_manager._parse_nat_and_static_routes(config_lines)
                    
            # Map which extended ACLs are referenced in NAT configs
            self.vrf_manager._map_acls_to_vrfs()
    
            # Map IP SLA and tracking to VRFs
            self.vrf_manager._map_sla_and_tracking_to_vrfs()
    
            # Add relevant prefix-lists to VRFs
            self.vrf_manager._map_prefix_lists_to_vrfs()
            
            # Identify VRF site roles
            self.vrf_manager._identify_vrf_site_role()
    
            # Extract VRF-specific crypto configurations
            self.vrf_manager._extract_vrf_crypto_configs(config_lines)
    
            # If preview_only mode, just return the parsed VRFs
            if preview_only:
                return True, list(self.config_parser.vrfs.keys())
    
            self._write_output_files(selected_vrf, config_date, device_name)
            
            self.log("Processing completed successfully!")  # This is NOT debug level
            return True, list(self.config_parser.vrfs.keys())
    
        except Exception as e:
            self.log(f"Error during processing: {str(e)}")  # This is NOT debug level
            return False, []

    def normalize_route_map(self, rm_lines):
        """
        Remove accidental nested indentation so each route-map block is flat.
        """
        normalized = []
        for line in rm_lines:
            stripped = line.lstrip()
            # If it's a route-map definition, force no indent
            if stripped.startswith("route-map "):
                normalized.append(stripped)
            # If it's a continuation under the same route-map (match/set/call/set community/etc.)
            else:
                # Keep exactly 1 indent level (2 spaces)
                normalized.append("  " + stripped)
        return normalized


    def _write_output_files(self, selected_vrf, config_date, device_name):
        """Write the parsed configuration to output files."""
        if selected_vrf:
            if selected_vrf not in self.config_parser.vrfs:
                self.log(f"Error: VRF {selected_vrf} not found")
                return False, []
            
            vrfs_to_process = [selected_vrf]
            # NOTE: this used to be hardcoded to ~/ios/vrf_outputs/deployed/<vrf>,
            # silently ignoring the configurable OUTPUT_DIR (and the UI's Output
            # Directory field). Fixed to respect OUTPUT_DIR like every other
            # output path in this class.
            output_dir = os.path.join(self.OUTPUT_DIR, 'deployed', selected_vrf)
        else:
            vrfs_to_process = self.config_parser.vrfs.keys()
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            output_dir = os.path.join(self.OUTPUT_DIR, 'deployed', 'all_vrf', timestamp)
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Output per VRF
        total_vrfs = len(vrfs_to_process)
        for i, vrf in enumerate(vrfs_to_process):
            data = self.config_parser.vrfs[vrf]
            self.log(f"Processing VRF {vrf} ({i+1}/{total_vrfs})")

            # DEBUG: Log ACL information
            self.log(f"VRF {vrf} has {len(data['acls'])} standard ACLs and {len(data['ext_acls'])} extended ACLs")
            if data['acls']:
                self.log(f"Standard ACLs in VRF {vrf}: {list(data['acls'].keys())}")
            if data['ext_acls']:
                self.log(f"Extended ACLs in VRF {vrf}: {list(data['ext_acls'].keys())}")

            if config_date:
                output_filename = os.path.join(output_dir, f"{device_name}-{vrf}_{config_date}.txt")
            else:
                output_filename = os.path.join(output_dir, f"{device_name}-{vrf}.txt")

            with open(output_filename, "w") as f:
                # Write header (missing "\n"s here used to mash these three
                # lines into one unreadable line -- fixed).
                f.write(f"! Extracted from {os.path.basename(self.INPUT_FILE) if hasattr(self, 'INPUT_FILE') else 'live device'}\n")
                if config_date:
                    f.write(f"! Last config change: {config_date.replace('_', ' ')}\n")
                    f.write("!\n")


####Working code
            # Format and write the configuration
#                formatted_config = self.config_parser.format_config_for_output([
#                    "! VRF Definition",
#                    *data['definition'],
#                    "",
#                    "! Interfaces",
#                    *[line for iface in data['interfaces'] for line in iface],
#                    ""
#                ])
#                f.write('\n'.join(formatted_config) + '\n')
##########

                # ---- VRF DEFINITION SECTION ----
                vrf_section = [
                    "! VRF Definition",
                    *data['definition'],
                    ""
                ]
                
                formatted_vrf = self.config_parser.format_config_for_output(vrf_section)
                f.write('\n'.join(formatted_vrf) + '\n')
                
                
                # ---- INTERFACES SECTION ----
                interfaces_section = [
                    "! Interfaces",
                    *[line for iface in data['interfaces'] for line in iface],
                    ""
                ]
                
                formatted_intf = self.config_parser.format_config_for_output(interfaces_section)
                f.write('\n'.join(formatted_intf) + '\n')


                sections = [
                    ("NAT inside Statements", data['nat']),
                    ("NAT outside Statements", data['nat_outside']),
                    ("NAT inside dynamic Statement", data['nat_inside_dynamic']),
                    ("NAT inside dynamic (route-map) Statement", data.get('nat_inside_dynamic2', [])),
                    ("NAT Pool Configuration", data['nat_pool']),
                    ("Access Control Lists", [line for acl in data['acls'].values() for line in acl]),
                    ("Extended Access Control Lists", [line for acl in data['ext_acls'].values() for line in acl]),
                    ("IP SLA Configurations", [line for block in data['ip_sla'] for line in block]),
                    ("Tracking Configurations", [line for block in data['tracking'] for line in block]),
                    ("BGP Config", data['bgp']),
                    ("Static Routes", data['static_routes']),
                    ("Route Maps", [
                        line
                        for rm in data['route_maps']
                        if rm in self.config_parser.route_maps
                        for line in self.normalize_route_map(self.config_parser.route_maps[rm])
                    ]),

                    ("Prefix Lists", [
                        line
                        for pf in data['prefix_lists']
                        if pf in self.config_parser.prefix_lists
                        for line in self.config_parser.prefix_lists[pf]
                    ])
                   # ("Route Maps", [line for rm in data['route_maps'] if rm in self.config_parser.route_maps for line in self.config_parser.route_maps[rm]]),
                   # ("Prefix Lists", [line for pf in data['prefix_lists'] if pf in self.config_parser.prefix_lists for line in self.config_parser.prefix_lists[pf]])
                ]

                for section_name, section_lines in sections:
                    if section_lines:
                        formatted_section = self.config_parser.format_config_for_output([
                            f"! {section_name}",
                            *section_lines,
                            ""
                        ])
                        f.write('\n'.join(formatted_section) + '\n')

                # Write crypto configurations if they exist
                crypto_sections = [
                    ("IKEv2 Keyrings", data['ikev2']['keyring']),
                    ("IKEv2 Proposals", data['ikev2']['proposal']),
                    ("IKEv2 Policies", data['ikev2']['policy']),
                    ("IKEv2 Profiles", data['ikev2']['profile']),
                    ("IPSec Transform Sets", data['ipsec']['transform_set']),
                    ("IPSec Profiles", data['ipsec']['profile'])
                ]

                has_crypto = any(any(items) for _, items in crypto_sections)
                if has_crypto:
                    f.write("! Crypto Configurations\n")
                    for section_name, section_items in crypto_sections:
                        if section_items:
                            formatted_section = self.config_parser.format_config_for_output([
                                f"! {section_name}",
                                *[line for item in section_items for line in item],
                                ""
                            ])
                            f.write('\n'.join(formatted_section) + '\n')

                # Write footer
                f.write("!")

        # Output global IPSec and IKEv2 configurations (only when processing all VRFs)
        if not selected_vrf:
            with open(f"{self.OUTPUT_DIR}/global_ipsec_ikev2.txt", "w") as f:
                f.write("! Global IKEv2 and IPSec Configurations\n")
                f.write("! IKEv2 Keyring\n")
                for keyring in self.config_parser.ikev2_keyring:
                    f.writelines(keyring)
                
                f.write("\n! IKEv2 Policy\n")
                for policy in self.config_parser.ikev2_policy:
                    f.writelines(policy)
                
                f.write("\n! IKEv2 Profile\n")
                for profile in self.config_parser.ikev2_profile:
                    f.writelines(profile)
                
                f.write("\n! IKEv2 Proposal\n")
                for proposal in self.config_parser.ikev2_proposal:
                    f.writelines(proposal)
                
                f.write("\n! IPSec Profile\n")
                for profile in self.config_parser.ipsec_profile:
                    f.writelines(profile)
                
                f.write("\n! IPSec Transform Set\n")
                for ts in self.config_parser.ipsec_transform_set:
                    f.writelines(ts)
                
                f.write("\n! IP SLA Configurations\n")
                for sla_num, sla_data in self.config_parser.ip_sla.items():
                    f.writelines(sla_data['config'])
                
                f.write("\n! Tracking Configurations\n")
                for track_num, track_data in self.config_parser.tracking.items():
                    f.writelines(track_data['config'])
                    
                f.write("\n! Access Control Lists\n")
                for acl in self.config_parser.acls:
                    f.writelines(acl)
        

    

    def generate_vrf_json(self, vrf_name):
        """Generate a JSON string for a specific VRF."""
        if vrf_name not in self.config_parser.vrfs:
            return json.dumps({"error": f"VRF {vrf_name} not found"}, indent=2)
        
        data_to_dump = self.config_parser.vrfs[vrf_name].copy()
        
        # Convert sets to lists for JSON serialization
        for key, value in data_to_dump.items():
            if isinstance(value, set):
                data_to_dump[key] = list(value)

        # Populate content for route-maps and prefix-lists
        if 'route_maps' in data_to_dump:
            data_to_dump['route_maps'] = {rm: self.config_parser.route_maps.get(rm, []) for rm in data_to_dump['route_maps']}
        if 'prefix_lists' in data_to_dump:
            data_to_dump['prefix_lists'] = {pf: self.config_parser.prefix_lists.get(pf, []) for pf in data_to_dump['prefix_lists']}
        
        # Remove duplicate tunnel interfaces key
        if 'tunnel_interfaces' in data_to_dump:
            del data_to_dump['tunnel_interfaces']

        return json.dumps(data_to_dump, indent=2)

    
    def get_vrf_config(self, vrf_name):
        """Return the raw configuration lines for a specific VRF"""
        if vrf_name not in self.config_parser.vrfs:
            return None
        
        data = self.config_parser.vrfs[vrf_name]
        config_lines = []
    
        try:
           # VRF Definition
            config_lines.extend(data['definition'])
            config_lines.append('')
        
           # Interfaces
            for iface in data['interfaces']:
                config_lines.extend(iface)
                config_lines.append('')
            
           # NAT configurations
            if data['nat']:
                config_lines.extend(data['nat'])
                config_lines.append('')
            
            if data['nat_outside']:
                config_lines.extend(data['nat_outside'])
                config_lines.append('')
            
            if data['nat_inside_dynamic']:
                config_lines.extend(data['nat_inside_dynamic'])
                config_lines.append('')

            if data.get('nat_inside_dynamic2'):
                config_lines.extend(data['nat_inside_dynamic2'])
                config_lines.append('') 
            
            if data['nat_pool']:
                config_lines.extend(data['nat_pool'])
                config_lines.append('')
            
            # ACLs
            if data['acls']:
                config_lines.append('!')
                config_lines.append('! ACL & Extended ACL details')
                config_lines.append('!')
                for acl_name, acl_lines in data['acls'].items():
                    config_lines.extend(acl_lines)
                    config_lines.append('')
                
            if data['ext_acls']:
                for ext_acl_name, ext_acl_lines in data['ext_acls'].items():
                    config_lines.extend(ext_acl_lines)
                    config_lines.append('')
                
            # IP SLA and Tracking
            if data['ip_sla']:
                for sla in data['ip_sla']:
                    config_lines.extend(sla)
                    config_lines.append('')
                
            if data['tracking']:
                for track in data['tracking']:
                    config_lines.extend(track)
                    config_lines.append('')
                
            # BGP and static routes
            if data['bgp']:
                config_lines.append('!')
                config_lines.append('! BGP configuration')
                config_lines.append('!')
                config_lines.extend(data['bgp'])
                config_lines.append('')
            
            if data['static_routes']:
                config_lines.append('!')
                config_lines.append('! Static Routes')
                config_lines.append('!')
                config_lines.extend(data['static_routes'])
                config_lines.append('')
                
            # Route-maps and prefix-lists
            if hasattr(self.config_parser, 'route_maps') and hasattr(self.config_parser, 'prefix_lists'):
                # Add route-maps referenced by this VRF
                if data['route_maps']:
                    config_lines.append('!')
                    config_lines.append('! Route Maps')
                    config_lines.append('!')
                    for rm in sorted(data['route_maps']):
                        if rm in self.config_parser.route_maps:
                            config_lines.extend(self.config_parser.route_maps[rm])
                            config_lines.append('')
            
            # Add prefix-lists referenced by this VRF
            if data['prefix_lists']:
                config_lines.append('! Prefix Lists')
                for pf in sorted(data['prefix_lists']):
                    if pf in self.config_parser.prefix_lists:
                        config_lines.extend(self.config_parser.prefix_lists[pf])
                        config_lines.append('')
            
        
            # Crypto configurations
            if (data['ikev2']['keyring'] or data['ikev2']['policy'] or 
                data['ikev2']['profile'] or data['ikev2']['proposal'] or
                data['ipsec']['profile'] or data['ipsec']['transform_set']):
            
                if data['ikev2']['keyring']:
                    for keyring in data['ikev2']['keyring']:
                        config_lines.extend(keyring)
                        config_lines.append('')
            
                if data['ikev2']['proposal']:
                    for proposal in data['ikev2']['proposal']:
                        config_lines.extend(proposal)
                        config_lines.append('')
            
                if data['ikev2']['policy']:
                    for policy in data['ikev2']['policy']:
                        config_lines.extend(policy)
                        config_lines.append('')
            
                if data['ikev2']['profile']:
                    for profile in data['ikev2']['profile']:
                        config_lines.extend(profile)
                        config_lines.append('')
            
                if data['ipsec']['transform_set']:
                    for ts in data['ipsec']['transform_set']:
                        config_lines.extend(ts)
                        config_lines.append('')
            
                if data['ipsec']['profile']:
                    for profile in data['ipsec']['profile']:
                        config_lines.extend(profile)
                        config_lines.append('')
                    
            return config_lines
            
        except Exception as e:
            self.log(f"Error generating VRF config: {str(e)}")
            return [f"Error generating configuration for VRF {vrf_name}"]

    def format_config_for_output(self, config_lines):
        """Format configuration lines for file output with proper Cisco formatting."""
        return self.config_parser.format_config_for_output(config_lines)

    

    def _is_profile_used_by_other_vrfs(self, profile_name, current_vrf):
        """Check if a crypto profile is used by other VRFs"""
        for vrf, data in self.config_parser.vrfs.items():
            if vrf != current_vrf:
                # Check IPSec profiles
                for profile in data.get('ipsec', {}).get('profile', []):
                    try:
                        parts = profile[0].strip().split()
                        if len(parts) >= 4 and parts[3] == profile_name:
                            return True
                    except (IndexError, AttributeError) as e:
                        self.log(f"[WARNING] Error parsing IPSec profile in VRF {vrf}: {e}", debug_level=True)
                        continue
                
                # Also check IKEv2 profiles
                for profile in data.get('ikev2', {}).get('profile', []):
                    try:
                        parts = profile[0].strip().split()
                        if len(parts) >= 4 and parts[3] == profile_name:
                            return True
                    except (IndexError, AttributeError) as e:
                        self.log(f"[WARNING] Error parsing IKEv2 profile in VRF {vrf}: {e}", debug_level=True)
                        continue
        return False

    def _is_transform_set_used_elsewhere(self, ts_name, current_vrf):
        """Check if transform set is used by other profiles"""
        for vrf, data in self.config_parser.vrfs.items():
            if vrf != current_vrf:
                for ts in data.get('ipsec', {}).get('transform_set', []):
                    try:
                        parts = ts[0].strip().split()
                        if len(parts) >= 4 and parts[3] == ts_name:
                            return True
                    except (IndexError, AttributeError) as e:
                        self.log(f"[WARNING] Error parsing transform-set in VRF {vrf}: {e}", debug_level=True)
                        continue
        return False

    def _is_route_map_used_elsewhere(self, rm_name, current_vrf):
        """Check if route-map is used by other VRFs"""
        for vrf, data in self.config_parser.vrfs.items():
            if vrf != current_vrf and rm_name in data['route_maps']:
                return True
        return False

    def _is_prefix_list_used_elsewhere(self, pf_name, current_vrf):
        """Check if prefix-list is used by other VRFs"""
        for vrf, data in self.config_parser.vrfs.items():
            if vrf != current_vrf and pf_name in data['prefix_lists']:
                return True
        return False

    def _is_acl_used_elsewhere(self, acl_name, current_vrf):
        """Check if ACL is used by other VRFs (not in global configuration)"""
        # Check other VRFs
        for vrf, data in self.config_parser.vrfs.items():
            if vrf != current_vrf:
                # Check standard ACLs
                if acl_name in data['acls']:
                    return True
                # Check extended ACLs
                if acl_name in data['ext_acls']:
                    return True
                # Check if ACL is referenced in NAT configuration
                for nat_line in data.get('nat_inside_dynamic', []):
                    if f'list {acl_name}' in nat_line:
                        return True
        
        return False

    def generate_rollback_script(self, vrf_name):
        """Generate optimized rollback script focusing on ACLs and NAT pools"""
        self.log(f"[ROLLBACK] generate_rollback_script called for VRF: '{vrf_name}'")
        self.log(f"[ROLLBACK] Available VRFs: {list(self.config_parser.vrfs.keys())}")
        
        if vrf_name not in self.config_parser.vrfs:
            self.log(f"[ROLLBACK] ERROR: VRF '{vrf_name}' not found in parsed VRFs!")
            self.log(f"[ROLLBACK] VRF keys type: {type(list(self.config_parser.vrfs.keys())[0]) if self.config_parser.vrfs else 'N/A'}")
            self.log(f"[ROLLBACK] Input VRF type: {type(vrf_name)}")
            return None
        
        self.log(f"[ROLLBACK] VRF '{vrf_name}' found, generating script...")
        rollback_commands = []
        data = self.config_parser.vrfs[vrf_name]

        # Debug: Log initial VRF data
        self.log(f"\n[DEBUG] Starting rollback for VRF {vrf_name}")
        self.log(f"[DEBUG] VRF has {len(data['ext_acls'])} extended ACLs: {list(data['ext_acls'].keys())}")
        
        # Add header
        rollback_commands.append(f"! Rollback script for VRF {vrf_name}")
        rollback_commands.append(f"! Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        rollback_commands.append("!")
        
        # 1. First remove tunnel interfaces
        for interface_block in data['interfaces']:
            interface_line = interface_block[0].strip()
            if_name = interface_line.split()[1]
            if 'Tunnel' in interface_line:
                rollback_commands.append(f"interface {if_name}")
                rollback_commands.append(" shutdown")
                rollback_commands.append(" exit")
                rollback_commands.append(f"no interface {if_name}")
        
        # 2. Remove NAT inside configurations that reference ACLs
        acl_references = set()
        pool_references = set()

        self.log(f"[DEBUG] Processing {len(data['nat_inside_dynamic'])} NAT rules")

        for nat_line in data['nat_inside_dynamic']:

            self.log(f"[DEBUG] Processing NAT line: {nat_line.strip()}")
            # Extract ACL and pool names from NAT configuration
            acl_match = re.search(r'ip nat inside source list (\S+)', nat_line)        
            if acl_match:
                acl_name = acl_match.group(1)
                acl_references.add(acl_name)
                self.log(f"[DEBUG] Found ACL reference in NAT: {acl_name}")

            pool_match = re.search(r'pool (\S+)', nat_line)
            if pool_match:
                pool_name = pool_match.group(1)
                pool_references.add(pool_name)
                self.log(f"[DEBUG] Found pool reference in NAT: {pool_name}")
            
            # Add NAT removal command
            rollback_commands.append(f"no {nat_line.strip()}")

           # # Add NAT removal command
           # nat_cmd = re.sub(r'^ip nat ', '', nat_line.strip())
           # rollback_commands.append(f"no ip nat {nat_cmd}")
        
        # 3. Remove NAT pools referenced in dynamic NAT
        for pool_name in pool_references:
            rollback_commands.append(f"no ip nat pool {pool_name}")
        
        # 4. Remove extended ACLs referenced in NAT configurations
        for acl_name in acl_references:
            if not self._is_acl_used_elsewhere(acl_name, vrf_name):
                rollback_commands.append(f"no ip access-list extended {acl_name}")
        
        # 5. Remove VRF definition (this will clean up remaining VRF-specific configs)
        rollback_commands.append(f"no vrf definition {vrf_name}")
        rollback_commands.append("!")
        
        # 6. Remove crypto components in dependency order
        rollback_commands.append("!")
        rollback_commands.append("! Removing crypto configurations")
        
        # IPSec profiles - only if not used by other VRFs
        for profile in data['ipsec']['profile']:
            profile_name = profile[0].strip().split()[3]
            if not self._is_profile_used_by_other_vrfs(profile_name, vrf_name):
                rollback_commands.append(f"no crypto ipsec profile {profile_name}")
                self.log(f"[DEBUG] Removing IPSec profile: {profile_name}", debug_level=True)
            else:
                rollback_commands.append(f"! Skipping {profile_name} - used by other VRFs")
                self.log(f"[DEBUG] Skipping IPSec profile {profile_name} - shared with other VRFs", debug_level=True)
        
        # IKEv2 profiles - only if not used by other VRFs
        for profile in data['ikev2']['profile']:
            profile_name = profile[0].strip().split()[3]
            if not self._is_profile_used_by_other_vrfs(profile_name, vrf_name):
                rollback_commands.append(f"no crypto ikev2 profile {profile_name}")
                self.log(f"[DEBUG] Removing IKEv2 profile: {profile_name}", debug_level=True)
            else:
                rollback_commands.append(f"! Skipping {profile_name} - used by other VRFs")
                self.log(f"[DEBUG] Skipping IKEv2 profile {profile_name} - shared with other VRFs", debug_level=True)
        
        # IKEv2 keyrings
        for keyring in data['ikev2']['keyring']:
            keyring_name = keyring[0].strip().split()[3]
            rollback_commands.append(f"no crypto ikev2 keyring {keyring_name}")
            self.log(f"[DEBUG] Removing IKEv2 keyring: {keyring_name}", debug_level=True)

        # Transform sets - only if not used elsewhere
        for transform_set in data['ipsec']['transform_set']:
            transform_name = transform_set[0].strip().split()[3]
            if not self._is_transform_set_used_elsewhere(transform_name, vrf_name):
                rollback_commands.append(f"no crypto ipsec transform-set {transform_name}")
                self.log(f"[DEBUG] Removing transform-set: {transform_name}", debug_level=True)
            else:
                rollback_commands.append(f"! Skipping {transform_name} - used by other VRFs")
                self.log(f"[DEBUG] Skipping transform-set {transform_name} - shared with other VRFs", debug_level=True)
        
        # 7. Remove route-maps and prefix-lists (check if used elsewhere)
        for rm_name in data['route_maps']:
            if not self._is_route_map_used_elsewhere(rm_name, vrf_name):
                rollback_commands.append(f"no route-map {rm_name}")
        
        for pf_name in data['prefix_lists']:
            if not self._is_prefix_list_used_elsewhere(pf_name, vrf_name):
                rollback_commands.append(f"no ip prefix-list {pf_name}")
        
        # Add footer
        rollback_commands.append("!")
        rollback_commands.append("! Rollback script complete")
        
        return rollback_commands

    
    


    def parse_vpn_status(self, command, output):
        """Parse VPN status command outputs"""
        return self.vpn_monitor.parse_vpn_status(command, output)


    def check_vpn_status(self, connection):
        """Check all VPN status information"""
        results = {}
        
        for cmd in self.vpn_monitor.VPN_STATUS_COMMANDS:
            try:
                output = connection.send_command(cmd)
                results[cmd] = self.vpn_monitor.parse_vpn_status(cmd, output)
            except Exception as e:
                self.log(f"Failed to execute {cmd}: {str(e)}")
        return results

    def get_vrfs(self):
        """Get the VRF dictionary"""
        return self.config_parser.vrfs 


    def generate_troubleshooting_commands(self, vrf_name):
        """Generate troubleshooting commands for a VRF"""
        if vrf_name not in self.config_parser.vrfs:
            return "VRF not found"
        
        vrf_data = self.config_parser.vrfs[vrf_name]
        commands = []
        
        # Header
        commands.append(f"# Troubleshooting Commands for VRF {vrf_name}")
        commands.append("# Generated on {}\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        # Check tunnel status
        commands.append("# Check tunnel status")
        for interface_block in vrf_data.get('interfaces', []):
            if interface_block and 'Tunnel' in interface_block[0]:
                interface_name = interface_block[0].strip().split()[1]
                commands.append(f"show interface {interface_name}")
                
                # Try to find tunnel destination
                tunnel_dest = "TUNNEL_DEST"
                for line in interface_block:
                    if 'tunnel destination' in line:
                        tunnel_dest = line.strip().split()[2]
                        break
                        
                commands.append(f"show crypto ipsec sa peer {tunnel_dest}")
        
        commands.append("show crypto ikev2 sa\n")
        
        # Check BGP status
        commands.append("# Check BGP status")
        commands.append(f"show ip bgp vpnv4 vrf {vrf_name} summary")
        
        # Extract BGP neighbors
        bgp_neighbors = set()
        for line in vrf_data.get('bgp', []):
            if 'neighbor' in line and 'remote-as' in line:
                parts = line.strip().split()
                for i, part in enumerate(parts):
                    if part == 'neighbor' and i+1 < len(parts):
                        bgp_neighbors.add(parts[i+1])
                        break
        
        for neighbor in sorted(bgp_neighbors):
            commands.append(f"show ip bgp vpnv4 vrf {vrf_name} neighbors {neighbor} advertised-routes")
            commands.append(f"show ip bgp vpnv4 vrf {vrf_name} neighbors {neighbor} received-routes")
        
        commands.append("")
        
        # Check routing table
        commands.append("# Check routing table")
        commands.append(f"show ip route vrf {vrf_name}\n")
        
        # Check BFD status (if applicable)
        commands.append("# Check BFD status")
        commands.append(f"show bfd neighbors vrf {vrf_name}\n")
        
        # Advanced diagnostic commands
        commands.append("# Advanced diagnostic commands")
        commands.append("# debug crypto ikev2")
        commands.append("# debug crypto ipsec")
        commands.append("# debug ip bgp vpnv4 unicast")
        commands.append("# debug ip bgp events\n")
        
        # Interface debugging
        commands.append("# Interface status")
        for interface_block in vrf_data.get('interfaces', []):
            if interface_block:
                interface_name = interface_block[0].strip().split()[1]
                commands.append(f"show interface {interface_name} | include line protocol")
        
        commands.append("")
        
        # Route-map analysis
        commands.append("# Route-map analysis")
        for rm_name in vrf_data.get('route_maps', []):
            commands.append(f"show route-map {rm_name}")
        
        # Add packet capture commands
        commands.append(self._generate_packet_capture_commands(vrf_data))
        
        return "\n".join(commands)

    
    def _generate_packet_capture_commands(self, vrf_data):
        """Generate packet capture commands for tunnel interfaces"""
        commands = [
            "\n# Packet Capture Commands",
            "# Create capture access-list (adjust parameters as needed)",
            "ip access-list extended CAPTURE-ACL",
            " permit ip any any",
            " exit",
            ""
        ]
        
        # Add capture commands for each tunnel interface
        tunnel_interfaces = []
        for interface_block in vrf_data.get('interfaces', []):
            if interface_block and 'Tunnel' in interface_block[0]:
                interface_name = interface_block[0].strip().split()[1]
                tunnel_interfaces.append(interface_name)
                
                commands.extend([
                    f"# Capture on {interface_name}",
                    f"monitor capture CAPTURE-{interface_name} interface {interface_name} both",
                    f"monitor capture CAPTURE-{interface_name} match access-group CAPTURE-ACL",
                    f"monitor capture CAPTURE-{interface_name} start",
                    "# Wait for traffic...",
                    f"monitor capture CAPTURE-{interface_name} stop",
                    f"monitor capture CAPTURE-{interface_name} export tftp://<tftp_server>/capture_{interface_name}.pcap",
                    ""
                ])
        
        if tunnel_interfaces:
            commands.extend([
                "# Alternative: Embedded Packet Capture (EPC) for specific traffic",
                "monitor capture CAPTURE-BUFFER interface Tunnel0 in",
                "monitor capture CAPTURE-BUFFER access-list CAPTURE-ACL",
                "monitor capture CAPTURE-BUFFER limit duration 60",
                "monitor capture CAPTURE-BUFFER start",
                "# Wait for capture to complete...",
                "monitor capture CAPTURE-BUFFER stop",
                "monitor capture CAPTURE-BUFFER export tftp://<tftp_server>/capture_buffer.pcap",
                ""
            ])
        else:
            commands.append("# No tunnel interfaces found for packet capture\n")
        
        return "\n".join(commands)


    def get_vrf_summaries(self):
        """Get summaries for all VRFs"""
        return self.vrf_manager.generate_all_vrf_summaries()

# ==================== GUI CLASSES ====================
