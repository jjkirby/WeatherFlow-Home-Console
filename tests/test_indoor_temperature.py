from datetime import datetime, timedelta, timezone
import builtins
from functools import lru_cache
import os
from pathlib import Path
import tempfile
from threading import get_ident
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from lib import properties

from home_telemetry.config import Binding, Config, ProviderConfig, load_config
from home_telemetry.console import (
    IndoorTemperatureBridge,
    start_indoor_temperature,
)
from home_telemetry.exceptions import ConfigurationError
from home_telemetry.models import (
    DataQuality,
    HealthStatus,
    IndoorClimateObservation,
    ProviderHealth,
)
from home_telemetry.readers import SnapshotReader
from home_telemetry.readers.snapshot import IndoorTemperature
from home_telemetry.registry import Registry
from home_telemetry.storage.database import open_writer

ZONE = "America/Denver"
NOW = datetime(2026, 7, 2, 18, 1, tzinfo=timezone.utc)


def sample(provider, when, value, *, device=None, quality=DataQuality.GOOD):
    return IndoorClimateObservation(
        provider,
        "mock",
        device or f"{provider}-device",
        when,
        when,
        room="Living room",
        temperature_c=value,
        quality=quality,
    )


@lru_cache
def piconsole_code(name):
    path = Path("lib", f"{name}.py")
    return compile(path.read_bytes(), str(path), "exec")


def load_piconsole_modules(app):
    """Load the original parser and formatter without starting the app or Kivy."""
    package = ModuleType("lib")
    package.properties = properties
    package.request_api = SimpleNamespace(weatherflow_api=Mock())
    system = SimpleNamespace(system=Mock())
    fakes = {
        "lib": package,
        "lib.request_api": package.request_api,
        "lib.system": system,
        "pytz": SimpleNamespace(timezone=ZoneInfo, utc=timezone.utc),
        "ephem": ModuleType("ephem"),
        "kivy": ModuleType("kivy"),
        "kivy.app": SimpleNamespace(App=SimpleNamespace(get_running_app=lambda: app)),
        "kivy.clock": SimpleNamespace(mainthread=lambda method: method),
        "kivy.logger": SimpleNamespace(Logger=Mock()),
    }

    def import_dependency(name, *args):
        if name in fakes:
            return fakes[name]
        return builtins.__import__(name, *args)

    namespace = dict(vars(builtins), __import__=import_dependency)
    for name in ("derived_variables", "observation_format", "observation_parser"):
        module = ModuleType(f"lib.{name}")
        module.__dict__["__builtins__"] = namespace
        setattr(package, name, module)
        exec(piconsole_code(name), module.__dict__)
    return package.observation_parser, package.observation_format


class IndoorTemperatureReaderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "indoor.db"
        self.reader = SnapshotReader(self.path)
        self.registry = Registry(external=False)
        providers = tuple(
            ProviderConfig(key, "mock", f"{key}-device", key, room="Living room")
            for key in ("primary", "backup")
        )
        self.config = Config(
            self.path,
            providers,
            {"indoor": Binding("primary", ("backup",))},
            None,
            60,
            True,
        )

    def setup_writer(self, writer, now):
        writer.configure(self.config, self.registry, now)
        for cfg in self.config.providers:
            writer.health(cfg.id, ProviderHealth(HealthStatus.HEALTHY))

    def test_fresh_and_stale_keep_valid_same_day_extrema(self):
        first, peak = NOW - timedelta(hours=3), NOW - timedelta(hours=1)
        with open_writer(self.path) as writer:
            self.setup_writer(writer, NOW)
            for row in (
                sample("primary", first, 17.2),
                sample("primary", peak, 24.5),
                sample(
                    "primary",
                    NOW - timedelta(minutes=3),
                    80,
                    quality=DataQuality.INVALID,
                ),
                sample("primary", NOW, 22.53),
            ):
                writer.record(row, 300)

            fresh = self.reader.indoor_temperature(ZONE, now=NOW)
            self.assertEqual(fresh.current.temperature_c, 22.53)
            self.assertEqual(fresh.minimum.observed_at, first)
            self.assertEqual(fresh.maximum.observed_at, peak)
            later = NOW + timedelta(seconds=130)
            writer.heartbeat(later)
            for previous in (fresh, None):
                stale = self.reader.indoor_temperature(ZONE, previous, now=later)
                self.assertIsNone(stale.current)
                self.assertEqual(stale.minimum, fresh.minimum)
                self.assertEqual(stale.maximum, fresh.maximum)

    def test_station_local_midnight_and_deduplicated_first_sample(self):
        midnight = datetime(2026, 7, 2, 6, tzinfo=timezone.utc)
        yesterday = midnight - timedelta(seconds=10)
        today = midnight + timedelta(seconds=10)
        with open_writer(self.path) as writer:
            self.setup_writer(writer, yesterday)
            writer.record(sample("primary", yesterday, 18), 300)
            before = self.reader.indoor_temperature(ZONE, now=yesterday)
            self.assertEqual(before.minimum.temperature_c, 18)
            writer.heartbeat(midnight)
            after = self.reader.indoor_temperature(ZONE, before, now=midnight)
            self.assertEqual(after.day.day, 2)
            self.assertEqual(after.current.temperature_c, 18)
            self.assertIsNone(after.minimum)
            self.assertIsNone(after.maximum)
            writer.record(sample("primary", today, 18), 300)
            writer.heartbeat(today)
            next_sample = self.reader.indoor_temperature(ZONE, after, now=today)
            self.assertEqual(len(self.reader.recent_history("primary", now=today)), 1)
            self.assertEqual(next_sample.minimum.observed_at, today)
            self.assertEqual(next_sample.maximum.observed_at, today)

    def test_fall_back_day_includes_the_25th_hour(self):
        late = datetime(2026, 11, 2, 6, 30, tzinfo=timezone.utc)
        with open_writer(self.path) as writer:
            self.setup_writer(writer, late)
            writer.record(sample("primary", late - timedelta(hours=24), 14), 300)
            writer.record(sample("primary", late, 25), 300)
            result = self.reader.indoor_temperature(ZONE, now=late)
            self.assertEqual(result.day.day, 1)
            self.assertEqual(result.minimum.temperature_c, 14)
            self.assertEqual(result.maximum.observed_at, late)

    def test_fallback_switches_entire_day_to_exact_provider_and_device(self):
        backup_minimum = NOW - timedelta(hours=1)
        with open_writer(self.path) as writer:
            self.setup_writer(writer, NOW)
            writer.record(sample("primary", NOW - timedelta(hours=2), 5), 300)
            writer.record(sample("backup", backup_minimum, 21), 300)
            writer.record(
                sample(
                    "backup", NOW - timedelta(minutes=5), 41, device="other-room-device"
                ),
                300,
            )
            writer.record(sample("primary", NOW, 18), 300)
            primary = self.reader.indoor_temperature(ZONE, now=NOW)
            self.assertEqual(primary.sensor, ("primary", "primary-device"))
            self.assertEqual(primary.minimum.temperature_c, 5)

            later = NOW + timedelta(minutes=3)
            writer.record(sample("backup", later, 23), 300)
            writer.heartbeat(later)
            backup = self.reader.indoor_temperature(ZONE, primary, now=later)
            self.assertEqual(backup.sensor, ("backup", "backup-device"))
            self.assertEqual(backup.current.temperature_c, 23)
            self.assertEqual(backup.minimum.temperature_c, 21)
            self.assertEqual(backup.minimum.observed_at, backup_minimum)
            self.assertEqual(backup.maximum.temperature_c, 23)

            stale_at = later + timedelta(minutes=3)
            writer.heartbeat(stale_at)
            stale = self.reader.indoor_temperature(ZONE, backup, now=stale_at)
            self.assertIsNone(stale.current)
            self.assertEqual(stale.sensor, backup.sensor)
            self.assertEqual(stale.minimum, backup.minimum)


class ConsoleIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.defaults = properties.Obs()
        self.app = SimpleNamespace(
            CurrentConditions=SimpleNamespace(Obs=self.defaults.copy()),
            config={
                "Station": {
                    "Timezone": ZONE,
                    "InAirID": "7",
                    "InAirSN": "air",
                    "OutAirID": "",
                    "OutAirSN": "",
                    "TempestID": "",
                    "TempestSN": "",
                },
                "Display": {"TimeFormat": "24 hr"},
                "System": {"Hardware": "Other", "rest_api": "0"},
                "Units": {"Temp": "f"},
            },
            connection_client=SimpleNamespace(activeThreads=lambda: False),
        )
        self.parser, self.formatter = load_piconsole_modules(self.app)

    def test_default_air_publish_and_telemetry_protection_through_reset(self):
        app = self.app
        observations = app.CurrentConditions.Obs
        outdoor = {
            "outTemp": ["40", "℉"],
            "Humidity": ["58", "%"],
            "FeelsLike": ["38", "℉", "", "Cold"],
            "DewPoint": ["32", "℉"],
        }
        app.indoor_telemetry = None
        parser = self.parser.obs_parser()
        parser.display_obs.update(outdoor)
        parser.parse_obs_in_air(
            {"device_id": 7, "obs": [[NOW.timestamp(), 0, 20]]}, app.config
        )
        self.assertEqual(observations["inTemp"], ["68.0", "℉"])
        for key in ("inTempMin", "inTempMax"):
            self.assertEqual(observations[key][:3], ["68.0", "℉", "12:01"])
        for key, value in outdoor.items():
            self.assertEqual(observations[key], value)

        app.indoor_telemetry = object()
        owned = {
            "inTemp": ["71.0", "℉"],
            "inTempMin": ["65.0", "℉", "10:30"],
            "inTempMax": ["75.0", "℉", "14:30"],
        }
        observations.update(owned)
        parser.update_display("obs_all")
        parser.reset_display()
        reconnected = self.parser.obs_parser()
        reconnected.display_obs.update(outdoor)
        reconnected.parse_obs_in_air(
            {"serial_number": "air", "obs": [[NOW.timestamp(), 0, 25]]},
            app.config,
        )
        for key, value in (owned | outdoor).items():
            self.assertEqual(observations[key], value)

    def test_clock_refresh_uses_worker_and_formats_on_caller_thread(self):
        current = sample("primary", NOW, 22)
        low = sample("primary", NOW - timedelta(minutes=1), 20)
        stat = IndoorTemperature(
            NOW.date(), current=current, minimum=low, maximum=current
        )
        worker_threads = []
        results = iter(
            (stat, IndoorTemperature(NOW.date(), minimum=low, maximum=current))
        )

        def read(zone, previous):
            self.assertEqual(zone, ZONE)
            worker_threads.append(get_ident())
            return next(results, None)

        bridge = IndoorTemperatureBridge(
            self.app,
            SimpleNamespace(indoor_temperature=read),
            self.formatter,
            self.defaults,
        )
        self.addCleanup(bridge.stop)
        with patch("home_telemetry.console.utc_now", return_value=NOW):
            bridge.refresh(0)
            bridge.pending.result(timeout=2)
            self.assertEqual(self.app.CurrentConditions.Obs["inTemp"], "--")
            bridge.refresh(1)
            self.assertEqual(self.app.CurrentConditions.Obs["inTemp"], ["71.6", "℉"])
            self.assertEqual(
                self.app.CurrentConditions.Obs["inTempMin"][:3], ["68.0", "℉", "12:00"]
            )
            self.app.config["Display"]["TimeFormat"] = "12 hr"
            bridge.pending.result(timeout=2)
            bridge.refresh(1)
        fields = self.app.CurrentConditions.Obs
        self.assertEqual(fields["inTemp"], "--")
        self.assertEqual(fields["inTempMax"][:3], ["71.6", "℉", "12:01 PM"])
        self.assertTrue(all(thread != get_ident() for thread in worker_threads))
        self.assertEqual(fields["outTemp"], self.defaults["outTemp"])

    def test_extension_flag_defaults_off_and_requires_temperature_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            clock = Mock()
            with patch.dict(os.environ, {"HOME_TELEMETRY_CONFIG": str(path)}):
                self.assertIsNone(start_indoor_temperature(self.app, clock, Mock()))
                path.write_text("[console]\nuse_indoor_binding = false\n")
                self.assertIsNone(start_indoor_temperature(self.app, clock, Mock()))
                clock.schedule_interval.assert_not_called()
                path.write_text("[console]\nuse_indoor_binding = true\n")
                with self.assertRaisesRegex(
                    ConfigurationError, "requires bindings.indoor"
                ):
                    load_config(path)
                path.write_text(
                    "[console]\nuse_indoor_binding = true\n"
                    "[bindings.indoor]\ncapability='temperature'\n"
                )
                self.assertTrue(load_config(path).use_indoor_binding)
