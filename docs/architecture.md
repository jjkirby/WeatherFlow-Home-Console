# Home Telemetry

Home Telemetry is an open-source extension maintained in the WeatherFlow Home Console fork. It collects indoor climate observations independently of upstream WeatherFlow PiConsole. The collector runs as `home-telemetry`. PiConsole reads persisted snapshots through its supported custom-panel interface. Pete Davis maintains upstream PiConsole. Home Telemetry issues belong in the fork, and device-specific adapters may have separate community owners.

A provider owns its connection and authentication. It declares capabilities, then pushes normalized observations and health updates into the coordinator. The coordinator validates configuration before starting tasks and supervises each task independently. SQLite stores the current observation for each device, history, provider health, and the public portion of source configuration. The read-only snapshot API computes freshness and selection using one consistent SQLite transaction. No provider settings or credentials are part of that contract.

Mock is implemented for offline development. Govee BLE supports the H5074 with an optional Bluetooth dependency. Nest SDM is a scaffold, and WeatherFlow AIR collection is planned. See [provider status](providers/README.md), [configuration](configuration.md), [storage](database.md), [deployment](deployment.md), and [provider development](provider-development.md).

## Offline quick start

From the checkout on macOS or Linux with Python 3.11 or later:

```sh
mkdir -p ~/.config/home-telemetry
cp -n deploy/home-telemetry.toml.example ~/.config/home-telemetry/config.toml
python3 -m home_telemetry config validate
python3 -m home_telemetry run
```

In another terminal:

```sh
python3 -m home_telemetry status
python3 -m home_telemetry selection explain indoor
python3 -m unittest discover -s tests -v
```

Use Ctrl+C to stop the collector cleanly. The sample configuration runs three mock providers across two rooms. Run the collector alone to test the entire data path through SQLite and the reader. See deployment for installing the optional panel.

Report bugs in the [WeatherFlow Home Console fork](https://github.com/jjkirby/WeatherFlow-Home-Console/issues). Include the fork revision, Python and OS versions, the provider type, and sanitized reproduction steps. Use a MockProvider reproduction when practical. Keep credentials, raw Bluetooth captures, device identifiers, and home telemetry out of public issues. This project uses the repository’s [GPL-3.0 license](../LICENSE).
