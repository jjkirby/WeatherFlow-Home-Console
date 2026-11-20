from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest

from home_telemetry.config import Binding, Config, ProviderConfig
from home_telemetry.exceptions import SchemaError, WriterBusy
from home_telemetry.models import Capability, HealthStatus, ProviderHealth
from home_telemetry.readers import SnapshotReader, SnapshotState
from home_telemetry.registry import Registry
from home_telemetry.selection import ReadingStatus
from home_telemetry.storage.database import BUSY_TIMEOUT_MS, open_writer
from home_telemetry.storage.migrations import SCHEMA_VERSION

from test_selection_models import NOW, observation


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "climate.db"
        self.providers = (
            ProviderConfig("a", "mock", "device-a", "A", "Living room", priority=0),
            ProviderConfig("b", "mock", "device-b", "B", "Entryway", retention_days=1),
            ProviderConfig(
                "n",
                "nest_sdm",
                "device-n",
                "Nest",
                "Entryway",
                enabled=False,
                retention_days=30,
            ),
        )
        self.config = Config(
            self.path,
            self.providers,
            {"indoor": Binding("a", ("b",), allow_cross_room=True)},
            ("a", "b"),
            60,
        )
        self.registry = Registry(external=False)
        self.reader = SnapshotReader(self.path, busy_timeout_ms=10)

    def test_migration_wal_foreign_keys_busy_timeout_and_writer_exclusion(self):
        with open_writer(self.path) as writer:
            db = writer.connection
            self.assertEqual(
                db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION
            )
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(
                db.execute("PRAGMA busy_timeout").fetchone()[0], BUSY_TIMEOUT_MS
            )
            with self.assertRaises(WriterBusy), open_writer(self.path):
                self.fail("writer exclusion failed")
        with open_writer(self.path):
            self.assertEqual(self.reader.read(now=NOW).state, SnapshotState.EMPTY)

    def test_reader_sees_committed_snapshot_during_uncommitted_wal_write(self):
        with open_writer(self.path) as writer:
            writer.configure(self.config, self.registry, NOW)
            writer.connection.execute("BEGIN IMMEDIATE")
            writer.connection.execute(
                "UPDATE providers SET status='healthy' WHERE id='a'"
            )
            snapshot = self.reader.read(now=NOW)
            self.assertEqual(snapshot.sources["a"].health.status, HealthStatus.STARTING)
            writer.connection.commit()
            self.assertEqual(
                self.reader.read(now=NOW).sources["a"].health.status,
                HealthStatus.HEALTHY,
            )
            with self.reader._connection() as reader:
                with self.assertRaises(sqlite3.OperationalError):
                    reader.execute("DELETE FROM providers")

    def test_changes_heartbeat_exact_retry_and_latest(self):
        with open_writer(self.path) as writer:
            writer.configure(self.config, self.registry, NOW)
            first = observation("a")
            writer.record(first, 60)
            writer.record(replace(first, received_at=NOW + timedelta(seconds=1)), 60)
            t10 = NOW + timedelta(seconds=10)
            writer.record(replace(first, observed_at=t10, received_at=t10), 60)
            t70 = NOW + timedelta(seconds=70)
            writer.record(replace(first, observed_at=t70, received_at=t70), 60)
            t80 = NOW + timedelta(seconds=80)
            writer.record(
                replace(first, observed_at=t80, received_at=t80, temperature_c=23), 60
            )
            t79 = NOW + timedelta(seconds=79)
            writer.record(
                replace(first, observed_at=t79, received_at=t80, temperature_c=22), 60
            )
            writer.health(
                "a", ProviderHealth(HealthStatus.HEALTHY, last_connection=NOW)
            )
            writer.heartbeat(t80)
            history = self.reader.recent_history("a", now=t80)
            self.assertEqual(len(history), 4)
            self.assertEqual({row.observed_at for row in history}, {NOW, t70, t79, t80})
            snapshot = self.reader.read(now=t80)
            self.assertEqual(
                snapshot.latest_by_provider("a").observation.temperature_c, 23
            )
            self.assertEqual(
                snapshot.latest_by_device("a", "device-a").observation.observed_at, t80
            )
            self.assertEqual(
                snapshot.latest_by_room("Living room").status, ReadingStatus.FRESH
            )
            self.assertEqual(
                snapshot.latest_healthy(Capability.TEMPERATURE).source.id, "a"
            )
            self.assertEqual(snapshot.selected("indoor").selected.source.id, "a")
            self.assertEqual(snapshot.sources["a"].health.last_observation, t80)
            self.assertEqual(snapshot.sources["a"].health.last_connection, NOW)

    def test_auth_stale_optional_attributes_and_multiple_rooms(self):
        with open_writer(self.path) as writer:
            writer.configure(self.config, self.registry, NOW)
            writer.record(
                observation(
                    "a", temperature_c=None, attributes={"firmware": "Demo v2"}
                ),
                60,
            )
            old = NOW - timedelta(minutes=10)
            writer.record(
                replace(observation("b", room="Entryway"), observed_at=old), 60
            )
            writer.health("a", ProviderHealth(HealthStatus.AUTHENTICATION_REQUIRED))
            writer.health("b", ProviderHealth(HealthStatus.HEALTHY))
            snapshot = self.reader.read(now=NOW)
            alpha, bravo = snapshot.panel_readings()
            self.assertEqual(alpha.status, ReadingStatus.AUTHENTICATION_REQUIRED)
            self.assertEqual(alpha.observation.attributes["firmware"], "Demo v2")
            self.assertIsNone(alpha.observation.temperature_c)
            self.assertEqual(bravo.status, ReadingStatus.STALE)
            self.assertEqual(snapshot.latest_by_room("Entryway").source.id, "b")
            self.assertIsNone(snapshot.selected("indoor").selected)

    def test_retention_hard_cap_even_for_removed_source_and_offline_reader(self):
        with open_writer(self.path) as writer:
            writer.configure(self.config, self.registry, NOW)
            for key in ("a", "b", "n"):
                old = NOW - timedelta(days=10)
                item = replace(observation(key), observed_at=old, received_at=old)
                writer.record(
                    replace(item, provider_type="nest_sdm") if key == "n" else item, 60
                )
            recent = NOW - timedelta(days=9)
            writer.record(
                replace(
                    observation("n"),
                    provider_type="nest_sdm",
                    observed_at=recent,
                    received_at=recent,
                    temperature_c=24,
                ),
                60,
            )
            self.assertEqual(len(self.reader.recent_history("n", now=NOW)), 1)
            self.assertEqual(len(self.reader.recent_history("a", now=NOW)), 1)
            self.assertEqual(len(self.reader.recent_history("b", now=NOW)), 0)
            self.assertEqual(writer.purge(NOW), 2)
            next_day = NOW + timedelta(days=1)
            writer.configure(
                replace(self.config, providers=self.providers[:2]),
                self.registry,
                next_day,
            )
            self.assertEqual(
                writer.connection.execute(
                    "SELECT COUNT(*) FROM observations",
                ).fetchone()[0],
                1,
            )
            self.assertIsNone(
                self.reader.read(now=next_day).latest_by_provider("n").observation
            )
            self.assertEqual(writer.purge(next_day), 0)

    def test_missing_empty_locked_and_schema_incompatible(self):
        self.assertEqual(self.reader.read(now=NOW).state, SnapshotState.MISSING)
        self.assertFalse(self.path.exists())
        with sqlite3.connect(self.path) as raw:
            raw.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
            self.assertEqual(
                self.reader.read(now=NOW).state, SnapshotState.INCOMPATIBLE
            )
            raw.execute("BEGIN EXCLUSIVE")
            self.assertEqual(self.reader.read(now=NOW).state, SnapshotState.BUSY)
        raw.close()
        with self.assertRaises(SchemaError), open_writer(self.path):
            self.fail("future schema opened for writing")
