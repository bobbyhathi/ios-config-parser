"""
Entry point for the Router Configuration Parser GUI.

Shows the Settings window first (settings_window.py) -- choose which
optional tabs to show and the initial configuration source (devices.json
for live devices, or a static config file). Clicking Launch there opens
the main app window (ui.py) already configured with that choice, so no
restart-and-lose-your-place is needed for a tab change: the main window
is only built *after* Settings closes.

Settings > Change Settings... in the main window's menu bar comes back
here (via app.wants_settings) to reconfigure and relaunch. Each phase runs
its own sequential mainloop() -- one Tk root at a time, never nested.
"""
import tkinter as tk

from settings_window import SettingsWindow
from ui import RouterConfigParserUI


def _run_settings():
    """Show the Settings window and block until it closes.

    Returns the chosen settings dict if the user clicked Launch, or None if
    they closed the window without launching (e.g. the [x] button).
    """
    root = tk.Tk()
    window = SettingsWindow(root)
    root.mainloop()
    return window.settings if window.launched else None


def _run_main(settings):
    """Show the main app window, pre-configured from `settings`, and block
    until it closes. Returns True if the user chose Settings > Change
    Settings... (so main() should loop back to _run_settings())."""
    root = tk.Tk()
    app = RouterConfigParserUI(root)

    app.input_source.set(settings.get("input_source", "device"))
    app.config_file.set(settings.get("config_file", "devices.json"))
    if settings.get("input_source") == "file" and settings.get("input_file"):
        app.input_file.set(settings["input_file"])
    # config_file may differ from what __init__ already loaded -- reload
    # against the path actually chosen in Settings.
    app.load_device_config()

    root.mainloop()
    return app.wants_settings


def main():
    settings = _run_settings()
    while settings is not None:
        wants_settings_again = _run_main(settings)
        settings = _run_settings() if wants_settings_again else None


if __name__ == "__main__":
    main()
