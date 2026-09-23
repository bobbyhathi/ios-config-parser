"""
Pre-flight Settings window, shown by main.py before the main app window
opens. Lets the user choose:

  1. Which optional tabs to show (see tab_registry.py) -- Log and Cisco IOS
     VRF Preview are always shown and aren't listed here.
  2. Where the initial data comes from: a devices.json inventory (for live
     device connections) or a static config file -- the same mutually
     exclusive choice the main window's "Configuration Source" controls
     make, just relocated here so it's decided before the main window (and
     its tabs) get built.

Clicking Launch saves these to settings.json and closes the window; main.py
then reads self.settings / self.launched to decide what to do next. The
main window keeps its own Browse/Reload controls (ui.py) for switching
files mid-session -- this window only sets the *starting* point.
"""
import tkinter as tk
from tkinter import ttk, filedialog

from settings import load_settings, save_settings
from tab_registry import TAB_REGISTRY, TAB_ORDER


class SettingsWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Router Configuration Parser -- Settings")
        self.root.resizable(False, False)

        # Set by _launch(); main.py checks these after root.mainloop() returns.
        self.launched = False
        self.settings = None

        saved = load_settings()
        self.input_source = tk.StringVar(value=saved["input_source"])
        self.config_file = tk.StringVar(value=saved["config_file"])
        self.input_file = tk.StringVar(value=saved["input_file"])
        self._saved_enabled_tabs = set(saved["enabled_tabs"])

        self._build()

    def _build(self):
        pad = {"padx": 14, "pady": 6}

        intro = ttk.Label(
            self.root,
            text="Choose your configuration source and which optional tabs to show,\n"
                 "then click Launch to open the app.",
            justify=tk.LEFT,
        )
        intro.pack(anchor=tk.W, **pad)

        # --- Configuration source -------------------------------------
        source_frame = ttk.LabelFrame(self.root, text="Configuration Source", padding=10)
        source_frame.pack(fill=tk.X, **pad)
        source_frame.columnconfigure(0, weight=1)

        ttk.Radiobutton(
            source_frame, text="Live Device (devices.json inventory)",
            variable=self.input_source, value="device", command=self._sync_source_state,
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W)
        self.config_file_entry = ttk.Entry(source_frame, textvariable=self.config_file, width=42)
        self.config_file_entry.grid(row=1, column=0, sticky=tk.EW, padx=(22, 6), pady=(2, 10))
        ttk.Button(source_frame, text="Browse", command=self._browse_devices_json).grid(row=1, column=1, pady=(2, 10))

        ttk.Radiobutton(
            source_frame, text="Config File (parse a saved backup)",
            variable=self.input_source, value="file", command=self._sync_source_state,
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W)
        self.input_file_entry = ttk.Entry(source_frame, textvariable=self.input_file, width=42)
        self.input_file_entry.grid(row=3, column=0, sticky=tk.EW, padx=(22, 6), pady=(2, 0))
        self.input_file_browse = ttk.Button(source_frame, text="Browse", command=self._browse_input_file)
        self.input_file_browse.grid(row=3, column=1, pady=(2, 0))

        # --- Optional tabs -----------------------------------------------
        tabs_frame = ttk.LabelFrame(self.root, text="Optional Tabs", padding=10)
        tabs_frame.pack(fill=tk.X, **pad)
        ttk.Label(
            tabs_frame, text="Log and Cisco IOS VRF Preview are always shown.", foreground="gray",
        ).pack(anchor=tk.W, pady=(0, 6))

        self.tab_vars = {}
        for tab_id in TAB_ORDER:
            info = TAB_REGISTRY[tab_id]
            var = tk.BooleanVar(value=tab_id in self._saved_enabled_tabs)
            self.tab_vars[tab_id] = var
            row = ttk.Frame(tabs_frame)
            row.pack(fill=tk.X, pady=2, anchor=tk.W)
            ttk.Checkbutton(row, text=info["label"], variable=var, width=22).pack(side=tk.LEFT)
            ttk.Label(row, text=info["description"], foreground="gray").pack(side=tk.LEFT, padx=8)

        ttk.Button(self.root, text="Launch", command=self._launch).pack(pady=(6, 16))

        self._sync_source_state()

    def _sync_source_state(self):
        """Only the Config File row is mutually-exclusive with device mode --
        devices.json stays editable either way, matching the main window
        (its device inventory isn't tied to which source you're parsing)."""
        if self.input_source.get() == "file":
            self.input_file_entry.config(state=tk.NORMAL)
            self.input_file_browse.config(state=tk.NORMAL)
        else:
            self.input_file_entry.config(state=tk.DISABLED)
            self.input_file_browse.config(state=tk.DISABLED)

    def _browse_devices_json(self):
        file = filedialog.askopenfilename(title="Select devices.json", filetypes=[("JSON", "*.json"), ("All Files", "*.*")])
        if file:
            self.config_file.set(file)

    def _browse_input_file(self):
        file = filedialog.askopenfilename(title="Select Config File", filetypes=[("Text", "*.txt"), ("All Files", "*.*")])
        if file:
            self.input_file.set(file)

    def _launch(self):
        settings = {
            "enabled_tabs": [t for t in TAB_ORDER if self.tab_vars[t].get()],
            "input_source": self.input_source.get(),
            "config_file": self.config_file.get(),
            "input_file": self.input_file.get(),
        }
        save_settings(settings)
        self.settings = settings
        self.launched = True
        self.root.destroy()
