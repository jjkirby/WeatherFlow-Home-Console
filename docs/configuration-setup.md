# Configure PiConsole and Home Telemetry

Use the INI to identify the weather station and choose how its console looks. Use the TOML to identify indoor sensors and choose which one supplies a reading. A working PiConsole installation already has its INI. Adding a Bluetooth sensor only requires configuring telemetry and pointing the display at it.

| File | Location | Who creates and reads it |
| --- | --- | --- |
| `wfpiconsole.ini` | PiConsole's working directory, usually alongside `main.py` | PiConsole creates it on first launch, reads or migrates it on later launches, and saves display settings here. Treat it as private because it can contain API keys. |
| Telemetry TOML | CLI default `~/.config/home-telemetry/config.toml`. Mac H5074 launcher default `~/.config/home-telemetry/govee-h5074.toml`. Pi service default `/etc/home-telemetry/config.toml`. | The setup commands below create or deploy it. The collector reads it on startup. The console integration uses it to enable the indoor binding. Personal configs live outside Git so an update preserves them. |
| SQLite database | `[collector].database` in the TOML | The collector creates the schema and writes observations. PiConsole reads it. Use the same absolute path for both processes. |
| `collector.env` | Optional `/etc/home-telemetry/collector.env` on the Pi | The supplied systemd unit loads process environment overrides from this file. A local H5074 needs no API key or environment file. |

## Create the telemetry TOML

From the fork checkout with Python 3.11+ and the project virtual environment active, install `python -m pip install -e '.[govee]'` for H5074. Use the exact advertised name from the [Govee guide](providers/govee.md). For the Mac launcher, run:

```bash
CFG="$HOME/.config/home-telemetry/govee-h5074.toml"
python -m home_telemetry --config "$CFG" config init \
  --sensor-name Govee_H5074_XXXX --room "Living room" --use-indoor-binding
python -m home_telemetry --config "$CFG" config validate
./scripts/start-mac.sh
```

Replace `Govee_H5074_XXXX` with your unit's name. The generator writes the H5074 provider, stable logical IDs, room, database, panel source, and indoor temperature binding. The flag adds `[console]` with `use_indoor_binding = true`; omitting it leaves WeatherFlow AIR in charge of the built-in Indoor column. Enable **Menu → Settings → Display → Indoor temperature** to show the column. For additional rooms, fallback sources, sampling and retention, see the [TOML field reference](configuration.md).

If you already have a working TOML, keep it and run only the validation command. Both `init` and `deploy` validate before installing, create missing parent directories, and accept repeat installs of identical content. They refuse to replace a different existing file. For a deliberate change, generate to a new filename, compare it with the live file, then edit the live config and restart the processes that read it.

For a hardware-free trial, use a separate destination and database:

```bash
python -m home_telemetry --config ~/.config/home-telemetry/demo.toml config init --mock
python -m home_telemetry --config ~/.config/home-telemetry/demo.toml run
```

The Python commands also work in PowerShell. Pass paths directly with `"$HOME/.config/home-telemetry/demo.toml"` instead of using a Bash variable assignment. The Mac launcher is specific to macOS.

## Deploy the telemetry TOML on a Raspberry Pi

Run these commands **on the Pi** after installing the fork with the Govee extra in the service virtual environment and creating the service user/group as described in [Deployment](deployment.md#raspberry-pi-collector). Generate into the service location in one command:

```bash
sudo install -d -o home-telemetry -g home-telemetry -m 0750 /etc/home-telemetry
sudo -u home-telemetry /opt/home-telemetry/venv/bin/python -m home_telemetry \
  --config /etc/home-telemetry/config.toml config init \
  --sensor-name Govee_H5074_XXXX --room "Living room" \
  --database /var/lib/home-telemetry/telemetry.db --use-indoor-binding
```

To deploy a prepared TOML instead, transfer it privately to the target, set its database path for the Pi, and place the input in a location readable by the service account. Substitute this command for `config init`:

```bash
sudo -u home-telemetry /opt/home-telemetry/venv/bin/python -m home_telemetry \
  --config /etc/home-telemetry/config.toml config deploy /path/to/prepared.toml
```

Set the installed TOML to group-readable (`sudo chmod 0640 /etc/home-telemetry/config.toml`). The PiConsole display account needs membership in the telemetry group and read access to the database directory, SQLite database and WAL sidecars. Group membership changes take effect at the next session. The supplied collector unit sets its config path and creates the state directory when started. Set these variables **in the display launch environment** as well:

```ini
HOME_TELEMETRY_CONFIG=/etc/home-telemetry/config.toml
HOME_TELEMETRY_DB=/var/lib/home-telemetry/telemetry.db
```

With the collector unit installed, run `sudo systemctl restart home-telemetry`, then check the service's actual config:

```bash
sudo -u home-telemetry /opt/home-telemetry/venv/bin/python -m home_telemetry \
  --config /etc/home-telemetry/config.toml status
```

Look for a fresh observation and the selected indoor binding before switching the display. Installing a config leaves the existing PiConsole service and station INI in place. Mac hardware verification is documented in the [developer notes](developer-notes.md). The Pi service workflow still needs a live deployment test.

## How PiConsole creates and populates the INI

Launch `python main.py` from the checkout in a terminal with the display dependencies installed. Before opening its window, PiConsole checks for `wfpiconsole.ini` **in the current directory**. When it is missing, the terminal wizard offers a minimal demo file or a guided station setup. For a live station choose **no** at the minimal-file prompt.

- **WebSocket + REST or UDP + REST.** Supply the credentials and station information requested by the wizard, including the WeatherFlow personal access token, station/device selection, and CheckWX key for METAR. PiConsole uses WeatherFlow responses to populate or verify station metadata and fills other fields from defaults.
- **UDP only.** The wizard asks for local station/device details, location, elevation and units. This mode uses local broadcasts. The REST credentials are skipped.
- **Display preferences.** The wizard writes sections for station, units, display, panels and system settings. Adjust panels, units and time format through the console menu. The station timezone controls the day used for indoor extrema.

For an existing Pi, copy its working INI into the new checkout before the first launch. With the new checkout as your current directory, use `cp -n /path/to/old/checkout/wfpiconsole.ini ./wfpiconsole.ini` and restrict access to the display account. Preserve the old checkout as a backup. On launch, PiConsole may verify station data or migrate and rewrite the copy, prompting for new fields. Do this first launch interactively before enabling unattended startup. This INI carries host-specific hardware and display settings, so use the Pi's own copy when moving between Pi checkouts. See the [upstream station wizard instructions](../README.md#configure-and-run-weatherflow-piconsole).

## Other runtime settings

- **Custom panels.** Install the Python/KV pair under `user/` to use the separate Indoor Climate panel. See [Deployment](deployment.md#optional-piconsole-panel) for an installation with existing custom panels.
- **Kivy display settings.** PiConsole generates `~/.kivy/config_wfpiconsole.ini` using Kivy’s base configuration and the PiConsole display settings. The Mac launcher supplies density and font scaling for the verified desktop layout.
- **Configuration lookup.** For the CLI, explicit `--config PATH` takes precedence over `HOME_TELEMETRY_CONFIG`, then the CLI default applies. The Mac launcher accepts a config path as its first argument and obtains the DB from that TOML. Use absolute database paths on a service installation. Keep keys, personal station settings and databases out of commits.
