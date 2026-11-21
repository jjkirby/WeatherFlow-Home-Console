# Station setup and Raspberry Pi desktop startup

For install commands, paths, and prerequisites, use the [platform setup guide](../setup.md).

## Answer the prompts

1. **Choose your indoor source.** Accept the existing telemetry file when offered. New users can pick Govee or a simulated sensor. The wizard installs the project and display dependencies in the checkout’s `.venv` and adds the Bluetooth extra for an enabled Govee provider.
2. **Select the sensor and room.** For a new Govee configuration, pick a numbered H5074 from the scan or type its advertised name. Choose whether the built-in **Indoor** column should use it. The wizard calls `config init` and validates the result. Existing TOMLs are reused. To try different settings, enter a new TOML path.
3. **Choose station settings.** Setup uses the INI already in the checkout. Otherwise it looks for the Pi’s installed service working directory, `~/wfpiconsole`, and a sibling `WeatherFlow_PiConsole` checkout. Accept a suggested INI, enter another path, or press Enter at the path prompt to run PiConsole’s own station wizard. For live weather, choose guided station setup when the station wizard offers a minimal demo INI.
4. **Check the display.** Close any *manually launched* collector and display before accepting the preview. If the standard Pi display service is active, the wizard offers to stop it temporarily. It starts a collector, waits up to two minutes for a fresh selected indoor observation, prints the reading, and opens PiConsole. Check your station data and sensor reading, then choose **Menu → Exit** to finish the preview. If the telemetry binding is enabled and the Indoor column is hidden, setup offers to enable it. For this test, bind the sensor or mock source to a binding named `indoor`.
5. **On the Pi, choose startup behavior.** After you confirm the preview worked, the wizard can create a per-user desktop-login startup entry. If the existing `wfpiconsole.service` is enabled, it asks before disabling it. Declining the switch or failing the preview restores a service the wizard temporarily stopped. Other custom launchers or services must be accounted for separately.

## Use it again

Run `./scripts/setup.sh` again to validate or select another configuration. To skip setup and start the collector and display directly, run the command the wizard printed, for example:

```bash
./scripts/setup.sh --start "$HOME/.config/home-telemetry/govee-h5074.toml"
```

The existing `./scripts/start-mac.sh` is also available for the configured Mac. Use one launcher at a time. Both the preview and paired launch stop their own collector when the window closes. Daily high and low values reflect the readings actually collected.

## Startup and recovery on the Pi

Desktop startup runs after the selected user signs in. Raspberry Pi OS **desktop autologin** must already be configured for this to happen unattended after a reboot. SSH-only systems and continuous collection while the display is closed should use the [independent systemd service deployment](deployment.md). The wizard's desktop mode runs both processes as the same user.

To undo a desktop switch, exit the fork, remove its `weatherflow-home-console.desktop` entry from `$XDG_CONFIG_HOME/autostart` (normally `~/.config/autostart`), and, **if setup disabled your original service**, run `sudo systemctl enable --now wfpiconsole.service`. The original checkout and its INI are available for rollback.

If a preview reports a writer lock, exit the collector already using the selected database. If no reading arrives, check the sensor name, Bluetooth permission for the app running Python on the Mac, and the adapter on the Pi. Setup can be rerun after correcting these. If a Pi dependency fails to build, check [upstream compatibility and install prerequisites](../docs/upstream-piconsole.md#compatibility) for that OS and Pi model.

The Govee/display combination and original launcher were hardware-tested on a Mac Studio. This wizard needs a live Mac run and a live Pi touchscreen/startup test.
