# WeatherFlow PiConsole

<!-- weatherflow-fork-intro -->
## WeatherFlow Home Console enhancements

Display live Tempest weather alongside indoor temperature from a Govee H5074 Bluetooth sensor. This fork extends Pete Davis’s WeatherFlow PiConsole. The Indoor column can show the current reading and today’s low and high with their times. Existing WeatherFlow indoor AIR installations keep their default source.

## Install and run

Download and extract this fork or clone its `feature/home-telemetry` branch. Open a terminal in the folder containing `main.py` and run the command for your machine.

| Platform | Command |
| --- | --- |
| Raspberry Pi OS Desktop, macOS, or Linux desktop | `./scripts/setup.sh` |
| Windows 11 x64 · PowerShell | `.\scripts\setup-windows.cmd` |

Follow the prompts to select your Govee or try a simulated sensor. Reuse your station settings or choose guided station setup for live weather. On a Pi, run from the desktop to see the preview. **[Setup guide and troubleshooting](setup.md)**

## Power users and developers

You can develop with a simulated sensor or deploy a live display on a Pi or desktop. The Govee H5074 has been verified on a Mac Studio. Google Nest is planned. The guides below cover testing, deployment, and adding providers.

| File | When to use it |
| --- | --- |
| [README.md](README.md) | Install this fork and find a guide. |
| [setup.md](setup.md) | Check host compatibility, Python and native libraries. Find config and data paths or troubleshoot setup. |
| [docs/setup.md](docs/setup.md) | Walk through station setup, preview the display, and enable or roll back Pi desktop autostart. |
| [docs/windows-setup.md](docs/windows-setup.md) | Prepare a clean Windows PC, check Python and WinGet, and verify the native display and Bluetooth. |
| [docs/upstream-piconsole.md](docs/upstream-piconsole.md) | Pete Davis’s original console instructions, hardware compatibility, panel API, updates, and credits. |
| [docs/developer-notes.md](docs/developer-notes.md) | Inspect the mock collector and a live display, compare readings, and reproduce the Mac hardware test. |
| [docs/architecture.md](docs/architecture.md) | Trace observations from a provider through the collector and SQLite to the display. |
| [docs/configuration-setup.md](docs/configuration-setup.md) | Generate, validate, or deploy a private sensor TOML and populate the station INI. |
| [docs/configuration.md](docs/configuration.md) | Look up TOML fields, room bindings, fallback rules, and CLI commands. |
| [docs/database.md](docs/database.md) | Inspect the SQLite schema, locking, snapshot reader, and retention rules. |
| [docs/deployment.md](docs/deployment.md) | Run the collector as a service, configure display access, and maintain an installation. |
| [docs/providers/README.md](docs/providers/README.md) | Check provider availability and find the individual integration guides. |
| [docs/providers/govee.md](docs/providers/govee.md) | Identify an H5074, diagnose missing Bluetooth readings, and verify the indoor display. |
| [docs/providers/mock.md](docs/providers/mock.md) | Configure simulated readings, stale data, and failures for testing. |
| [docs/providers/nest.md](docs/providers/nest.md) | Review the planned Google Nest integration, authorization requirements, and implementation status. |
| [docs/providers/weatherflow_air.md](docs/providers/weatherflow_air.md) | Understand the built-in WeatherFlow AIR source and the proposed collector plugin. |
| [docs/provider-development.md](docs/provider-development.md) | Implement, register, and test an additional indoor sensor provider. |
| [.github/ISSUE_TEMPLATE/bug_report.md](.github/ISSUE_TEMPLATE/bug_report.md) | Report a reproducible problem and include the relevant environment details. |
<!-- /weatherflow-fork-intro -->

<a href="https://www.buymeacoffee.com/peted.davis" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>

The WeatherFlow PiConsole is a Python console that displays the data collected
by a WeatherFlow Tempest or Smart Home Weather Station. The console uses either
the WeatherFlow REST API and websocket service or the local UDP connection to
stream data from your station in real time, including the 3-second rapid wind
updates. In UDP only mode, the console requires no connection to the internet
once installation is complete.

The console is fully supported for Raspberry Pi 3 Model B/B+, Raspberry Pi 4 
and Raspberry Pi 5 running the 64 bit version of Raspberry Pi OS Trixie
or the 32/64 bit version of Raspberry Pi OS Bookworm. It can be run on 
earlier models, but no direct support is provided for these systems. It is 
not compatible with Raspberry Pi Zero or Zero W. For full compatibility 
details, see below.

