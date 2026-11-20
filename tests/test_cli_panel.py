from concurrent.futures import Future
from configparser import ConfigParser
from contextlib import redirect_stdout
from importlib.util import module_from_spec, spec_from_file_location
import io
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from home_telemetry.cli import main
from home_telemetry.config import Config, ProviderConfig
from home_telemetry.models import HealthStatus, ProviderHealth
from home_telemetry.readers import SnapshotReader
from home_telemetry.registry import Registry
from home_telemetry.storage.database import open_writer

from test_selection_models import NOW, observation


class CliTests(unittest.TestCase):
    def test_provider_discovery_availability(self):
        capture = io.StringIO()
        with redirect_stdout(capture):
            self.assertEqual(main(["providers", "discover", "mock"]), 0)
            self.assertEqual(main(["providers", "discover", "govee_ble"]), 1)
            self.assertEqual(main(["providers", "discover", "nest_sdm"]), 1)
        self.assertIn("discovery", capture.getvalue())
        self.assertIn("does not support discovery", capture.getvalue())
        self.assertIn("authorization", capture.getvalue())

    def test_run_status_selection_sigterm_and_maintenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            db = path.with_name("climate.db")
            example = Path("deploy/home-telemetry.toml.example").read_text()
            path.write_text(
                example.replace("~/.local/share/home-telemetry/telemetry.db", str(db))
            )
            command = [
                sys.executable,
                "-B",
                "-m",
                "home_telemetry",
                "--config",
                str(path),
            ]
            collector = subprocess.Popen(
                command + ["run"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                for _ in range(200):
                    snapshot = SnapshotReader(db).read()
                    if (
                        snapshot.selected("indoor").selected
                        or collector.poll() is not None
                    ):
                        break
                    time.sleep(0.015)
                self.assertIsNotNone(snapshot.selected("indoor").selected)
                status = subprocess.check_output(
                    command + ["status"], text=True, timeout=5
                )
                decision = subprocess.check_output(
                    command + ["selection", "explain", "indoor"],
                    text=True,
                    timeout=5,
                )
                self.assertIn("Collector: running", status)
                self.assertIn("Selected: demo-main", decision)
                self.assertIn("future-nest", status)
                locked = subprocess.run(
                    command + ["db", "purge"], capture_output=True, timeout=5
                )
                self.assertEqual(locked.returncode, 1)
            finally:
                if collector.poll() is None:
                    collector.send_signal(signal.SIGTERM)
                try:
                    _, errors = collector.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    collector.kill()
                    collector.communicate()
                    raise
            self.assertEqual(collector.returncode, 0, errors.decode())
            self.assertFalse(SnapshotReader(db).read().running)
            for action in ("status", "migrate", "purge"):
                result = subprocess.run(
                    command + ["db", action],
                    capture_output=True,
                    timeout=5,
                )
                self.assertEqual(result.returncode, 0, result.stdout.decode())


class Widget:
    def __init__(self):
        self.parent = None
        self.callbacks = []

    def bind(self, *, parent):
        self.callbacks.append(parent)

    def unbind(self, *, parent):
        self.callbacks.remove(parent)

    def attach(self, parent):
        self.parent = parent
        if hasattr(self, "on_parent"):
            self.on_parent(self, parent)
        for callback in self.callbacks[:]:
            callback(self, parent)


class PanelTests(unittest.TestCase):
    def test_mock_snapshot_and_nested_layout_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "climate.db"
            room = ProviderConfig("main", "mock", "device-main", "Demo", "Living room")
            other = ProviderConfig(
                "upper", "mock", "device-upper", "Demo upstairs", "Upstairs"
            )
            with open_writer(db) as writer:
                writer.configure(
                    Config(db, (room, other), {}, None, 60),
                    Registry(external=False),
                    NOW,
                )
                writer.record(observation("main", humidity_percent=45), 60)
                writer.record(
                    observation(
                        "upper",
                        room="Upstairs",
                        battery_percent=90,
                        attributes={"hvac_status": "HEATING", "heat_setpoint_c": 22},
                    ),
                    60,
                )
                for key in ("main", "upper"):
                    writer.health(key, ProviderHealth(HealthStatus.HEALTHY))
                snapshot = SnapshotReader(db).read(now=NOW)

            cfg = ConfigParser()
            cfg.read_dict(
                {
                    "Units": {"Temp": "f"},
                    "Display": {"TimeFormat": "12 hr"},
                    "Station": {"Timezone": "UTC"},
                }
            )
            app = SimpleNamespace(
                CurrentConditions=Widget(), config=cfg, IndoorClimatePanel=[]
            )

            class Template(Widget):
                def __init__(self, mode=None, **kwargs):
                    super().__init__()
                    self.app = app
                    app.IndoorClimatePanel.append(self)

            events = []

            def schedule(callback, _interval):
                event = SimpleNamespace(active=True, callback=callback)
                event.cancel = lambda: setattr(event, "active", False)
                events.append(event)
                return event

            def submit(_read):
                future = Future()
                future.set_result(snapshot)
                return future

            dependencies = {
                "kivy": {},
                "kivy.clock": {"Clock": SimpleNamespace(schedule_interval=schedule)},
                "kivy.properties": {"StringProperty": str},
                "kivy.uix": {},
                "kivy.uix.relativelayout": {"RelativeLayout": Widget},
                "panels.template": {"panelTemplate": Template},
            }
            modules = {}
            for name, attrs in dependencies.items():
                module = ModuleType(name)
                module.__dict__.update(attrs)
                modules[name] = module
            spec = spec_from_file_location(
                "telemetry_test_panel", "deploy/customPanels.py"
            )
            module = module_from_spec(spec)
            with (
                patch.dict(sys.modules, modules),
                patch.dict(os.environ, {"HOME_TELEMETRY_DB": str(db)}),
            ):
                spec.loader.exec_module(module)
                with patch.object(module, "_READERS", SimpleNamespace(submit=submit)):
                    panel = module.IndoorClimatePanel("manual")
                    parent, row = Widget(), Widget()
                    parent.attach(row)
                    panel.attach(parent)
                    self.assertEqual(events, [])
                    row.attach(app.CurrentConditions)
                    self.assertEqual(len(events), 1)
                    events[-1].callback(1)
                    self.assertIn("Living room", panel.summary)
                    self.assertIn("Upstairs", panel.summary)
                    self.assertIn("70.2 °F", panel.summary)
                    self.assertIn("45% RH", panel.summary)
                    self.assertIn("90% battery", panel.summary)
                    self.assertIn("HVAC HEATING", panel.summary)
                    self.assertIn("12:00 PM", panel.summary)
                    row.attach(None)
                    self.assertFalse(events[0].active)
                    self.assertNotIn(panel, app.IndoorClimatePanel)
                    new_panel = module.IndoorClimatePanel()
                    new_panel.attach(app.CurrentConditions)
                    self.assertEqual(sum(event.active for event in events), 1)
                    new_panel.attach(None)
                    self.assertFalse(any(event.active for event in events))
