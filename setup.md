# Set up WeatherFlow Home Console

Run setup from the **root of the extracted fork or checkout**, the directory containing `main.py`. Use your normal desktop account. Setup supports two uses of the same codebase: **development**, with a temporary mock sensor and automated tests, and **deployment**, with persistent station settings, sensor readings, and a live console. Native Windows has its own launcher. Both launchers use the shared Python configuration wizard.

| Goal | macOS, Linux or Raspberry Pi OS | Windows PowerShell |
|---|---|---|
| Inspect host and Python, without installing anything | `./scripts/setup.sh --check` | `.\scripts\setup-windows.cmd -Check` |
| Prepare a development environment and run the mock smoke test | `./scripts/setup.sh --smoke-test` | `.\scripts\setup-windows.cmd -SmokeTest` |
| Configure a new deployment or reuse an existing one | `./scripts/setup.sh` | `.\scripts\setup-windows.cmd` |

**Clean Pi quick start:** Start Raspberry Pi OS Desktop, open a terminal in the fork, and run `./scripts/setup.sh`. Choose Govee or mock. At the existing-station-INI prompt, press Enter for PiConsole’s station wizard and choose guided setup for live weather. Have your Tempest token available. Verify the touchscreen preview before enabling startup at desktop login. Enable desktop autologin on the Pi if the display should start unattended after reboot.

## Host policy

“Target” means a platform the installer is designed for. Validate graphics, sensors and boot behavior on the actual deployment machine. Upstream PiConsole compatibility and this extension’s Python requirements both apply.

| Platform | How setup treats it |
|---|---|
| Raspberry Pi 3 B/B+, 4 B or 5 B | Targets Bookworm 32/64-bit and Trixie 64-bit desktop images. Checks device-tree model, release and userspace bitness. Debian release IDs are also used by 64-bit Pi OS; the ID alone cannot certify an official image. |
| Known incompatible Pi configurations | Stops on original Zero/Zero W, Buster on Pi, and 32-bit Debian-family Trixie on Pi. Zero 2 W and other unlisted models are unverified. Upstream supports official touchscreens or HDMI equivalents; an SPI-only display is incompatible and must be identified by the operator. |
| Linux PC | Ubuntu 22.04+ is an upstream desktop target. Other distributions can try setup after an explicit prompt. Install a suitable CPython separately when the distribution default is too old. WSL, containers, SSH and remote desktops can have different graphics and Bluetooth access from the host. |
| macOS | Targets Apple Silicon and Intel desktop environments. The original H5074 display path was demonstrated on Apple Silicon. The wizard probes the actual Python environment, graphics and optional Bluetooth. |
| Windows | Native launcher targets x64 Windows 11 desktop (build 22000 or later), with x64 CPython 3.11 or 3.12. Other Windows CPU architectures are outside this launcher’s target. Run from PowerShell or Command Prompt. |
| Other kernels | Unix launcher exits before creating the environment. Git Bash on Windows directs you to the Windows launcher. |

## What the installer does

1. **Checks the host and interpreter.** Unix setup checks the checkout, existing venv, CPython 3.11+, SQLite and TLS. A clean Unix setup prefers 3.12, then 3.11, then a suitable `python3`. To select a specific installed interpreter, use `PYTHON=/path/to/python ./scripts/setup.sh` when creating the venv. Windows checks the registered interpreters, launcher and PATH, and can offer a per-user Python installation using WinGet. A missing Python in check-only mode is an actionable result; run normal setup for the install offer.
2. **Builds an isolated environment.** Installs the project editable in the checkout’s `.venv`, installs its desktop dependencies, runs `pip check`, imports the required modules and verifies a station timezone. Keep the checkout in place while using its venv. First installation needs network access to the applicable package repositories.
3. **Creates or reuses the telemetry TOML.** Choose a Govee H5074 or mock thermometer, sensor name, room and optional built-in Indoor binding. The wizard validates the file. It offers an existing configuration first, including a legacy home-directory TOML. A Govee deployment exercises the Bluetooth scanner under the current user account. A successful scan start and a fresh observation from your specific device are separate checks.
4. **Checks the display and configures the station.** Desktop setup creates a brief Kivy/OpenGL window. Linux without a graphical session defers that test. Reuse an existing private INI or press Enter to let PiConsole create and populate one. Setup also installs the supplied custom panel pair when it can preserve local customizations.
5. **Previews deployment.** With the preview accepted, the collector writes to SQLite and the wizard waits for a fresh indoor reading, then starts the display. Verify outdoor station readings, indoor temperature, today’s high/low and their times. Quit via **Menu → Exit**. On a Pi, optional service switching requires a running systemd installation, `systemctl` and `sudo`. Confirm the working preview before switching an existing boot setup.
6. **Prints the relaunch command.** Use the exact config path it prints. The paired launcher runs the collector alongside the display and stops its own collector when the display exits. For continuous independent collection, use the service deployment guide.

