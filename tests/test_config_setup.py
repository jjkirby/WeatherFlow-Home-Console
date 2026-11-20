import tempfile
import unittest
import tomllib
from pathlib import Path

from home_telemetry.cli import main
from home_telemetry.config_setup import generate


class ConfigSetupTests(unittest.TestCase):
    def test_govee_config_round_trip(self):
        data = generate("Govee_H5074_XXXX", 'Den "A"', "/var/lib/test.db", True)
        parsed = tomllib.loads(data.decode())
        sensor = parsed["providers"][0]
        self.assertEqual(sensor["settings"]["sensor_name"], "Govee_H5074_XXXX")
        self.assertEqual(sensor["room"], 'Den "A"')
        self.assertEqual(parsed["bindings"]["indoor"]["primary"], sensor["id"])
        self.assertTrue(parsed["console"]["use_indoor_binding"])
        self.assertEqual(parsed["collector"]["database"], "/var/lib/test.db")

    def test_init_deploy_and_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "personal" / "test.toml"
            dst = Path(directory) / "target" / "config.toml"
            self.assertEqual(main(["--config", str(src), "config", "init", "--mock"]), 0)
            deploy = ["--config", str(dst), "config", "deploy", str(src)]
            self.assertEqual(main(deploy), 0)
            self.assertEqual(main(deploy), 0)
            original = dst.read_bytes()
            src.write_bytes(original + b"\n# local note\n")
            self.assertEqual(main(deploy), 1)
            self.assertEqual(dst.read_bytes(), original)

    def test_invalid_source_is_never_published(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "bad.toml"
            dst = Path(directory) / "dest.toml"
            src.write_text("[bad")
            self.assertEqual(main(["--config", str(dst), "config", "deploy", str(src)]), 1)
            self.assertFalse(dst.exists())
