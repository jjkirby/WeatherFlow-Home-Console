# Mock provider

**Status** — Implemented and tested offline. Maintained by the Home Telemetry fork.

The mock emits temperature, humidity, battery percentage, and online connectivity. Its discovery command returns a simulated logical ID. It supports simulated devices only. The source can keep values fixed, cycle through deterministic offsets, publish observations with an old capture timestamp, or fail after a configured observation count.

```toml
[[providers]]
id = "demo-sensor"
type = "mock"
room = "Demo room"

[providers.settings]
interval_seconds = 5
temperature_c = 21.5
humidity_percent = 45
battery_percent = 90
vary = true
# stale_age_seconds = 600
# fail_after = 3
```

With `fail_after = 0`, the worker fails before sending its first observation. Mock uses no credentials, radios, external services, or physical equipment. Public examples use synthetic data. It uses the configured retention policy and defaults to unlimited history.
