"""Apply forward-only schema migrations in a single transaction."""

from ..exceptions import SchemaError

SCHEMA_VERSION = 1

_SCHEMA = (
    """CREATE TABLE providers (
        id TEXT PRIMARY KEY, type TEXT NOT NULL, display_name TEXT NOT NULL, room TEXT,
        enabled INTEGER NOT NULL, priority INTEGER NOT NULL, stale_seconds REAL NOT NULL,
        retention_days REAL, capabilities TEXT NOT NULL, status TEXT NOT NULL,
        last_observation TEXT, last_connection TEXT, last_error TEXT, error_summary TEXT,
        consecutive_failures INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE devices (
        provider_id TEXT NOT NULL REFERENCES providers(id), device_id TEXT NOT NULL,
        PRIMARY KEY (provider_id, device_id)
    )""",
    """CREATE TABLE observations (
        id INTEGER PRIMARY KEY, provider_id TEXT NOT NULL, device_id TEXT NOT NULL,
        observed_at TEXT NOT NULL, received_at TEXT NOT NULL, payload TEXT NOT NULL,
        FOREIGN KEY (provider_id, device_id) REFERENCES devices(provider_id, device_id),
        UNIQUE (provider_id, device_id, observed_at, payload)
    )""",
    """CREATE INDEX observations_device_received
        ON observations(provider_id, device_id, received_at DESC, id DESC)""",
    """CREATE TABLE latest (
        provider_id TEXT NOT NULL, device_id TEXT NOT NULL, observed_at TEXT NOT NULL,
        received_at TEXT NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY (provider_id, device_id),
        FOREIGN KEY (provider_id, device_id) REFERENCES devices(provider_id, device_id)
    )""",
    """CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)""",
)


def schema_version(connection):
    return connection.execute("PRAGMA user_version").fetchone()[0]


def require_schema(connection):
    found = schema_version(connection)
    if found != SCHEMA_VERSION:
        raise SchemaError(
            f"database schema {found} is incompatible; expected {SCHEMA_VERSION}"
        )


def migrate(connection):
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        found = schema_version(connection)
        if found == 0:
            for sql in _SCHEMA:
                connection.execute(sql)
            connection.execute("PRAGMA user_version = 1")
        require_schema(connection)
