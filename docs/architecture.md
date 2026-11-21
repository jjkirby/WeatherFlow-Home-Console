# Home Telemetry

Home Telemetry is an open-source extension maintained in the WeatherFlow Home Console fork. It collects indoor climate observations independently of upstream WeatherFlow PiConsole. The collector runs as `home-telemetry`. PiConsole reads persisted snapshots through its supported custom-panel interface. Pete Davis maintains upstream PiConsole. Home Telemetry issues belong in the fork, and device-specific adapters may have separate community owners.

A provider owns its connection and authentication. It declares capabilities, then pushes normalized observations and health updates into the coordinator. The coordinator validates configuration before starting tasks and supervises each task independently. SQLite stores the current observation for each device, history, provider health, and the public portion of source configuration. The read-only snapshot API computes freshness and selection using one consistent SQLite transaction. No provider settings or credentials are part of that contract.

See [provider status](providers/README.md) for available sensors and [provider development](provider-development.md) for the plugin interface.

## Offline quick start

Run the [development smoke test](../setup.md#development-and-acceptance-tests) to exercise the collector, SQLite, and reader with simulated data. For manual inspection, see the [developer notes](developer-notes.md#smoke-test-the-mock-collector).

Report bugs in the [WeatherFlow Home Console fork](https://github.com/jjkirby/WeatherFlow-Home-Console/issues). Include the fork revision, Python and OS versions, the provider type, and sanitized reproduction steps. Use a MockProvider reproduction when practical. Keep credentials, raw Bluetooth captures, device identifiers, and home telemetry out of public issues. This project uses the repository’s [GPL-3.0 license](../LICENSE).
