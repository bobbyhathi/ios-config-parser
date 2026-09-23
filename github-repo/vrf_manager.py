"""
Parses VRF definitions, interfaces, NAT, BGP, route-maps/prefix-lists and
crypto/IPsec configuration out of a Cisco IOS config and assembles the
per-VRF data structures the rest of the app works with.
"""
import re


class VRFManager:
    def __init__(self, config_parser):
        self.parser = config_parser
        
    def parse_vrf_definitions(self, config_lines):
        """Parse VRF definitions from configuration lines."""
        i = 0
        while i < len(config_lines):
            line = config_lines[i]
            match = re.match(r'^(vrf definition|ip vrf) (\S+)', line, re.IGNORECASE)
            if match:
                vrf = match.group(2)
                block, i = self.parser.extract_block(i, config_lines)
                self.parser.vrfs[vrf]['definition'] = block
                self.parser.log(f"Found VRF: {vrf}")
                continue
            i += 1

### WORKING CODE            
    def parse_interfaces(self, config_lines):
        """Parse interface configurations."""
        i = 0
        while i < len(config_lines):
            line = config_lines[i]
            if line.startswith('interface '):
                block, i = self.parser.extract_block(i, config_lines)
                interface_vrf = None
                ipsec_profile_name = None
                
                for l in block:
                    vrf_match = re.search(r'vrf forwarding (\S+)', l)
                    if vrf_match:
                        interface_vrf = vrf_match.group(1)
                    
                    profile_match = re.search(r'tunnel protection ipsec profile (\S+)', l)
                    if profile_match:
                        ipsec_profile_name = profile_match.group(1)
                
                if interface_vrf in self.parser.vrfs:
                    self.parser.vrfs[interface_vrf]['interfaces'].append(block)
                    if 'Tunnel' in line and ipsec_profile_name:
                        self.parser.vrfs[interface_vrf]['tunnel_interfaces'].append({
                            'interface': block,
                            'ipsec_profile': ipsec_profile_name
                        })
            else:
                i += 1




    # Enhanced version with better error handling:
    def _parse_nat_and_static_routes(self, config_lines):
        """Parse NAT and static routes from configuration lines."""
        for line in config_lines:
            try:
                # Existing patterns
                nat = re.match(r'ip nat inside source static .* vrf (\S+)', line)
                nat_outside = re.match(r'ip nat outside source static .* vrf (\S+)', line)
                nat_inside_dynamic = re.match(r'ip nat inside source list (\S+) pool (\S+) vrf (\S+)', line)
                
                # Fixed route-map based NAT pattern
                nat_inside_dynamic2 = re.match(r'ip nat inside source route-map (\S+) pool (\S+) vrf (\S+)', line)
                
                route = re.match(r'ip route vrf (\S+)', line)            
                
                if nat:
                    vrf = nat.group(1)
                    if vrf in self.parser.vrfs:
                        self.parser.vrfs[vrf]['nat'].append(line)
                        
                elif nat_outside:
                    vrf = nat_outside.group(1)
                    if vrf in self.parser.vrfs:
                        self.parser.vrfs[vrf]['nat_outside'].append(line)
                        
                elif nat_inside_dynamic:
                    pool_name = nat_inside_dynamic.group(2)
                    vrf = nat_inside_dynamic.group(3)
                    if vrf in self.parser.vrfs:
                        self.parser.vrfs[vrf]['nat_inside_dynamic'].append(line)
                        if pool_name in self.parser.nat_pool:
                            self.parser.vrfs[vrf]['nat_pool'] = self.parser.nat_pool[pool_name]
                
                # Handle route-map based NAT configuration
                elif nat_inside_dynamic2:
                    route_map_name = nat_inside_dynamic2.group(1)
                    pool_name = nat_inside_dynamic2.group(2)
                    vrf = nat_inside_dynamic2.group(3)
                    
                    if vrf in self.parser.vrfs:
                        # Ensure the list exists
                        if 'nat_inside_dynamic2' not in self.parser.vrfs[vrf]:
                            self.parser.vrfs[vrf]['nat_inside_dynamic2'] = []
                            
                        self.parser.vrfs[vrf]['nat_inside_dynamic2'].append(line)
                        
                        # Store the route-map reference
                        self.parser.vrfs[vrf]['route_maps'].add(route_map_name)
                        
                        # Add the NAT pool if it exists
                        if pool_name in self.parser.nat_pool:
                            self.parser.vrfs[vrf]['nat_pool'] = self.parser.nat_pool[pool_name]
                
                if route:
                    vrf = route.group(1)
                    if vrf in self.parser.vrfs:
                        self.parser.vrfs[vrf]['static_routes'].append(line)
                        
                        # Extract track number from static route
                        track_match = re.search(r'track (\d+)', line)
                        if track_match:
                            track_num = track_match.group(1)
                            # Store track numbers referenced by this VRF
                            if 'referenced_tracks' not in self.parser.vrfs[vrf]:
                                self.parser.vrfs[vrf]['referenced_tracks'] = set()
                            self.parser.vrfs[vrf]['referenced_tracks'].add(track_num)
                        
            except Exception as e:
                self.parser.log(f"Warning: Error parsing line '{line}': {str(e)}")
                continue


    def _parse_bgp(self, config_lines):
        """Parse BGP configurations."""
        i = 0
        # --- grab global ASN once ---
        asn = None
        for l in config_lines:
            m = re.search(r'^router bgp (\d+)', l.strip())
            if m:
                asn = m.group(1)
                break
        # store it in every VRF so we never have to search again
        for v in self.parser.vrfs:
            self.parser.vrfs[v]['asn'] = asn
    
        while i < len(config_lines):
            line = config_lines[i]
            if line.strip().startswith('router bgp '):
                bgp_block, i = self.parser.extract_block(i, config_lines)
                current_vrf = None
                
                for bgp_line in bgp_block:
                    af_match = re.search(r'address-family ipv4 vrf (\S+)', bgp_line.strip())
                    if af_match:
                        current_vrf = af_match.group(1)
                        if current_vrf in self.parser.vrfs:
                            # Add only the router bgp statement and the address-family line
                            # Don't include global BGP configuration
                            self.parser.vrfs[current_vrf]['bgp'].append(line)  # The original 'router bgp X' line
                            self.parser.vrfs[current_vrf]['bgp'].append(bgp_line)
                    elif current_vrf and current_vrf in self.parser.vrfs:
                        # Only add lines that are indented (sub-commands of the address-family)
                        if bgp_line.startswith(' ') or bgp_line.startswith('\t'):
                            self.parser.vrfs[current_vrf]['bgp'].append(bgp_line)
                            for rm in re.findall(r'route-map (\S+)', bgp_line):
                                self.parser.vrfs[current_vrf]['route_maps'].add(rm)
                    # Skip global BGP configuration that's not part of any VRF
            else:
                i += 1


    def _parse_route_maps_and_prefix_lists(self, config_lines):
        """Parse route-maps and prefix-lists from configuration lines."""
        self.parser.log("=== Starting route-map parsing ===", debug_level=True)
        i = 0
        route_maps_found = 0
        
        while i < len(config_lines):
            line = config_lines[i]
            if line.strip().startswith('route-map '):
                route_maps_found += 1
                name = line.strip().split()[1] 
                self.parser.log(f"Found route-map: {name} at line {i}", debug_level=True)
                
                block, i = self.parser.extract_block(i, config_lines)
                
                # Store the route-map
                if name not in self.parser.route_maps:
                    self.parser.route_maps[name] = []
                self.parser.route_maps[name].extend(block)
                
                self.parser.log(f"Stored route-map {name} with {len(block)} lines", debug_level=True)
                
            elif line.strip().startswith('ip prefix-list '):
                name = line.strip().split()[2].strip(':')
                block, i = self.parser.extract_block(i, config_lines)
                if name not in self.parser.prefix_lists:
                    self.parser.prefix_lists[name] = []
                self.parser.prefix_lists[name].extend(block)
            else:
                i += 1
        
        self.parser.log(f"=== Finished route-map parsing: found {route_maps_found} route-maps, stored {len(self.parser.route_maps)} ===", debug_level=True)    
    
    # Update the _map_acls_to_vrfs method to better handle ACL extraction from route-maps:
    def _map_acls_to_vrfs(self):
        """Map ACLs to VRFs based on NAT configurations and route-maps."""
        for vrf, data in self.parser.vrfs.items():
            referenced_acl_names = set()
    
            self.parser.log(f"=== Processing VRF: {vrf} ===", debug_level=True)
            self.parser.log(f"nat_inside_dynamic2 lines: {len(data.get('nat_inside_dynamic2', []))}", debug_level=True)
            self.parser.log(f"route_maps in VRF: {list(data.get('route_maps', set()))}", debug_level=True)
            self.parser.log(f"Available route-maps in parser: {list(self.parser.route_maps.keys())}", debug_level=True)
    
            # Check traditional NAT configurations
            for line in data['nat_inside_dynamic']:
                match = re.search(r'ip nat inside source list (\S+)', line)
                if match:
                    acl_name = match.group(1)
                    referenced_acl_names.add(acl_name)
                    self.parser.log(f"Found ACL reference in NAT for VRF {vrf}: {acl_name}", debug_level=True)
    
            # Check route-map based NAT configurations
            for line in data.get('nat_inside_dynamic2', []):
                self.parser.log(f"Processing NAT line: {line.strip()}", debug_level=True)
                rm_match = re.search(r'route-map (\S+)', line)
                if rm_match:
                    route_map_name = rm_match.group(1)
                    self.parser.log(f"Found route-map reference: {route_map_name} in VRF {vrf}", debug_level=True)
                    
                    # Check if route-map exists
                    if route_map_name in self.parser.route_maps:
                        self.parser.log(f"Route-map {route_map_name} found in parser.route_maps", debug_level=True)
                        for rm_line in self.parser.route_maps[route_map_name]:
                            acl_match = re.search(r'match ip address (?:access-list )?(\S+)', rm_line.strip())
                            if acl_match:
                                acl_name = acl_match.group(1).strip()
                                referenced_acl_names.add(acl_name)
                                self.parser.log(f"Found ACL reference in route-map {route_map_name} for VRF {vrf}: {acl_name}", debug_level=True)
                    else:
                        self.parser.log(f"WARNING: Route-map {route_map_name} not found in parser.route_maps", debug_level=True)
    
            self.parser.log(f"VRF {vrf} references these ACLs after NAT check: {list(referenced_acl_names)}", debug_level=True)
    
            # Map extended ACLs
            acls_mapped = 0
            for block in self.parser.ext_acls:
                match = re.match(r'ip access-list extended (\S+)', block[0].strip())
                if not match:
                    continue
                acl_name = match.group(1)
                if acl_name in referenced_acl_names:
                    # Use assignment to replace any existing value
                    data['ext_acls'][acl_name] = block
                    acls_mapped += 1
                    self.parser.log(f"SUCCESS: Mapped extended ACL {acl_name} to VRF {vrf}", debug_level=True)
                    
            # Map standard ACLs  
            for block in self.parser.acls:
                match = re.match(r'ip access-list standard (\S+)', block[0].strip())
                if not match:
                    continue
                acl_name = match.group(1)
                if acl_name in referenced_acl_names:
                    data['acls'][acl_name] = block
                    acls_mapped += 1
                    self.parser.log(f"SUCCESS: Mapped standard ACL {acl_name} to VRF {vrf}", debug_level=True)
    
            self.parser.log(f"Total ACLs mapped to VRF {vrf}: {acls_mapped}", debug_level=True)
            self.parser.log(f"Final ACLs in VRF {vrf}: standard={list(data['acls'].keys())}, extended={list(data['ext_acls'].keys())}", debug_level=True)
            self.parser.log(f"=== Finished VRF: {vrf} ===\n", debug_level=True)

    def _map_sla_and_tracking_to_vrfs(self):
        """Map IP SLA and tracking configurations to VRFs."""
        for sla_num, sla_data in self.parser.ip_sla.items():
            if sla_data['vrf'] and sla_data['vrf'] in self.parser.vrfs:
                self.parser.vrfs[sla_data['vrf']]['ip_sla'].append(sla_data['config'])

        for track_num, track_data in self.parser.tracking.items():
            # Handle SLA-based tracking
            if track_data['sla_num'] and track_data['sla_num'] in self.parser.ip_sla:
                vrf = self.parser.ip_sla[track_data['sla_num']]['vrf']
                if vrf and vrf in self.parser.vrfs:
                    self.parser.vrfs[vrf]['tracking'].append(track_data['config'])
            # Handle IP route reachability tracking with explicit VRF
            elif track_data.get('type') == 'ip_route' and track_data.get('vrf'):
                vrf = track_data['vrf']
                if vrf in self.parser.vrfs:
                    self.parser.vrfs[vrf]['tracking'].append(track_data['config'])
        
        # Additionally, map tracks referenced by static routes in each VRF
        for vrf_name, vrf_data in self.parser.vrfs.items():
            if 'referenced_tracks' in vrf_data:
                for track_num in vrf_data['referenced_tracks']:
                    if track_num in self.parser.tracking:
                        track_config = self.parser.tracking[track_num]['config']
                        # Only add if not already present
                        if track_config not in vrf_data['tracking']:
                            vrf_data['tracking'].append(track_config)

    def _map_prefix_lists_to_vrfs(self):
        """Map prefix-lists to VRFs based on route-maps."""
        for vrf, data in self.parser.vrfs.items():
            for rm in data['route_maps']:
                if rm in self.parser.route_maps:
                    for l in self.parser.route_maps[rm]:
                        for pf in re.findall(r'ip address prefix-list (\S+)', l):
                            if pf in self.parser.prefix_lists:
                                data['prefix_lists'].add(pf)

    def _identify_vrf_site_role(self):
        """Identifies the primary/secondary site role for each VRF based on BGP communities."""
        for vrf_name, vrf_data in self.parser.vrfs.items():
            vrf_data['site_role'] = 'Unknown' # Default

            # Check BGP config within this VRF for route-maps
            for bgp_line in vrf_data.get('bgp', []):
                rm_matches = re.findall(r'route-map (\S+)', bgp_line)
                for rm_name in rm_matches:
                    if rm_name in self.parser.route_maps:
                        for rm_line in self.parser.route_maps[rm_name]:
                            if 'set community' in rm_line:
                                if ':6300' in rm_line:
                                    vrf_data['site_role'] = 'Primary'
                                    break # Found primary, no need to check further for this VRF
                                elif ':6200' in rm_line:
                                    vrf_data['site_role'] = 'Secondary'
                                    # Don't break yet, a primary might override secondary
                        if vrf_data['site_role'] == 'Primary':
                            break # Found primary, no need to check further for this VRF
                if vrf_data['site_role'] == 'Primary':
                    break # Found primary, no need to check further for this VRF

    
    def _extract_vrf_crypto_configs(self, config_lines):
        """Extract VRF-specific crypto configurations for all VRFs."""
        # First, extract all crypto configurations
        self.parser.ikev2_keyring = self.parser._extract_blocks_by_prefix(config_lines, 'crypto ikev2 keyring ')
        self.parser.ikev2_policy = self.parser._extract_blocks_by_prefix(config_lines, 'crypto ikev2 policy ')
        self.parser.ikev2_profile = self.parser._extract_blocks_by_prefix(config_lines, 'crypto ikev2 profile ')
        self.parser.ikev2_proposal = self.parser._extract_blocks_by_prefix(config_lines, 'crypto ikev2 proposal ')
        self.parser.ipsec_profile = self.parser._extract_blocks_by_prefix(config_lines, 'crypto ipsec profile ')
        self.parser.ipsec_transform_set = self.parser._extract_blocks_by_prefix(config_lines, 'crypto ipsec transform-set ')
        
        # Now extract crypto config for each VRF
        for vrf_name, data in self.parser.vrfs.items():
            if data['tunnel_interfaces']:
                self.extract_vrf_crypto_config(data, config_lines, vrf_name)
            else:
                # Even if no tunnel interfaces, we might have crypto config
                # Check if VRF is referenced in any crypto configuration
                self._extract_crypto_for_non_tunnel_vrf(data, config_lines, vrf_name)

    def _extract_crypto_for_non_tunnel_vrf(self, vrf_data, config_lines, vrf_name):
        """Extract crypto config for VRFs without tunnel interfaces."""
        # Check if VRF is referenced in IKEv2 profiles
        for profile_block in self.parser.ikev2_profile:
            for line in profile_block:
                if 'match fvrf' in line and vrf_name in line:
                    profile_name = profile_block[0].strip().split()[3]
                    
                    # Add the profile
                    vrf_data['ikev2']['profile'].append(profile_block)
                    
                    # Extract keyring
                    for profile_line in profile_block:
                        if 'keyring local' in profile_line:
                            keyring_name = profile_line.strip().split()[2]
                            for keyring_block in self.parser.ikev2_keyring:
                                if keyring_block[0].strip().split()[3] == keyring_name:
                                    vrf_data['ikev2']['keyring'].append(keyring_block)
                                    break
                    
                    # Extract policy via match address local
                    for profile_line in profile_block:
                        if 'match address local' in profile_line:
                            local_addr = profile_line.strip().split()[2]
                            # Find policy with matching local address
                            for policy_block in self.parser.ikev2_policy:
                                policy_name = policy_block[0].strip().split()[3]
                                for policy_line in policy_block:
                                    if 'match address local' in policy_line and local_addr in policy_line:
                                        vrf_data['ikev2']['policy'].append(policy_block)
                                        
                                        # Extract proposals from policy
                                        for policy_line2 in policy_block:
                                            if 'proposal' in policy_line2 and not policy_line2.strip().startswith('!'):
                                                parts = policy_line2.strip().split()
                                                for i in range(1, len(parts)):
                                                    if parts[i] != 'proposal':
                                                        proposal_name = parts[i]
                                                        for proposal_block in self.parser.ikev2_proposal:
                                                            if proposal_block[0].strip().split()[3] == proposal_name:
                                                                vrf_data['ikev2']['proposal'].append(proposal_block)
                                        break


    def extract_vrf_crypto_config(self, vrf_data, config_lines, vrf_name):
        """Extract crypto config for VRF based on tunnel interfaces"""
        vrf_profiles = {t['ipsec_profile'] for t in vrf_data['tunnel_interfaces']}
        
        ikev2_profiles = set()
        for profile_block in self.parser.ipsec_profile:
            profile_name = profile_block[0].strip().split()[3]
            if profile_name in vrf_profiles:
                for line in profile_block:
                    if 'set ikev2-profile' in line:
                        ikev2_profiles.add(line.strip().split()[2])
        
        vrf_data['ipsec']['profile'] = [
            p for p in self.parser.ipsec_profile 
            if p[0].strip().split()[3] in vrf_profiles
        ]
        
        vrf_data['ikev2']['profile'] = [
            p for p in self.parser.ikev2_profile 
            if p[0].strip().split()[3] in ikev2_profiles
        ]
        
        keyring_names = set()
        profile_local_address = None
        profile_fvrf = None
        
        # Extract keyring and identity info from profiles
        for profile_block in vrf_data['ikev2']['profile']:
            for line in profile_block:
                line_stripped = line.strip()
                if 'keyring local' in line_stripped:
                    keyring_names.add(line_stripped.split()[2])
                elif 'identity local address' in line_stripped:
                    profile_local_address = line_stripped.split()[3]
                elif 'match fvrf' in line_stripped:
                    profile_fvrf = line_stripped.split()[2]
        
        vrf_data['ikev2']['keyring'] = [
            k for k in self.parser.ikev2_keyring 
            if k[0].strip().split()[3] in keyring_names
        ]
        
        # Find matching IKEv2 policies
        matching_policies = []
        proposal_names = set()
        
        for policy_block in self.parser.ikev2_policy:
            policy_name = policy_block[0].strip().split()[3]
            policy_local_addr = None
            policy_fvrf = None
            
            # Extract info from policy
            for line in policy_block:
                line_stripped = line.strip()
                if 'match address local' in line_stripped:
                    try:
                        policy_local_addr = line_stripped.split()[3]
                    except IndexError:
                        pass
                elif 'match fvrf' in line_stripped:
                    try:
                        policy_fvrf = line_stripped.split()[2]
                    except IndexError:
                        pass
            
            # Check for match
            match_found = False
            
            # Match by local address (most common)
            if policy_local_addr and profile_local_address:
                # Compare IPs (handle with/without subnet mask)
                profile_ip = profile_local_address.split('/')[0] if '/' in profile_local_address else profile_local_address
                policy_ip = policy_local_addr.split('/')[0] if '/' in policy_local_addr else policy_local_addr
                
                if profile_ip == policy_ip:
                    match_found = True
            
            # Match by fvrf (secondary)
            if not match_found and policy_fvrf and profile_fvrf and policy_fvrf == profile_fvrf:
                match_found = True
            
            if match_found:
                matching_policies.append(policy_block)
                
                # Extract proposal from this policy
                for line in policy_block:
                    if 'proposal ' in line and not line.strip().startswith('!'):
                        parts = line.strip().split()
                        for i in range(1, len(parts)):
                            if parts[i] != 'proposal':
                                proposal_names.add(parts[i])
        
        # Add matching policies
        vrf_data['ikev2']['policy'] = matching_policies
        
        # Get the actual proposal blocks
        vrf_data['ikev2']['proposal'] = [
            p for p in self.parser.ikev2_proposal 
            if p[0].strip().split()[3] in proposal_names
        ]
        
        # If no proposals found but we have policies, use all available proposals
        if not vrf_data['ikev2']['proposal'] and matching_policies:
            vrf_data['ikev2']['proposal'] = self.parser.ikev2_proposal
        
        # Get transform sets
        transform_names = set()
        for profile_block in vrf_data['ipsec']['profile']:
            for line in profile_block:
                if 'set transform-set' in line:
                    transform_names.update(line.strip().split()[2:])
        
        vrf_data['ipsec']['transform_set'] = [
            t for t in self.parser.ipsec_transform_set 
            if t[0].strip().split()[3] in transform_names
        ]
        
        # Debug logging
        self.parser.log(f"VRF {vrf_name}:", debug_level=True)
        self.parser.log(f"  Profile local address: {profile_local_address}", debug_level=True)
        self.parser.log(f"  Profile FVRF: {profile_fvrf}", debug_level=True)
        self.parser.log(f"  Found {len(matching_policies)} matching policies", debug_level=True)
        self.parser.log(f"  Found {len(vrf_data['ikev2']['proposal'])} proposals", debug_level=True)
    

    def _add_shared_crypto_configs(self, vrf_data):
        """Add shared crypto configurations that might be used by multiple VRFs."""
        # Check for commonly shared configurations
        if not vrf_data['ikev2']['policy'] and self.parser.ikev2_policy:
            # Add default policies if none found
            for policy in self.parser.ikev2_policy:
                if 'default' in policy[0].lower():
                    vrf_data['ikev2']['policy'].append(policy)
        
        if not vrf_data['ikev2']['proposal'] and self.parser.ikev2_proposal:
            # Add default proposals if none found
            for proposal in self.parser.ikev2_proposal:
                if 'default' in proposal[0].lower():
                    vrf_data['ikev2']['proposal'].append(proposal)
        
        # Check for transform-sets that might be shared
        if not vrf_data['ipsec']['transform_set'] and self.parser.ipsec_transform_set:
            # Add commonly used transform sets
            common_sets = ['ESP-AES-256-SHA', 'ESP-AES-128-SHA', 'ESP-3DES-SHA']
            for ts in self.parser.ipsec_transform_set:
                ts_name = ts[0].strip().split()[3]
                if any(common in ts_name for common in common_sets):
                    vrf_data['ipsec']['transform_set'].append(ts)


    def generate_all_vrf_summaries(self):
        """Generate summaries for all VRFs"""
        summaries = []
        
        for vrf_name, vrf_data in self.parser.vrfs.items():
            summary = {
                'vrf_name': vrf_name,
                'tunnel_interfaces': 0,
                'has_outside_nat': False,
                'has_inside_nat': False,
                'has_dynamic_nat': False,
                'acl_count': 0,
                'site_role': vrf_data.get('site_role', 'Unknown'),
                'interface_count': 0,
                'static_route_count': len(vrf_data.get('static_routes', [])),
                'bgp_configured': len(vrf_data.get('bgp', [])) > 0,
                'ipsec_profiles': len(vrf_data.get('ipsec', {}).get('profile', [])),
                'total_nat_rules': 0
            }
            
            # Count tunnel interfaces and total interfaces
            for interface_block in vrf_data.get('interfaces', []):
                if interface_block:
                    summary['interface_count'] += 1
                    if 'Tunnel' in interface_block[0]:
                        summary['tunnel_interfaces'] += 1
            
            # Check NAT types and count rules
            nat_inside = len(vrf_data.get('nat', []))
            nat_outside = len(vrf_data.get('nat_outside', []))
            nat_dynamic = len(vrf_data.get('nat_inside_dynamic', [])) + len(vrf_data.get('nat_inside_dynamic2', []))
            
            summary['has_inside_nat'] = nat_inside > 0
            summary['has_outside_nat'] = nat_outside > 0
            summary['has_dynamic_nat'] = nat_dynamic > 0
            summary['total_nat_rules'] = nat_inside + nat_outside + nat_dynamic
            
            # Count ACLs
            summary['acl_count'] = len(vrf_data.get('acls', {})) + len(vrf_data.get('ext_acls', {}))
            
            # Add migration complexity score (simple heuristic)
            complexity_score = 0
            if summary['tunnel_interfaces'] > 0:
                complexity_score += 2
            if summary['bgp_configured']:
                complexity_score += 2
            if summary['total_nat_rules'] > 0:
                complexity_score += 1
            if summary['acl_count'] > 0:
                complexity_score += 1
                
            summary['migration_complexity'] = complexity_score
            
            summaries.append(summary)
        
        return sorted(summaries, key=lambda x: x['vrf_name'])
