#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Command Executor Tab Add-on for Router Configuration Parser
Integrates with existing JumphostConnector and creates a tab interface

@author: Bobby Hathiramani
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from datetime import datetime
from threading import Thread


class CommandExecutorTab:
    """
    Command executor tab that integrates with existing connections.
    Uses JumphostConnector for device connections.
    """
    
    # Pre-defined troubleshooting commands organized by category
    COMMAND_CATEGORIES = {
        'Interface': [
            'show ip interface brief',
            'show interface description',
            'show interfaces | include line protocol',
        ],
        'Routing': [
            'show ip route',
            'show ip route summary',
            'show ip bgp all summary',
            'show ip bgp all neighbors',
            'show ip protocols',
        ],
        'VPN/IPSec': [
            'show crypto session',
            'show crypto session brief',
            'show crypto ipsec sa',
            'show crypto ikev2 sa',
            'show crypto ipsec transform-set',
        ],
        'System': [
            'show version',
            'show running-config',
            'show startup-config',
            'show inventory',
            'show processes cpu sorted',
            'show memory statistics',
        ],
        'Troubleshooting': [
            'show logging',
            'show ip sla statistics',
            'show track',
            'show cdp neighbors detail',
            'show ip arp',
            'show ip route vrf *',
        ]
    }
    
    def __init__(self, notebook, parser_ui):
        """
        Initialize the command executor tab.
        
        Args:
            notebook: The ttk.Notebook widget to add the tab to
            parser_ui: Reference to RouterConfigParserUI instance
        """
        self.notebook = notebook
        self.parser_ui = parser_ui
        self.command_history = []
        self.history_index = -1
        self.current_connection = None
        
        # Create the tab
        self.create_tab()
        
    def create_tab(self):
        """Create the command executor tab interface with improved layout."""
        # Main frame for the tab
        self.frame = ttk.Frame(self.notebook)
        self.notebook.add(self.frame, text="Command Executor")
        
        # Use PanedWindow to split top controls and output
        self.paned_window = ttk.PanedWindow(self.frame, orient=tk.VERTICAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Top section: All controls
        top_section = ttk.Frame(self.paned_window)
        self.paned_window.add(top_section, weight=0)
        
        # Bottom section: Output
        bottom_section = ttk.Frame(self.paned_window)
        self.paned_window.add(bottom_section, weight=1)
        
        # Build top section (compact)
        self.create_command_input_section(top_section)
        self.create_quick_commands_section(top_section)
        self.create_vrf_troubleshooting_section(top_section)
        
        # Build bottom section (expandable)
        self.create_output_section(bottom_section)
        
#    def create_command_input_section(self, parent):
#        """Create the command input section (compact)."""
#        input_frame = ttk.LabelFrame(parent, text="Command Input", padding=5)
#        input_frame.pack(fill=tk.X, pady=(0, 5))
#        
#        # First row: Command entry
#        entry_row = ttk.Frame(input_frame)
#        entry_row.pack(fill=tk.X)
#        
#        ttk.Label(entry_row, text="Command:").pack(side=tk.LEFT, padx=(0, 5))
#        
#        self.command_entry = ttk.Entry(entry_row, width=60)
#        self.command_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
#        self.command_entry.bind('<Return>', lambda e: self.execute_command())
#        self.command_entry.bind('<Up>', lambda e: self.history_up())
#        self.command_entry.bind('<Down>', lambda e: self.history_down())
#        
#        # Buttons on same row
#        ttk.Button(entry_row, text="Execute", 
#                  command=self.execute_command, width=10).pack(side=tk.LEFT, padx=2)
#        ttk.Button(entry_row, text="Clear", 
#                  command=self.clear_entry, width=8).pack(side=tk.LEFT, padx=2)
#        ttk.Button(entry_row, text="Disconnect", 
#                  command=self.disconnect_device, width=10).pack(side=tk.LEFT, padx=2)
#        
#        # Second row: Connection status
#        status_row = ttk.Frame(input_frame)
#        status_row.pack(fill=tk.X, pady=(5, 0))
#        
#        ttk.Label(status_row, text="Device:").pack(side=tk.LEFT, padx=(0, 5))
#        self.status_label = ttk.Label(status_row, 
#                                      text="Not connected - Select device and click 'Get Config'",
#                                      foreground='red')
#        self.status_label.pack(side=tk.LEFT)



    def create_command_input_section(self, parent):
        """Create the command input section (compact)."""
        input_frame = ttk.LabelFrame(parent, text="Command Input", padding=5)
        input_frame.pack(fill=tk.X, pady=(0, 5))
        
        # First row: Command entry
        entry_row = ttk.Frame(input_frame)
        entry_row.pack(fill=tk.X)
        
        ttk.Label(entry_row, text="Command:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.command_entry = ttk.Entry(entry_row, width=30)
        self.command_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.command_entry.bind('<Return>', lambda e: self.execute_command())
        self.command_entry.bind('<Up>', lambda e: self.history_up())
        self.command_entry.bind('<Down>', lambda e: self.history_down())
        
        # Buttons on same row
        ttk.Button(entry_row, text="Execute", 
                  command=self.execute_command, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(entry_row, text="Clear", 
                  command=self.clear_entry, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Button(entry_row, text="Disconnect", 
                  command=self.disconnect_device, width=8).pack(side=tk.LEFT, padx=2)
        
        # Second row: Connection status
        status_row = ttk.Frame(input_frame)
        status_row.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Label(status_row, text="Device:").pack(side=tk.LEFT, padx=(0, 5))
        self.status_label = ttk.Label(status_row, 
                                      text="Not connected - Select device and click 'Get Config'",
                                      foreground='red')
        self.status_label.pack(side=tk.LEFT)
        
    
    def create_quick_commands_section(self, parent):
        """Create the quick commands section with dropdown and listbox (compact)."""
        quick_frame = ttk.LabelFrame(parent, text="Quick Commands", padding=5)
        quick_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Single row with category dropdown and listbox side by side
        content_row = ttk.Frame(quick_frame)
        content_row.pack(fill=tk.X)
        
        # Left side: Category dropdown (narrow)
        left_side = ttk.Frame(content_row)
        left_side.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        
        ttk.Label(left_side, text="Category:").pack(anchor=tk.W, pady=(0, 2))
        
        self.category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(
            left_side,
            textvariable=self.category_var,
            values=list(self.COMMAND_CATEGORIES.keys()),
            state='readonly',
            width=15
        )
        self.category_combo.pack(fill=tk.X)
        self.category_combo.bind('<<ComboboxSelected>>', self.on_category_selected)
        
        # Set default category
        if self.COMMAND_CATEGORIES:
            self.category_combo.current(0)
        
        # Right side: Commands listbox (takes remaining space)
        right_side = ttk.Frame(content_row)
        right_side.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        ttk.Label(right_side, text="Commands (double-click to execute):").pack(anchor=tk.W, pady=(0, 2))
        
        # Listbox with scrollbar - reduced height
        list_container = ttk.Frame(right_side)
        list_container.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL)
        self.commands_listbox = tk.Listbox(
            list_container,
            height=4,  # Reduced from 6 to 4
            yscrollcommand=scrollbar.set,
            font=('Courier', 9),
            selectmode=tk.SINGLE
        )
        scrollbar.config(command=self.commands_listbox.yview)
        
        self.commands_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True) 
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind events
        self.commands_listbox.bind('<Double-Button-1>', self.on_command_double_click)
        self.commands_listbox.bind('<<ListboxSelect>>', self.on_command_select)
        
        # Populate initial commands
        self.on_category_selected()

    
    def create_vrf_troubleshooting_section(self, parent):
        """Create VRF troubleshooting command generation section (compact)."""
        trouble_frame = ttk.LabelFrame(parent, text="VRF Troubleshooting", padding=5)
        trouble_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Single row with all controls
        controls_row = ttk.Frame(trouble_frame)
        controls_row.pack(fill=tk.X)
        
        ttk.Label(controls_row, text="VRF:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.vrf_var = tk.StringVar()
        self.vrf_combo = ttk.Combobox(
            controls_row,
            textvariable=self.vrf_var,
            state='readonly',
            width=20
        )
        self.vrf_combo.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(
            controls_row,
            text="Generate Commands",
            command=self.generate_vrf_troubleshooting,
            width=18
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            controls_row,
            text="Execute All",
            command=self.execute_all_troubleshooting,
            width=12
        ).pack(side=tk.LEFT, padx=2)
        
        # Update VRF list when parser is available
        self.update_vrf_list()
    
    def on_category_selected(self, event=None):
        """Handle category selection - populate commands list."""
        category = self.category_var.get()
        if not category or category not in self.COMMAND_CATEGORIES:
            return
        
        # Clear current list
        self.commands_listbox.delete(0, tk.END)
        
        # Add commands for selected category
        commands = self.COMMAND_CATEGORIES[category]
        for cmd in commands:
            self.commands_listbox.insert(tk.END, cmd)
    
    def on_command_select(self, event=None):
        """Handle command selection - put in entry field."""
        selection = self.commands_listbox.curselection()
        if not selection:
            return
        
        command = self.commands_listbox.get(selection[0])
        self.command_entry.delete(0, tk.END)
        self.command_entry.insert(0, command)
    
    def on_command_double_click(self, event=None):
        """Handle double-click on command - execute it."""
        selection = self.commands_listbox.curselection()
        if not selection:
            return
        
        command = self.commands_listbox.get(selection[0])
        self.execute_quick_command(command)
    
    def create_output_section(self, parent):
        """Create the output display section."""
        output_frame = ttk.LabelFrame(parent, text="Command Output", padding=5)
        output_frame.pack(fill=tk.BOTH, expand=True)
        
        # Output text widget with dark theme
        self.output_text = scrolledtext.ScrolledText(
            output_frame,
            wrap=tk.WORD,
            font=('Courier', 9),
            bg='#1e1e1e',
            fg='#d4d4d4',
            insertbackground='white',
            height=15
        )
        self.output_text.pack(fill=tk.BOTH, expand=True)
        
        # Configure text tags for colored output
        self.output_text.tag_configure('command', foreground='#4ec9b0', font=('Courier', 9, 'bold'))
        self.output_text.tag_configure('separator', foreground='#608b4e')
        self.output_text.tag_configure('error', foreground='#f48771')
        self.output_text.tag_configure('timestamp', foreground='#9cdcfe')
        self.output_text.tag_configure('success', foreground='#4ec9b0')
        
        # Button frame
        button_frame = ttk.Frame(output_frame)
        button_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Button(button_frame, text="Clear Output", 
                  command=self.clear_output).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Save Output", 
                  command=self.save_output).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Copy Output", 
                  command=self.copy_output).pack(side=tk.LEFT, padx=2)
        
    def update_connection_status(self):
        """Update the connection status label."""
        device = self.parser_ui.selected_device.get()
        if device and self.current_connection:
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
    
    def set_connection(self, connection):
        """
        Set the active connection from JumphostConnector.
        
        Args:
            connection: Netmiko connection object
        """
        self.current_connection = connection
        self.update_connection_status()
        self.update_vrf_list()  # Update VRF list when connection is established
        self.append_output("Connection established. Ready to execute commands.\n", 'success')
    
    def execute_command(self):
        """Execute the command entered in the entry field."""
        command = self.command_entry.get().strip()
        if not command:
            return
        
        # Check if we have a connection
        if not self.current_connection:
            device = self.parser_ui.selected_device.get()
            if device:
                self.append_output(
                    f"Not connected to {device}. Click 'Get Config' button first to establish connection.\n", 
                    'error'
                )
            else:
                self.append_output(
                    "No device selected. Please select a device from the dropdown and click 'Get Config'.\n", 
                    'error'
                )
            return
        
        # Add to history
        if not self.command_history or self.command_history[-1] != command:
            self.command_history.append(command)
        self.history_index = len(self.command_history)
        
        # Display command
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.append_output(f"\n[{timestamp}] ", 'timestamp')
        self.append_output(f"{command}\n", 'command')
        self.append_output("=" * 80 + "\n", 'separator')
        
        # Execute in thread to prevent UI blocking
        def execute_thread():
            try:
                self.parser_ui.log_message(f"Executing command: {command}")
                output = self.current_connection.send_command(command, read_timeout=30)
                self.append_output(output + "\n")
                self.parser_ui.log_message(f"Command executed successfully")
            except Exception as e:
                error_msg = f"Error executing command: {str(e)}\n"
                self.append_output(error_msg, 'error')
                self.parser_ui.log_message(f"Command execution error: {str(e)}")
        
        Thread(target=execute_thread, daemon=True).start()
        
        # Clear entry
        self.command_entry.delete(0, tk.END)
    
    def execute_quick_command(self, command):
        """Execute a quick command button."""
        self.command_entry.delete(0, tk.END)
        self.command_entry.insert(0, command)
        self.execute_command()
    
    def append_output(self, text, tag=None):
        """
        Append text to output window.
        
        Args:
            text: Text to append
            tag: Optional text tag for styling
        """
        self.output_text.insert(tk.END, text, tag)
        self.output_text.see(tk.END)
        self.output_text.update_idletasks()
    
    def clear_output(self):
        """Clear the output text."""
        self.output_text.delete(1.0, tk.END)
    
    def clear_entry(self):
        """Clear the command entry."""
        self.command_entry.delete(0, tk.END)
    
    def save_output(self):
        """Save output to file."""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[
                ("Text Files", "*.txt"),
                ("Log Files", "*.log"),
                ("All Files", "*.*")
            ],
            title="Save Command Output"
        )
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(self.output_text.get(1.0, tk.END))
                messagebox.showinfo("Success", f"Output saved to {filename}")
                self.parser_ui.log_message(f"Command output saved to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {str(e)}")
    
    def copy_output(self):
        """Copy output to clipboard."""
        try:
            self.frame.clipboard_clear()
            self.frame.clipboard_append(self.output_text.get(1.0, tk.END))
            messagebox.showinfo("Success", "Output copied to clipboard")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy: {str(e)}")
    
    def history_up(self):
        """Navigate up in command history."""
        if not self.command_history:
            return
        
        if self.history_index > 0:
            self.history_index -= 1
            self.command_entry.delete(0, tk.END)
            self.command_entry.insert(0, self.command_history[self.history_index])
    
    def history_down(self):
        """Navigate down in command history."""
        if not self.command_history:
            return
        
        if self.history_index < len(self.command_history) - 1:
            self.history_index += 1
            self.command_entry.delete(0, tk.END)
            self.command_entry.insert(0, self.command_history[self.history_index])
        elif self.history_index == len(self.command_history) - 1:
            self.history_index = len(self.command_history)
            self.command_entry.delete(0, tk.END)
    
    def disconnect_device(self):
        """Disconnect from the current device."""
        if not self.current_connection:
            messagebox.showinfo("Info", "Not currently connected to any device")
            return
        
        response = messagebox.askyesno(
            "Disconnect",
            "Disconnect from device?\n\nYou'll need to click 'Get Config' again to reconnect."
        )
        
        if response:
            try:
                self.current_connection.disconnect()
                self.parser_ui.log_message("Disconnected from device")
                self.append_output("\n[DISCONNECTED] Connection closed by user.\n", 'error')
            except Exception as e:
                self.parser_ui.log_message(f"Error during disconnect: {str(e)}")
            finally:
                self.current_connection = None
                # Clear connection in parser too
                if hasattr(self.parser_ui.parser, 'current_connection'):
                    self.parser_ui.parser.current_connection = None
                self.update_connection_status()
                messagebox.showinfo("Disconnected", "Device disconnected successfully")
    
    def update_vrf_list(self):
        """Update the VRF dropdown list from parser."""
        if not hasattr(self.parser_ui, 'parser') or not self.parser_ui.parser:
            self.vrf_combo['values'] = []
            return
        
        if not hasattr(self.parser_ui.parser, 'config_parser'):
            self.vrf_combo['values'] = []
            return
        
        vrfs = list(self.parser_ui.parser.config_parser.vrfs.keys())
        self.vrf_combo['values'] = vrfs
        
        if vrfs:
            self.vrf_combo.current(0)
    
    def generate_vrf_troubleshooting(self):
        """Generate troubleshooting commands for selected VRF."""
        vrf_name = self.vrf_var.get()
        
        if not vrf_name:
            messagebox.showwarning("No VRF Selected", "Please select a VRF first")
            return
        
        if not hasattr(self.parser_ui, 'parser') or not self.parser_ui.parser:
            messagebox.showerror("Error", "No parser available. Please fetch config first.")
            return
        
        try:
            # Generate commands using the parser's method
            commands = self.parser_ui.parser.generate_troubleshooting_commands(vrf_name)
            
            # Display in output
            self.append_output(f"\n{'='*80}\n", 'separator')
            self.append_output(f"Troubleshooting Commands for VRF: {vrf_name}\n", 'command')
            self.append_output(f"{'='*80}\n", 'separator')
            self.append_output(commands + "\n")
            
            self.parser_ui.log_message(f"Generated troubleshooting commands for VRF {vrf_name}")
            
            # Offer to save
            response = messagebox.askyesno(
                "Commands Generated",
                f"Troubleshooting commands generated for VRF {vrf_name}.\n\n"
                "Would you like to save them to a file?"
            )
            
            if response:
                self.save_troubleshooting_commands(vrf_name, commands)
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate commands: {str(e)}")
            self.parser_ui.log_message(f"Error generating troubleshooting commands: {str(e)}")
    
    def save_troubleshooting_commands(self, vrf_name, commands):
        """Save troubleshooting commands to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"troubleshooting_{vrf_name}_{timestamp}.txt"
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=default_filename,
            filetypes=[
                ("Text Files", "*.txt"),
                ("All Files", "*.*")
            ],
            title="Save Troubleshooting Commands"
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(commands)
                messagebox.showinfo("Success", f"Commands saved to {filename}")
                self.parser_ui.log_message(f"Troubleshooting commands saved to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {str(e)}")
    
    def execute_all_troubleshooting(self):
        """Execute all troubleshooting commands for selected VRF."""
        vrf_name = self.vrf_var.get()
        
        if not vrf_name:
            messagebox.showwarning("No VRF Selected", "Please select a VRF first")
            return
        
        if not self.current_connection:
            messagebox.showerror("Not Connected", "Please connect to device first")
            return
        
        response = messagebox.askyesno(
            "Execute All Commands",
            f"This will execute all troubleshooting commands for VRF {vrf_name}.\n\n"
            "This may take several minutes.\n\n"
            "Continue?"
        )
        
        if not response:
            return
        
        try:
            # Generate commands
            commands_text = self.parser_ui.parser.generate_troubleshooting_commands(vrf_name)
            
            # Parse commands (skip comments and empty lines)
            commands = []
            for line in commands_text.split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    commands.append(line)
            
            self.append_output(f"\n{'='*80}\n", 'separator')
            self.append_output(f"Executing {len(commands)} commands for VRF {vrf_name}\n", 'command')
            self.append_output(f"{'='*80}\n\n", 'separator')
            
            # Execute in thread
            def execute_thread():
                for i, cmd in enumerate(commands, 1):
                    try:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        self.append_output(f"[{timestamp}] ({i}/{len(commands)}) ", 'timestamp')
                        self.append_output(f"{cmd}\n", 'command')
                        
                        output = self.current_connection.send_command(cmd, read_timeout=30)
                        self.append_output(output + "\n\n")
                        
                    except Exception as e:
                        self.append_output(f"Error: {str(e)}\n\n", 'error')
                        self.parser_ui.log_message(f"Error executing '{cmd}': {str(e)}")
                
                self.append_output(f"{'='*80}\n", 'separator')
                self.append_output("All commands executed\n", 'success')
                self.parser_ui.log_message(f"Completed executing troubleshooting commands for VRF {vrf_name}")
            
            Thread(target=execute_thread, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to execute commands: {str(e)}")
            self.parser_ui.log_message(f"Error executing troubleshooting commands: {str(e)}")


# ============================================================================
# INTEGRATION INSTRUCTIONS FOR RouterConfigParserUI
# ============================================================================
"""
To integrate this tab into your existing RouterConfigParserUI:

1. ADD IMPORT at top of file (after line 20):
   from command_executor_tab import CommandExecutorTab

2. ADD to create_widgets() method, after line 2221 where other tabs are created:
   # Create command executor tab
   self.command_executor_tab = CommandExecutorTab(self.notebook, self)

3. MODIFY your connect_to_device() method to share the connection.
   Find the method around line 2700 and ADD after successful connection:
   
   # Share connection with command executor tab
   if hasattr(self, 'command_executor_tab'):
       self.command_executor_tab.set_connection(connection)
       self.command_executor_tab.update_connection_status()

4. SPECIFICALLY, in the connect_to_device() method, find where it says:
   connection = self.parser.jumphost_connector.connect_via_jumphost(device)
   
   And AFTER that line, ADD:
   # Share connection with command executor
   if hasattr(self, 'command_executor_tab'):
       self.command_executor_tab.set_connection(connection)

That's it! The command executor will now:
- Appear as a tab like VPN Status and BGP Status
- Use the same connection established by "Get Config"
- Update status automatically when device is selected/connected
"""