## Files and paths

| File | Location and ownership |
|---|---|
| Personal sensor TOML | Windows: `%APPDATA%\home-telemetry`. Mac: `~/.config/home-telemetry`. Linux/Pi: `$XDG_CONFIG_HOME/home-telemetry`, defaulting to `~/.config/home-telemetry`. Typical file names are `govee-h5074.toml` and `demo.toml`. Set `HOME_TELEMETRY_CONFIG` to offer a specific file. |
| Sensor database | The TOML’s `[collector].database` is authoritative. New defaults use `%LOCALAPPDATA%\home-telemetry` on Windows, `~/.local/share/home-telemetry` on Mac, or `$XDG_DATA_HOME/home-telemetry` on Linux/Pi (defaults under `~/.local/share`). Existing database paths are preserved. |
| Station INI | `wfpiconsole.ini` beside `main.py`. Contains station credentials and display preferences. Keep it private. |
| Python | Unix: `.venv/bin/python`. Windows: `.venv\Scripts\python.exe`. Create a separate environment on each host. |

## Development and acceptance tests

Start with the mock smoke command above on a clean machine. It installs dependencies, creates temporary settings and a database, runs the collector, verifies the selected indoor reading, checks shutdown, and removes the temporary data. It needs neither a Tempest token nor a sensor. Then run the offline suite:

- Unix: `.venv/bin/python -m unittest discover -s tests`
- Windows: `.\.venv\Scripts\python.exe -m unittest discover -s tests`

For deployment, run the interactive wizard next. Verify a real display and sensor, then restart the launcher. For unattended Pi use, reboot and confirm both live readings return after desktop login. A passing mock test leaves those hardware checks outstanding.

## Known issues and recovery

| Symptom | What to do |
|---|---|
| Missing Python, venv or ensurepip | On eligible Debian-family releases, setup can offer the exact apt command for system Python or the matching versioned venv package. Review it before authorizing. If apt cannot find a package, check repositories and refresh their indexes. A custom interpreter needs its own working venv support. On macOS install a suitable CPython. On Windows use the WinGet offer or install x64 Python 3.12. |
| Existing venv is incomplete or belongs to another OS | Rename it, leave your TOML and SQLite data in place, and rerun. Use a writable local checkout. NTFS on Windows supports the hard links used to publish configuration safely. |
| pip cannot install a binary wheel or imports fail | Record the first failing package, Python version, OS and CPU. Wheel availability varies, particularly on 32-bit ARM and new Python releases. Try a project-tested interpreter (3.11 or 3.12) where available. Source builds can require a compiler and additional development libraries specific to the failed package. |
| Kivy cannot open a window | Run on the graphical desktop. Check the GPU driver and SDL2/OpenGL support. On Debian-family hosts, a failed window probe can offer missing GL/EGL/Mesa runtime packages and retry. Windows and macOS graphics drivers must be addressed on the host. |
| Bluetooth unavailable or no observations | Turn on Bluetooth, use a BLE adapter, close Govee Home on your phone, and verify the advertised H5074 name. On Mac check Bluetooth privacy permission for the launching app. On Windows check Device Manager. On Linux setup reports system bus/controller diagnostics when available and can offer missing BlueZ/D-Bus packages. Check `systemctl status bluetooth` on systemd hosts and run as the intended user. |
| Writer lock or stale reading | Stop the earlier collector using that database. Check the selected TOML and sensor. First-day highs/lows cover the observations collected so far. |
| Pi running an older deployment | Use a separate checkout. Back up its private INI. Confirm a working preview before changing startup. See the Pi recovery instructions below for restoring the previous service. |

See [wizard, Pi autostart and rollback](docs/setup.md), [TOML and INI configuration](docs/configuration-setup.md), [independent service deployment](docs/deployment.md), [Windows walkthrough](docs/windows-setup.md), and [upstream hardware compatibility](docs/upstream-piconsole.md#compatibility).
