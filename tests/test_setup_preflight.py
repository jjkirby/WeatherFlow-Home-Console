import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from home_telemetry import setup_platform


class NativeRepairTests(unittest.TestCase):
    def test_install_only_missing_packages_after_consent(self):
        def query(args, **kwargs):
            if args[0] == "dpkg-query":
                return Mock(stdout="install ok installed" if args[-1] == "dbus" else "")
            return Mock(returncode=0)

        with patch.object(setup_platform.platform, "freedesktop_os_release",
                          return_value={"ID": "debian"}), patch.object(
            shutil, "which", return_value="/usr/bin/tool"
        ), patch.object(subprocess, "run", side_effect=query) as run:
            for consent in (False, True):
                confirm = Mock(return_value=consent)
                self.assertEqual(setup_platform.apt_repair(["dbus", "bluez"], confirm), consent)
                confirm.assert_called_once_with("Run sudo apt-get install bluez?")
                installs = [c for c in run.call_args_list if c.args[0][0] == "sudo"]
                self.assertEqual(len(installs), int(consent))
                run.reset_mock()


@unittest.skipUnless(shutil.which("bash") and os.name == "posix", "Unix launcher")
class LauncherTests(unittest.TestCase):
    def test_host_gates_before_python_or_checkout_writes(self):
        script = Path(__file__).resolve().parents[1] / "scripts/setup.sh"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            target = root / "scripts/setup.sh"
            shutil.copy2(script, target)
            uname = root / "uname"
            for kernel, message in (("FreeBSD", "Unsupported host"), ("MINGW64_NT", "PowerShell")):
                uname.write_text(f"#!/bin/sh\necho {kernel}\n")
                uname.chmod(0o755)
                env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"])
                result = subprocess.run(["bash", str(target)], env=env, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertFalse((root / ".venv").exists())
