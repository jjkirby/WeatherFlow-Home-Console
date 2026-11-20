# SQLite contract

Schema 1 uses `PRAGMA user_version`. Migrations advance the schema inside a transaction. The writer enables WAL, foreign keys, a 1.5-second busy timeout, and SQLite secure deletion. A filesystem lock protects the database from another framework writer. Use the same resolved database path for each process, on local storage. Do not open it with a second ad hoc writer.

| Table | Contents |
| --- | --- |
| `providers` | Public labels, declared capabilities, effective retention, and sanitized health. |
| `devices` | Logical identity within a provider instance. |
| `observations` | History rows with UTC timestamps and normalized payload JSON. |
| `latest` | The most recent observation for each provider/device, independent of history sampling. |
| `settings` | Public bindings, panel ordering, and collector heartbeat. |

Measurements use Celsius and percentage points. Times are UTC with fixed precision. The collector stamps receipt before storage. Capture time governs freshness and current-state ordering. Receipt time governs expiry and history sampling. Exact retries with the same measurement timestamp and payload do not add history or refresh the retained copy’s receipt time. Changed payloads and periodic samples with new observation timestamps are recorded. The collector heartbeat distinguishes an idle source from a disappeared collector.

Use `home_telemetry.readers.SnapshotReader` as the consumer interface. `read()` returns a `Snapshot` with status, public provider health, and methods `latest_by_provider`, `latest_by_device`, `latest_by_room`, `latest_healthy`, `selected`, and `panel_readings`. `recent_history(provider_id)` is a bounded query. A snapshot read uses a short transaction, read-only/query-only mode, and a 500 ms busy timeout. The schema check requires the reader and database versions to match.

The writer removes expired history and latest rows at collector startup, periodically, and on clean shutdown. Automatic cleanup runs at least once a minute and prunes Nest rows slightly early to allow for the interval until the next cleanup. `db purge` provides explicit maintenance. Readers exclude expired rows even during downtime. Nest uses at most ten days from receipt, including when a provider is disabled or removed from configuration. The framework stores no long-term Nest aggregates. Keep exports and backups within the same retention window or omit Nest data from them. A powered-off host cannot physically delete rows until maintenance runs again. A concurrent read can defer WAL truncation. Schedule `db purge` when leaving a stopped deployment online for an extended period.

The database contains room labels, sensor values, times, and device state. Restrict permissions, avoid public exports, and remove the database and its sidecars when retiring a deployment.
