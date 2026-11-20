# Developing an indoor climate provider

Implement the `IndoorClimateProvider` interface in a module that owns its transport and authentication. Declare a stable lowercase `provider_type`, a frozen set of `Capability` values, a short description, and an optional `max_retention_days`. `validate_config` checks only public field names, types, and required settings. It runs before any provider starts. Raise `InvalidProviderSetting` with a schema field name. Keep values out of exceptions.

Implement `async run(publish, report_health)`. The inherited `start` creates the worker, `wait` monitors it, and `stop` cancels it. Put resource cleanup in `finally`. Integrations overriding lifecycle methods must preserve those semantics and complete cancellation promptly. Use async I/O or move blocking calls off the event loop. Provider callbacks run on the coordinator’s event loop and are awaitable. A bridge from a worker thread should submit its coroutine to that loop. Use asynchronous, rate-limited retries for recoverable transport failures. A worker that raises records an error and exits independently. The coordinator does not restart failed workers automatically.

Use stable logical IDs, with one ID per emitted device. Treat platform addresses and other discovery details as private unless needed. Implement `discover` only with the discovery capability and yield public labels. Discovery uses an isolated instance with defaults or settings from an enabled provider ID. Never store raw packets, HTTP headers, auth codes, or responses. Resolve secrets in configuration, keep OAuth exchanges inside the provider, and avoid logging response bodies or arbitrary exception strings. Review all text values and attribute fields before publication. The framework rejects secret-like keys and known secret values and deliberately stores a generic error summary when a plugin fails. Plugins are installed executable Python code and must be trusted.

Publish an `IndoorClimateObservation` with UTC timestamps, Celsius, humidity percentages, and missing values represented by `None`. The coordinator stamps its own receipt time. Emit health as `ProviderHealth`, including connection and error times and failure counts as applicable. Use authentication-required, unavailable, stale, or degraded states to signal recovery work. Keep optional attributes small and JSON-safe. The reader recognizes `thermostat_mode`, `hvac_status`, `heat_setpoint_c`, and `cool_setpoint_c` as conventional capability fields. Those fields stay optional. Setpoint values use Celsius. Keep published JSON and declared capabilities compatible across versions.

## Minimal provider

```python
import asyncio

from home_telemetry.models import (
    Capability, HealthStatus, IndoorClimateObservation, ProviderHealth, utc_now,
)
from home_telemetry.providers.base import IndoorClimateProvider


class ExampleProvider(IndoorClimateProvider):
    provider_type = "example_temperature"
    capabilities = frozenset({Capability.TEMPERATURE})
    description = "Demonstration of a temperature-only provider."

    async def run(self, publish, report_health):
        await report_health(ProviderHealth(HealthStatus.HEALTHY, last_connection=utc_now()))
        while True:
            now = utc_now()
            await publish(IndoorClimateObservation(
                self.provider_id, self.provider_type, self.config.device_id, now, now,
                temperature_c=20.0,
            ))
            await asyncio.sleep(10)
```

Register the class in an installed package through its packaging metadata. The collector discovers entry points by type name. Repository-maintained providers may also be enrolled in the built-in registry. Use a unique type and install only packages you trust.

```toml
[project.entry-points."home_telemetry.providers"]
example_temperature = "example_package.provider:ExampleProvider"
```

```toml
[[providers]]
id = "example-sensor"
type = "example_temperature"
room = "Example room"
retention_days = 30
```

Every provider contribution needs an implementation, credential-free tests, a configuration example, a capability declaration, and a provider Markdown document. The document should describe status, ownership and where to report issues, the supported-device table, tested environments, privacy, secret handling, and retention. Verify lifecycle, malformed input, missing capabilities, reconnection or auth failure, and sanitized errors. Test real hardware before calling a model supported. Declare experimental coverage explicitly. Announce deprecations before removing configuration or public fields, and document a migration when changing logical identity or the public observation contract.
