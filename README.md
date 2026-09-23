# Router Configuration Parser

A desktop tool for parsing Cisco IOS/IOS-XE router configurations into
per-VRF data, monitoring live VPN/BGP state over SSH, and re-generating
clean, deployable Cisco IOS config extracts and JSON exports per VRF.

Built for day-to-day SD-WAN / VRF-lite operations work: pulling a VRF's
full config (definition, interfaces, NAT, ACLs, BGP, route-maps,
prefix-lists, IKEv2/IPsec crypto) back out of an 8,000+ line production
router config, in a form that's actually reviewable and redeployable.

## What it does

- **Parses** a Cisco IOS running-config (from a file or a live device) into
  structured per-VRF data: VRF definitions, interfaces, NAT rules, ACLs,
  BGP config, route-maps/prefix-lists, IP SLA/tracking, and IKEv2/IPsec
  crypto (keyrings, policies, profiles, transform-sets).
- **Classifies** each VRF's site role (Primary/Secondary) from BGP
  community tags set in its route-maps.
- **Connects to live devices** over SSH (directly, or via a jumphost with
  Paramiko port-forwarding + Netmiko) to pull running config and check
  VPN/BGP status.
- **Re-generates output** per VRF: a clean Cisco IOS config extract, a JSON
  export, and an IPsec/VPN rollback script.
- **Monitors** live VPN sessions, IPsec SAs, BGP neighbor state and traffic
  counters across one or more connected devices at once.

See [`sample_configs/sample-edge-router-config.txt`](sample_configs/sample-edge-router-config.txt)
for a fully synthetic example input, and [`vrf_outputs/`](vrf_outputs/) for
the output the tool actually produced from it (Cisco IOS extract, JSON, and
the global IKEv2/IPsec summary) -- see [Sample data](#sample-data) below.

## Architecture

The original single-file prototype has been split along its existing class
boundaries into focused modules:

| Module | Responsibility |
|---|---|
| `config_parser.py` | Low-level config-block extraction (NAT pools, IP SLA, tracking, generic `crypto ...` blocks) |
| `vrf_manager.py` | VRF definitions, interfaces, NAT/static routes, BGP, route-maps/prefix-lists, crypto-to-VRF mapping, site-role classification |
| `vpn_monitor.py` | Parses live `show crypto session` / `show crypto ipsec sa` output into VPN status + traffic-flow data |
| `bgp_manager.py` | Parses live BGP status output per VRF |
| `jumphost_connector.py` | SSH connectivity: direct, or via jumphost port-forwarding |
| `router_config_parser.py` | The non-GUI engine tying the above together (`RouterConfigParser`). Usable headlessly with no `tkinter` import at all. |
| `command_executor_addon.py` | Ad-hoc command execution tab |
| `multi_device_vrf_analysis_tab.py` | Multi-device VRF/VPN comparison tab |
| `tab_registry.py` / `settings.py` | The modular tab system (see below) |
| `settings_window.py` | The pre-flight Settings window (tabs + config source) |
| `ui.py` | The Tkinter front-end (`RouterConfigParserUI`) |
| `main.py` | Entry point -- runs Settings, then the main window (see below) |

`router_config_parser.py` has no GUI dependency, so the parsing engine can
be driven headlessly (see the snippet under [Usage](#headless-use)) --
handy for batch-processing a directory of config backups, or for tests.

## Modular tabs & the Settings window

Only two tabs are core to the parse -> preview workflow and always shown:
**Log** and **Cisco IOS VRF Preview**. Everything else is optional,
live-device-oriented functionality that not every user wants open:

- VPN Status
- BGP Status
- VPN Traffic Flow
- VRF Summary
- Command Executor
- Multi-Device Analysis

Running `main.py` opens a **Settings window** first, where you choose which
of these to show and where the initial data comes from -- a `devices.json`
inventory (live devices) or a static config file. Clicking **Launch**
writes that choice to [`settings.json`](settings.json) and opens the main
window already built with exactly those tabs -- there's no "restart to see
your tab change" step, because the main window doesn't exist yet when you
make the choice. Disabling a tab means its module isn't even imported --
e.g. if you leave Multi-Device Analysis off, `multi_device_vrf_analysis_tab.py`'s
dependencies are never loaded.

To reconfigure later, use **Settings > Change Settings... (restart)** in
the main window's menu bar -- it closes the main window and reopens
Settings, pre-filled with your current choices.

```json
{
  "enabled_tabs": ["vrf_summary", "command_executor"],
  "input_source": "file",
  "config_file": "devices.json",
  "input_file": "sample_configs/sample-edge-router-config.txt"
}
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate        # .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

`tkinter` ships with the Python standard library on Windows/Linux. On
macOS with Homebrew Python you'll also need:

```bash
brew install python-tk@3.11   # match your python3's minor version
```

Copy the example device inventory and fill in real credentials (this file
is gitignored -- never commit it):

```bash
cp devices.json.example devices.json
```

## Usage

```bash
python3 main.py
```

This opens the **Settings window**: pick Live Device or Config File (with
Browse), and which optional tabs you want, then click **Launch**. The main
window opens pre-configured -- either pick a device from the dropdown and
click **Get Config**, or use **Browse**/**Reload** in the main window's
Config File row to load a different file without restarting. From there,
use **Cisco IOS Preview**, **Generate Output**, or any enabled optional
tab. **Settings > Change Settings... (restart)** takes you back to the
Settings window at any time.

### Headless use

```python
from router_config_parser import RouterConfigParser

rcp = RouterConfigParser(output_dir="vrf_outputs")
ok, vrf_names = rcp.parse_configuration("path/to/running-config.txt")
```

## Sample data

`sample_configs/sample-edge-router-config.txt` is a **fully synthetic**
Cisco IOS config -- fictional hostnames and partner names, IPs drawn only
from the IANA/IETF documentation ranges (RFC 5737 / RFC 1918), and
obviously-fake pre-shared keys. It exercises the full parsing path: 3
VRFs, VTI tunnels, per-VRF BGP with route-map community tags (so both
Primary and Secondary site-role classification are demonstrated), NAT,
ACLs, IP SLA/tracking, and IKEv2/IPsec crypto.

`vrf_outputs/` is the **real, tool-generated output** from running the
parser against that sample config -- not hand-written -- so it's an
accurate preview of what the tool produces: a per-VRF Cisco IOS extract
under `deployed/all_vrf/<timestamp>/`, per-VRF JSON under `json/`, and the
global IKEv2/IPsec summary.

**Never** replace this sample with a real device config. A real running
config contains live pre-shared keys, password hashes and internal
addressing -- treat `devices.json` and any real config backups as secrets
and keep them out of version control (see `.gitignore`).

## License

MIT -- see [LICENSE](LICENSE).
