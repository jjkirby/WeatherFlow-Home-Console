# WeatherFlow AIR provider

**Status** — Planned. The registry reserves the type `weatherflow_air`, and the independent collector has no AIR implementation. PiConsole’s original AIR integration remains available through its normal configuration.

Temperature and humidity are planned. No devices are verified for the independent provider. Future contributors should document source transport, connection requirements, capabilities, identity mapping, privacy and retention before enabling it. Contact the Home Telemetry fork’s issue tracker for coordination.

```toml
[[providers]]
id = "future-air"
type = "weatherflow_air"
enabled = false
```
