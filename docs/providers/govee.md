# Govee H5074 Bluetooth provider

**Status** — The H5074 decoder is verified against a real macOS Bleak capture. The collector and SQLite integration are tested with offline scanner callbacks. Live collector testing on macOS and Raspberry Pi remains open. The Home Telemetry fork maintains this provider.

| Supported model | Firmware | Verification |
| --- | --- | --- |
| H5074 | Unknown | macOS capture decoded offline. Live collector smoke test pending. |

The provider listens for advertisements through Bleak and reports temperature, humidity, and battery. It matches the exact configured H5074 name and manufacturer ID `0xec88`. Name and manufacturer data can arrive in separate callbacks, so the provider associates them by their scanner address during a scan. Other names, including H5083, are ignored. The configured `device_id` is what SQLite stores. Keep it stable when moving between Macs, which can use different CoreBluetooth UUIDs, or to Linux, where BlueZ can expose a Bluetooth address. The collector does not persist scanner addresses or raw packets. [Bleak scanner](https://bleak.readthedocs.io/en/stable/api/scanner.html) · [macOS backend](https://bleak.readthedocs.io/en/stable/backends/macos.html) · [Linux backend](https://bleak.readthedocs.io/en/stable/backends/linux.html)

## macOS smoke test

From the repository root, use a Python 3.11 or newer virtual environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[govee]'
mkdir -p "$HOME/.config/home-telemetry"
```

Save this example as `~/.config/home-telemetry/govee-h5074.toml`. For another H5074, use its full advertised name and a unique logical ID. The dedicated database keeps demo samples out of this test.

```toml
[collector]
database = "~/.local/share/home-telemetry/h5074.db"

[[providers]]
id = "govee-living-room"
type = "govee_ble"
device_id = "h5074-living-room"
display_name = "Govee H5074"
room = "Living room"
stale_seconds = 120

[providers.settings]
sensor_name = "Govee_H5074_9844"

[bindings.indoor]
primary = "govee-living-room"
room = "Living room"
capability = "temperature"

[panel]
sources = ["govee-living-room"]
```

In the first terminal, validate the configuration and start collection with the sensor powered on and nearby. Allow Bluetooth access for the terminal or application running Python if macOS prompts.

```sh
CFG="$HOME/.config/home-telemetry/govee-h5074.toml"
home-telemetry --config "$CFG" config validate
home-telemetry --config "$CFG" run
```

In a second terminal, run these from the same repository:

```sh
source .venv/bin/activate
CFG="$HOME/.config/home-telemetry/govee-h5074.toml"
home-telemetry --config "$CFG" status
home-telemetry --config "$CFG" selection explain indoor
```

Wait for `govee-living-room (govee_ble)` to show `healthy fresh` and a recent observation timestamp. The binding explanation should show `Selected: govee-living-room` and `fresh reading selected`. If the provider is healthy but has no observation, scanning has started and a valid matching packet has yet to arrive. Check Bluetooth permissions, sensor range, and the full advertised name. Missing Bleak produces an install hint in the collector log. The default mock demo works with the base package and needs no Bluetooth permissions.

## Confirm the custom panel

If the panel is already installed in your configured PiConsole environment, keep the collector running and start PiConsole from its checkout with the test database path:

```sh
HOME_TELEMETRY_DB="$HOME/.local/share/home-telemetry/h5074.db" python main.py
```

Choose `IndoorClimate` in Primary or Secondary Panels. If deployed as secondary, open **Indoor**. Look for **Govee H5074 · Living room**, the `govee_ble` source type, `fresh`, and a recent last-seen time. Compare the live temperature and humidity with the sensor and allow for display units and rounding. The panel shows the configured sources, while `selection explain indoor` confirms the binding's choice. For first-time installation, see the [deployment guide](../deployment.md).

## Use the built-in Indoor column

Add this table to your existing `~/.config/home-telemetry/govee-h5074.toml`. If the file already has a `[console]` table, add the key under that table. Keep the existing `[bindings.indoor]` with `primary = "govee-living-room"`.

```toml
[console]
use_indoor_binding = true
```

Keep the collector running on `h5074.db`. Quit PiConsole and relaunch it from the repository root in the same Python environment you used for the custom panel.

```sh
source .venv/bin/activate
HOME_TELEMETRY_CONFIG="$HOME/.config/home-telemetry/govee-h5074.toml" \
HOME_TELEMETRY_DB="$HOME/.local/share/home-telemetry/h5074.db" \
python main.py
```

If the column is hidden, turn on **Menu → Settings → Display → Indoor temperature** and open the built-in **Temperature** panel. The current value should agree with the Indoor Climate panel after applying PiConsole's configured units and rounding. The min and max include their occurrence times and use the selected device's samples for the current station-local day. Use `selection explain indoor` to check the source. Changing just the `[console]` flag requires a PiConsole relaunch. The existing collector can keep running.

## Capture and retention

The offline fixture uses `00 cd 08 41 0a 64 02` and decodes to 22.53°C, 26.25% RH, and 100% battery. Tests also cover signed negative temperatures, malformed packets, and callbacks from a different device. The provider uses the normal freshness and SQLite sampling rules. Changes in radio signal strength alone do not generate history rows. Local retention defaults to unlimited and can be bounded with `retention_days`. Keep room histories and any new captures private and remove radio addresses from shared fixtures.

## Mac field verification

[Expected built-in Indoor display](../developer-notes.md#what-this-fork-adds) · [One-command startup](../deployment.md#macos)

**Waiting for observations.** In the Mac test, the H5074 measurement broadcast reappeared after closing Govee Home on the connected iPhone. Leave phone Bluetooth enabled, close the app, keep the sensor near the Mac, and check the collector timestamp again.

**Custom panel is fresh but the built-in Indoor column shows dashes.** Check the binding with the command above. Confirm the launcher loads the TOML with `use_indoor_binding = true` and the same database as the collector. If the column is hidden, enable **Menu → Settings → Display → Indoor temperature**. Relaunch PiConsole after editing its telemetry configuration.
