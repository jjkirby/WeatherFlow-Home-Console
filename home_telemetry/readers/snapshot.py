"""Read a consistent SQLite snapshot without importing a provider plugin."""

from contextlib import closing, contextmanager
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
import fcntl
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from ..config import Binding, DEFAULT_DATABASE
from ..exceptions import SchemaError
from ..models import (
    Capability,
    HealthStatus,
    IndoorClimateObservation,
    parse_time,
    utc_now,
)
from ..selection import Decision, Reading, ReadingStatus, Source, reading_status, select
from ..storage import queries
from ..storage.migrations import require_schema, schema_version

LEASE_SECONDS = 15
READER_TIMEOUT_MS = 500


class SnapshotState(StrEnum):
    READY = "ready"
    MISSING = "missing"
    EMPTY = "empty"
    BUSY = "busy"
    INCOMPATIBLE = "incompatible"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class Snapshot:
    state: SnapshotState
    now: datetime
    message: str = ""
    schema: int | None = None
    running: bool = False
    sources: dict[str, Source] = field(default_factory=dict)
    observations: dict[str, tuple[IndoorClimateObservation, ...]] = field(
        default_factory=dict
    )
    bindings: dict[str, Binding] = field(default_factory=dict)
    panel_sources: tuple[str, ...] | None = None

    def latest_by_provider(self, provider_id):
        rows = self.observations.get(provider_id, ())
        return self._reading(provider_id, rows[0] if rows else None)

    def latest_by_device(self, provider_id, device_id):
        return next(
            (
                self._reading(provider_id, row)
                for row in self.observations.get(provider_id, ())
                if row.device_id == device_id
            ),
            None,
        )

    def latest_by_room(self, room):
        matches = [
            obs
            for key, rows in self.observations.items()
            for obs in rows
            if (obs.room or self.sources[key].room) == room
        ]
        row = max(
            matches,
            key=lambda item: (item.observed_at, item.provider_id, item.device_id),
            default=None,
        )
        return self._reading(row.provider_id, row) if row else None

    def latest_healthy(self, capability: Capability, room=None):
        candidates = (
            self._reading(key, obs)
            for key, rows in self.observations.items()
            for obs in rows
            if capability in self.sources[key].capabilities
            and obs.supports_value(capability)
            and (room is None or (obs.room or self.sources[key].room) == room)
        )
        return max(
            (item for item in candidates if item.status == ReadingStatus.FRESH),
            key=lambda item: (
                item.observation.observed_at,
                item.source.id,
                item.observation.device_id,
            ),
            default=None,
        )

    def selected(self, binding):
        if binding not in self.bindings:
            return Decision(None, ((binding, "binding unknown"),))
        return select(self.bindings[binding], self.sources, self.observations, self.now)

    def panel_readings(self):
        names = self.panel_sources
        if names is None:
            names = tuple(key for key, source in self.sources.items() if source.enabled)
        readings = []
        for key in names:
            if key in self.sources:
                rows = self.observations.get(key, ())
                readings.extend(self._reading(key, row) for row in rows or (None,))
        return tuple(readings)

    def _reading(self, key, obs):
        source = self.sources.get(key)
        return (
            Reading(source, obs, reading_status(source, obs, self.now))
            if source
            else None
        )


@dataclass(frozen=True, slots=True)
class IndoorTemperature:
    day: date
    binding: Binding | None = None
    sensor: tuple[str, str] | None = None
    current: IndoorClimateObservation | None = None
    minimum: IndoorClimateObservation | None = None
    maximum: IndoorClimateObservation | None = None


