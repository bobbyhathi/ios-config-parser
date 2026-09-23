"""
Loads and saves user-configurable app settings from settings.json in the
project root: which optional Notebook tabs are enabled, and the initial
configuration source chosen in the Settings window (settings_window.py) --
either a devices.json path (live devices) or a static config file. Falls
back to sane defaults for anything missing, unreadable, or invalid, so a
hand-edited or stale settings.json can never crash the app.
"""
import json
import os

from tab_registry import TAB_ORDER

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

DEFAULT_SETTINGS = {
    "enabled_tabs": list(TAB_ORDER),
    "input_source": "device",  # "device" (devices.json) or "file" (static config)
    "config_file": "devices.json",
    "input_file": "",
}


def load_settings(path=None):
    path = path or SETTINGS_FILE
    if not os.path.exists(path):
        return dict(DEFAULT_SETTINGS)
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_SETTINGS)

    # Drop unknown / stale tab ids rather than failing on them.
    enabled = data.get("enabled_tabs", DEFAULT_SETTINGS["enabled_tabs"])
    enabled = [t for t in enabled if t in TAB_ORDER]

    input_source = data.get("input_source", DEFAULT_SETTINGS["input_source"])
    if input_source not in ("device", "file"):
        input_source = DEFAULT_SETTINGS["input_source"]

    return {
        "enabled_tabs": enabled,
        "input_source": input_source,
        "config_file": data.get("config_file") or DEFAULT_SETTINGS["config_file"],
        "input_file": data.get("input_file", DEFAULT_SETTINGS["input_file"]),
    }


def save_settings(settings, path=None):
    path = path or SETTINGS_FILE
    with open(path, "w") as f:
        json.dump(settings, f, indent=2)
