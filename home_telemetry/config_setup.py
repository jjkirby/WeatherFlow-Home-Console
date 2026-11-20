"""Generate and install validated, private collector configurations."""

import json
import os
import tempfile
from pathlib import Path

from .config import load_config
from .exceptions import ConfigurationError


def generate(sensor_name, room, database, use_indoor_binding):
    """Create a single-source starter. IDs remain stable if room labels change."""
    govee = sensor_name is not None
    kind = "govee_ble" if govee else "mock"
    label = "Govee H5074" if govee else "Demo thermometer"
    source = "govee-living-room" if govee else "demo-main"
    device = "h5074-living-room" if govee else "demo-thermometer"
    db_name = "h5074" if govee else "demo"
    db = database or f"~/.local/share/home-telemetry/{db_name}.db"

    def quote(value):
        return json.dumps(value, ensure_ascii=False)

    lines = [
        "[collector]",
        f"database = {quote(db)}",
        "",
        "[[providers]]",
        f'id = "{source}"',
        f'type = "{kind}"',
        f'device_id = "{device}"',
        f'display_name = "{label}"',
        f"room = {quote(room)}",
        "stale_seconds = 120",
    ]
    if govee:
        lines.extend(["", "[providers.settings]", f"sensor_name = {quote(sensor_name)}"])
    lines.extend([
        "",
        "[bindings.indoor]",
        f'primary = "{source}"',
        f"room = {quote(room)}",
        'capability = "temperature"',
        "",
        "[panel]",
        f'sources = ["{source}"]',
    ])
    if use_indoor_binding:
        lines.extend(["", "[console]", "use_indoor_binding = true"])
    return ("\n".join(lines) + "\n").encode()


def install(content, destination, registry):
    """Validate beside the destination, then publish atomically without clobbering."""
    path = Path(destination).expanduser()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        temporary.write_bytes(content)
        load_config(temporary, registry=registry)
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_file() and not path.is_symlink() and path.read_bytes() == content:
                return False
            raise ConfigurationError(
                f"Existing configuration preserved at {path}. "
                "Use a new destination or edit the existing file."
            ) from None
        return True
    finally:
        temporary.unlink(missing_ok=True)