class SnapshotReader:
    def __init__(self, path=DEFAULT_DATABASE, *, busy_timeout_ms=READER_TIMEOUT_MS):
        self.path = Path(path).expanduser().resolve()
        self.busy_timeout_ms = busy_timeout_ms

    @contextmanager
    def _connection(self):
        # A different, read-only service account cannot create WAL sidecars
        # when the collector is stopped. Only use immutable mode while holding
        # a shared lock and after verifying there is no WAL to read.
        lock_path = self.path.with_name(self.path.name + ".writer.lock")
        try:
            lock = lock_path.open("rb")
        except OSError:
            lock = None
        if lock is not None:
            with lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                except OSError:
                    pass
                else:
                    wal = self.path.with_name(self.path.name + "-wal")
                    if not wal.exists():
                        with self._connect("&immutable=1") as connection:
                            yield connection
                        return
        with self._connect() as connection:
            yield connection

    @contextmanager
    def _connect(self, options=""):
        with closing(
            sqlite3.connect(
                f"{self.path.as_uri()}?mode=ro{options}",
                uri=True,
                timeout=self.busy_timeout_ms / 1000,
            )
        ) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN")
            yield connection

    def read(self, *, now=None):
        now = now or utc_now()
        version = None
        try:
            if not self.path.exists():
                return Snapshot(
                    SnapshotState.MISSING, now, "Telemetry database is missing"
                )
            with self._connection() as connection:
                version = schema_version(connection)
                require_schema(connection)
                return self._read_snapshot(connection, now, version)
        except SchemaError as error:
            return Snapshot(SnapshotState.INCOMPATIBLE, now, str(error), version)
        except sqlite3.Error as error:
            code = getattr(error, "sqlite_errorcode", 0) & 255
            if code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                return Snapshot(
                    SnapshotState.BUSY, now, "Telemetry database is busy", version
                )
            return Snapshot(
                SnapshotState.UNAVAILABLE,
                now,
                "Telemetry database is unavailable",
                version,
            )
        except OSError:
            return Snapshot(
                SnapshotState.UNAVAILABLE,
                now,
                "Telemetry database is unavailable",
                version,
            )
        except (ValueError, TypeError, KeyError, OverflowError):
            return Snapshot(
                SnapshotState.UNAVAILABLE, now, "Invalid telemetry data", version
            )

    @staticmethod
    def _read_snapshot(connection, now, version):
        data = queries.settings(connection)
        sources = queries.sources(connection, now)
        observations = queries.latest(connection, sources, now)
        runtime = data.get("runtime", {})
        heartbeat = parse_time(runtime.get("heartbeat"))
        running = bool(
            runtime.get("running")
            and heartbeat
            and 0 <= (now - heartbeat).total_seconds() <= LEASE_SECONDS
        )
        if not running:
            sources = {
                name: (
                    replace(
                        source,
                        health=replace(source.health, status=HealthStatus.STOPPED),
                    )
                    if source.health.status
                    in {
                        HealthStatus.HEALTHY,
                        HealthStatus.DEGRADED,
                        HealthStatus.STARTING,
                    }
                    else source
                )
                for name, source in sources.items()
            }
        panel = data.get("panel_sources")
        return Snapshot(
            SnapshotState.READY if observations else SnapshotState.EMPTY,
            now,
            "" if observations else "Waiting for observations",
            version,
            running,
            sources,
            {key: tuple(value) for key, value in observations.items()},
            queries.bindings(data),
            tuple(panel) if panel is not None else None,
        )

    def indoor_temperature(self, station_timezone, previous=None, *, now=None):
        """Read the indoor binding and that device's station-day extrema atomically."""
        now = now or utc_now()
        zone = ZoneInfo(station_timezone)
        day = now.astimezone(zone).date()
        start = datetime.combine(day, time.min, zone).astimezone(timezone.utc)
        end = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(
            timezone.utc
        )
        try:
            if not self.path.exists():
                return None
            with self._connection() as connection:
                require_schema(connection)
                snapshot = self._read_snapshot(
                    connection, now, schema_version(connection)
                )
                binding = snapshot.bindings.get("indoor")
                if binding is None or binding.capability != Capability.TEMPERATURE:
                    return IndoorTemperature(day)

                selected = snapshot.selected("indoor").selected
                current = selected.observation if selected else None
                if current is not None:
                    sensor = (current.provider_id, current.device_id)
                elif (
                    previous is not None
                    and previous.binding == binding
                    and previous.sensor is not None
                    and previous.sensor[0] in snapshot.sources
                    and snapshot.sources[previous.sensor[0]].enabled
                ):
                    # No fresh fallback took over. Keep the previous device's extrema.
                    sensor = previous.sensor
                else:
                    # A console started while the sensor is stale can still show
                    # today's history using the binding's usual ordering and room rules.
                    historical = select(
                        binding,
                        snapshot.sources,
                        snapshot.observations,
                        now,
                        historical=True,
                    ).selected
                    if historical is None:
                        return IndoorTemperature(day, binding)
                    obs = historical.observation
                    sensor = (obs.provider_id, obs.device_id)
                source = snapshot.sources[sensor[0]]
                minimum, maximum = queries.temperature_extrema(
                    connection, source, sensor[1], start, end, now
                )
                return IndoorTemperature(
                    day, binding, sensor, current, minimum, maximum
                )
        except (
            OSError,
            sqlite3.Error,
            SchemaError,
            ValueError,
            TypeError,
            KeyError,
            OverflowError,
        ):
            return None

    def recent_history(self, provider_id, *, limit=100, now=None):
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise ValueError("history limit must be 1 to 10000")
        now = now or utc_now()
        if not self.path.exists():
            return ()
        with self._connection() as connection:
            require_schema(connection)
            source = queries.sources(connection, now).get(provider_id)
            return queries.history(connection, source, now, limit)
