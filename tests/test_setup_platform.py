from pathlib import Path
import unittest
from unittest.mock import patch

from home_telemetry import setup_platform as setup


class PlatformSetupTests(unittest.TestCase):
    def test_platform_paths(self):
        home = Path.home()
        config, data = home / "config", home / "data"
        win = setup.directories("Windows", home, {"APPDATA": str(config), "LOCALAPPDATA": str(data)})
        linux = setup.directories("Linux", home, {"XDG_CONFIG_HOME": str(config), "XDG_DATA_HOME": str(data)})
        self.assertEqual(win, linux)
        self.assertEqual(win, (config / "home-telemetry", data / "home-telemetry"))
        legacy = (home / ".config/home-telemetry", home / ".local/share/home-telemetry")
        self.assertEqual(setup.directories("Darwin", home, {}), legacy)
        self.assertEqual(setup.directories("Linux", home, {"XDG_DATA_HOME": "relative"}), legacy)

    def test_pi_model(self):
        with patch.object(setup.platform, "system", return_value="Linux"), patch.object(
            Path, "read_bytes", side_effect=[FileNotFoundError(), b"Raspberry Pi 4"]
        ):
            self.assertTrue(setup.is_pi())

    def test_headless_and_failed_display(self):
        with patch.object(setup.platform, "system", return_value="Linux"), patch.dict(
            setup.os.environ, {}, clear=True
        ), patch.object(setup.subprocess, "run") as run:
            setup.check_display()
            run.assert_not_called()
            setup.os.environ["DISPLAY"] = ":0"
            run.return_value.returncode = 1
            with self.assertRaisesRegex(RuntimeError, "OpenGL"):
                setup.check_display()
