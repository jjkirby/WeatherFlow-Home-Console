"""Optional PiConsole bridge for the built-in indoor temperature display."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import DEFAULT_CONFIG, load_config
from .exceptions import ConfigurationError
from .models import utc_now

FIELDS = ("inTemp", "inTempMin", "inTempMax")


def start_indoor_temperature(app, clock, logger):
    """Load display settings without resolving credentials or loading providers."""
    path = Path(os.environ.get("HOME_TELEMETRY_CONFIG", DEFAULT_CONFIG)).expanduser()
    try:
        if not path.exists():
            return None
        config = load_config(path, resolve_settings=False)
    except (ConfigurationError, OSError) as error:
        logger.warning(
            "Home Telemetry: unable to read console configuration (%s)", error
        )
        return None
    if not config.use_indoor_binding:
        return None

    from lib import observation_format, properties

    try:
        from .readers import SnapshotReader
    except ImportError:
        logger.warning(
            "Home Telemetry: SQLite reader is unavailable on this installation"
        )
        return None

    reader = SnapshotReader(os.environ.get("HOME_TELEMETRY_DB", config.database))
    bridge = IndoorTemperatureBridge(app, reader, observation_format, properties.Obs())
    bridge.event = clock.schedule_interval(bridge.refresh, 1)
    bridge.refresh(0)
    return bridge


class IndoorTemperatureBridge:
    def __init__(self, app, reader, formatter, defaults):
        self.app = app
        self.reader = reader
        self.formatter = formatter
        self.defaults = {key: defaults[key] for key in FIELDS}
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="indoor-temperature"
        )
        self.event = None
        self.pending = None
        self.requested_zone = None
        self.previous = None

    def refresh(self, _dt):
        """Called on the Kivy thread. The worker only reads SQLite."""
        zone = self.app.config["Station"]["Timezone"]
        try:
            day = utc_now().astimezone(ZoneInfo(zone)).date()
        except (ValueError, ZoneInfoNotFoundError):
            self._publish(None)
            return
        if self.pending is not None:
            if not self.pending.done():
                return
            result = self.pending.result()
            if result is not None and zone == self.requested_zone and result.day == day:
                self.previous = result
            else:
                result = None
            self._publish(result)
        self.requested_zone = zone
        self.pending = self.executor.submit(
            self.reader.indoor_temperature, zone, self.previous
        )

    def _publish(self, result):
        observations = self.app.CurrentConditions.Obs
        config = self.app.config
        units = config["Units"]["Temp"]
        values = self.defaults.copy()
        if result is not None:
            for key, sample in zip(
                FIELDS, (result.current, result.minimum, result.maximum)
            ):
                if sample is None:
                    continue
                value = [sample.temperature_c, "c"]
                if key == "inTemp":
                    values[key] = self.formatter.format(
                        self.formatter.units(value, units), "Temp"
                    )
                else:
                    value.extend((sample.observed_at.timestamp(), "s"))
                    values[key] = self.formatter.format(
                        self.formatter.units(value, units), ["Temp", "Time"], config
                    )
        for key, value in values.items():
            if observations.get(key) != value:
                observations[key] = value

    def stop(self):
        if self.event is not None:
            self.event.cancel()
        self.executor.shutdown(wait=False, cancel_futures=True)
