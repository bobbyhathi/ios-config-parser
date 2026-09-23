"""
Registry of the *optional* Notebook tabs in the Router Configuration Parser
GUI.

The "Log" and "Cisco IOS VRF Preview" tabs are core to the parse -> preview
workflow and are always built. Everything below is optional, live-device
oriented functionality that a given user may not want open by default (e.g.
someone who only ever parses offline config backups has no use for the
Command Executor or Multi-Device Analysis tabs). Which of these are shown
is controlled by settings.json (see settings.py), editable either by hand
or via the in-app "Manage Tabs..." dialog.

Each entry's "build" callable receives the running RouterConfigParserUI
instance and is responsible for attaching its tab to ui.notebook. Imports
of the tab's own module are deliberately deferred to inside the builder, so
a disabled tab's dependencies are never even imported.
"""


def _build_command_executor(ui):
    from command_executor_addon import CommandExecutorTab
    ui.command_executor_tab = CommandExecutorTab(ui.notebook, ui)


def _build_multi_device_analysis(ui):
    from multi_device_vrf_analysis_tab import SimpleMultiDeviceAnalysis
    ui.md_analysis = SimpleMultiDeviceAnalysis(ui)
    ui.md_analysis.create_multi_device_tab()


TAB_REGISTRY = {
    "vpn_status": {
        "label": "VPN Status",
        "description": "Live crypto session / IPsec SA status for the connected device.",
        "build": lambda ui: ui.create_vpn_status_tab(),
    },
    "bgp_status": {
        "label": "BGP Status",
        "description": "Per-VRF BGP neighbor and route summary from a live device.",
        "build": lambda ui: ui.create_bgp_status_tab(),
    },
    "vpn_traffic": {
        "label": "VPN Traffic Flow",
        "description": "Interface/tunnel traffic counters for active VPN sessions.",
        "build": lambda ui: ui.create_vpn_traffic_tab(),
    },
    "vrf_summary": {
        "label": "VRF Summary",
        "description": "Table summarizing every VRF parsed from the loaded config.",
        "build": lambda ui: ui.create_vrf_summary_tab(),
    },
    "command_executor": {
        "label": "Command Executor",
        "description": "Run ad-hoc / quick show commands against a connected device.",
        "build": _build_command_executor,
    },
    "multi_device_analysis": {
        "label": "Multi-Device Analysis",
        "description": "Compare VRF/VPN state across several connected devices at once.",
        "build": _build_multi_device_analysis,
    },
}

# Display / build order for optional tabs.
TAB_ORDER = [
    "vpn_status",
    "bgp_status",
    "vpn_traffic",
    "vrf_summary",
    "command_executor",
    "multi_device_analysis",
]
