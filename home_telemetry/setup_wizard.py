"""Interactive station/telemetry setup and paired launch for desktop installations."""

import asyncio
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib


from .setup_platform import apt_repair, bluetooth_diagnostics, check_bluetooth, check_display, is_pi, user_dirs

ROOT = Path.cwd()
PYTHON = sys.executable
INI = ROOT / "wfpiconsole.ini"
UNIT = "wfpiconsole.service"


def ask(label, default=""):
    hint = f" [{default}]" if default else ""
    return input(f"{label}{hint}: ").strip() or default


def yes(label, default=False):
    while True:
        value = ask(label, "Y/n" if default else "y/N").lower()
        if value == "y/n":
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False


def run(*args):
    subprocess.run(args, check=True)


def cli(cfg, *args):
    return [PYTHON, "-m", "home_telemetry", "--config", str(cfg), *args]


def expanded(value):
    return Path(value).expanduser().resolve()


def new_file(path, data):
    """Publish a complete user-owned file without overwriting concurrent changes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
    try:
        temp.write_bytes(data)
        os.link(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def service_value(field):
    result = subprocess.run(
        ["systemctl", "show", UNIT, "-p", field, "--value"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


async def scan():
    from bleak import BleakScanner

    names = set()

    def report(device, adv):
        for name in (adv.local_name, device.name):
            if name and "5074" in name:
                names.add(name)

    print("Listening for H5074 advertisements for 35 seconds…", flush=True)
    async with BleakScanner(detection_callback=report):
        await asyncio.sleep(35)
    return sorted(names)


def install_dependencies(bluetooth):
    packages = ["kivy[base]", "requests", "websockets", "numpy", "pytz", "tzlocal",
                "ephem", "packaging", "pyOpenSSL", "certifi"]
    if os.name == "nt":
        packages.append("tzdata")
    run(PYTHON, "-m", "pip", "install", "-e", ".[govee]" if bluetooth else ".", *packages)
    run(PYTHON, "-m", "pip", "check")
    imports = ("import kivy, requests, websockets, numpy, pytz, tzlocal, ephem, packaging, "
               "OpenSSL, certifi, sqlite3, ssl; sqlite3.connect(':memory:').execute('SELECT 1'); ssl.create_default_context(); from zoneinfo import ZoneInfo; ZoneInfo('America/Denver')")
    if bluetooth:
        imports += "; from bleak import BleakScanner"
    run(PYTHON, "-c", imports)
    print("Package and timezone checks passed.", flush=True)


def configure_telemetry():
    directory, data_dir = user_dirs()
    defaults = [directory / name for name in ("govee-h5074.toml", "config.toml", "demo.toml")]
    legacy = Path.home() / ".config/home-telemetry"
    candidates = defaults + [legacy / path.name for path in defaults]
    existing = next((path for path in candidates if path.is_file()), None)
    default = os.environ.get("HOME_TELEMETRY_CONFIG") or existing
    profile = None
    if not default:
        profile = "govee" if yes("Set up a Govee H5074? Choose no for demo", True) else "mock"
        default = defaults[0 if profile == "govee" else 2]
    cfg = expanded(ask("Telemetry file to use or create", str(default)))
    if cfg.exists():
        with cfg.open("rb") as stream:
            settings = tomllib.load(stream)
        bluetooth = any(
            p.get("type") == "govee_ble" and p.get("enabled", True)
            for p in settings.get("providers", [])
        )
        print("Reusing", cfg)
    else:
        bluetooth = profile == "govee" if profile else yes("Use a Govee H5074?", True)
    install_dependencies(bluetooth)
    if bluetooth:
        try:
            asyncio.run(check_bluetooth())
        except RuntimeError:
            if platform.system() != "Linux":
                raise
            bluetooth_diagnostics()
            if not apt_repair(["bluez", "dbus"], yes):
                raise
            asyncio.run(check_bluetooth())
    if not cfg.exists():
        database = data_dir / ("h5074.db" if bluetooth else "demo.db")
        args = ["config", "init", "--database", str(database)]
        if bluetooth:
            names = []
            if yes("Scan for nearby H5074s? Close Govee Home first", True):
                from bleak.exc import BleakError

                try:
                    names = asyncio.run(scan())
                except (OSError, RuntimeError, BleakError) as exc:
                    print("Bluetooth scan:", exc)
            for i, name in enumerate(names, 1):
                print(f"{i}. {name}")
            value = ask("Advertised sensor name or list number", "1" if names else "")
            if value.isdigit() and 1 <= int(value) <= len(names):
                value = names[int(value) - 1]
            if not value or value.isdigit():
                raise ValueError("Supply the exact advertised sensor name.")
            args += ["--sensor-name", value]
        else:
            args.append("--mock")
        args += ["--room", ask("Room", "Living room")]
        if yes("Show this source in the built-in Indoor column?", True):
            args.append("--use-indoor-binding")
        run(*cli(cfg, *args))
    run(*cli(cfg, "config", "validate"))
    return cfg


def station(pi):
    if not INI.exists():
        candidates = [Path.home() / "wfpiconsole", ROOT.parent / "WeatherFlow_PiConsole"]
        if pi:
            wd = service_value("WorkingDirectory")
            if wd:
                candidates.insert(0, Path(wd))
        found = next((p / INI.name for p in candidates if (p / INI.name).is_file()), None)
        if found and yes(f"Reuse station settings from {found}?", True):
            new_file(INI, found.read_bytes())
        else:
            value = ask("Existing station INI path (Enter for PiConsole's station wizard)")
            if value:
                new_file(INI, expanded(value).read_bytes())
            else:
                from lib import config
                config.create()
    else:
        print("Using existing", INI)
    for suffix in ("py", "kv"):
        source = ROOT / "deploy" / f"customPanels.{suffix}"
        target = ROOT / "user" / source.name
        if target.exists() and target.read_bytes() != source.read_bytes():
            print("Existing custom panels detected. See docs/setup.md to merge the pair.")
            return
    for source in (ROOT / "deploy/customPanels.py", ROOT / "deploy/customPanels.kv"):
        target = ROOT / "user" / source.name
        if not target.exists():
            new_file(target, source.read_bytes())


def enable_indoor_column():
    # Change only the visibility flag, preserving comments, keys and other sections.
    original = INI.read_bytes()
    section = re.search(rb"(?ims)^\[Display\][^\n]*\n(.*?)(?=^\[|\Z)", original)
    setting = re.compile(rb"(?im)^(IndoorTemp[ \t]*=[ \t]*)0(?=[ \t]*\r?$)")
    if not section or not setting.search(section[1]):
        return
    if not yes("Enable the Indoor column in this checkout's station INI?", True):
        return
    replacement = setting.sub(rb"\g<1>1", section[1], count=1)
    with tempfile.NamedTemporaryFile(dir=INI.parent, delete=False) as stream:
        temp = Path(stream.name)
    try:
        temp.write_bytes(original[:section.start(1)] + replacement + original[section.end(1):])
        if INI.read_bytes() != original:
            raise RuntimeError("Station settings changed during setup. Rerun after exiting PiConsole.")
        os.replace(temp, INI)
    finally:
        temp.unlink(missing_ok=True)


def launch(cfg, verify):
    from home_telemetry.config import load_config
    from home_telemetry.readers.snapshot import SnapshotReader

    database = load_config(cfg).database
    env = dict(os.environ, HOME_TELEMETRY_CONFIG=str(cfg), HOME_TELEMETRY_DB=str(database))
    if platform.system() == "Darwin":
        env.setdefault("KIVY_METRICS_DENSITY", "1")
        env.setdefault("KIVY_METRICS_FONTSCALE", "1")
    collector = subprocess.Popen(cli(cfg, "run", "--parent-pipe"), stdin=subprocess.PIPE, env=env)
    try:
        if verify:
            print("Waiting up to 120 seconds for a fresh indoor reading…", flush=True)
            reader = SnapshotReader(database)
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                time.sleep(2)
                if collector.poll() is not None:
                    raise RuntimeError("Collector exited. Check its output (including writer-lock errors).")
                snapshot = reader.read()
                choice = snapshot.selected("indoor").selected if "indoor" in snapshot.bindings else None
                if choice and snapshot.running and choice.observation.temperature_c is not None:
                    c = choice.observation.temperature_c
                    print(f"Selected {choice.source.id}: {c:.2f} °C / {c*1.8+32:.1f} °F")
                    break
            else:
                print("No fresh indoor reading yet. Check Bluetooth, sensor name and binding.")
                return False
        display = subprocess.Popen([PYTHON, "main.py"], env=env)
        try:
            while display.poll() is None:
                if collector.poll() is not None:
                    raise RuntimeError("Collector exited. Check its output.")
                time.sleep(0.5)
            if display.returncode:
                raise RuntimeError(f"PiConsole exited with status {display.returncode}.")
        finally:
            stop(display)
    finally:
        collector.stdin.close()
        try:
            collector.wait(timeout=12)
        except subprocess.TimeoutExpired:
            stop(collector)
    return True


def stop(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def desktop_entry(cfg):
    # Desktop Entry string escaping precedes Exec argument unquoting.
    def argument(path):
        text = str(path)
        if any(ord(ch) < 32 for ch in text):
            raise ValueError("Control characters in autostart paths are unsupported.")
        for ch in ('\\', '"', '$', '`'):
            text = text.replace(ch, '\\' + ch)
        return '"' + text.replace('\\', '\\\\').replace('%', '%%') + '"'

    return ("[Desktop Entry]\nType=Application\nName=WeatherFlow Home Console\n"
            f"Exec={argument(ROOT / 'scripts/setup.sh')} --start {argument(cfg)}\n"
            "Terminal=false\n").encode()


def wizard():
    pi = is_pi()
    print("Platform:", "Raspberry Pi" if pi else platform.system(), platform.machine())
    print("Setup directories (config, data):", *user_dirs(), sep="\n  ")
    cfg = configure_telemetry()
    check_display(yes)
    service_tools = pi and shutil.which("systemctl") and shutil.which("sudo") and Path("/run/systemd/system").is_dir()
    if pi and not service_tools:
        print("Pi service switching unavailable: requires systemd, systemctl and sudo. Check for an existing collector before preview.")
    station(bool(service_tools))
    with cfg.open("rb") as stream:
        use_indoor = tomllib.load(stream).get("console", {}).get("use_indoor_binding", False)
    if use_indoor:
        enable_indoor_column()
    if os.name == "nt":
        print(f'Configured. Launch from PowerShell with .\\scripts\\setup-windows.cmd -StartConfig "{cfg}"')
    else:
        print(f"Configured. Launch again with ./scripts/setup.sh --start {shlex.quote(str(cfg))}")
    if platform.system() == "Linux" and not (os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY")):
        print("Open a terminal on the graphical desktop and rerun setup to verify the display.")
        return
    if not yes("Test the collector and display now? Close any manual collector first", True):
        return
    old_active = service_tools and service_value("ActiveState") == "active"
    if old_active:
        if not yes(f"Temporarily stop {UNIT} during the test?"):
            return
        run("sudo", "systemctl", "stop", UNIT)
    switched = False
    try:
        if not launch(cfg, True) or not service_tools:
            return
        if not yes("Did the touchscreen show the expected weather and indoor readings?"):
            return
        if not yes("Start the new console at desktop login (after boot with desktop autologin)?"):
            return
        target = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "autostart/weatherflow-home-console.desktop"
        data = desktop_entry(cfg)
        if target.exists() and target.read_bytes() != data:
            raise RuntimeError(f"Different startup entry exists at {target}. Review it before switching.")
        state = service_value("UnitFileState")
        if state not in {"", "enabled", "disabled", "not-found"}:
            raise RuntimeError(f"Existing service state {state!r} needs manual review.")
        if state == "enabled" and not yes(f"Disable {UNIT} for future boots?"):
            return
        created = not target.exists()
        if created:
            new_file(target, data)
        try:
            if state == "enabled":
                run("sudo", "systemctl", "disable", UNIT)
        except BaseException:
            if created:
                target.unlink()
            raise
        switched = True
        print("Desktop login startup configured.")
    finally:
        if old_active and not switched:
            run("sudo", "systemctl", "start", UNIT)


def smoke_test():
    install_dependencies(False)
    from home_telemetry.readers.snapshot import SnapshotReader

    with tempfile.TemporaryDirectory(prefix="piconsole-smoke-") as tmp:
        cfg = Path(tmp) / "demo.toml"
        db = Path(tmp) / "demo.db"
        run(*cli(cfg, "config", "init", "--mock", "--database", db.as_posix()))
        proc = subprocess.Popen(cli(cfg, "run", "--parent-pipe"), stdin=subprocess.PIPE)
        try:
            for _ in range(60):
                if proc.poll() is not None:
                    raise RuntimeError(f"Mock collector exited during smoke test ({proc.returncode}).")
                decision = SnapshotReader(db).read().selected("indoor")
                if decision.selected and decision.selected.source.id == "demo-main":
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("Timed out waiting for the mock indoor reading.")
        finally:
            proc.stdin.close()
            try:
                proc.wait(timeout=12)
            except subprocess.TimeoutExpired:
                stop(proc)
                raise RuntimeError("Collector did not shut down cleanly.") from None
        if proc.returncode or SnapshotReader(db).read().running:
            raise RuntimeError("Collector shutdown check failed.")
    print("PASS: packages, mock collector, SQLite, indoor selection, and shutdown.")


if __name__ == "__main__":
    os.umask(0o077)
    try:
        if sys.argv[1:2] == ["--start"]:
            launch(expanded(sys.argv[2]), False)
        elif sys.argv[1:] == ["--smoke-test"]:
            smoke_test()
        else:
            wizard()
    except (EOFError, KeyboardInterrupt):
        sys.exit("Setup interrupted.")
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))