For a list of supported features and screenshots of the console in action,
please checkout the WeatherFlow community forums: https://community.weatherflow.com/t/weatherflow-piconsole/20083

https://weatherflow.com/tempest-weather-system/<br/>
https://community.weatherflow.com/

## Indoor telemetry in this fork

WeatherFlow Home Console extends Pete Davis’s PiConsole with a separate indoor sensor collector and local SQLite history. Choose a sensor for the built-in Temperature panel to display its current reading and daily low and high with their times. The optional Indoor Climate panel shows individual sensors and freshness.

**Run on Mac.** After [first-time setup](docs/developer-notes.md) and [H5074 configuration](docs/providers/govee.md), run `./scripts/start-mac.sh` from the checkout. See the [verified display](docs/developer-notes.md#what-this-fork-adds) and [launcher behavior](docs/deployment.md#macos).

## Contents

**[Compatibility](#compatibility)**<br>
**[Installation Instructions](#installation-instructions)**<br>
**[Update Instructions](#update-instructions)**<br>
**[Auto-Start Instructions](#auto-start-instructions)**<br>
**[Advanced: Custom Panels](#advanced-custom-panels)**<br>
**[Advanced: Device Replacement](#advanced-device-replacement)**<br>
**[Advanced: Windows Installation](#advanced-installation-windows)**<br>
**[Credits](#credits)**<br>

## Compatibility

### Raspberry Pi

The console is fully supported for Raspberry Pi 3 Model B/B+, Raspberry Pi 4 and 
Raspberry Pi 5 running the 64 bit version of Raspberry Pi OS Trixie or the 32/64 
bit legacy version of Raspberry Pi OS Bookworm. It can be run on earlier models, 
but no direct support is provided for these systems. It is not compatible with 
the 32 bit version of Raspberry Pi OS Trixie or Raspberry Pi Zero or Zero W. 
While the console is compatible with Raspberry Pi 3, the graphics hardware on 
this model is ageing and performance of the console can be sluggish. It is 
recommended to use a Pi 4 or above. The console is not compatible with 
Raspberry Pi OS Buster.

The console is compatible with the Raspberry Pi Official 7 inch Touchscreen or
other HDMI equivalents. Note, screens that attach solely to the GPIO pins (SPI)
are not compatible and the console will not start.

### PC / Laptop

The console is fully supported on laptops and PCs running Ubuntu 22.04 LTS or
later, or the desktop version of Raspberry Pi OS. It will run on other
debian-based operating systems with Python version 3.9 or above, but no direct
support is provided for these environments.

## Installation Instructions

The installation of the WeatherFlow PiConsole is fully automated, and can
be started from the terminal with a single command. The automated installation
should take no longer than 10 minutes.

The automated installer assumes you have already successfully setup your Raspberry
Pi and have installed Raspberry Pi OS with Desktop, or you ar running on a PC
with Ubuntu 20.04 or later or Raspberry Pi OS installed. For a Raspberry Pi you
should have also attached the touch screen, and have either a keyboard and mouse
attached directly to the Pi, or have accessesd the Pi remotely through SSH/VNC.
If you are starting from scratch with a Raspberry Pi, the documentation should
help get you started:

* https://www.raspberrypi.org/documentation/

### Install WeatherFlow PiConsole

The WeatherFlow PiConsole can be installed quickly and conveniently with the
following command:
```
curl -sSL https://peted-davis.github.io/wfpiconsole | bash
```
Piping a command directly to ```bash``` is controversial, as it prevents the
user from reading code that is about to run on their system. If you are worried
about the contents of the installer, please examine the [first](https://raw.githubusercontent.com/peted-davis/peted-davis.github.io/master/wfpiconsole)
and [second](https://raw.githubusercontent.com/peted-davis/WeatherFlow_PiConsole/master/wfpiconsole.sh)
installation files in the Git repository before running the install command.

### Configure and Run WeatherFlow PiConsole

When the console is run for the first time, you'll first be asked whether you 
want to install a blank configuration file for demonstration purposes or 
advanced setup. You can use this option if you wish to try out the console 
before your WeatherFlow hardware has arrived, or if you are a power user and 
wish to configure the console manually rather than using the configuration 
wizard. For most users, the advanced installation option is not appropriate and 
the default option of 'no' should be selected at this prompt. If you choose to 
install a blank configuration file, the console will start but no data will 
show unless you edit the configuration file manually. 

You will also be prompted to specify your preferred connection type: Websocket 
and REST API (default), UDP and REST API, or UDP only. For UDP only you will be
required to manually enter futher information about your station (location,
name, elevation etc.). For Websocket and REST API or UDP and REST API you will
be asked to enter a WeatherFlow Personal Access Token and a CheckWX Aviation
Weather API key. The Personal Access Token is required for the PiConsole to
access the data from your station, and the CheckWX API key is required to
download the closest METAR information to your station location.

A Personal Access Token can be generated, viewed, and deleted here: 
https://tempestwx.com/settings/tokens, and a CheckWX API key can be obtained by 
registering for a free account here: https://www.checkwxapi.com/auth/signup

Once you have a Personal Access Token and registered with CheckWX (if required),
go ahead and run the console for the first time using:
```
wfpiconsole start
```
Depending on the connection type you select, you'll be asked to enter the API
keys you have just generated above, as well as information about your station.
This includes your station ID and device IDs for your AIR, SKY, or TEMPEST
modules. To find this information either open the WeatherFlow app or view your
station page in a web browser. Click on the gear (settings) icon -> Stations ->
[Station name] -> Status.

If all goes smoothly the console should automatically add the extra information
it needs to your configuration file and then start running. You should not need
to enter this configuration information again.

Congratulations, you have installed the PiConsole for the Weather Flow Tempest
and Smart Home Weather Stations.

### Screen size

By default the PiConsole will run in full screen mode. Fullscreen mode can be
disabled in Menu -> Settings -> Display. In this case the console will use the
dimensions specified in the configuration file (```wfpiconsole.ini```), which
can be changed manually. Please note that extreme changes to the aspect ratio
will result in text fields running into one another. Under Settings -> Display
there are also settings to show/hide the cursor and show/hide the window border.

### Remote access

Please note that you cannot use SSH to start the console remotely.  Instead for
remote access it is recommended to setup VNC (https://www.raspberrypi.org/documentation/remote-access/vnc/).
Note there are currently issues using Real VNC (the default VNC provider on
Raspberry Pis) with the latest version of Raspberry  Pi OS (Bookworm): https://help.realvnc.com/hc/en-us/articles/14110635000221-Raspberry-Pi-5-Bookworm-and-RealVNC-Connect

## Update Instructions

The WeatherFlow PiConsole can be updated quickly and easily with the following
command:
```
wfpiconsole update
```
The update process will retain your existing user settings, but may prompt for
input from time to time in order to add new functionality. Once the update has
finished, restart the console using:
```
wfpiconsole start
```

## Auto-Start Instructions

The WeatherFlow PiConsole can be configured to run automatically when the
Raspberry Pi powers up. To enable the console to start automatically, run
```
wfpiconsole autostart-enable
```
To stop the WeatherFlow PiConsole from starting automatically, run
```
wfpiconsole autostart-disable
```
If you are going to use the auto-start method, it is highly recommended that you
can SSH into your Raspberry Pi, as the console can only be stopped using the
stop command or a hard shutdown:
```
wfpiconsole stop
```

## Advanced: Custom Panels

The console is distributed with 7 built-in panels to display weather, forecast
and astronomical information. For advanced users, custom panels can be created
allowing the data display to be customised, or additional data sources to be 
integrated into the console. Custom panels should not be overwritten when the 
console is updated.

The custom panel templates are contained within the `~\wfpiconsole\user` folder. 
To use the custom panel feature, you first need to rename `customPanels.kv.tmpl` 
to `customPanels.kv` and `customPanels.py.tmpl` to `customPanels.py`. An example 
panel called "BigTemperature" is included as an example, and will be loaded the 
next time you start the console.

In the `customPanels.py` file you must create two classes per custom panel called: 
`[panel_name]Panel` and `[panel_name]Button`. "panel_name" can be whatever you want, 
but you must add the two classes that end with Panel and Button per custom panel. 
The classes should be empty (just add pass under the class name), unless you want 
to add methods to your custom panel to control its behaviour. The classes required
for the "BigTemperature" panel can be used as examples. 

In the `customPanels.kv` file you can define the layout of the panel. You need to 
add the two class names that you defined in `customPanels.py` surrounded by left and 
right angled brackets: <>. Again, you can see the "BigTemperature" panel in 
`customPanels.kv.tmpl` as an example. For the Button class, you can change the text 
attribute under PanelButton: to set the name of the panel that will be displayed in 
the bottom bar of the PiConsole. Otherwise leave this class unchanged. For the Panel 
class, the panel title is defined by the _title attribute under PanelTitle:. This can 
be different to the name of the panel that is displayed in the bottom bar. Otherwise 
you are free to define the layout however you want using in-built or custom Kivy 
widgets (https://kivy.org/doc/stable/api-kivy.uix.html).

## Advanced: Device Replacement

Occasionally it may be necessary to replace your Tempest device due to hardware
failure. Depending on how the replacement Tempest is added to your existing station,
the Tempest device ID and serial number may change. If this is the case, the
`wfpiconsole.ini` file needs to be updated with the new device ID and serial number.
The `.ini` file can either be edited directly, or if  you are not comfortable editing 
the `.ini` file, you can delete it and then restart the console. You will be taken
through the steps to generate a new `.ini` file with the updated device ID and serial
number. 

When a device is replaced, the total monthly/yearly rain accumulation displayed in the
console will also reset to zero as these fields are calculated directly from the 
total rain accumuluation recorded by the new device (which is naturally zero as 
the device is brand new). To retain the correct values, it is necessary to switch
the console to use the Tempest Statistics API endpoint using `Menu` -> `Settings` -> 
`System` -> `Statistics API endpoint`. By default this option is disbaled as it
results in a small loss of accuracy through rounding errors. Therefore it is not 
recommended for use unless you have replaced a device within the last calendar 
year. At the end of a calendar year, the Statistics endoint can be switched off.  

## Advanced Installation: Windows

Although not officially supported, use the following step-by-step instructions
to install and run the WeatherFlow PiConsole on Windows.

1. Download and install the Python 3.11.5 version of Miniconda for Windows (a
lightweight Python interpreter): https://conda.io/miniconda.html

2. Once Miniconda is installed open the ‘Anaconda Prompt’ program.

3. In the Anaconda prompt, run:
```
python -m pip install --upgrade pip
```

4. Once that process has finished, run:
```
python -m pip install websockets numpy pytz tzlocal ephem packaging pyOpenSSL certifi
```

5. Once that has finished, install Kivy using
```
python -m pip install kivy[base]
```
This is the GUI library that drives the console.

6. Once Kivy is installed, run the following commands in order in the Anaconda
Prompt. This will install the WeatherFlow PiConsole.
```
cd && mkdir wfpiconsole && cd wfpiconsole
curl -sL https://api.github.com/repos/peted-davis/WeatherFlow_PiConsole/tarball -o PiConsole.tar.gz
tar -xvf PiConsole.tar.gz --strip 1
del /f PiConsole.tar.gz
```

7. You’re almost there now! You can start the console using ```python main.py```.
As this is the first time you have run the console, you’ll be asked for some API
keys. Details of what you need can be found under "Configure and Run WeatherFlow
PiConsole" in the **[Installation Instructions](#installation-instructions)**.

## Credits

Many of the graphical elements in the console are based on the Weather34 Home
Weather Station Template (https://www.weather34.com/homeweatherstation/)
copyright 2015-2021 Brian Underdown. The Weather34 Home Weather Station Template
is licensed under a Creative Commons Attribution-NonCommercial-NoDerivatives 4.0
International License.

## Home Telemetry in this fork

This fork includes an independent [Home Telemetry collector](docs/architecture.md)
and an optional Indoor Climate custom panel. The collector normalizes readings
from pluggable sources and shares them with PiConsole through SQLite. It supports
multiple providers and rooms, with explicit bindings for primary and fallback
sources. The current release runs with MockProvider and requires no hardware or
cloud account. The optional [Govee H5074 provider](docs/providers/govee.md) uses
Bluetooth. Nest SDM is a scaffold, and WeatherFlow AIR collection is planned.

See the [offline quick start](docs/architecture.md), [configuration and CLI](docs/configuration.md),
[storage and retention](docs/database.md), [Raspberry Pi deployment](docs/deployment.md),
[provider status](docs/providers/README.md), and [contribution guide](docs/provider-development.md).
The Home Telemetry fork and its provider contributors maintain this extension.
Report extension issues to the fork’s issue tracker.
