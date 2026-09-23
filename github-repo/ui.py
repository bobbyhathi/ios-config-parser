"""
RouterConfigParserUI: the Tkinter front-end. Which optional tabs (VPN
Status, BGP Status, VPN Traffic Flow, VRF Summary, Command Executor,
Multi-Device Analysis) are built is driven by tab_registry.py + settings.py
so the app can be run as a lighter-weight tool with only the tabs a given
user wants. The Log and Cisco IOS VRF Preview tabs are always present.
"""
import csv
import json
import os
import threading
from datetime import datetime
from threading import Thread
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from router_config_parser import RouterConfigParser
from settings import load_settings
from tab_registry import TAB_REGISTRY, TAB_ORDER


class RouterConfigParserUI:

    def __init__(self, root):
        self.root = root
        self.root.title("Router Configuration Parser")
        self.root.geometry("1400x1200")
        self._build_menu_bar()
        self.wants_settings = False  # set True by _change_settings(); main.py checks this

        # Variables
        self.input_source = tk.StringVar(value="device")  # "device" or "file"
        self.input_file = tk.StringVar()
        self.config_file = tk.StringVar(value="devices.json")
        self.output_dir = tk.StringVar()
        self.status_text = tk.StringVar(value="Ready")
        self.progress_value = tk.IntVar(value=0)
        self.selected_vrf = tk.StringVar()
        self.selected_device = tk.StringVar()
        self.debug_mode = tk.BooleanVar(value=False)
        #self.connection_manager = DeviceConnectionManager(gui_callback=self.log_message)

        # Parse instance
        self.parser = None
        self.last_config = None
        
        # Setup UI
        self.create_widgets()
        self.load_device_config()

        # Add debug mode trace
        self.debug_mode.trace_add('write', self._on_debug_mode_changed)

    def _on_debug_mode_changed(self, *args):
        """Update debug mode when checkbox changes"""
        self.update_debug_mode()

    def update_debug_mode(self):
        """Update debug mode for the parser"""
        if hasattr(self, 'parser') and self.parser:
            self.parser.debug_mode = self.debug_mode.get()
            self.parser.config_parser.debug_mode = self.debug_mode.get()
            self.log_message(f"Debug mode updated to: {self.debug_mode.get()}")
            
            # Test debug messages
            self.parser.log("=== DEBUG MODE TEST ===", debug_level=True)
            self.parser.log("This debug message should only appear when debug mode is ON", debug_level=True)
            self.parser.log("This regular message should always appear")

    def _build_menu_bar(self):
        """Top menu bar. Settings > Change Settings... closes this window and
        hands control back to the Settings window (settings_window.py) so
        tabs/source can be reconfigured -- see main.py's run loop."""
        menubar = tk.Menu(self.root)
        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Change Settings... (restart)", command=self._change_settings)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        self.root.config(menu=menubar)

    def _change_settings(self):
        """Close the main window and signal main.py to reopen the Settings
        window. main.py checks self.wants_settings after its mainloop() call
        returns (see the run loop in main.py)."""
        self.wants_settings = True
        self.root.destroy()

    def _current_device_name(self):
        """Best name for the currently loaded config, used in log messages
        and output filenames: the live device name, or the input file's
        name with its extension stripped (previously this kept the
        extension, producing filenames like "foo.txt-VRF_....txt")."""
        if self.input_source.get() == "device":
            return self.selected_device.get()
        return os.path.splitext(os.path.basename(self.input_file.get()))[0]

    def create_widgets(self):
        """Build the GUI interface"""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=False)
    

        main_frame2 = ttk.Frame(self.root, padding="10")
        main_frame2.pack(fill=tk.BOTH, expand=True)


        # Row 0: Config file selection
        #ttk.Label(main_frame, text="Devices Config File:").grid(row=0, column=0, sticky=tk.W)
        config_frame = ttk.LabelFrame(main_frame, text="Devices Config File:", padding=10)
        config_frame.grid(row=0, column=0, columnspan=6, sticky=tk.EW, pady=5)
        ttk.Entry(config_frame, textvariable=self.config_file, width=30).pack(side=tk.LEFT, fill=tk.X, expand=False)
        ttk.Button(config_frame, text="Browse", command=self.browse_config_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(config_frame, text="Reload", command=self.load_device_config).pack(side=tk.LEFT)
        ttk.Button(config_frame, text="⚙ Change Settings...", command=self._change_settings).pack(side=tk.RIGHT, padx=5)


        # Row 3: Device selection (only enabled when live device is selected)
        device_frame = ttk.LabelFrame(main_frame, text="Device:", padding=10)
        device_frame.grid(row=3, column=0, columnspan=6, sticky=tk.EW, pady=5)
        self.device_combo = ttk.Combobox(device_frame, textvariable=self.selected_device, width=28, state="readonly")
        self.device_combo.grid(row=4, column=0, sticky=tk.EW)#, padx=5
        ttk.Button(device_frame, text="Get Config", command=self.connect_to_device).grid(row=4, column=1, padx=5)
        ttk.Button(device_frame, text="Test Connection", command=self.test_device_connection).grid(row=4, column=2, padx=5)
        ttk.Button(device_frame, text="Disconnect", command=self.disconnect_device).grid(row=4, column=3, padx=5)


        # Row 7: VRF selection
        vrf_frame = ttk.LabelFrame(main_frame, text="VRF Selection:", padding=10)
        vrf_frame.grid(row=6, column=0, columnspan=6, sticky=tk.EW, pady=5)
        #ttk.Label(vrf_frame, text="VRF:").grid(row=0, column=0)
        self.vrf_combo = ttk.Combobox(vrf_frame, textvariable=self.selected_vrf, width=28, state="readonly")
        self.vrf_combo.grid(row=0, column=0, sticky=tk.EW) #, padx=5
        ttk.Button(vrf_frame, text="Cisco IOS Preview", command=self.preview_vrf).grid(row=0, column=2, padx=5)
        ttk.Checkbutton(vrf_frame, text="Debug Mode", variable=self.debug_mode).grid(row=0, column=5, padx=10)
    
    #    # Row 2: Input source selection
    #    input_frame = ttk.LabelFrame(main_frame, text="Configuration Source", padding=10)
    #    input_frame.grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=5)

    #    # Radio buttons for input source
    #    ttk.Radiobutton(input_frame, text="Live Device", variable=self.input_source, 
    #               value="device").grid(row=0, column=0, padx=5)
    #    ttk.Radiobutton(input_frame, text="Config File", variable=self.input_source, 
    #               value="file").grid(row=0, column=1, padx=5)
    
######## New 

        # Row 2: Input source selection
        input_frame = ttk.LabelFrame(main_frame, text="Configuration Source", padding=10)
        input_frame.grid(row=0, column=10, columnspan=3, sticky=tk.EW, pady=5)
        
        # Radio buttons for input source
        ttk.Radiobutton(input_frame, text="Live Device", variable=self.input_source, 
                   value="device").grid(row=0, column=0, padx=5)
        ttk.Radiobutton(input_frame, text="Config File", variable=self.input_source, 
                   value="file").grid(row=0, column=1, padx=5)

        # File input controls
        self.file_entry = ttk.Entry(input_frame, textvariable=self.input_file, width=40, state=tk.DISABLED)
        self.file_entry.grid(row=0, column=2, padx=5)
        self.browse_file_btn = ttk.Button(input_frame, text="Browse", command=self.browse_input_file, state=tk.DISABLED)
        self.browse_file_btn.grid(row=0, column=3)

############    
        


        
        # Row 5: Output directory
        dir_frame =ttk.LabelFrame(main_frame, text="Output directory:",padding=10)
        dir_frame.grid(row=3, column=10, columnspan=3, sticky=tk.EW)
        ttk.Entry(dir_frame, textvariable=self.output_dir, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(dir_frame, text="Browse", command=self.browse_output_dir).pack(side=tk.LEFT, padx=5)
        #ttk.Checkbutton(dir_frame, text="Debug Mode", variable=self.debug_mode).pack(side=tk.LEFT, padx=10)


        # Row 8: File Output
        output_frame = ttk.LabelFrame(main_frame, text="File Output:", padding=10)
        output_frame.grid(row=6, column=10, columnspan=3, sticky=tk.EW) #, pady=10)
        
        self.output_action = tk.StringVar()
        self.output_combo = ttk.Combobox(output_frame, textvariable=self.output_action, width=28, state="disabled",
                                         values=["Cisco IOS VRF Output", 
                                                 "Cisco IOS All VRF Output", 
                                                 "JSON VRF Output",
                                                 "JSON All VRF Output",
                                                 "Generate VPN Rollback"])
        self.output_combo.grid(row=0, column=0, padx=5)
        self.output_combo.set("Cisco IOS VRF Output") # Default value
        
        self.generate_output_button = ttk.Button(output_frame, text="Generate Output", command=self.run_output_action, state="disabled")
        self.generate_output_button.grid(row=0, column=1, padx=5)
        
        # Keep the rollback button
        #ttk.Button(output_frame, text="Generate VPN Rollback", command=self.generate_rollback).grid(row=0, column=2, padx=5)
        
        # Row 9: Progress and status -> I am unable to get this to work presently
        #ttk.Progressbar(main_frame, variable=self.progress_value, maximum=100).grid(row=14, column=0, columnspan=6, sticky=tk.EW)
        #ttk.Label(main_frame, textvariable=self.status_text).grid(row=15, column=0, columnspan=3, sticky=tk.W)
        

###############################

        status_row = ttk.Frame(main_frame)
        #status_row.pack(fill=tk.X, pady=(5, 0))

        status_row.grid(row=12, column=0, columnspan=2, sticky=tk.EW, pady=5)
        
        ttk.Label(status_row, text="Device:").pack(side=tk.LEFT, padx=(0, 5))
        self.status_label = ttk.Label(status_row, 
                                      text="Not connected - Select device and click 'Get Config'",
                                      foreground='red')
        self.status_label.pack(side=tk.LEFT)

################################

        # Row 11: Notebook for output
        notebook = ttk.Notebook(main_frame2)
        notebook.grid(row=0, column=0, columnspan=6, sticky=tk.NSEW) # 
    
        # Log tab
        log_frame = ttk.Frame(notebook)
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, state=tk.DISABLED)
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        notebook.add(log_frame, text="Log")
    
        # Preview tab
        preview_frame = ttk.Frame(notebook)
        self.preview_text = tk.Text(preview_frame, wrap=tk.WORD, state=tk.DISABLED, font=('Courier', 10))
        scroll_preview = ttk.Scrollbar(preview_frame, command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=scroll_preview.set)
        scroll_preview.pack(side=tk.RIGHT, fill=tk.Y)
        self.preview_text.pack(fill=tk.BOTH, expand=True)
        notebook.add(preview_frame, text="Cisco IOS VRF Preview")

        self.notebook = notebook

        # Build whichever optional tabs are enabled in settings.json (all of
        # them, by default). See tab_registry.py for what each one does.
        self.settings = load_settings()
        self.build_optional_tabs()

        # Configure grid weights
        main_frame2.columnconfigure(0, weight=1)
        main_frame2.rowconfigure(0, weight=1)

        # Set up trace for input source changes -- this is what enables the
        # file Browse controls when "Config File" is selected.
        self.input_source.trace_add('write', self.toggle_input_source)

    def build_optional_tabs(self):
        """(Re)build the optional tabs listed in self.settings['enabled_tabs'].

        Tabs are additive-only here: this is called once at startup, using
        whatever was chosen in the Settings window (settings_window.py)
        before this main window was built -- so there's no "restart to see
        your tab change" step, since the tab list is already final by the
        time this runs.
        """
        enabled = set(self.settings.get("enabled_tabs", TAB_ORDER))
        for tab_id in TAB_ORDER:
            if tab_id in enabled:
                TAB_REGISTRY[tab_id]["build"](self)

    def update_connection_status(self):
        """Update the connection status label."""
        device = self.selected_device.get()
        if device and hasattr(self, 'parser') and hasattr(self.parser, 'current_connection') and self.parser.current_connection:
            self.status_label.config(
                text=f"Connected to: {device}",
                foreground='green'
            )
        elif device:
            self.status_label.config(
                text=f"Device selected: {device} (Click 'Get Config' to connect)",
                foreground='orange'
            )
        else:
            self.status_label.config(
                text="Not connected - Select device and click 'Get Config'",
                foreground='red'
            )


    def _ensure_parser_exists(self):
        """Ensure parser exists with current debug mode settings"""
        if not hasattr(self, 'parser') or not self.parser:
            self.parser = RouterConfigParser(
                config_file=self.config_file.get(),
                output_dir=self.output_dir.get(),
                gui_callback=self.log_message,
                debug_mode=self.debug_mode.get()
            )
        else:
            # Update existing parser's debug mode
            self.parser.debug_mode = self.debug_mode.get()
            self.parser.config_parser.debug_mode = self.debug_mode.get()


    def test_device_connection(self):
        """Test device connection without retrieving full config"""
        device = self.selected_device.get()
        if not device:
            messagebox.showerror("Error", "No device selected")
            return
        
        self._ensure_parser_exists()
        self.log_message(f"Testing connection to {device}...")
    
        def test_connection_thread():
            try:
                success, message = self.parser.jumphost_connector.test_connection(device)
                if success:
                    self.root.after(0, lambda: self.log_message(f"✓ Connection test successful: {message}"))
                    self.root.after(0, lambda: messagebox.showinfo("Success", f"Connection test successful:\n{message}"))
                else:
                    self.root.after(0, lambda: self.log_message(f"✗ Connection test failed: {message}"))
                    self.root.after(0, lambda: messagebox.showerror("Error", f"Connection test failed:\n{message}"))
            except Exception as e:
                self.root.after(0, lambda: self.log_message(f"✗ Connection test error: {str(e)}"))
                self.root.after(0, lambda: messagebox.showerror("Error", f"Connection test error:\n{str(e)}"))
        
        Thread(target=test_connection_thread, daemon=True).start()    


#################Create TABS for VPN, BGP, status, summary etc

    def create_vpn_status_tab(self):
        """Create the VPN status monitoring tab"""
        vpn_frame = ttk.Frame(self.notebook)
        self.notebook.add(vpn_frame, text="VPN Status")
        
        # Treeview
        self.vpn_tree = ttk.Treeview(vpn_frame, columns=('vrf', 'peer', 'interface', 'status', 'uptime' , 'description'), show='headings')
        self.vpn_tree.heading('vrf', text='VRF')
        self.vpn_tree.heading('peer', text='Peer')
        self.vpn_tree.heading('interface', text='Interface')
        self.vpn_tree.heading('status', text='Status')
        self.vpn_tree.heading('uptime', text='Uptime')
        self.vpn_tree.heading('description', text='Description')
        
        # Scrollbar
        scroll_vpn = ttk.Scrollbar(vpn_frame, orient="vertical", command=self.vpn_tree.yview)
        self.vpn_tree.configure(yscrollcommand=scroll_vpn.set)
        
        # Pack widgets
        scroll_vpn.pack(side=tk.RIGHT, fill=tk.Y)
        self.vpn_tree.pack(fill=tk.BOTH, expand=True)

        # Button frame
        btn_frame = ttk.Frame(vpn_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        # Add buttons
        ttk.Button(btn_frame, text="Refresh", command=lambda: self.refresh_vpn_status(manual_refresh=True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Export to CSV", command=self.export_vpn_status).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Export to JSON", command=lambda: self.export_vpn_status('json')).pack(side=tk.LEFT)
        
        # Add double-click binding to show details
        self.vpn_tree.bind('<Double-1>', self.on_vpn_double_click)

    
    def create_bgp_status_tab(self):
        """Create a tab for BGP session monitoring"""
        bgp_frame = ttk.Frame(self.notebook)
        self.notebook.add(bgp_frame, text='BGP Status')
        
        # Treeview
        self.bgp_tree = ttk.Treeview(bgp_frame, columns=('vrf', 'neighbor', 'as', 'uptime', 'state', 'prefixes'), show='headings')
        self.bgp_tree.heading('vrf', text='VRF')
        self.bgp_tree.heading('neighbor', text='Neighbor')
        self.bgp_tree.heading('as', text='AS')
        self.bgp_tree.heading('uptime', text='Uptime')
        self.bgp_tree.heading('state', text='State')
        self.bgp_tree.heading('prefixes', text='Prefixes')
    
        # Scrollbar
        scroll_bgp = ttk.Scrollbar(bgp_frame, orient="vertical", command=self.bgp_tree.yview)
        self.bgp_tree.configure(yscrollcommand=scroll_bgp.set)

        # Pack widgets
        scroll_bgp.pack(side=tk.RIGHT, fill=tk.Y)
        self.bgp_tree.pack(fill=tk.BOTH, expand=True)
    
        # Button frame
        btn_frame = ttk.Frame(bgp_frame)
        btn_frame.pack(fill=tk.X, pady=5)      

        # Add buttons
        ttk.Button(btn_frame, text="Refresh", command=lambda: self.refresh_bgp_status(manual_refresh=True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Export to CSV", command=self.export_bgp_status).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Export to JSON", command=lambda: self.export_bgp_status('json')).pack(side=tk.LEFT)

        # Add double-click binding to show details
        self.bgp_tree.bind('<Double-1>', self.on_bgp_double_click)
            


    def create_vpn_traffic_tab(self):
        """Create a tab for VPN traffic flow."""
        traffic_frame = ttk.Frame(self.notebook)
        self.notebook.add(traffic_frame, text="VPN Traffic Flow")

        # Treeview
        self.traffic_tree = ttk.Treeview(traffic_frame, columns=('vrf', 'peer', 'interface', 'description', 'local_ident', 'remote_ident', 'pkts_encrypt', 'pkts_decrypt'), show='headings')
        self.traffic_tree.heading('vrf', text='VRF')
        self.traffic_tree.heading('peer', text='Peer')
        self.traffic_tree.heading('interface', text='Interface')
        self.traffic_tree.heading('description', text='Description')
        self.traffic_tree.heading('local_ident', text='Local_ident')
        self.traffic_tree.heading('remote_ident', text='Remote_ident')
        self.traffic_tree.heading('pkts_encrypt', text='Pkts_encrypt')
        self.traffic_tree.heading('pkts_decrypt', text='Pkts_decrypt')
        
        # Scrollbar
        scroll_traffic = ttk.Scrollbar(traffic_frame, orient="vertical", command=self.traffic_tree.yview)
        self.traffic_tree.configure(yscrollcommand=scroll_traffic.set)
        
        # Pack widgets
        scroll_traffic.pack(side=tk.RIGHT, fill=tk.Y)
        self.traffic_tree.pack(fill=tk.BOTH, expand=True)
        
        # Add status label
        self.traffic_status_label = ttk.Label(traffic_frame, text="Status: Ready")
        self.traffic_status_label.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        
        # Button frame
        btn_frame = ttk.Frame(traffic_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        # Add buttons
        ttk.Button(btn_frame, text="Refresh VPN Traffic", command=lambda: self.refresh_vpn_traffic_status(manual_refresh=True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Export to CSV", command=lambda: self.export_traffic_data('csv')).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Export to JSON", command=lambda: self.export_traffic_data('json')).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Debug Info", command=self.show_vpn_traffic_debug).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Test Data Flow", command=self.test_vpn_traffic_data_flow).pack(side=tk.LEFT, padx=5)

        # Add double-click binding to show details
        self.traffic_tree.bind('<Double-1>', self.on_traffic_double_click)



    def create_vrf_summary_tab(self):
        """Create a tab showing VRF configuration summaries"""
        summary_frame = ttk.Frame(self.notebook)
        self.notebook.add(summary_frame, text="VRF Summary")

        # Status label
        self.summary_status_label = ttk.Label(summary_frame, text="Status: Ready - Click Refresh to load VRF summaries")
        self.summary_status_label.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        
        # Treeview
        self.summary_tree = ttk.Treeview(summary_frame, 
                    columns=('vrf_name', 'site_role', 'tunnel_interfaces', 'interface_count', 'has_inside_nat', 'has_outside_nat', 'has_dynamic_nat','total_nat_rules', 'acl_count', 'bgp_configured', 'static_route_count', 'ipsec_profiles', 'migration_complexity'), 
                    show='headings')
        self.summary_tree.heading('vrf_name', text='VRF Name')
        self.summary_tree.heading('site_role', text='Site Role')
        self.summary_tree.heading('tunnel_interfaces', text='Tunnel Ifaces')
        self.summary_tree.heading('interface_count', text='Total Ifaces')
        self.summary_tree.heading('has_inside_nat', text='Inside NAT')
        self.summary_tree.heading('has_outside_nat', text='Outside NAT')
        self.summary_tree.heading('has_dynamic_nat', text='Dynamic NAT')
        self.summary_tree.heading('total_nat_rules', text='NAT rules')
        self.summary_tree.heading('acl_count', text='ACLs')
        self.summary_tree.heading('bgp_configured', text='BGP')
        self.summary_tree.heading('static_route_count', text='Static Routes')
        self.summary_tree.heading('ipsec_profiles', text='IPSec Profiles')
        self.summary_tree.heading('migration_complexity', text='Complexity')    
        
        # Add scrollbar
        scroll_summary = ttk.Scrollbar(summary_frame, orient="vertical", command=self.summary_tree.yview)
        self.summary_tree.configure(yscrollcommand=scroll_summary.set)
        
        # Pack widgets
        scroll_summary.pack(side=tk.RIGHT, fill=tk.Y)
        self.summary_tree.pack(fill=tk.BOTH, expand=True)

        # Button frame
        btn_frame = ttk.Frame(summary_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="Refresh VRF Summary", command=self.refresh_vrf_summary).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Export to CSV", command=self.export_vrf_summary).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Sort by Complexity", command=self.sort_by_complexity).pack(side=tk.LEFT, padx=5)
        
        # Add double-click binding to show details
        self.summary_tree.bind('<Double-1>', self.on_summary_double_click)
        
     
        
        
        

#    def create_troubleshooting_tab(self):
#        """Create a tab for troubleshooting commands"""
#        troubleshooting_frame = ttk.Frame(self.notebook)
#        
#        # Text widget for commands
#        self.troubleshooting_text = tk.Text(troubleshooting_frame, wrap=tk.WORD, state=tk.DISABLED, font=('Courier', 10))
#        scroll = ttk.Scrollbar(troubleshooting_frame, command=self.troubleshooting_text.yview)
#        self.troubleshooting_text.configure(yscrollcommand=scroll.set)
#        
#        # Button frame
#        btn_frame = ttk.Frame(troubleshooting_frame)
#        ttk.Button(btn_frame, text="Generate Troubleshooting Commands", 
#                   command=self._generate_troubleshooting_with_check).pack(side=tk.LEFT, padx=5)
#        ttk.Button(btn_frame, text="Copy to Clipboard", 
#                   command=self.copy_troubleshooting_to_clipboard).pack(side=tk.LEFT, padx=5)
#        ttk.Button(btn_frame, text="Save to File", 
#                   command=self.save_troubleshooting_to_file).pack(side=tk.LEFT, padx=5)
#        
#        # Layout
#        btn_frame.pack(fill=tk.X, pady=5)
#        scroll.pack(side=tk.RIGHT, fill=tk.Y)
#        self.troubleshooting_text.pack(fill=tk.BOTH, expand=True)
#        
#        self.notebook.add(troubleshooting_frame, text="Troubleshooting")

    
    def _generate_troubleshooting_with_check(self):
        """Helper method to check if VRF is selected before generating commands"""
        if not self.selected_vrf.get():
            messagebox.showerror("Error", "No VRF selected")
            return
        
        if not hasattr(self, 'parser') or not self.parser:
            messagebox.showerror("Error", "Parser not initialized")
            return
        
        # Use the parser's method to generate troubleshooting commands
        commands = self.parser.generate_troubleshooting_commands(self.selected_vrf.get())

        
        # Display in the troubleshooting text widget
        self.troubleshooting_text.config(state=tk.NORMAL)
        self.troubleshooting_text.delete(1.0, tk.END)
        self.troubleshooting_text.insert(tk.END, commands)
        self.troubleshooting_text.config(state=tk.DISABLED)
    
    def copy_troubleshooting_to_clipboard(self):
        """Copy troubleshooting commands to clipboard"""
        commands = self.troubleshooting_text.get(1.0, tk.END)
        if commands.strip():
            self.root.clipboard_clear()
            self.root.clipboard_append(commands)
            messagebox.showinfo("Success", "Troubleshooting commands copied to clipboard")
        else:
            messagebox.showwarning("Warning", "No troubleshooting commands to copy")
    
    def save_troubleshooting_to_file(self):
        """Save troubleshooting commands to file"""
        commands = self.troubleshooting_text.get(1.0, tk.END)
        if not commands.strip():
            messagebox.showwarning("Warning", "No troubleshooting commands to save")
            return
            
        filename = filedialog.asksaveasfilename(
            title="Save Troubleshooting Commands",
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
            initialfile=f"troubleshooting_{self.selected_vrf.get()}.txt"
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(commands)
                messagebox.showinfo("Success", f"Troubleshooting commands saved to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {str(e)}")


############Export to file VPN and BGP statuses

    def export_vpn_status(self, format='csv'):
        """Export VPN status to file"""
        if not hasattr(self.parser, 'last_vpn_status'):
            messagebox.showerror("Error", "No VPN status data to export")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=f".{format}",
            filetypes=[("CSV Files", "*.csv"), ("JSON Files", "*.json")],
            title=f"Export VPN Status as {format.upper()}"
        )
        
        if not filename:
            return
        
        try:
            # Collect all sessions
            sessions = []
            for cmd, data in self.parser.last_vpn_status.items():
                if isinstance(data, list):
                    sessions.extend(data)
            
            if format == 'csv':
                with open(filename, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['VRF', 'Peer' , 'Interface', 'Status', 'Uptime' , 'Description', 'Timestamp'])
                    for session in sessions:
                        writer.writerow([
                            session.get('vrf', ''),
                            session.get('peer', ''),
                            session.get('interface', ''),
                            session.get('status', session.get('session_status', '')),
                            session.get('uptime', ''),
                            session.get('description'),
                            datetime.now().isoformat()
                        ])
            else:  # JSON
                export_data = {
                    'timestamp': datetime.now().isoformat(),
                    'sessions': sessions
                }
                with open(filename, 'w') as f:
                    json.dump(export_data, f, indent=2)
            
            messagebox.showinfo("Success", f"VPN status exported to {filename}")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))




    def export_bgp_status(self, format='csv'):
        """Export BGP status to file"""
        if not hasattr(self.parser, 'last_bgp_status'):
            messagebox.showerror("Error", "No BGP status data to export")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=f".{format}",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            title="Export BGP Status"
        )
        
        if not filename:
            return
        
        try:
            # Collect all BGP peers
            all_peers = []
            for vrf, peers in self.parser.last_bgp_status.items():
                if isinstance(peers, list):  # Skip error messages
                    for peer in peers:
                        peer['vrf'] = vrf
                        all_peers.append(peer)
            
            if format == 'csv':
                with open(filename, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['VRF', 'Neighbor', 'AS', 'State', 'Prefixes', 'Uptime', 'Timestamp'])
                    for peer in all_peers:
                        writer.writerow([
                            peer.get('vrf', ''),
                            peer.get('neighbor', ''),
                            peer.get('remote_as', ''),
                            peer.get('state', ''),
                            peer.get('prefixes', ''),
                            peer.get('uptime', ''),
                            datetime.now().isoformat()
                        ])
            
            messagebox.showinfo("Success", f"BGP status exported to {filename}")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

##################End export

        
    def toggle_input_source(self, *args):
        """Enable/disable file input controls based on selection"""
        if self.input_source.get() == "file":
            self.file_entry.config(state=tk.NORMAL)
            self.browse_file_btn.config(state=tk.NORMAL)
            self.device_combo.config(state=tk.DISABLED)
        else:
            self.file_entry.config(state=tk.DISABLED)
            self.browse_file_btn.config(state=tk.DISABLED)
            self.device_combo.config(state="readonly")

    def log_message(self, message):
        """Add message to log"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)
        self.root.update_idletasks()
        
    def browse_input_file(self):
        """Select input config file"""
        file = filedialog.askopenfilename(title="Select Config File", 
                                         filetypes=[("Text", "*.txt"), ("All Files", "*.*")])
        if file:
            self.input_file.set(file)

    def browse_config_file(self):
        """Select config file"""
        file = filedialog.askopenfilename(title="Select Config File", filetypes=[("JSON", "*.json")])
        if file:
            self.config_file.set(file)
            self.load_device_config()

    
    def load_device_config(self):
        """Load devices from config file"""
        try:
            self.parser = RouterConfigParser(
                config_file=self.config_file.get(),
                output_dir=self.output_dir.get(),
                gui_callback=self.log_message,
                debug_mode=self.debug_mode.get()
            )
            self.device_combo['values'] = list(self.parser.devices.keys())
            if self.parser.devices:
                self.selected_device.set(next(iter(self.parser.devices.keys())))
            self.log_message("Device config loaded successfully")
            
            # Test debug mode
            self.parser.log("=== INITIAL DEBUG TEST ===", debug_level=True)
            self.parser.log("This debug message should appear if debug mode is ON", debug_level=True)
            
        except Exception as e:
            self.log_message(f"Error loading config: {str(e)}")


    def _load_config_file(self):
        """Threaded config file loader"""
        try:
            # Ensure parser exists with current debug settings
            self._ensure_parser_exists()
            
            with open(self.input_file.get(), 'r') as f:
                config_lines = f.readlines()
            
            device_name = self._current_device_name()
            success, vrf_list = self.parser.parse_configuration(config_lines, preview_only=True, device_name=device_name)
            if success:
                self.vrf_combo['values'] = vrf_list
                if vrf_list:
                    self.selected_vrf.set(vrf_list[0])
                self.log_message(f"Found {len(vrf_list)} VRFs")
                self.last_config = config_lines
                
                # Refresh status displays for file-based config too (only
                # for tabs that are actually enabled/built -- see settings.json)
                if hasattr(self, 'traffic_tree'):
                    self.root.after(0, self.refresh_vpn_traffic_status)
                
                self.output_combo.config(state="readonly")
                self.generate_output_button.config(state="normal")
                
                self.log_message("Configuration loaded from file - refreshing status tabs")
        except Exception as e:
            self.log_message(f"Failed to load config file: {str(e)}")


    def connect_to_device(self):
        """Connect to selected device or load config file"""
        self.output_combo.config(state="disabled")
        self.generate_output_button.config(state="disabled")
        if self.input_source.get() == "file":
            if not self.input_file.get():
                messagebox.showerror("Error", "No config file selected")
                return
            
            self.log_message(f"Loading config from {self.input_file.get()}...")
            Thread(target=self._load_config_file, daemon=True).start()
        else:
            device = self.selected_device.get()
            if not device:
                messagebox.showerror("Error", "No device selected")
                return
            
            self.log_message(f"Connecting to {device}...")
            Thread(target=self._connect_and_parse, daemon=True).start()


    def _connect_and_parse(self):
        """Threaded connection handler"""
        try:
            # Ensure parser exists with current debug settings
            self._ensure_parser_exists()
            
            config_lines = self.parser.fetch_live_config(self.selected_device.get())
            if config_lines:
                success, vrf_list = self.parser.parse_configuration(config_lines, preview_only=True, device_name=self.selected_device.get())
                if success:
                    self.vrf_combo['values'] = vrf_list
                    if vrf_list:
                        self.selected_vrf.set(vrf_list[0])
                    self.log_message(f"Found {len(vrf_list)} VRFs")
                    self.last_config = config_lines
                    
                    # Refresh status displays after successful config fetch --
                    # only for tabs that are actually enabled/built (see
                    # settings.json / the Settings window).
                    self.root.after(0, self.update_connection_status)
                    if hasattr(self, 'vpn_tree'):
                        self.root.after(0, self.refresh_vpn_status)
                    if hasattr(self, 'bgp_tree'):
                        self.root.after(100, self.refresh_bgp_status)  # Small delay
                    if hasattr(self, 'traffic_tree'):
                        self.root.after(200, self.refresh_vpn_traffic_status)  # Another small delay
                    
                    self.output_combo.config(state="readonly")
                    self.generate_output_button.config(state="normal")
                    
                    self.log_message("Configuration fetched successfully - refreshing all status tabs")
                    if hasattr(self, 'command_executor_tab') and hasattr(self.parser, 'current_connection'):
                        self.command_executor_tab.set_connection(self.parser.current_connection)

            else:
                self.log_message("Failed to fetch configuration from device")
        except Exception as e:
            self.log_message(f"Connection failed: {str(e)}")


    def start_parsing(self, selected_only=False):
        """Start parsing process"""
        if selected_only and not self.selected_vrf.get():
            messagebox.showerror("Error", "No VRF selected")
            return
        
        if not self.last_config:
            messagebox.showerror("Error", "No configuration loaded")
            return
        
        Thread(
            target=self._run_parsing,
            args=(self.selected_vrf.get() if selected_only else None,),
            daemon=True
        ).start()


    def _run_parsing(self, selected_vrf=None):
        """Threaded parsing handler"""
        try:
            device_name = self._current_device_name()
            success, vrf_keys = self.parser.parse_configuration(
                config_source=self.last_config,
                selected_vrf=selected_vrf,
                device_name=device_name
            )
            if success:
                if selected_vrf: # Single VRF output
                    # Construct the expected output filename
                    output_dir = os.path.join(self.parser.OUTPUT_DIR, 'deployed', selected_vrf)
                    config_date = self.parser.config_parser.get_config_last_change_date(self.last_config)
                    device_name = self._current_device_name()
                    if config_date:
                        output_filename = os.path.join(output_dir, f"{device_name}-{selected_vrf}_{config_date}.txt")
                    else:
                        output_filename = os.path.join(output_dir, f"{device_name}-{selected_vrf}.txt")
                    
                    self._display_ios_preview_from_file(output_filename)
                    messagebox.showinfo("Success", f"Parsing completed successfully. Output saved to {output_filename}")
                else: # All VRFs output
                    messagebox.showinfo("Success", "Parsing completed successfully. All VRF outputs saved to files.")
            else:
                messagebox.showerror("Error", "Parsing failed.") # More generic error
        except Exception as e:
            self.log_message(f"Parsing failed: {str(e)}")
            messagebox.showerror("Error", f"Parsing failed: {str(e)}") # Show error to user


    def load_bgp_data(self):
        """
        Load BGP summary outputs for all VRFs and parse them.
        This can be enhanced to run commands on a live device or read saved outputs.
        """
        # Simulate or dynamically load outputs for each VRF
        vrf_outputs = {}
        
        for vrf in self.parser.vrf_list:  # Or however you store VRFs
            file_path = f"outputs/bgp_summary_{vrf}.txt"  # You can customize path
            if os.path.exists(file_path):
                with open(file_path) as f:
                    vrf_outputs[vrf] = f.read()
            else:
                print(f"[WARN] Missing BGP summary for VRF {vrf}: {file_path}")
        
        self.parser.parse_bgp_vrf_summaries(vrf_outputs)
        self.refresh_bgp_status()


    def browse_output_dir(self):
        """Select output directory"""
        dir = filedialog.askdirectory(title="Select Output Directory")
        if dir:
            self.output_dir.set(dir)
            
                     
    def preview_vrf(self):
        """Preview selected VRF config in proper Cisco format"""
        if not self.selected_vrf.get():
            messagebox.showerror("Error", "No VRF selected")
            return
        
        self.notebook.select(self.preview_text.master)
    
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete(1.0, tk.END)
    
        try:
            config_lines = self.parser.get_vrf_config(self.selected_vrf.get())
            if not config_lines:
                self.preview_text.insert(tk.END, "No configuration available")
                return
            
            # Start with Cisco-style header
            formatted_output = [
                f"! Command: show running-config vrf {self.selected_vrf.get()}",
                "!",
                ""
            ]
        
            current_indent = 0
            in_block = False
        
            for line in config_lines:
                line = line.rstrip()
            
                # Skip empty lines unless we're in a block
                if not line and not in_block:
                    continue
                
                # Handle block start/end
                if not line.startswith(' '):
                    # Main command - reset indentation
                    in_block = False
                    current_indent = 0
                    formatted_output.append(line)
                
                    # Check if this starts a block that should be indented
                    if any(line.startswith(cmd) for cmd in [
                        'vrf definition',
                        'interface',
                        'router bgp',
                        'ip nat',
                        'ip access-list',
                        'ip prefix-list',
                        'route-map',
                        'crypto ',
                        'track ',
                        'ip sla '
                    ]):
                        in_block = True
                        current_indent = 1
                else:
                    # Sub-command - apply indentation
                    if not in_block:
                        in_block = True
                        current_indent = 1
                    formatted_output.append((' ' * current_indent) + line.lstrip())
        
            # Add Cisco-style footer
            formatted_output.extend(["", "!"])
        
            # Insert the formatted configuration
            self.preview_text.insert(tk.END, '\n'.join(formatted_output))
        
        except Exception as e:
            self.preview_text.insert(tk.END, f"Error: {str(e)}")
    
        self.preview_text.config(state=tk.DISABLED)
    

   
    
############################


    def _display_ios_preview_from_file(self, file_path):
        """Display content of a Cisco IOS config file in the VRF Preview tab."""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            self.preview_text.config(state=tk.NORMAL)
            self.preview_text.delete(1.0, tk.END)
            self.preview_text.insert(tk.END, content)
            self.preview_text.config(state=tk.DISABLED)
            self.notebook.select(self.preview_text.master) # Select "Cisco IOS VRF Preview" tab
        except Exception as e:
            self.log_message(f"Error displaying file {file_path}: {str(e)}")
            messagebox.showerror("Error", f"Error displaying file: {str(e)}")

    def refresh_vpn_status(self, manual_refresh=False):
        """Refresh and display VPN status from crypto session brief"""
        if not hasattr(self, 'vpn_tree'):
            return  # VPN Status tab isn't enabled/built -- nothing to refresh
        # If manually triggered and we have an active connection, fetch fresh data
        if manual_refresh and (hasattr(self, 'parser') and self.parser and 
            hasattr(self.parser, 'current_connection') and self.parser.current_connection):
            self.log_message("Fetching fresh VPN status from device...")
            success = self.parser.refresh_status_data()
            if success:
                self.log_message("VPN status refreshed from device")
            else:
                self.log_message("Failed to refresh from device, showing cached data")
        
        if not hasattr(self.parser, 'last_vpn_status') or not self.parser.last_vpn_status:
            self.log_message("No VPN status data available")
            return
            
        self.vpn_tree.delete(*self.vpn_tree.get_children())
        
        # Get both crypto sessions and interface descriptions
        crypto_sessions = []
        interface_descriptions = {}
        
        for cmd, data in self.parser.last_vpn_status.items():
            if 'show crypto session brief' in cmd and isinstance(data, list):
                crypto_sessions = data
            elif 'show interface description' in cmd and isinstance(data, dict):
                interface_descriptions = data
        
        # Add descriptions to crypto sessions
        for session in crypto_sessions:
            interface = session['interface']
            # Try exact match first
            if interface in interface_descriptions:
                session['description'] = interface_descriptions[interface]
            else:
                # Try tunnel interface variations
                if interface.startswith('Tu') and interface[2:].isdigit():
                    alt_name = f"Tunnel{interface[2:]}"
                elif interface.startswith('Tunnel') and interface[6:].isdigit():
                    alt_name = f"Tu{interface[6:]}"
                else:
                    alt_name = None
                
                if alt_name and alt_name in interface_descriptions:
                    session['description'] = interface_descriptions[alt_name]
                else:
                    session['description'] = 'N/A'
        
        # Configure columns
        self.vpn_tree['columns'] = ('vrf', 'peer', 'interface', 'status', 'uptime', 'description')
        for col in self.vpn_tree['columns']:
            self.vpn_tree.heading(col, text=col.replace('_', ' ').title())
        
        # Add to treeview
        for session in crypto_sessions:
            self.vpn_tree.insert('', 'end', values=(
                session.get('vrf', ''),
                session.get('peer', ''),
                session.get('interface', ''),
                session.get('status', ''),
                session.get('uptime', ''),
                session.get('description', 'N/A')
            ))
        
        # Color coding
        self.vpn_tree.tag_configure('active', foreground='green')
        self.vpn_tree.tag_configure('inactive', foreground='red')
        
        for item in self.vpn_tree.get_children():
            status = self.vpn_tree.item(item, 'values')[3].upper()
            tags = ('active',) if 'UA' in status or 'A-' in status else ('inactive',)
            self.vpn_tree.item(item, tags=tags)

        
    
    def refresh_bgp_status(self, manual_refresh=False):
        """Refresh and display BGP session status by VRF"""
        if not hasattr(self, 'bgp_tree'):
            return  # BGP Status tab isn't enabled/built -- nothing to refresh
        # If manually triggered and we have an active connection, fetch fresh data
        if manual_refresh and (hasattr(self, 'parser') and self.parser and 
            hasattr(self.parser, 'current_connection') and self.parser.current_connection):
            self.log_message("Fetching fresh BGP status from device...")
            success = self.parser.refresh_status_data()
            if success:
                self.log_message("BGP status refreshed from device")
            else:
                self.log_message("Failed to refresh from device, showing cached data")
        
        if not hasattr(self.parser, 'last_bgp_status') or not self.parser.last_bgp_status:
            self.log_message("No BGP status data available")
            return
            self.log_message("No BGP status data available")
            return
        
        self.log_message(f"Refreshing BGP status with {len(self.parser.last_bgp_status)} VRFs") 

        # Clear existing tree items
        self.bgp_tree.delete(*self.bgp_tree.get_children())
    
        # Collect and sort all BGP peers
        all_peers = []
        for vrf, peers in self.parser.last_bgp_status.items():
            self.log_message(f"Processing VRF {vrf} with {len(peers) if isinstance(peers, list) else 1} entries")
            if isinstance(peers, list):  # Skip error messages
                for peer in peers:
                    peer['vrf'] = vrf
                    all_peers.append(peer)
            else:
                self.log_message(f"VRF {vrf} has non-list data: {peers}")
        
        # Sort by VRF and neighbor IP
        all_peers.sort(key=lambda p: (p['vrf'], p['neighbor']))

        # Populate treeview
        for peer in all_peers:
            self.bgp_tree.insert('', 'end', values=(
                peer.get('vrf', ''),
                peer.get('neighbor', ''),
                peer.get('remote_as', ''),
                peer.get('uptime', ''),
                peer.get('state', ''),
                peer.get('prefixes', '')
            ))

        # Color coding
        self.bgp_tree.tag_configure('established', foreground='green')
        self.bgp_tree.tag_configure('idle', foreground='red')
        self.bgp_tree.tag_configure('active', foreground='orange')

        for item in self.bgp_tree.get_children():
            state = self.bgp_tree.item(item, 'values')[4].lower()
            if state == 'established':
                tags = ('established',)
            elif state == 'idle':
                tags = ('idle',)
            else:
                tags = ('active',)
            self.bgp_tree.item(item, tags=tags)


    def run_output_action(self):
        """Execute the selected file output action."""
        action = self.output_action.get()
        self.log_message(f"=== run_output_action called with: '{action}' ===")
        
        if action == "Cisco IOS VRF Output":
            self.start_parsing(True)
        elif action == "Cisco IOS All VRF Output":
            self.start_parsing(False)
        elif action == "JSON VRF Output":
            self.generate_json_for_selected()
        elif action == "JSON All VRF Output":
            self.generate_json_for_all_vrfs()
        elif action == "Generate VPN Rollback":  # Fixed: Capital 'R' to match dropdown
            self.log_message("Matched 'Generate VPN Rollback' - calling generate_rollback()")
            self.generate_rollback()
        else:
            self.log_message(f"ERROR: Unknown action '{action}'")
            messagebox.showerror("Error", f"Unknown output action: {action}")


    def generate_json_for_selected(self):
        if not self.selected_vrf.get():
            messagebox.showerror("Error", "No VRF selected")
            return
        if not self.parser:
            messagebox.showerror("Error", "No configuration parsed")
            return

        json_output = self.parser.generate_vrf_json(self.selected_vrf.get())
        
        device_name = self._current_device_name()
        config_date = self.parser.config_parser.get_config_last_change_date(self.last_config)
        
        output_dir = os.path.join(self.parser.OUTPUT_DIR, 'json')
        os.makedirs(output_dir, exist_ok=True)
        
        if config_date:
            output_file = os.path.join(output_dir, f"{device_name}-{self.selected_vrf.get()}_{config_date}.json")
        else:
            output_file = os.path.join(output_dir, f"{device_name}-{self.selected_vrf.get()}.json")
            
        if output_file:
            with open(output_file, 'w') as f:
                f.write(json_output)
            messagebox.showinfo("Success", f"JSON output saved to {output_file}")
            
            # Display in Cisco IOS VRF Preview tab
            self.preview_text.config(state=tk.NORMAL)
            self.preview_text.delete(1.0, tk.END)
            self.preview_text.insert(tk.END, json_output)
            self.preview_text.config(state=tk.DISABLED)
            self.notebook.select(self.preview_text.master)


    def generate_json_for_all_vrfs(self):
        """Generate JSON output for all VRFs in separate files with same structure as Cisco IOS"""
        if not self.parser:
            messagebox.showerror("Error", "No configuration parsed")
            return
        
        # Check if we have VRF data - it's stored in config_parser.vrfs
        if not hasattr(self.parser.config_parser, 'vrfs') or not self.parser.config_parser.vrfs:
            messagebox.showerror("Error", "No VRFs found to export. Please parse a configuration first.")
            return
    
        try:
            device_name = self._current_device_name()
            config_date = self.parser.config_parser.get_config_last_change_date(self.last_config)
            
            # Create output directory structure identical to Cisco IOS All VRF Output
            base_output_dir = os.path.join(self.parser.OUTPUT_DIR, 'deployed')
            
            vrf_count = 0
            exported_vrfs = []
            
            for vrf_name, vrf_data in self.parser.config_parser.vrfs.items():
                # Create VRF-specific directory (same as Cisco IOS output structure)
                vrf_output_dir = os.path.join(base_output_dir, 'json', vrf_name)
                os.makedirs(vrf_output_dir, exist_ok=True)
                
                # Create a copy to avoid modifying original data
                data_to_dump = vrf_data.copy()
                
                # Convert sets to lists for JSON serialization
                for key, value in data_to_dump.items():
                    if isinstance(value, set):
                        data_to_dump[key] = list(value)
    
                # Populate content for route-maps and prefix-lists
                if 'route_maps' in data_to_dump:
                    data_to_dump['route_maps'] = {rm: self.parser.config_parser.route_maps.get(rm, []) for rm in data_to_dump['route_maps']}
                if 'prefix_lists' in data_to_dump:
                    data_to_dump['prefix_lists'] = {pf: self.parser.config_parser.prefix_lists.get(pf, []) for pf in data_to_dump['prefix_lists']}
                
                # Remove duplicate tunnel interfaces key
                if 'tunnel_interfaces' in data_to_dump:
                    del data_to_dump['tunnel_interfaces']
                
                # Generate filename identical to Cisco IOS output but with .json extension
                if config_date:
                    output_file = os.path.join(vrf_output_dir, f"{device_name}-{vrf_name}_{config_date}.json")
                else:
                    output_file = os.path.join(vrf_output_dir, f"{device_name}-{vrf_name}.json")
                
                # Write individual VRF JSON file
                with open(output_file, 'w') as f:
                    json.dump(data_to_dump, f, indent=2)
                
                vrf_count += 1
                exported_vrfs.append({
                    'vrf_name': vrf_name,
                    'file_path': output_file,
                    'file_name': os.path.basename(output_file)
                })
                
                self.log_message(f"Exported VRF '{vrf_name}' to {output_file}")
            
            # Create a summary file in the base directory
            summary_data = {
                'metadata': {
                    'device_name': device_name,
                    'config_date': config_date,
                    'export_timestamp': datetime.now().isoformat(),
                    'total_vrfs': vrf_count,
                    'base_output_directory': base_output_dir
                },
                'exported_vrfs': exported_vrfs
            }
            
            summary_file = os.path.join(base_output_dir, 'json', f"{device_name}-all_vrfs_json_export_summary.json")
            with open(summary_file, 'w') as f:
                json.dump(summary_data, f, indent=2)
            
            # Display the summary in preview tab
            self.preview_text.config(state=tk.NORMAL)
            self.preview_text.delete(1.0, tk.END)
            self.preview_text.insert(tk.END, f"JSON All VRF Export Summary\n")
            self.preview_text.insert(tk.END, f"===========================\n")
            self.preview_text.insert(tk.END, f"Device: {device_name}\n")
            self.preview_text.insert(tk.END, f"Config Date: {config_date or 'N/A'}\n")
            self.preview_text.insert(tk.END, f"Base Output Directory: {base_output_dir}\n")
            self.preview_text.insert(tk.END, f"Total VRFs Exported: {vrf_count}\n\n")
            self.preview_text.insert(tk.END, f"Exported VRFs:\n")
            for vrf_info in exported_vrfs:
                self.preview_text.insert(tk.END, f"  - {vrf_info['vrf_name']}: {vrf_info['file_name']}\n")
            self.preview_text.insert(tk.END, f"\nSummary file: {os.path.basename(summary_file)}")
            self.preview_text.config(state=tk.DISABLED)
            self.notebook.select(self.preview_text.master)
            
            messagebox.showinfo("Success", 
                              f"All VRF JSON output completed!\n\n"
                              f"Total VRFs exported: {vrf_count}\n"
                              f"Base output directory: {base_output_dir}/json/\n\n"
                              f"Each VRF saved in its own subdirectory with naming:\n"
                              f"{device_name}-<vrf_name>_{config_date or ''}.json")
            
        except Exception as e:
            self.log_message(f"Error generating all VRF JSON: {str(e)}")
            messagebox.showerror("Error", f"Failed to generate all VRF JSON:\n{str(e)}")

   
    def generate_rollback(self):
        """Generate rollback script for selected VRF"""
        self.log_message("=== Starting Rollback Generation ===")
        
        if not self.selected_vrf.get():
            self.log_message("ERROR: No VRF selected")
            messagebox.showerror("Error", "No VRF selected")
            return
        
        self.log_message(f"Selected VRF: {self.selected_vrf.get()}")
        
        if not self.last_config:
            self.log_message("ERROR: No configuration loaded")
            messagebox.showerror("Error", "No configuration loaded")
            return
        
        self.log_message(f"Config loaded: {len(self.last_config)} lines")
        
        try:
            # Ensure parser exists
            self.log_message("Ensuring parser exists...")
            self._ensure_parser_exists()
            self.log_message(f"Parser exists: {self.parser is not None}")
            
            # First ensure we have parsed the config
            device_name = self._current_device_name()
            self.log_message(f"Device name: {device_name}")
            self.log_message("Parsing configuration...")
            
            success, _ = self.parser.parse_configuration(self.last_config, preview_only=True, device_name=device_name)
            self.log_message(f"Parse result: {success}")
            
            if not success:
                self.log_message("ERROR: Failed to parse configuration")
                messagebox.showerror("Error", "Failed to parse configuration")
                return
            
            self.log_message("Generating rollback script...")
            
            # Check what VRFs are available
            available_vrfs = list(self.parser.config_parser.vrfs.keys())
            self.log_message(f"Available VRFs after parse: {available_vrfs}")
            self.log_message(f"Looking for VRF: '{self.selected_vrf.get()}'")
            
            rollback_commands = self.parser.generate_rollback_script(self.selected_vrf.get())
            self.log_message(f"Rollback commands generated: {rollback_commands is not None}")
            
            if rollback_commands:
                self.log_message(f"Generated {len(rollback_commands)} rollback commands")
            
            if not rollback_commands:
                self.log_message("ERROR: Failed to generate rollback script (empty result)")
                messagebox.showerror("Error", "Failed to generate rollback script")
                return
            
            # Ask for output file
            output_file = filedialog.asksaveasfilename(
                title="Save Rollback Script",
                defaultextension=".txt",
                filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
                initialfile=f"rollback_vrf_{self.selected_vrf.get()}.txt"
            )
            
            if output_file:  # User didn't cancel
                with open(output_file, 'w') as f:
                    f.write('\n'.join(rollback_commands))
                
                self.log_message(f"Rollback script saved to {output_file}")
                
                # Preview the rollback script
                self.preview_text.config(state=tk.NORMAL)
                self.preview_text.delete(1.0, tk.END)
                self.preview_text.insert(tk.END, '\n'.join(rollback_commands))
                self.preview_text.config(state=tk.DISABLED)
                
                messagebox.showinfo("Success", f"Rollback script saved to:\n{output_file}")
                
        except Exception as e:
            self.log_message(f"Error generating rollback script: {str(e)}")
            messagebox.showerror("Error", f"Failed to generate rollback script:\n{str(e)}")



###### START - Button option available in "VPN Fraffic flow tab"

    def export_traffic_data(self, format='csv'):
        """Export VPN traffic data to file"""
        traffic_data = self.parser.vpn_monitor.get_vpn_traffic_flow()
        if not traffic_data:
            messagebox.showerror("Error", "No VPN traffic data to export")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=f".{format}",
            filetypes=[("CSV Files", "*.csv"), ("JSON Files", "*.json")],
            title=f"Export VPN Traffic Data as {format.upper()}"
        )
        
        if not filename:
            return
        
        try:
            if format == 'csv':
                with open(filename, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['VRF', 'Peer', 'Interface', 'Description', 'Local Ident', 'Remote Ident', 'Packets Encrypted', 'Packets Decrypted', 'Timestamp'])
                    for session in traffic_data:
                        writer.writerow([
                            session.get('vrf', ''),
                            session.get('peer', ''),
                            session.get('interface', ''),
                            session.get('description', ''),
                            session.get('local_ident', ''),
                            session.get('remote_ident', ''),
                            session.get('pkts_encrypt', ''),
                            session.get('pkts_decrypt', ''),
                            datetime.now().isoformat()
                        ])
            else:  # JSON
                export_data = {
                    'timestamp': datetime.now().isoformat(),
                    'sessions': traffic_data
                }
                with open(filename, 'w') as f:
                    json.dump(export_data, f, indent=2)
            
            messagebox.showinfo("Success", f"VPN traffic data exported to {filename}")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))


    def refresh_vpn_traffic_status(self, manual_refresh=False):
        """Refresh and display VPN traffic flow."""
        if not hasattr(self, 'traffic_tree'):
            return  # VPN Traffic Flow tab isn't enabled/built -- nothing to refresh
        self.traffic_status_label.config(text="Status: Refreshing...")
        self.log_message("=== Refreshing VPN Traffic Status ===")
        
        if not self.parser:
            self.log_message("Parser not initialized")
            self.traffic_tree.delete(*self.traffic_tree.get_children())
            self.traffic_tree.insert('', 'end', values=("Error", "Parser not initialized", "", "", "", "", "", ""))
            self.traffic_status_label.config(text="Status: Parser not initialized")
            return
        
        # If manually triggered and we have an active connection, fetch fresh data
        if manual_refresh and (hasattr(self.parser, 'current_connection') and self.parser.current_connection):
            self.log_message("Fetching fresh VPN traffic data from device...")
            success = self.parser.refresh_status_data()
            if success:
                self.log_message("VPN traffic data refreshed from device")
            else:
                self.log_message("Failed to refresh from device, showing cached data")
            
        # Clear existing data
        self.traffic_tree.delete(*self.traffic_tree.get_children())
        
        # Check if we have VPN status data
        if not hasattr(self.parser, 'last_vpn_status'):
            self.log_message("No VPN status data available")
            self.traffic_tree.insert('', 'end', values=("No Data", "Fetch config first", "", "", "", "", "", ""))
            self.traffic_status_label.config(text="Status: No VPN data - Fetch config first")
            return
            
        if not self.parser.last_vpn_status:
            self.log_message("VPN status data is empty")
            self.traffic_tree.insert('', 'end', values=("Empty", "No VPN sessions found", "", "", "", "", "", ""))
            self.traffic_status_label.config(text="Status: No VPN sessions")
            return
        
        # Debug: Show what commands we have data for
        self.log_message(f"Available VPN status commands: {list(self.parser.last_vpn_status.keys())}")
        
        try:
            traffic_data = self.parser.vpn_monitor.get_vpn_traffic_flow()
            
            if not traffic_data:
                self.log_message("No VPN traffic data returned by parser")
                self.traffic_tree.insert('', 'end', values=(
                    "No Traffic", "No IPSec sessions active", "", "", "", "", "", ""
                ))
                self.traffic_status_label.config(text="Status: No IPSec traffic")
                return
            
            self.log_message(f"Displaying {len(traffic_data)} VPN traffic sessions")
            
            # Add to treeview
            for session in traffic_data:
                self.traffic_tree.insert('', 'end', values=(
                    session.get('vrf', 'N/A'),
                    session.get('peer', 'N/A'),
                    session.get('interface', 'N/A'),
                    session.get('description', 'N/A'),
                    session.get('local_ident', 'N/A'),
                    session.get('remote_ident', 'N/A'),
                    session.get('pkts_encrypt', 'N/A'),
                    session.get('pkts_decrypt', 'N/A')
                ))
                
            self.log_message(f"Successfully displayed {len(traffic_data)} traffic sessions")
            self.traffic_status_label.config(text=f"Status: Showing {len(traffic_data)} IPSec sessions")
                
        except Exception as e:
            error_msg = f"Error refreshing VPN traffic: {str(e)}"
            self.log_message(error_msg)
            self.traffic_tree.insert('', 'end', values=(
                "Error", str(e), "", "", "", "", "", ""
            ))
            self.traffic_status_label.config(text="Status: Error - see log")


    def show_vpn_traffic_debug(self):
        """Show detailed debug information about VPN traffic data"""
        self.log_message("=== VPN Traffic Debug Information ===")
        
        if not self.parser:
            self.log_message("Parser not available")
            return
            
        if not hasattr(self.parser, 'last_vpn_status'):
            self.log_message("No VPN status data available")
            return
            
        self.log_message(f"VPN status data keys: {list(self.parser.last_vpn_status.keys())}")
        
        # Check each command's data
        for cmd, data in self.parser.last_vpn_status.items():
            self.log_message(f"Command: {cmd}")
            self.log_message(f"  Type: {type(data)}")
            
            if isinstance(data, list):
                self.log_message(f"  List length: {len(data)}")
                if data and len(data) > 0:
                    self.log_message(f"  First item: {data[0]}")
                    
            elif isinstance(data, dict):
                self.log_message(f"  Dict keys: {list(data.keys())}")
                if data:
                    sample_key = list(data.keys())[0]
                    self.log_message(f"  Sample value: {data[sample_key]}")
                    
            elif isinstance(data, str):
                # This should only happen for error messages
                self.log_message(f"  Error message: {data}")


    def test_vpn_traffic_data_flow(self):
        """Test method to verify VPN traffic data flow"""
        self.log_message("=== Testing VPN Traffic Data Flow ===")
        
        if not self.parser or not hasattr(self.parser, 'last_vpn_status'):
            self.log_message("No parser or VPN status data available")
            return
        
        # Check if we have the IPSec SA data
        ipsec_data = self.parser.last_vpn_status.get('show crypto ipsec sa')
        if ipsec_data and isinstance(ipsec_data, list):
            self.log_message(f"IPSec SA data found: {len(ipsec_data)} sessions")
            self.log_message(f"Sample session: {ipsec_data[0] if ipsec_data else 'None'}")
        else:
            self.log_message("No IPSec SA data found or wrong type")
            return
        
        # Test the get_vpn_traffic_flow method
        traffic_data = self.parser.vpn_monitor.get_vpn_traffic_flow()
        self.log_message(f"Traffic flow data: {len(traffic_data)} sessions")
        if traffic_data:
            self.log_message(f"Sample traffic session: {traffic_data[0]}")


######## END   - Button option available in "VPN Fraffic flow" tab


######## START - Button options available in "VRF Summary" tab

    
    
    def refresh_vrf_summary(self):
        """Refresh the VRF summary table"""
        if not hasattr(self, 'parser') or not self.parser:
            self.summary_status_label.config(text="Status: No parser available - Load configuration first")
            return
        
        # Clear existing data
        self.summary_tree.delete(*self.summary_tree.get_children())
        
        self.summary_status_label.config(text="Status: Generating VRF summaries...")
        
        try:
            summaries = self.parser.get_vrf_summaries()
            
            if not summaries:
                self.summary_tree.insert('', 'end', values=("No VRFs", "Load config first", "", "", "", "", "", "", "", "", "", "", ""))
                self.summary_status_label.config(text="Status: No VRFs found - Parse configuration first")
                return
            
            # Add summaries to treeview
            for summary in summaries:
                values = (
                    summary['vrf_name'],
                    summary['site_role'],
                    summary['tunnel_interfaces'],
                    summary['interface_count'],
                    'Yes' if summary['has_inside_nat'] else 'No',
                    'Yes' if summary['has_outside_nat'] else 'No',
                    'Yes' if summary['has_dynamic_nat'] else 'No',
                    summary['total_nat_rules'],
                    summary['acl_count'],
                    'Yes' if summary['bgp_configured'] else 'No',
                    summary['static_route_count'],
                    summary['ipsec_profiles'],
                    summary['migration_complexity']
                )
                item = self.summary_tree.insert('', 'end', values=values)
                
                # Color code by complexity
                complexity = summary['migration_complexity']
                if complexity >= 5:
                    self.summary_tree.item(item, tags=('high',))
                elif complexity >= 3:
                    self.summary_tree.item(item, tags=('medium',))
                else:
                    self.summary_tree.item(item, tags=('low',))
            
            # Configure tags for color coding
            self.summary_tree.tag_configure('high', background='#ffcccc', foreground='black')  # Light red
            self.summary_tree.tag_configure('medium', background='#fff0cc', foreground='black')  # Light yellow
            self.summary_tree.tag_configure('low', background='#ccffcc', foreground='black')  # Light green
            
            self.summary_status_label.config(text=f"Status: Showing {len(summaries)} VRFs - Double-click for details")
            
        except Exception as e:
            self.summary_status_label.config(text=f"Status: Error - {str(e)}")
            self.log_message(f"Error generating VRF summaries: {str(e)}")
    
    def sort_by_complexity(self):
        """Sort the summary table by migration complexity"""
        if not hasattr(self, 'parser') or not self.parser:
            return
        
        try:
            summaries = self.parser.get_vrf_summaries()
            sorted_summaries = sorted(summaries, key=lambda x: x['migration_complexity'], reverse=True)
            
            # Clear and repopulate
            self.summary_tree.delete(*self.summary_tree.get_children())
            
            for summary in sorted_summaries:
                values = (
                    summary['vrf_name'],
                    summary['site_role'],
                    summary['tunnel_interfaces'],
                    summary['interface_count'],
                    'Yes' if summary['has_inside_nat'] else 'No',
                    'Yes' if summary['has_outside_nat'] else 'No',
                    'Yes' if summary['has_dynamic_nat'] else 'No',
                    summary['total_nat_rules'],
                    summary['acl_count'],
                    'Yes' if summary['bgp_configured'] else 'No',
                    summary['static_route_count'],
                    summary['ipsec_profiles'],
                    summary['migration_complexity']
                )
                item = self.summary_tree.insert('', 'end', values=values)
                
                complexity = summary['migration_complexity']
                if complexity >= 5:
                    self.summary_tree.item(item, tags=('high',))
                elif complexity >= 3:
                    self.summary_tree.item(item, tags=('medium',))
                else:
                    self.summary_tree.item(item, tags=('low',))
                    
            self.summary_status_label.config(text=f"Status: Sorted by complexity (high to low)")
            
        except Exception as e:
            self.summary_status_label.config(text=f"Status: Error sorting - {str(e)}")
    
    def on_summary_double_click(self, event):
        """Show detailed VRF information when double-clicked"""
        item = self.summary_tree.selection()[0] if self.summary_tree.selection() else None
        if item:
            vrf_name = self.summary_tree.item(item, 'values')[0]
            self.selected_vrf.set(vrf_name)
            self.preview_vrf()  # Show the detailed config
            self.notebook.select(self.preview_text.master)  # Switch to Cisco IOS Preview tab

    def on_bgp_double_click(self, event):
        """Show detailed VRF information when double-clicked"""
        item = self.bgp_tree.selection()[0] if self.bgp_tree.selection() else None
        if item:
            vrf_name = self.bgp_tree.item(item, 'values')[0]
            self.selected_vrf.set(vrf_name)
            self.preview_vrf()  # Show the detailed config
            self.notebook.select(self.preview_text.master)  # Switch to Cisco IOS Preview tab

    def on_vpn_double_click(self, event):
        """Show detailed VRF information when double-clicked"""
        item = self.vpn_tree.selection()[0] if self.vpn_tree.selection() else None
        if item:
            vrf_name = self.vpn_tree.item(item, 'values')[0]
            self.selected_vrf.set(vrf_name)
            self.preview_vrf()  # Show the detailed config
            self.notebook.select(self.preview_text.master)  # Switch to Cisco IOS Preview tab

    def on_traffic_double_click(self, event):
        """Show detailed VRF information when double-clicked"""
        item = self.traffic_tree.selection()[0] if self.traffic_tree.selection() else None
        if item:
            vrf_name = self.traffic_tree.item(item, 'values')[0]
            self.selected_vrf.set(vrf_name)
            self.preview_vrf()  # Show the detailed config
            self.notebook.select(self.preview_text.master)  # Switch to Cisco IOS Preview tab
    
    def export_vrf_summary(self):
        """Export VRF summary to CSV"""
        if not hasattr(self, 'parser') or not self.parser:
            messagebox.showerror("Error", "No VRF data available to export")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            title="Export VRF Summary"
        )
        
        if not filename:
            return
        
        try:
            summaries = self.parser.get_vrf_summaries()
            
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                # Write header
                writer.writerow([
                    'VRF Name', 'Site Role', 'Tunnel Interfaces', 'Total Interfaces',
                    'Inside NAT', 'Outside NAT', 'Dynamic NAT', 'Total NAT Rules',
                    'ACL Count', 'BGP Configured', 'Static Routes', 'IPSec Profiles',
                    'Migration Complexity', 'Export Timestamp'
                ])
                
                # Write data
                for summary in summaries:
                    writer.writerow([
                        summary['vrf_name'],
                        summary['site_role'],
                        summary['tunnel_interfaces'],
                        summary['interface_count'],
                        'Yes' if summary['has_inside_nat'] else 'No',
                        'Yes' if summary['has_outside_nat'] else 'No',
                        'Yes' if summary['has_dynamic_nat'] else 'No',
                        summary['total_nat_rules'],
                        summary['acl_count'],
                        'Yes' if summary['bgp_configured'] else 'No',
                        summary['static_route_count'],
                        summary['ipsec_profiles'],
                        summary['migration_complexity'],
                        datetime.now().isoformat()
                    ])
            
            messagebox.showinfo("Success", f"VRF summary exported to {filename}")
            
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))


###############END VRF Summary tab functions

#
    def disconnect_device(self):
        """Disconnect from current device."""
        # Check if we have a connection
        if not hasattr(self, 'parser') or not self.parser:
            messagebox.showinfo("Info", "Not currently connected to any device")
            return
        
        if not hasattr(self.parser, 'current_connection') or not self.parser.current_connection:
            messagebox.showinfo("Info", "Not currently connected to any device")
            return
        
        response = messagebox.askyesno(
            "Disconnect",
            "Are you sure you want to disconnect from the device?"
        )
        
        if response:
            try:
                self.parser.current_connection.disconnect()
                self.log_message("Disconnected from device")
                messagebox.showinfo("Success", "Disconnected successfully")
            except Exception as e:
                self.log_message(f"Error during disconnect: {str(e)}")
                messagebox.showerror("Error", f"Disconnect failed: {str(e)}")
            finally:
                self.parser.current_connection = None
                
                # Update main connection status label
                self.update_connection_status()
                
                # Update command executor tab status
                if hasattr(self, 'command_executor_tab'):
                    self.command_executor_tab.current_connection = None
                    self.command_executor_tab.update_connection_status()
