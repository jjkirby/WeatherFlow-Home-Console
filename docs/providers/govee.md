# Govee Bluetooth provider

**Status** — Framework/scaffold only. No models verified. Not production-ready. Enablement fails validation. Discovery and decoding require a supported model implementation.

The planned provider will collect local measurements and emit normalized temperature, humidity, battery when present, and signal strength when available. Planned discovery will identify candidate advertisements or GATT devices, let the user confirm a physical sensor, and associate it with a stable logical ID.

| Supported models | Firmware | Verification |
| --- | --- | --- |
| None verified | — | Awaiting hardware and known-good samples |

Different models or firmware can advertise different identifiers and data layouts, or require different read mechanisms. A decoder must be based on verified observations for that model and tested against known-good values. Maintain multiple model decoders behind one `govee_ble` provider. Choose a third-party library only after identifying the device and reviewing model coverage, maintenance, licensing, and security.

```toml
[[providers]]
id = "future-govee"
type = "govee_ble"
enabled = false
device_id = "example-living-room-sensor"
room = "Example living room"
retention_days = "unlimited"

[providers.settings]
model = "MODEL-TO-BE-VERIFIED"
```

The settings above are illustrative. Treat scanner identifiers as host-local. macOS CoreBluetooth can expose a UUID, while Linux BlueZ can expose a Bluetooth address. Keep a human-assigned logical ID across both environments. Local retention defaults to unlimited and can be bounded. Temperature histories can reveal room occupancy patterns. Remove radio addresses and identifiers from shared captures, and keep sanitized fixtures only. [Bleak macOS backend](https://bleak.readthedocs.io/en/stable/backends/macos.html) · [Bleak Linux backend](https://bleak.readthedocs.io/en/stable/backends/linux.html)

## Contributor checklist

- Record the exact model number, firmware, host OS, adapter, and discovery behavior.
- Gather matched payloads and reference temperature, humidity, and battery readings across several values. Sanitize captures for review while preserving bytes needed for decoding.
- Determine experimentally whether advertisements supply measurements or a GATT read is necessary. Record expected intervals and how the sensor behaves when it leaves range or restarts.
- Implement a model-specific decoder and test malformed, truncated, repeated, and unfamiliar packets. Validate units and negative Celsius values against references.
- Verify collection and recovery with the Raspberry Pi service account, then record the model and firmware in the support table. Use the fork issue tracker to coordinate ownership.

For troubleshooting on the Pi, check the adapter and rfkill state, BlueZ availability, D-Bus permissions, range, sensor power, and the exact firmware/model. On macOS also check Bluetooth permission for the application running Python. Collect examples of the observed behavior before assuming a decoding fault.
