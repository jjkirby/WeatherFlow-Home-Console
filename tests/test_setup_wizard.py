import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from home_telemetry import setup_wizard as wizard


class WizardTests(unittest.TestCase):
    def test_existing_panel_customization_preserves_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "user").mkdir()
            (root / "deploy").mkdir()
            ini = root / "wfpiconsole.ini"
            ini.write_text("existing private config")
            for suffix in ("py", "kv"):
                (root / "deploy" / f"customPanels.{suffix}").write_text("template")
            (root / "user/customPanels.kv").write_text("local edits")
            with patch.object(wizard, "ROOT", root), patch.object(wizard, "INI", ini):
                wizard.station(False)
            self.assertFalse((root / "user/customPanels.py").exists())
            self.assertEqual((root / "user/customPanels.kv").read_text(), "local edits")
            self.assertEqual(ini.read_text(), "existing private config")

    def test_verified_switch_requires_visual_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.toml"
            cfg.write_text("")
            with (patch.object(wizard, "is_pi", return_value=True),
                  patch.object(wizard, "configure_telemetry", return_value=cfg),
                  patch.object(wizard, "station"),
                  patch.object(wizard.shutil, "which", return_value="/usr/bin/tool"),
                  patch.object(Path, "is_dir", return_value=True),
                  patch.object(wizard, "check_display"),
                  patch.dict(wizard.os.environ, DISPLAY=":0"),
                  patch.object(wizard, "service_value", return_value="active"),
                  patch.object(wizard, "yes", side_effect=[True, True, False]),
                  patch.object(wizard, "launch", return_value=True),
                  patch.object(wizard, "run") as run):
                wizard.wizard()
            self.assertEqual([call.args for call in run.call_args_list], [
                ("sudo", "systemctl", "stop", wizard.UNIT),
                ("sudo", "systemctl", "start", wizard.UNIT),
            ])
