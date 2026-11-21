# First run on Windows 11

Use a full checkout of the WeatherFlow Home Console feature branch including the Windows launcher, H5074 provider, config generator and wizard. Extract a downloaded source ZIP first. Choose a local NTFS folder that your account can write to. A folder such as `Documents\WeatherFlow-Home-Console` works. The first run downloads packages, so it needs internet access. The native Windows test target is x64 CPython 3.12 or 3.11.

## Clean-machine test

In File Explorer, open the extracted folder **containing main.py**. Type `powershell` into the address bar and press Enter. Run:

```powershell
.\scripts\setup-windows.cmd -SmokeTest
```

The launcher looks for an existing Windows virtual environment and checks its interpreter. On a new machine it checks the Python launcher, registered interpreters, common per-user locations, and PATH. If it needs Python, it offers to install Python 3.12 x64 with WinGet. If WinGet is unavailable, install Microsoft App Installer or the x64 Windows installer for Python 3.12 from python.org, then repeat the command.

A passing smoke test prints **PASS**. For dependency checks, file locations and recovery steps, see the [platform guide](../setup.md).

## Configure the actual console

In the same PowerShell window, run:

```powershell
.\scripts\setup-windows.cmd
```

Follow the [wizard](setup.md). Choose **no** when asked about Govee to try the mock display first, or choose **yes** for the real H5074. Govee mode installs and imports Bleak. Turn on Bluetooth, close Govee Home on the phone, and put the H5074 near the PC. If you created a mock TOML and later want Govee, enter a new TOML path at the wizard prompt.

PiConsole’s first-run wizard creates `wfpiconsole.ini` in the checkout. A minimal/demo INI lets you preview the layout; use guided station setup for live Tempest data. Check the [configuration guide](configuration-setup.md) for both INI and TOML settings. Windows uses your own profile directory for the default TOML and database.

Use the `-StartConfig` command printed by the wizard for subsequent launches. For example:

```powershell
.\scripts\setup-windows.cmd -StartConfig "$env:APPDATA\home-telemetry\govee-h5074.toml"
```

For the full offline regression suite after setup:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Record the Python version, smoke-test result, and whether the graphical display and Bluetooth scan worked. The launcher has not yet been verified on a physical Windows machine.
