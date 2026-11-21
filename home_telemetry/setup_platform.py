"""Desktop setup defaults and native capability checks."""
from pathlib import Path
import os
import platform
import shutil
import subprocess
import sys


def is_pi():
    if platform.system() != "Linux":
        return False
    for model in ("/proc/device-tree/model", "/sys/firmware/devicetree/base/model"):
        try:
            return b"Raspberry Pi" in Path(model).read_bytes()
        except OSError:
            continue
    return False


def directories(system, home, env):
    def base(key, fallback):
        value = Path(env.get(key) or fallback)
        return value if value.is_absolute() else fallback

    if system == "Windows":
        config = base("APPDATA", home / "AppData/Roaming")
        data = base("LOCALAPPDATA", home / "AppData/Local")
    elif system == "Darwin":
        config, data = home / ".config", home / ".local/share"
    elif system == "Linux":
        config = base("XDG_CONFIG_HOME", home / ".config")
        data = base("XDG_DATA_HOME", home / ".local/share")
    else:
        raise ValueError(f"Unsupported operating system: {system}")
    return config / "home-telemetry", data / "home-telemetry"


def user_dirs():
    return directories(platform.system(), Path.home(), os.environ)


def check_display(confirm=None):
    system = platform.system()
    if system == "Linux" and not (os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY")):
        print("Display check deferred. Run setup on the graphical desktop to verify Kivy.")
        return
    # A subprocess also isolates SDL startup failures from the configuration wizard.
    probe = ("from kivy.core.window import Window; "
             "from kivy.graphics.opengl import glGetString, GL_VERSION; "
             "assert Window is not None and glGetString(GL_VERSION), 'No OpenGL window'")
    result = subprocess.run([sys.executable, "-c", probe], timeout=45)
    if result.returncode and system == "Linux" and confirm:
        if apt_repair(["libgl1", "libegl1", "libgl1-mesa-dri"], confirm):
            result = subprocess.run([sys.executable, "-c", probe], timeout=45)
    if result.returncode:
        hint = {"Windows": "Check the GPU driver and Kivy SDL2 wheel dependencies.",
                "Darwin": "Run from a logged-in Mac desktop and check the Kivy wheel for this CPU.",
                "Linux": "Check the desktop session, SDL2 and OpenGL/EGL graphics driver."}
        raise RuntimeError(f"Kivy window test failed. {hint[system]}")
    print("Kivy window and OpenGL check passed.")


async def check_bluetooth():
    from bleak import BleakScanner
    import asyncio

    try:
        async with BleakScanner():
            await asyncio.sleep(2)
    except Exception as error:
        hint = {"Linux": "Check BlueZ, the system D-Bus, adapter power, and access for this user.",
                "Darwin": "Check Bluetooth power and Privacy & Security > Bluetooth for your terminal or IDE.",
                "Windows": "Check Bluetooth power and the Bluetooth adapter driver in Device Manager."}
        raise RuntimeError(f"Bluetooth scan could not start. {hint[platform.system()]} ({error})") from error
    print("Bluetooth scanner started and stopped successfully.")

def apt_repair(packages, confirm):
    """Offer targeted Debian-family repairs after a native capability failure."""
    try:
        distro = platform.freedesktop_os_release().get("ID")
    except OSError:
        return False
    if distro not in {"debian", "raspbian", "ubuntu"}:
        return False
    if not all(shutil.which(tool) for tool in ("sudo", "apt-get", "dpkg-query")):
        return False
    missing = []
    for name in packages:
        query = subprocess.run(["dpkg-query", "-W", "-f=${Status}", name],
                               capture_output=True, text=True)
        if query.stdout.strip() != "install ok installed":
            missing.append(name)
    if not missing:
        return False
    command = ["sudo", "apt-get", "install", *missing]
    if not confirm("Run " + " ".join(command) + "?"):
        return False
    subprocess.run(command, check=True)
    return True


def bluetooth_diagnostics():
    if not os.getenv("DBUS_SYSTEM_BUS_ADDRESS") and not Path("/run/dbus/system_bus_socket").exists():
        print("System D-Bus socket missing. Check the system bus and desktop session.")
    if shutil.which("bluetoothctl"):
        try:
            state = subprocess.run(["bluetoothctl", "show"], capture_output=True,
                                   text=True, timeout=6)
            power = next((line.strip() for line in state.stdout.splitlines()
                          if "Powered:" in line), "")
            print("BlueZ controller:", power or "no default controller reported")
        except subprocess.TimeoutExpired:
            print("BlueZ controller query timed out. Check bluetooth.service.")
