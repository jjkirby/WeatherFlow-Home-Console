"""One SQLite writer with short transactions and an independent reader contract."""

from contextlib import closing, contextmanager
from dataclasses import asdict
import json
import os
from pathlib import Path
import sqlite3

from ..storage.file_lock import acquire
from ..exceptions import ConfigurationError, WriterBusy
from ..models import HealthStatus, parse_time, utc_text
from .migrations import migrate
from .retention import effective_days, purge_expired

BUSY_TIMEOUT_MS = 1500


@contextmanager
def writer_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    lock_path = path.with_name(path.name + ".writer.lock")
    with os.fdopen(os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o640), "r+b") as lock:
        try:
            acquire(lock, shared=False)
        except BlockingIOError:
            raise WriterBusy(
                "collector or database maintenance owns the writer lock"
            ) from None
        yield


@contextmanager
def open_writer(path):
    path = Path(path).expanduser().resolve()
    with writer_lock(path):
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o640)
        os.close(fd)
        with closing(sqlite3.connect(path)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
            connection.execute("PRAGMA foreign_keys = ON")
            migrate(connection)
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA secure_delete = ON")
            yield Database(connection)


def _json(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))


def _payload(observation):
    data = asdict(observation)
    for key in (
        "provider_id",
        "provider_type",
        "device_id",
        "observed_at",
        "received_at",
    ):
        del data[key]
    return _json(data)


class Database:
    def __init__(self, connection):
        self.connection = connection

    def _setting(self, key, data):
        self.connection.execute(
            "INSERT INTO settings VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, _json(data)),
        )

    def configure(self, config, registry, now, *, nest_lookahead_seconds=0):
        with self.connection:
            self.connection.execute("UPDATE providers SET enabled=0, status='stopped'")
            for cfg in config.providers:
                existing = self.connection.execute(
                    "SELECT type FROM providers WHERE id=?",
                    (cfg.id,),
                ).fetchone()
                if existing and existing["type"] != cfg.type:
                    raise ConfigurationError(
                        f"provider {cfg.id}.type: use a new ID for a different type"
                    )
                item = registry.describe(cfg.type)
                limit = item.factory.max_retention_days if item.factory else None
                days = effective_days(cfg.type, cfg.retention_days)
                if limit is not None:
                    days = min(days, limit) if days is not None else limit
                self.connection.execute(
                    """INSERT INTO providers
                       (id,type,display_name,room,enabled,priority,stale_seconds,
                        retention_days,capabilities,status,consecutive_failures)
                       VALUES (?,?,?,?,?,?,?,?,?,?,0)
                       ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,
                       room=excluded.room, enabled=excluded.enabled, priority=excluded.priority,
                       stale_seconds=excluded.stale_seconds,
                       retention_days=excluded.retention_days,
                       capabilities=excluded.capabilities, status=excluded.status,
                       consecutive_failures=0""",
                    (
                        cfg.id,
                        cfg.type,
                        cfg.display_name,
                        cfg.room,
                        cfg.enabled,
                        cfg.priority,
                        cfg.stale_seconds,
                        days,
                        _json(sorted(item.capabilities)),
                        HealthStatus.STARTING if cfg.enabled else HealthStatus.STOPPED,
                    ),
                )
            self._setting(
                "bindings", {key: asdict(val) for key, val in config.bindings.items()}
            )
            self._setting("panel_sources", config.panel_sources)
            self._setting("runtime", {"running": True, "heartbeat": utc_text(now)})
            removed = purge_expired(
                self.connection,
                now,
                nest_lookahead_seconds=nest_lookahead_seconds,
            )
        if removed:
            self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def health(self, provider_id, health):
        health = health.sanitized()
        with self.connection:
            self.connection.execute(
                """UPDATE providers SET status = ?,
                    last_observation = COALESCE(?, last_observation),
                    last_connection = COALESCE(?, last_connection),
                    last_error = COALESCE(?, last_error),
                    error_summary = COALESCE(?, error_summary),
                    consecutive_failures = ? WHERE id = ?""",
                (
                    health.status,
                    *(
                        utc_text(value) if value else None
                        for value in (
                            health.last_observation,
                            health.last_connection,
                            health.last_error,
                        )
                    ),
                    health.error_summary,
                    health.consecutive_failures,
                    provider_id,
                ),
            )

    def record(self, observation, heartbeat_seconds):
        obs = observation.validated()
        observed = utc_text(obs.observed_at)
        received = utc_text(obs.received_at)
        payload = _payload(obs)
        identity = (obs.provider_id, obs.device_id)
        with self.connection:
            provider = self.connection.execute(
                "SELECT type FROM providers WHERE id = ?", (obs.provider_id,)
            ).fetchone()
            if provider is None or provider["type"] != obs.provider_type:
                raise ValueError("observation provider type does not match storage")
            self.connection.execute(
                "INSERT OR IGNORE INTO devices VALUES (?, ?)", identity
            )
            previous = self.connection.execute(
                """SELECT payload, received_at FROM observations
                   WHERE provider_id = ? AND device_id = ?
                   ORDER BY received_at DESC, id DESC LIMIT 1""",
                identity,
            ).fetchone()
            history_due = (
                previous is None
                or previous["payload"] != payload
                or (
                    obs.received_at - parse_time(previous["received_at"])
                ).total_seconds()
                >= heartbeat_seconds
            )
            if history_due:
                inserted = self.connection.execute(
                    """INSERT INTO observations
                       (provider_id,device_id,observed_at,received_at,payload) VALUES (?,?,?,?,?)
                       ON CONFLICT(provider_id,device_id,observed_at,payload) DO NOTHING""",
                    (*identity, observed, received, payload),
                ).rowcount
                if not inserted:
                    return
            self.connection.execute(
                """INSERT INTO latest VALUES (?,?,?,?,?)
                   ON CONFLICT(provider_id,device_id) DO UPDATE SET
                       observed_at=excluded.observed_at, received_at=excluded.received_at,
                       payload=excluded.payload
                   WHERE excluded.observed_at > latest.observed_at
                      OR (excluded.observed_at = latest.observed_at
                          AND excluded.payload != latest.payload
                          AND excluded.received_at >= latest.received_at)""",
                (*identity, observed, received, payload),
            )
            if obs.quality != "invalid":
                self.connection.execute(
                    """UPDATE providers SET last_observation = ?
                       WHERE id = ? AND (last_observation IS NULL OR last_observation < ?)""",
                    (observed, obs.provider_id, observed),
                )

    def purge(self, now):
        with self.connection:
            removed = purge_expired(self.connection, now)
        self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return removed

    def maintenance(self, now, *, running=True, nest_lookahead_seconds=0):
        with self.connection:
            self._setting("runtime", {"running": running, "heartbeat": utc_text(now)})
            removed = purge_expired(
                self.connection,
                now,
                nest_lookahead_seconds=nest_lookahead_seconds,
            )
        if removed:
            self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def heartbeat(self, now):
        with self.connection:
            self._setting("runtime", {"running": True, "heartbeat": utc_text(now)})
