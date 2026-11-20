# Deployment

## macOS

Use Python 3.11 or later for the standard-library TOML parser. The MockProvider and tests need neither Kivy nor network access. Follow the [quick start](architecture.md) to collect mock data. For future Bluetooth plugins, macOS CoreBluetooth provides host-specific UUIDs. Linux BlueZ can expose BLE addresses. Keep a logical `device_id` in configuration and manage scanner identity separately for each host. [Bleak macOS backend](https://bleak.readthedocs.io/en/stable/backends/macos.html) · [Bleak Linux backend](https://bleak.readthedocs.io/en/stable/backends/linux.html)

## Raspberry Pi collector

1. Create a dedicated unprivileged `home-telemetry` account and group. Install the fork’s telemetry package into a Python 3.11+ virtual environment at `/opt/home-telemetry/venv`. Keep `/opt/home-telemetry` readable to the service account. For example, run `/opt/home-telemetry/venv/bin/python -m pip install /path/to/fork` as the account managing that environment.
2. Copy the public example to `/etc/home-telemetry/config.toml`. Set `collector.database` to `/var/lib/home-telemetry/telemetry.db`. Give the service account read access to the configuration. If needed later, put actual credentials in `/etc/home-telemetry/collector.env` with restricted permissions. The example environment file shows the expected path variables.
3. Install the [unit template](../deploy/home-telemetry.service) under `/etc/systemd/system/`. Check account and paths before enabling it. Run `sudo systemctl daemon-reload`, then `sudo systemctl enable --now home-telemetry`. Inspect service messages with `journalctl -u home-telemetry`. Use `home-telemetry status` with the deployed configuration.
4. Future BLE collectors need a working controller and BlueZ, with D-Bus access under the service account. Verify the adapter, rfkill state, and permissions on the Pi before using live sensors. Mock uses none of those services.

## Optional PiConsole panel

Install the telemetry package in PiConsole’s virtual environment as well. Only the snapshot reader runs in that process. Put the PiConsole user in the telemetry group, with directory traversal and read access to the database and its SQLite sidecars. Set `HOME_TELEMETRY_DB=/var/lib/home-telemetry/telemetry.db` for the PiConsole process, for example with a systemd drop-in. Verify a read as that user while the collector is running.

Install `deploy/customPanels.py` and `deploy/customPanels.kv` at `user/customPanels.py` and `user/customPanels.kv` in PiConsole. If those live files already contain panels, merge the new class definitions and KV rules into them. On restart, choose **IndoorClimate** in the primary or secondary panel settings. The panel scrolls through configured sources, including multiple devices from a provider, and uses PiConsole’s temperature units and time format. It updates with mock data and displays missing, busy, incompatible, stale, and provider health states. PiConsole and the collector can be stopped or restarted independently.

The stock PiConsole updater can switch branches and clean the checkout. Update the fork by fetching upstream, merging or rebasing into your feature branch, and deploying that tested revision explicitly. Reinstall the extension package and panel sources as needed. Back up your panel sources and keep runtime data and secrets outside the checkout.
