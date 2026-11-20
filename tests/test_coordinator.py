import asyncio
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest

from home_telemetry.config import Binding, Config, ProviderConfig
from home_telemetry.coordinator import Coordinator
from home_telemetry.models import HealthStatus, utc_now
from home_telemetry.providers.mock import MockProvider
from home_telemetry.readers import SnapshotReader
from home_telemetry.registry import Registry
from home_telemetry.selection import ReadingStatus
from home_telemetry.storage.database import open_writer

from test_selection_models import NOW, observation


class FailingStartup(MockProvider):
    provider_type = "test_startup"
    stopped = False

    async def start(self, publish, report_health):
        raise RuntimeError("EXAMPLE-FAKE-PRIVATE-STARTUP")

    async def stop(self):
        type(self).stopped = True


class TracksShutdown(MockProvider):
    provider_type = "test_shutdown"
    stopped = False

    async def run(self, publish, report_health):
        try:
            await super().run(publish, report_health)
        finally:
            type(self).stopped = True


class MockTests(unittest.TestCase):
    def test_deterministic_series_changing_values_and_stale_timestamp(self):
        cfg = ProviderConfig(
            "x",
            "mock",
            "x",
            "Demo",
            settings={"temperature_c": 20, "vary": True, "stale_age_seconds": 60},
        )
        mock = MockProvider(cfg)
        results = [mock.observation(index, NOW) for index in range(4)]
        self.assertEqual(
            [obs.temperature_c for obs in results], [20, 20.25, 20.5, 19.75]
        )
        self.assertEqual(
            [obs.humidity_percent for obs in results], [45, 45.25, 45.5, 44.75]
        )
        self.assertTrue(
            all((NOW - obs.observed_at).total_seconds() == 60 for obs in results)
        )


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_framework_failure_isolation_staleness_and_shutdown(self):
        registry = Registry(external=False)
        registry.register(FailingStartup.provider_type, FailingStartup)
        registry.register(TracksShutdown.provider_type, TracksShutdown)
        FailingStartup.stopped = TracksShutdown.stopped = False
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.db"
            healthy = ProviderConfig(
                "healthy",
                TracksShutdown.provider_type,
                "device1",
                "Healthy",
                "Demo",
                settings={"interval_seconds": 0.01},
            )
            stale = ProviderConfig(
                "stale",
                "mock",
                "device2",
                "Old",
                "Demo",
                settings={"stale_age_seconds": 500, "interval_seconds": 0.01},
            )
            failing = ProviderConfig(
                "failing",
                "mock",
                "device3",
                "Failure",
                "Demo",
                settings={"interval_seconds": 0.01, "fail_after": 1},
            )
            startup = ProviderConfig(
                "startup", FailingStartup.provider_type, "device4", "Startup"
            )
            config = Config(
                path,
                (healthy, stale, failing, startup),
                {"indoor": Binding("stale", ("healthy",))},
                None,
                0.03,
            )
            reader = SnapshotReader(path)
            stop = asyncio.Event()
            coordinator = Coordinator(config, registry)
            with self.assertLogs("home_telemetry", "WARNING") as logs:
                task = asyncio.create_task(coordinator.run(stop))
                try:
                    for _ in range(100):
                        await asyncio.sleep(0.01)
                        state = reader.read()
                        failed = state.sources.get("failing")
                        if failed and failed.health.status == HealthStatus.ERROR:
                            break
                    self.assertEqual(
                        state.latest_by_provider("healthy").status, ReadingStatus.FRESH
                    )
                    self.assertEqual(
                        state.latest_by_provider("stale").status, ReadingStatus.STALE
                    )
                    self.assertTrue(state.running)
                    self.assertEqual(
                        state.selected("indoor").selected.source.id, "healthy"
                    )
                    self.assertEqual(
                        state.sources["startup"].health.status, HealthStatus.ERROR
                    )
                    self.assertEqual(
                        state.sources["startup"].health.error_summary,
                        "Provider startup failed",
                    )
                    self.assertEqual(
                        state.sources["failing"].health.consecutive_failures, 1
                    )
                    self.assertEqual(len(reader.recent_history("failing")), 1)
                finally:
                    stop.set()
                    await asyncio.wait_for(task, 2)
            self.assertNotIn("EXAMPLE-FAKE-PRIVATE-STARTUP", str(logs.output))
            self.assertFalse(reader.read().running)
            self.assertEqual(
                reader.read().sources["healthy"].health.status, HealthStatus.STOPPED
            )
            self.assertTrue(FailingStartup.stopped)
            self.assertTrue(TracksShutdown.stopped)

    async def test_bad_sample_is_dropped_and_provider_recovers(self):
        class MalformedThenHealthy(MockProvider):
            provider_type = "test_malformed"

            async def run(self, publish, report_health):
                first = self.observation(0, utc_now())
                await publish(
                    replace(first, attributes={"access_token": "FAKE-REJECTED-VALUE"})
                )
                await publish(self.observation(1, utc_now()))
                await asyncio.Future()

        registry = Registry(external=False)
        registry.register(MalformedThenHealthy.provider_type, MalformedThenHealthy)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.db"
            cfg = ProviderConfig(
                "source", MalformedThenHealthy.provider_type, "test-device", "Demo"
            )
            config = Config(path, (cfg,), {}, None, 60)
            reader = SnapshotReader(path)
            stop = asyncio.Event()
            with self.assertLogs("home_telemetry", "WARNING") as logs:
                running = asyncio.create_task(Coordinator(config, registry).run(stop))
                try:
                    for _ in range(100):
                        await asyncio.sleep(0.01)
                        reading = reader.read().latest_by_provider("source")
                        if reading and reading.status == ReadingStatus.FRESH:
                            break
                    self.assertEqual(reading.status, ReadingStatus.FRESH)
                    self.assertEqual(reading.source.health.consecutive_failures, 0)
                    self.assertEqual(len(reader.recent_history("source")), 1)
                    self.assertNotIn("FAKE-REJECTED-VALUE", repr(reading))
                finally:
                    stop.set()
                    await asyncio.wait_for(running, 2)
            self.assertNotIn("FAKE-REJECTED-VALUE", str(logs.output))

    async def test_periodic_retention_physically_removes_disabled_nest_rows(self):
        registry = Registry(external=False)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "climate.db"
            cfg = ProviderConfig("nest", "nest_sdm", "demo-nest", "Demo", enabled=False)
            config = Config(path, (cfg,), {}, None, 0.01)
            clock = [NOW]
            with open_writer(path) as writer:
                writer.configure(config, registry, clock[0])
                old = NOW - timedelta(days=10) + timedelta(seconds=10)
                writer.record(
                    replace(
                        observation("nest"),
                        provider_type="nest_sdm",
                        observed_at=old,
                        received_at=old,
                    ),
                    60,
                )
            stop = asyncio.Event()
            running = asyncio.create_task(
                Coordinator(config, registry, clock=lambda: clock[0]).run(stop)
            )
            try:
                await asyncio.sleep(0.025)
                self.assertEqual(
                    len(SnapshotReader(path).recent_history("nest", now=NOW)), 1
                )
                clock[0] += timedelta(seconds=11)
                with sqlite3.connect(path) as database:
                    for _ in range(100):
                        await asyncio.sleep(0.01)
                        count = database.execute(
                            "SELECT COUNT(*) FROM observations"
                        ).fetchone()[0]
                        if count == 0:
                            break
                    self.assertEqual(count, 0)
                    self.assertEqual(
                        database.execute("SELECT COUNT(*) FROM latest").fetchone()[0], 0
                    )
                database.close()
            finally:
                stop.set()
                await asyncio.wait_for(running, 2)
