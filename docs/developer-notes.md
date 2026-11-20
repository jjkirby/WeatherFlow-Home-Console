# WeatherFlow Home Console Developer Notes

## What this fork adds

Pete Davis’s WeatherFlow PiConsole displays observations from a Tempest or Smart Home Weather Station. It already supports local UDP, WeatherFlow cloud services, and custom display panels. WeatherFlow Home Console uses that existing panel interface to show readings from indoor sensors in multiple rooms alongside the station’s weather.

The collector writes readings to SQLite. The Indoor Climate panel shows each configured sensor’s temperature, humidity, battery (when available), and last-seen time. The built-in Temperature panel can also follow the configured `indoor` binding for its current value and daily extrema. WeatherFlow AIR remains the default. The H5074 has been tested on macOS. Mock providers support hardware-free development, and Nest SDM is a scaffold.

![PiConsole Temperature panel showing Govee indoor temperature, daily extrema and times beside Tempest outdoor temperature](images/govee-indoor-temperature.png)

On the Mac Studio, the built-in panel showed **72.2°F indoors**, a low of **72.1°F at 14:22**, and a high of **73.1°F at 14:06**. The outdoor Tempest reading was **62.2°F**. The times follow the station timezone and console time format.

## Choose your starting point

| Goal | Start here |
|---|---|
| Install the original console on a Raspberry Pi or configure a weather station | [README compatibility](../README.md#compatibility) and [installation instructions](../README.md#installation-instructions) |
| Run the fork on a development machine | Follow the checkout and mock test below. Add the optional desktop display to see the full result. |
| Deploy the fork on a Pi | Use the [fork deployment guide](deployment.md). Deploy a tested fork revision; the stock updater targets upstream. |
| Add a sensor type | Start with [provider development](provider-development.md). PiConsole’s [custom panel API](../README.md#advanced-custom-panels) covers changes to the display itself. |

Run the commands below from the fork’s repository root after cloning.

## Check out the project

Use the `feature/home-telemetry` branch. Use a revision that includes the H5074 provider and Mac launcher for the live test. If you already have the fork open in VS Code, check your branch with `git branch --show-current` and continue to the next section.

```bash
git clone --branch feature/home-telemetry https://github.com/jjkirby/WeatherFlow-Home-Console.git
cd WeatherFlow-Home-Console
```

## Set up Python

Use Python 3.11 or 3.12 for the telemetry extension. Choose the section for your shell, then continue with the shared install and tests.

### Windows (PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` wherever the shared commands say `python`. This works with your existing execution policy. For upstream Windows setup details, see [Advanced Windows Installation](../README.md#advanced-installation-windows).

### Linux (Bash)

Use an installed Python 3.11 or 3.12 interpreter. For example, with Python 3.12:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

On Ubuntu or Debian, if creation fails because `ensurepip` is unavailable, install the matching distribution package (for example, `python3.12-venv` for distribution Python 3.12). Use a graphical desktop session for the optional display test. The collector and CLI also run from a terminal.

### macOS (zsh or Bash)

The six-panel display test used Python 3.12.5 and Kivy 2.3.2 on a Mac Studio.

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
```

### Install the framework on all platforms

```sh
python -m pip install -e .
python -m home_telemetry providers list
```

The provider list should show `mock` as installed. Activate this environment in each new terminal.

## Run the offline tests

```bash
python -m unittest discover -s tests
python -m home_telemetry --config deploy/home-telemetry.toml.example config validate
```

The H5074 and built-in Indoor integration passed 46 offline tests on both Python 3.11 and 3.12. The configuration check should print `Configuration valid`. These checks require no Tempest token, Bluetooth sensor, Nest credentials, or open PiConsole window.

## Smoke-test the mock collector

Use a development account or a disposable copy of the example configuration with its database path changed if you already collect real telemetry. The example used the default database at `~/.local/share/home-telemetry/telemetry.db` in the Mac test. Keep the collector and display pointed at the same database when testing the panel.

In **Terminal 1**, activate the virtual environment and start the collector. Leave it running.

```bash
python -m home_telemetry --config deploy/home-telemetry.toml.example run
```

In **Terminal 2**, open the same repository, activate the virtual environment, and inspect the running collector.

```bash
python -m home_telemetry --config deploy/home-telemetry.toml.example status
python -m home_telemetry --config deploy/home-telemetry.toml.example selection explain indoor
python -m home_telemetry --config deploy/home-telemetry.toml.example selection explain upstairs_humidity
```

Expect `Collector: running`, three healthy and fresh mock providers, and `Selected: demo-main` for `indoor`. The upstairs binding should select `demo-upstairs`. The Govee and Nest entries should remain disabled. If the output says `stale`, check Terminal 1 and compare the last-observation timestamps in successive `status` calls.

## Open the desktop display

Install the display dependencies in the same virtual environment. Check the repository README for dependency changes when working from a newer revision.

```bash
python -m pip install 'kivy[base]' websockets numpy pytz tzlocal ephem packaging pyOpenSSL certifi
python -c 'import kivy, websockets, numpy, pytz, tzlocal, ephem, packaging, OpenSSL, certifi; print(kivy.__version__)'
```

For live outdoor weather, complete [PiConsole’s first-run station setup](../README.md#configure-and-run-weatherflow-piconsole), or use a copy of your own existing `wfpiconsole.ini`. Keep the original as a backup because startup can migrate the copy. Station credentials belong in the private INI. Indoor providers and room bindings use [Home Telemetry’s TOML configuration](configuration.md).

Confirm Git ignores the runtime files before adding credentials or installing the custom panel. Each listed path should have a matching rule.

```bash
git check-ignore -v wfpiconsole.ini user/customPanels.py user/customPanels.kv .venv/
```

Install the panel before launching PiConsole. If either destination already exists, inspect and back up the existing pair before updating it. On macOS or Linux, the following commands preserve existing files.

```bash
cp -n deploy/customPanels.py user/customPanels.py
cp -n deploy/customPanels.kv user/customPanels.kv
ls -l user/customPanels.py user/customPanels.kv
```

On Windows, run this in PowerShell from the repository root. It copies the pair only when both destinations are free.

```powershell
if ((Test-Path user/customPanels.py) -or (Test-Path user/customPanels.kv)) {
    Write-Warning 'Existing panel files found. Review the pair before installing.'
} else {
    Copy-Item deploy/customPanels.py, deploy/customPanels.kv -Destination user/
}
```

Keep Terminal 1 running the collector. In Terminal 2 on Windows or Linux, launch the display with `python main.py`. On macOS, use this launch command if Retina scaling makes labels overlap.

```bash
KIVY_METRICS_DENSITY=1 KIVY_METRICS_FONTSCALE=1 python main.py
```

1. Confirm the regular weather panels show your station data and a recent observation.
2. Open **Menu → Settings → Secondary Panels**. Choose an unused slot, such as Panel Two, and scroll the selector to `IndoorClimate`.
3. Close Settings and click the **Indoor Climate** button on the main display. The panel should show fresh mock readings with temperature, humidity, battery, and last-seen time. Scroll inside the panel to see the remaining rooms.

If `IndoorClimate` is missing from the selector, verify both deployed files are in `user/` and restart PiConsole. If it appears but shows stale readings, check the collector and confirm that both processes use the same database path.

## Switch from the mock demo to a real sensor

Exit the demo display and stop its collector. Follow the [H5074 setup](providers/govee.md) to install Bluetooth support, discover the advertised name, and create the live configuration. On macOS, follow the [one-command launch](deployment.md#macos) to run both processes. Open the Temperature panel and compare the Indoor column with the screenshot above. Use the custom Indoor Climate panel to check source, freshness, and battery.

## Finish the test

Close PiConsole and press **Control-C** in the collector terminal. SQLite data remains on disk for the next run. Check `git status --short` before committing. Provider source, tests, deployment templates and developer documentation belong in Git. Keep the runtime INI, personal TOML, API tokens, local databases and virtual environments private.

End-to-end testing on native Windows and Linux remains open for this fork. When checking either platform, record the OS, Python version, test count, selected source, and whether the panel displays fresh readings. The Mac Studio test covered the six-panel layout with live Tempest weather, the mock collector, live H5074 data, and the one-command launcher. Raspberry Pi service operation and the one- and four-panel layouts still need verification. Track hardware-specific progress in the [Govee notes](providers/govee.md) and [Nest notes](providers/nest.md).
