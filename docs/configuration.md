# Configuration

For first-time setup, see [Generate and deploy the telemetry TOML and configure the station INI](configuration-setup.md).

The collector uses `~/.config/home-telemetry/config.toml` by default. Set `HOME_TELEMETRY_CONFIG` or pass `--config PATH` before the command. Start with the [public example](../deploy/home-telemetry.toml.example). A relative database path is resolved from the configuration file’s directory. The default database is `~/.local/share/home-telemetry/telemetry.db`.

Each `[[providers]]` entry has a unique `id` and declared `type`. Set a stable `device_id` for the logical device. It defaults to the provider ID and must be unique across configured providers. IDs contain up to 64 letters, numbers, underscores, or hyphens and start with a letter or number. Use `display_name` and `room` for public labels. A multi-device plugin must emit a stable ID for each physical device. The database identifies each device by provider ID and device ID. Use a new provider ID when replacing its type.

| Field | Default | Behavior |
| --- | --- | --- |
| `enabled` | `true` | Disabled providers stay visible in collector status and skip plugin validation and environment resolution. |
| `priority` | `100` | Lower numbers rank first when no explicit source list is configured. Ties use provider ID. |
| `stale_seconds` | `120` | Maximum accepted age of an observation. |
| `heartbeat_seconds` | `300` | Minimum history interval for repeated measurement payloads with new observation timestamps. |
| `retention_days` | `"unlimited"` | Local history can be unlimited or a positive number of days. Nest is capped at ten days. Plugin types may define a stricter maximum. |
| `settings` | empty | Plugin-specific settings. |

Credential fields inside `[providers.settings]` must reference environment variables using a whole value such as `"${EXAMPLE_CLIENT_SECRET}"`. An enabled provider with a missing referenced variable fails configuration validation. Keep real values in the process environment or a restricted environment file outside the checkout. Labels, IDs, logging messages, and observation attributes are public data within the local database contract.

## Bindings and panel sources

A `[bindings.indoor]` table can set `primary`, ordered `fallbacks`, `room`, `capability`, `max_age_seconds`, and `allow_cross_room`. Other binding names work the same way. For example, a configured Govee provider can serve a living-room binding, a same-room sensor can be its first fallback, and a Nest in the entryway can be a further fallback when you explicitly enable cross-room selection. An upstairs binding can select its own sensor independently.

For explicit sources, the order in the binding takes precedence over priority. Without a room, the first preferred source anchors the room where known. If its room is unknown, an alternate cannot establish a same-room match. Set `allow_cross_room = true` to permit another room. Selection checks declared capability, a corresponding measurement, device connectivity, data quality, provider health, and the tighter of the provider and binding age limits. Healthy and degraded providers can serve fresh readings. The result identifies the source or supplies rejection reasons. The panel uses `[panel].sources` in the supplied order and defaults to every enabled provider.

## Built-in Temperature panel

WeatherFlow AIR supplies the built-in Indoor column by default. To use Home Telemetry, add the following to the same TOML file used by the collector. The `indoor` binding must have temperature capability.

```toml
[console]
use_indoor_binding = true
```

Set `HOME_TELEMETRY_CONFIG` to that file when starting PiConsole. The bridge uses `collector.database` unless `HOME_TELEMETRY_DB` overrides it. The collector must have started with that database and the intended `indoor` binding so the reader can use the binding stored in SQLite. In PiConsole, enable **Menu → Settings → Display → Indoor temperature** if the Indoor column is hidden.

The current value follows the same fresh source as `selection explain indoor`. Min and max are calculated from valid stored observations for that exact provider and device since station-local midnight. A stale current value shows the usual placeholder. If there is no fresh fallback, the display keeps the prior device's valid extrema for that day. A fresh fallback takes over all three fields. To restore AIR, set `use_indoor_binding = false` or remove the option and relaunch PiConsole.

## Commands

Run these as `home-telemetry [--config PATH] COMMAND` or `python3 -m home_telemetry [--config PATH] COMMAND`.

| Command | Use |
| --- | --- |
| `run` | Run until SIGINT or SIGTERM. |
| `status` | Show collector heartbeat, database schema, provider health, age state, selection, retention, and safe error summaries. |
| `config validate` | Parse settings and check enabled plugins and environment references. |
| `providers list` | List installed, planned, scaffold, and unavailable types. |
| `providers describe TYPE` | Show declared capabilities and implementation status. |
| `providers discover TYPE [--provider ID]` | Run discovery with defaults or settings from the specified provider ID. Mock is available for demonstration. |
| `db status` | Inspect storage and runtime state without acquiring the writer lock. |
| `db migrate` | Create or migrate the schema while the collector is stopped. |
| `db purge` | Apply stored retention policies immediately while the collector is stopped. |
| `selection explain BINDING` | Explain selection from the collector’s persisted binding and current observations. |
