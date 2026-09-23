#!/usr/bin/env python3
"""
Simple Multi-Device VRF Analysis - Uses Existing Connections
No threading issues - just reuses connections from main GUI
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import csv
from datetime import datetime


class SimpleMultiDeviceAnalysis:
    """Multi-device VRF analysis using existing connections - no threading issues"""
    
    def __init__(self, gui):
        self.gui = gui
        self.device_connections = {}  # {device_name: connection}
        
    def create_multi_device_tab(self):
        """Create improved multi-device analysis tab with better layout"""
        md_frame = ttk.Frame(self.gui.notebook)
        self.gui.notebook.add(md_frame, text="Multi-Device VRF Analysis")
        
        # Use PanedWindow for resizable sections
        main_paned = ttk.PanedWindow(md_frame, orient=tk.VERTICAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # ===== TOP SECTION: Device Management (side by side) =====
        top_section = ttk.Frame(main_paned)
        main_paned.add(top_section, weight=1)
        
        # Use another PanedWindow for side-by-side layout
        device_paned = ttk.PanedWindow(top_section, orient=tk.HORIZONTAL)
        device_paned.pack(fill=tk.BOTH, expand=True)
        
        # LEFT: Available Devices
        left_frame = ttk.LabelFrame(device_paned, text="Available Devices", padding=10)
        device_paned.add(left_frame, weight=1)
        
        # Search/filter
        search_frame = ttk.Frame(left_frame)
        search_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(search_frame, text="Filter:").pack(side=tk.LEFT, padx=(0, 5))
        self.device_filter = ttk.Entry(search_frame)
        self.device_filter.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.device_filter.bind('<KeyRelease>', lambda e: self.filter_devices())
        
        # Device listbox
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.device_listbox = tk.Listbox(list_frame, selectmode=tk.MULTIPLE)
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.device_listbox.yview)
        self.device_listbox.configure(yscrollcommand=scroll.set)
        
        self.device_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Populate devices
        if hasattr(self.gui, 'parser') and self.gui.parser:
            for device_name in sorted(self.gui.parser.devices.keys()):
                self.device_listbox.insert(tk.END, device_name)
        
        # Buttons
        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Button(btn_frame, text="🔌 Connect Selected", 
                  command=self.connect_selected_devices).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="🔄 Refresh List", 
                  command=self.refresh_device_list).pack(fill=tk.X, pady=2)
        
        self.avail_status = ttk.Label(left_frame, text=f"{self.device_listbox.size()} devices available")
        self.avail_status.pack(anchor=tk.W, pady=(5, 0))
        
        # RIGHT: Connected Devices
        right_frame = ttk.LabelFrame(device_paned, text="Connected Devices", padding=10)
        device_paned.add(right_frame, weight=1)
        
        # Connected devices tree with VPN status
        columns = ('device', 'status', 'vrfs', 'vpn_up', 'vpn_down')
        self.connected_tree = ttk.Treeview(right_frame, columns=columns, show='headings')
        
        self.connected_tree.heading('device', text='Device')
        self.connected_tree.heading('status', text='Status')
        self.connected_tree.heading('vrfs', text='VRFs')
        self.connected_tree.heading('vpn_up', text='VPN Up')
        self.connected_tree.heading('vpn_down', text='VPN Down')
        
        self.connected_tree.column('device', width=180)
        self.connected_tree.column('status', width=100)
        self.connected_tree.column('vrfs', width=60)
        self.connected_tree.column('vpn_up', width=80)
        self.connected_tree.column('vpn_down', width=80)
        
        conn_scroll = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.connected_tree.yview)
        self.connected_tree.configure(yscrollcommand=conn_scroll.set)
        
        self.connected_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        conn_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Color tags
        self.connected_tree.tag_configure('connected', foreground='#28a745')
        self.connected_tree.tag_configure('analyzing', foreground='#ffc107')
        self.connected_tree.tag_configure('error', foreground='#dc3545')
        
        # Connected device buttons
        conn_btn_frame = ttk.Frame(right_frame)
        conn_btn_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Button(conn_btn_frame, text="📊 Analyze All", 
                  command=self.analyze_connected_devices).pack(fill=tk.X, pady=2)
        ttk.Button(conn_btn_frame, text="🔄 Refresh VPN Status", 
                  command=self.refresh_vpn_status).pack(fill=tk.X, pady=2)
        ttk.Button(conn_btn_frame, text="❌ Disconnect All", 
                  command=self.disconnect_all).pack(fill=tk.X, pady=2)
        
        self.conn_status = ttk.Label(right_frame, text="0 devices connected")
        self.conn_status.pack(anchor=tk.W, pady=(5, 0))
        
        # ===== BOTTOM SECTION: VRF Analysis Results (LARGE) =====
        bottom_section = ttk.LabelFrame(main_paned, text="VRF Analysis Results", padding=10)
        main_paned.add(bottom_section, weight=3)  # 3x larger than top
        
        # Results tree
        result_cols = ('device', 'config_date', 'vrf_name', 'site_role', 'tunnels', 'interfaces', 
                      'inside_nat', 'outside_nat', 'bgp', 'static_routes', 'complexity',
                      'vpn_status', 'peer_ip', 'uptime', 'description')
        self.results_tree = ttk.Treeview(bottom_section, columns=result_cols, show='headings')
        
        self.results_tree.heading('device', text='Device')
        self.results_tree.heading('config_date', text='Config Date')
        self.results_tree.heading('vrf_name', text='VRF')
        self.results_tree.heading('site_role', text='Site')
        self.results_tree.heading('tunnels', text='Tunnels')
        self.results_tree.heading('interfaces', text='Ifaces')
        self.results_tree.heading('inside_nat', text='Inside NAT')
        self.results_tree.heading('outside_nat', text='Outside NAT')
        self.results_tree.heading('bgp', text='BGP')
        self.results_tree.heading('static_routes', text='Routes')
        self.results_tree.heading('complexity', text='Complexity')
        self.results_tree.heading('vpn_status', text='VPN Status')
        self.results_tree.heading('peer_ip', text='Peer IP')
        self.results_tree.heading('uptime', text='Uptime')
        self.results_tree.heading('description', text='Description')
        
        # Column widths
        self.results_tree.column('device', width=150)
        self.results_tree.column('config_date', width=150)
        self.results_tree.column('vrf_name', width=180)
        self.results_tree.column('site_role', width=80)
        self.results_tree.column('tunnels', width=70)
        self.results_tree.column('interfaces', width=70)
        self.results_tree.column('inside_nat', width=90)
        self.results_tree.column('outside_nat', width=90)
        self.results_tree.column('bgp', width=60)
        self.results_tree.column('static_routes', width=70)
        self.results_tree.column('complexity', width=90)
        self.results_tree.column('vpn_status', width=120)
        self.results_tree.column('peer_ip', width=120)
        self.results_tree.column('uptime', width=100)
        self.results_tree.column('description', width=300)
        
        # Scrollbars
        results_scroll_y = ttk.Scrollbar(bottom_section, orient=tk.VERTICAL, command=self.results_tree.yview)
        results_scroll_x = ttk.Scrollbar(bottom_section, orient=tk.HORIZONTAL, command=self.results_tree.xview)
        self.results_tree.configure(yscrollcommand=results_scroll_y.set, xscrollcommand=results_scroll_x.set)
        
        self.results_tree.grid(row=0, column=0, sticky='nsew')
        results_scroll_y.grid(row=0, column=1, sticky='ns')
        results_scroll_x.grid(row=1, column=0, sticky='ew')
        
        bottom_section.grid_rowconfigure(0, weight=1)
        bottom_section.grid_columnconfigure(0, weight=1)
        
        # Color tags for results
        self.results_tree.tag_configure('success', foreground='#28a745')
        self.results_tree.tag_configure('error', foreground='#dc3545')
        self.results_tree.tag_configure('vpn_up', foreground='#28a745')
        self.results_tree.tag_configure('vpn_down', foreground='#dc3545')
        
        # Export and summary frame
        bottom_controls = ttk.Frame(bottom_section)
        bottom_controls.grid(row=2, column=0, columnspan=2, pady=5, sticky='ew')
        
        # Export buttons
        ttk.Button(bottom_controls, text="Export CSV", command=self.export_csv).pack(side=tk.LEFT, padx=2)
        ttk.Button(bottom_controls, text="Export JSON", command=self.export_json).pack(side=tk.LEFT, padx=2)
        ttk.Button(bottom_controls, text="Clear Results", command=self.clear_results).pack(side=tk.LEFT, padx=2)
        
        # Summary
        self.summary_label = ttk.Label(bottom_controls, text="No results yet")
        self.summary_label.pack(side=tk.RIGHT, padx=10)
    
    def filter_devices(self):
        """Filter device list based on search text"""
        search_text = self.device_filter.get().lower()
        self.device_listbox.delete(0, tk.END)
        
        if hasattr(self.gui, 'parser') and self.gui.parser:
            filtered = [d for d in sorted(self.gui.parser.devices.keys()) 
                       if search_text in d.lower()]
            for device_name in filtered:
                self.device_listbox.insert(tk.END, device_name)
        
        self.avail_status.config(text=f"{self.device_listbox.size()} devices shown")
    
    def refresh_device_list(self):
        """Refresh the device list"""
        self.device_listbox.delete(0, tk.END)
        if hasattr(self.gui, 'parser') and self.gui.parser:
            for device_name in sorted(self.gui.parser.devices.keys()):
                self.device_listbox.insert(tk.END, device_name)
            self.gui.log_message(f"Refreshed device list: {self.device_listbox.size()} devices")
    
    def connect_selected_devices(self):
        """Connect to selected devices"""
        selected_indices = self.device_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("No Selection", "Please select devices to connect")
            return
        
        devices = [self.device_listbox.get(i) for i in selected_indices]
        self.gui.log_message(f"=== Connecting to {len(devices)} devices ===")
        
        for device_name in devices:
            try:
                self.gui.log_message(f"Connecting to {device_name}...")
                
                # Use parser's connection method (runs on main thread - no issues!)
                connection = self.gui.parser.connect_via_jumphost(device_name)
                
                if connection:
                    self.device_connections[device_name] = connection
                    self.gui.log_message(f"✓ {device_name} connected")
                    
                    # Update connected tree with initial status
                    self.connected_tree.insert('', 'end', 
                                              values=(device_name, 'Connected', '-', '-', '-'),
                                              tags=('connected',))
                else:
                    self.gui.log_message(f"✗ {device_name} failed to connect")
                    
            except Exception as e:
                self.gui.log_message(f"✗ {device_name}: {str(e)}")
        
        self.update_connection_status()
        self.gui.log_message(f"=== Connection complete: {len(self.device_connections)} devices connected ===")
    
    def refresh_vpn_status(self):
        """Refresh VPN status for all connected devices"""
        if not self.device_connections:
            messagebox.showwarning("No Connections", "No devices connected")
            return
        
        self.gui.log_message("=== Refreshing VPN status ===")
        
        for device_name, connection in self.device_connections.items():
            try:
                # Get VPN status
                vpn_output = connection.send_command("show crypto session brief", read_timeout=30)
                
                # Parse VPN status - check last column for UA/U or D
                vpn_up = 0
                vpn_down = 0
                for line in vpn_output.splitlines():
                    if line.strip() and not line.startswith(('Status:', 'Peer', 'ivrf', '===', ' ')):
                        parts = line.split()
                        if len(parts) > 0:
                            status_col = parts[-1]
                            if 'UA' in status_col or 'U' in status_col:
                                vpn_up += 1
                            elif 'D' in status_col:
                                vpn_down += 1
                
                # Update connected tree
                for item in self.connected_tree.get_children():
                    if self.connected_tree.item(item)['values'][0] == device_name:
                        current = self.connected_tree.item(item)['values']
                        self.connected_tree.item(item, values=(
                            device_name, current[1], current[2], vpn_up, vpn_down
                        ))
                        break
                
                self.gui.log_message(f"  {device_name}: {vpn_up} UP, {vpn_down} DOWN")
                
            except Exception as e:
                self.gui.log_message(f"✗ {device_name} VPN status error: {str(e)}")
        
        self.gui.log_message("=== VPN status refresh complete ===")
    
    def disconnect_all(self):
        """Disconnect all devices"""
        for device_name, connection in list(self.device_connections.items()):
            try:
                connection.disconnect()
                self.gui.log_message(f"Disconnected {device_name}")
            except:
                pass
        
        self.device_connections.clear()
        self.connected_tree.delete(*self.connected_tree.get_children())
        self.update_connection_status()
    
    def update_connection_status(self):
        """Update connection status label"""
        count = len(self.device_connections)
        self.conn_status.config(text=f"{count} device{'s' if count != 1 else ''} connected")
    
    def analyze_connected_devices(self):
        """Analyze all connected devices - NO THREADING ISSUES!"""
        if not self.device_connections:
            messagebox.showwarning("No Connections", "Please connect to devices first")
            return
        
        self.gui.log_message(f"=== Analyzing {len(self.device_connections)} devices ===")
        self.results_tree.delete(*self.results_tree.get_children())
        
        total_vrfs = 0
        
        for device_name, connection in self.device_connections.items():
            try:
                self.gui.log_message(f"Analyzing {device_name}...")
                
                # Fetch config (on main thread - works!)
                config = connection.send_command("show running-config", delay_factor=2, max_loops=3000)
                config_lines = config.splitlines()
                
                self.gui.log_message(f"  {device_name}: Received {len(config_lines)} lines")
                
                # Parse config
                temp_parser = type(self.gui.parser)()
                temp_parser.devices = self.gui.parser.devices
                temp_parser.parse_configuration(config_lines, preview_only=False, device_name=device_name)
                
                # Get VRFs
                vrfs_dict = {}
                if hasattr(temp_parser, 'config_parser') and hasattr(temp_parser.config_parser, 'vrfs'):
                    vrfs_dict = temp_parser.config_parser.vrfs
                elif hasattr(temp_parser, 'vrfs'):
                    vrfs_dict = temp_parser.vrfs
                
                vrf_count = len(vrfs_dict)
                self.gui.log_message(f"  {device_name}: Found {vrf_count} total VRFs")
                
                # Get config last modified date
                config_date = 'Unknown'
                try:
                    # Try method 1: show version
                    version_output = connection.send_command("show version", read_timeout=10)
                    for line in version_output.splitlines():
                        if 'Configuration last modified' in line or 'Last configuration change' in line:
                            # Extract date - usually after "at" or after "modified by"
                            if ' at ' in line:
                                config_date = line.split(' at ')[-1].strip()
                            elif ' by ' in line:
                                parts = line.split(' by ')
                                if len(parts) > 1:
                                    config_date = parts[0].split('modified')[-1].strip()
                            break
                    
                    # If still unknown, try method 2: show running-config header
                    if config_date == 'Unknown':
                        config_header = connection.send_command("show running-config | include Last config", read_timeout=10)
                        if config_header:
                            for line in config_header.splitlines():
                                if 'Last configuration change' in line:
                                    config_date = line.split('change at')[-1].strip() if 'at' in line else line.split('change')[-1].strip()
                                    break
                    
                    self.gui.log_message(f"  {device_name}: Config date = {config_date}")
                    
                except Exception as e:
                    self.gui.log_message(f"  {device_name}: Could not get config date: {str(e)}")
                    config_date = 'Unknown'
                
                # Update connected tree with VRF count and config date
                for item in self.connected_tree.get_children():
                    if self.connected_tree.item(item)['values'][0] == device_name:
                        current = self.connected_tree.item(item)['values']
                        # Keep VPN status if already there, otherwise show dash
                        vpn_up = current[3] if len(current) > 3 else '-'
                        vpn_down = current[4] if len(current) > 4 else '-'
                        self.connected_tree.item(item, values=(
                            device_name, 'Analyzed', vrf_count, vpn_up, vpn_down
                        ), tags=('connected',))
                        break
                
                # Extract VRF summaries (filter out MGMT-intf and VTI-extranet - case insensitive)
                excluded_vrfs = ['mgmt-intf', 'vti-extranet']
                
                vrfs_analyzed = 0
                for vrf_name, vrf_data in vrfs_dict.items():
                    # Skip excluded VRFs (case-insensitive check)
                    if vrf_name.lower() in excluded_vrfs:
                        self.gui.log_message(f"  {device_name}: Skipping excluded VRF: {vrf_name}")
                        continue
                    
                    # Debug: show interfaces for this VRF
                    interfaces = vrf_data.get('interfaces', [])
                    self.gui.log_message(f"  {device_name}/{vrf_name}: Interfaces = {interfaces}")

                    total_interfaces = len(interfaces)

                    tunnel_count = sum(
                        1 for iface in interfaces
                        if isinstance(iface, list)
                        and iface
                        and iface[0].startswith(('interface Tunnel', 'Tu'))
                    )
                          
                    self.gui.log_message(
                        f"  {device_name}/{vrf_name}: Total interfaces = {total_interfaces}, "
                        f"Tunnel interfaces = {tunnel_count}"
                    )

                    
                    # Count tunnels (check for Tunnel or Tu prefix)
                    #tunnel_count = sum(1 for iface in interfaces if iface.startswith('Tunnel') or iface.startswith('Tu'))
                    #tunnel_count = sum(1 for iface in interfaces if iface and iface[1].startswith(('Tunnel', 'Tu')))
                    #self.gui.log_message(f"  {device_name}/{vrf_name}: Found {tunnel_count} tunnels")
                    
                    has_inside_nat = 'Yes' if vrf_data.get('nat') else 'No'
                    has_outside_nat = 'Yes' if vrf_data.get('nat_outside') else 'No'
                    bgp = 'Yes' if vrf_data.get('bgp') else 'No'
                    static_routes = len(vrf_data.get('static_routes', []))
                    
                    # Complexity
                    complexity_score = tunnel_count * 2 + static_routes * 0.5
                    complexity = 'Low' if complexity_score < 10 else ('Medium' if complexity_score < 30 else 'High')
                    
                    # VPN status for this VRF's tunnels (returns dict with status, peer, uptime)
                    vpn_info = self.get_vpn_status_for_vrf(device_name, connection, vrf_data)
                    
                    # Determine row tag based on VPN status
                    row_tag = 'success' if 'UP' in vpn_info['status'] else 'error' if 'DOWN' in vpn_info['status'] else 'success'
                    
                    self.results_tree.insert('', 'end', values=(
                        device_name,
                        config_date,
                        vrf_name,
                        vrf_data.get('site_role', 'Unknown'),
                        tunnel_count,
                        len(interfaces),
                        has_inside_nat,
                        has_outside_nat,
                        bgp,
                        static_routes,
                        complexity,
                        vpn_info['status'],
                        vpn_info['peer_ip'],
                        vpn_info['uptime'],
                        vpn_info['description']
                    ), tags=(row_tag,))
                    
                    vrfs_analyzed += 1
                    total_vrfs += 1
                
                self.gui.log_message(f"✓ {device_name}: {vrfs_analyzed} VRFs analyzed (excluded {vrf_count - vrfs_analyzed})")
                
                # Check for VPNs not assigned to any VRF
                try:
                    self.gui.log_message(f"  {device_name}: Checking for VPNs outside VRFs...")
                    
                    # Get all tunnel interfaces from all VRFs
                    vrf_tunnels = set()
                    for vrf_name, vrf_data in vrfs_dict.items():
                        interfaces = vrf_data.get('interfaces', [])
                        for iface in interfaces:
                            if isinstance(iface, list) and len(iface) > 0:
                                first_line = iface[0].strip()
                                if 'Tunnel' in first_line:
                                    parts = first_line.split()
                                    if len(parts) >= 2:
                                        tunnel_num = ''.join(filter(str.isdigit, parts[1]))
                                        if tunnel_num:
                                            vrf_tunnels.add(tunnel_num)
                    
                    # Get all VPNs from crypto session
                    vpn_output = connection.send_command("show crypto session brief", read_timeout=30)
                    
                    orphan_vpns = []
                    for line in vpn_output.splitlines():
                        if line.strip() and not line.startswith(('Status:', 'Peer', 'ivrf', '===', ' ')):
                            parts = line.split()
                            if len(parts) >= 2 and 'Tu' in parts[1]:
                                # Extract tunnel number
                                tunnel_num = ''.join(filter(str.isdigit, parts[1]))
                                if tunnel_num and tunnel_num not in vrf_tunnels:
                                    # This VPN is not in any VRF
                                    peer_ip = parts[0] if parts else '-'
                                    tunnel_name = parts[1] if len(parts) > 1 else '-'
                                    uptime = parts[-2] if len(parts) > 2 else '-'
                                    status = parts[-1] if parts else '-'
                                    
                                    status_text = 'UP' if 'UA' in status or 'U' in status else 'DOWN' if 'D' in status else 'Unknown'
                                    
                                    orphan_vpns.append({
                                        'tunnel': tunnel_name,
                                        'peer_ip': peer_ip,
                                        'uptime': uptime,
                                        'status': status_text
                                    })
                                    
                                    self.gui.log_message(f"  {device_name}: Found orphan VPN: {tunnel_name} ({peer_ip})")
                    
                    # Add orphan VPNs to results (need to get description from config)
                    for vpn in orphan_vpns:
                        # Try to get tunnel description from running config
                        try:
                            tunnel_desc_output = connection.send_command(f"show run interface {vpn['tunnel']}", read_timeout=10)
                            description = '-'
                            for line in tunnel_desc_output.splitlines():
                                if 'description' in line.lower():
                                    description = line.split('description', 1)[-1].strip()
                                    break
                        except:
                            description = '-'
                        
                        row_tag = 'success' if vpn['status'] == 'UP' else 'error'
                        self.results_tree.insert('', 'end', values=(
                            device_name,
                            config_date,
                            '** NO VRF **',
                            '-',
                            1,  # 1 tunnel
                            1,  # 1 interface
                            '-',
                            '-',
                            '-',
                            '-',
                            'Orphan',
                            vpn['status'],
                            vpn['peer_ip'],
                            vpn['uptime'],
                            description
                        ), tags=(row_tag,))
                        total_vrfs += 1
                    
                    if orphan_vpns:
                        self.gui.log_message(f"  {device_name}: Found {len(orphan_vpns)} orphan VPNs (not in any VRF)")
                
                except Exception as e:
                    self.gui.log_message(f"  {device_name}: Error checking orphan VPNs: {str(e)}")
                
            except Exception as e:
                self.gui.log_message(f"✗ {device_name}: {str(e)}")
                # Add error row
                self.results_tree.insert('', 'end', values=(
                    device_name, 'ERROR', str(e)[:50], '', '', '', '', '', '', ''
                ), tags=('error',))
        
        self.summary_label.config(text=f"Total: {len(self.device_connections)} devices, {total_vrfs} VRFs")
        self.gui.log_message(f"=== Analysis complete: {total_vrfs} VRFs from {len(self.device_connections)} devices ===")
    
    def is_tunnel_interface(self, iface_block):
        """
        Detects Tunnel interfaces inside parsed interface blocks.
        Works for long form (Tunnel1234) and short form (Tu1234).
        """
        if not iface_block or not isinstance(iface_block, list):
            return False
    
        first = iface_block[0].strip().lower()   # example: 'interface tunnel2340'
    
        if first.startswith("interface Tunnel"):
            return True
    
        # Short form: Tu1234
        if first.startswith("interface Tu"):
            return True
    
        return False

    def extract_tunnel_name(self, iface_block):
        """
        Extracts tunnel name from interface blocks.
        Supports both 'TunnelXXXX' and 'TuXXXX'.
        """
        if not iface_block or not isinstance(iface_block, list):
            return None
    
        first = iface_block[0].strip()     # 'interface Tunnel2340'
        parts = first.split()
    
        if len(parts) < 2 or parts[0].lower() != "interface":
            return None
    
        name = parts[1]
    
        # Normalize Tu1234 → Tunnel1234
        if name.lower().startswith("tu") and name[2:].isdigit():
            return f"Tunnel{name[2:]}"      # always return long form
    
        if name.lower().startswith("tunnel") and name[6:].isdigit():
            return name
    
        return None



    def get_vpn_status_for_vrf(self, device_name, connection, vrf_data):
        """Get VPN status for tunnels in this VRF"""
        try:
            # Extract tunnel names from interface list
            interfaces = vrf_data.get('interfaces', [])
            
            # Filter for tunnel interfaces only
            tunnel_interfaces = []
            tunnel_descriptions = {}
            
            for iface in interfaces:
                # Interfaces are lists of config lines, first line has interface name
                if isinstance(iface, list) and len(iface) > 0:
                    first_line = iface[0].strip()
                    # Check if it's a tunnel interface
                    if 'Tunnel' in first_line:
                        # Extract tunnel number from "interface Tunnel2340"
                        parts = first_line.split()
                        if len(parts) >= 2:
                            iface_name = parts[1]  # "Tunnel2340"
                            tunnel_num = ''.join(filter(str.isdigit, iface_name))
                            if tunnel_num:
                                tunnel_interfaces.append(tunnel_num)
                                
                                # Extract description from config lines
                                description = '-'
                                for line in iface:
                                    if 'description' in line.lower():
                                        description = line.split('description', 1)[-1].strip()
                                        break
                                tunnel_descriptions[tunnel_num] = description
                                
                                self.gui.log_message(f"  [{device_name}] Found tunnel: {iface_name} -> {tunnel_num}")
            
            if not tunnel_interfaces:
                return {'status': 'No Tunnels', 'peer_ip': '-', 'uptime': '-', 'description': '-'}
            
            self.gui.log_message(f"  [{device_name}] Checking VPN status for tunnels: {tunnel_interfaces}")
            
            # Get VPN session brief
            vpn_output = connection.send_command("show crypto session brief", read_timeout=30)
            
            up_count = 0
            down_count = 0
            peer_ips = []
            uptimes = []
            descriptions = []
            
            # Check each tunnel
            for tunnel_num in tunnel_interfaces:
                found = False
                # Look for lines with this tunnel number
                for line in vpn_output.splitlines():
                    # Check if tunnel number appears in this line
                    if f'Tu{tunnel_num}' in line or f'Tunnel{tunnel_num}' in line:
                        found = True
                        parts = line.split()
                        
                        # Extract peer IP (first column)
                        if len(parts) > 0:
                            peer_ips.append(parts[0])
                        
                        # Extract uptime (second to last column, before status)
                        if len(parts) > 1:
                            uptime = parts[-2] if len(parts) > 2 else '-'
                            uptimes.append(uptime)
                        
                        # Add description
                        descriptions.append(tunnel_descriptions.get(tunnel_num, '-'))
                        
                        # Status is last column
                        status_col = parts[-1] if parts else ''
                        if 'UA' in status_col or 'U' in status_col:
                            up_count += 1
                            self.gui.log_message(f"  [{device_name}] Tunnel{tunnel_num}: UP (peer={parts[0] if parts else '?'})")
                        elif 'D' in status_col:
                            down_count += 1
                            self.gui.log_message(f"  [{device_name}] Tunnel{tunnel_num}: DOWN")
                        break
                
                if not found:
                    self.gui.log_message(f"  [{device_name}] Tunnel{tunnel_num}: Not found in crypto output")
            
            # Build status string
            if up_count > 0 and down_count == 0:
                status = f"All UP ({up_count})"
            elif down_count > 0 and up_count == 0:
                status = f"All DOWN ({down_count})"
            elif up_count > 0 and down_count > 0:
                status = f"{up_count} UP, {down_count} DOWN"
            else:
                status = f"Unknown ({len(tunnel_interfaces)} tunnels)"
            
            # Format peer IPs, uptimes, and descriptions
            peer_ip_str = ', '.join(peer_ips) if peer_ips else '-'
            uptime_str = ', '.join(uptimes) if uptimes else '-'
            description_str = ' | '.join(descriptions) if descriptions else '-'
            
            return {
                'status': status,
                'peer_ip': peer_ip_str,
                'uptime': uptime_str,
                'description': description_str
            }
        
        except Exception as e:
            self.gui.log_message(f"  [{device_name}] VPN status error: {str(e)}")
            return {'status': f'Error: {str(e)[:20]}', 'peer_ip': '-', 'uptime': '-', 'description': '-'}



#    def get_vpn_status_for_vrf(self, device_name, connection, vrf_data):
#        """Get VPN status for tunnels in this VRF"""
#        try:
#            # Get tunnel interfaces for this VRF
######test code
#            interfaces = vrf_data.get('interfaces', [])
#            tunnels = ( iface for iface in interfaces 
#                        if isinstance(iface, list)
#                        and iface
#                        and iface[0].startswith(('interface Tunnel', 'Tu')) )
######test code end
#
#            #tunnels = [iface for iface in vrf_data.get('interfaces', []) if 'Tunnel' in iface]
#            
#            if not tunnels:
#                return 'No Tunnels'
#            
#            # Get VPN status
#            vpn_output = connection.send_command("show crypto session brief", read_timeout=30)
#            
#            up_count = 0
#            down_count = 0
#            
#            # Check status for each tunnel
#            for tunnel in tunnels:
#                # Extract tunnel number (e.g., "Tunnel100" -> "100")
#                tunnel_num = ''.join(filter(str.isdigit, tunnel))
#                
#                # Look for this tunnel in VPN output
#                for line in vpn_output.splitlines():
#                    if tunnel_num in line:
#                        if 'UP-ACTIVE' in line or 'UP-IDLE' in line:
#                            up_count += 1
#                        elif 'DOWN' in line:
#                            down_count += 1
#                        break
#            
#            # Return status summary
#            if up_count > 0 and down_count == 0:
#                return f'All UP ({up_count})'
#            elif down_count > 0 and up_count == 0:
#                return f'All DOWN ({down_count})'
#            elif up_count > 0 and down_count > 0:
#                return f'{up_count} UP, {down_count} DOWN'
#            else:
#                return 'Unknown'
#                
#        except Exception as e:
#            return f'Error: {str(e)[:20]}'
    
    def export_csv(self):
        """Export results to CSV"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not filename:
            return
        
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Device', 'Config Date', 'VRF', 'Site', 'Tunnels', 'Interfaces', 
                           'Inside NAT', 'Outside NAT', 'BGP', 'Static Routes', 'Complexity', 
                           'VPN Status', 'Peer IP', 'Uptime', 'Description'])
            
            for item in self.results_tree.get_children():
                writer.writerow(self.results_tree.item(item)['values'])
        
        self.gui.log_message(f"Exported to {filename}")
        messagebox.showinfo("Export Complete", f"Results exported to {filename}")
    
    def export_json(self):
        """Export results to JSON"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not filename:
            return
        
        results = []
        for item in self.results_tree.get_children():
            values = self.results_tree.item(item)['values']
            results.append({
                'device': values[0],
                'config_date': values[1],
                'vrf': values[2],
                'site_role': values[3],
                'tunnels': values[4],
                'interfaces': values[5],
                'inside_nat': values[6],
                'outside_nat': values[7],
                'bgp': values[8],
                'static_routes': values[9],
                'complexity': values[10],
                'vpn_status': values[11],
                'peer_ip': values[12],
                'uptime': values[13],
                'description': values[14]
            })
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        
        self.gui.log_message(f"Exported to {filename}")
        messagebox.showinfo("Export Complete", f"Results exported to {filename}")
    
    def clear_results(self):
        """Clear results"""
        self.results_tree.delete(*self.results_tree.get_children())
        self.summary_label.config(text="No results yet")
        self.gui.log_message("Results cleared")