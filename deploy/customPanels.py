"""Install as user/customPanels.py alongside the matching KV file."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from kivy.clock import Clock
from kivy.properties import StringProperty
from kivy.uix.relativelayout import RelativeLayout

from home_telemetry.config import DEFAULT_DATABASE
from home_telemetry.readers import SnapshotReader
from panels.template import panelTemplate

_READERS = ThreadPoolExecutor(max_workers=1, thread_name_prefix="indoor-climate")


class IndoorClimatePanel(panelTemplate):
    summary = StringProperty("Waiting for indoor climate data")

    def __init__(self, mode=None, **kwargs):
        self._refresh = None
        self._pending = None
        self._ancestors = []
        self._reader = SnapshotReader(
            os.environ.get("HOME_TELEMETRY_DB", DEFAULT_DATABASE)
        )
        super().__init__(mode, **kwargs)

    def on_parent(self, instance, parent):
        self._check_tree()

    def _check_tree(self, *_args):
        for ancestor in self._ancestors:
            ancestor.unbind(parent=self._check_tree)
        self._ancestors.clear()
        app = getattr(self, "app", None)
        screen = getattr(app, "CurrentConditions", None)
        ancestor = self.parent
        while ancestor is not None and ancestor is not screen:
            ancestor.bind(parent=self._check_tree)
            self._ancestors.append(ancestor)
            ancestor = ancestor.parent
        if screen is not None and ancestor is screen:
            tracked = getattr(app, type(self).__name__, None)
            if tracked is not None and self not in tracked:
                tracked.append(self)
            if self._refresh is None:
                self._refresh = Clock.schedule_interval(self._tick, 1)
                self._tick(0)
            return

        if self._refresh is not None:
            self._refresh.cancel()
            self._refresh = None
        if self._pending is not None:
            self._pending.cancel()
            self._pending = None
        # A layout rebuild detaches a row, leaving the panel parented to its
        # wrapper. Remove the app's reference when any ancestor detaches.
        tracked = getattr(app, type(self).__name__, ())
        if self in tracked:
            tracked.remove(self)

    def _tick(self, _dt):
        if self._pending is None:
            self._pending = _READERS.submit(self._reader.read)
        elif self._pending.done():
            try:
                snapshot = self._pending.result()
                self.summary = self._display(snapshot)
            except Exception:
                self.summary = "Indoor climate data unavailable"
            self._pending = None

    def _display(self, snapshot):
        readings = snapshot.panel_readings()
        if not readings:
            return snapshot.message or "No indoor climate sources selected"
        rows = []
        for item in readings:
            source, obs = item.source, item.observation
            label = (obs.device_name if obs else None) or source.display_name
            location = (obs.room if obs else None) or source.room
            heading = f"{label} · {location}" if location else label
            state = item.status.value.replace("_", " ")
            if source.health.status.value not in {"healthy", "stale"}:
                state += f" · {source.health.status.value.replace('_', ' ')}"
            lines = [heading, f"{source.type} · {state}"]
            if obs:
                values = []
                if obs.temperature_c is not None:
                    values.append(self._temperature(obs.temperature_c))
                if obs.humidity_percent is not None:
                    values.append(f"{obs.humidity_percent:g}% RH")
                if obs.battery_percent is not None:
                    values.append(f"{obs.battery_percent:g}% battery")
                if values:
                    lines.append(" · ".join(values))
                zone = self.app.config.get("Station", "Timezone", fallback="UTC")
                try:
                    local = obs.observed_at.astimezone(ZoneInfo(zone))
                except (ValueError, ZoneInfoNotFoundError):
                    local = obs.observed_at
                connectivity = (
                    f" · {obs.connectivity.value}" if obs.connectivity else ""
                )
                lines.append(f"Last seen {self._time(local)}{connectivity}")
                details = self._details(obs.attributes)
                if details:
                    lines.append(" · ".join(details))
            rows.append("\n".join(lines))
        return "\n\n".join(rows)

    def _temperature(self, value):
        if self.app.config.get("Units", "Temp", fallback="c") == "f":
            return f"{value * 9 / 5 + 32:.1f} °F"
        return f"{value:.1f} °C"

    def _time(self, value: datetime):
        style = self.app.config.get("Display", "TimeFormat", fallback="24 hr")
        clock = (
            value.strftime("%I:%M %p").lstrip("0")
            if style == "12 hr"
            else value.strftime("%H:%M")
        )
        return f"{value:%Y-%m-%d} {clock}"

    def _details(self, attributes):
        details = []
        for key, label in (
            ("thermostat_mode", "Mode"),
            ("hvac_status", "HVAC"),
            ("heat_setpoint_c", "Heat"),
            ("cool_setpoint_c", "Cool"),
        ):
            value = attributes.get(key)
            if key.endswith("_c") and type(value) in (int, float):
                details.append(f"{label} {self._temperature(value)}")
            elif isinstance(value, str):
                details.append(f"{label} {value}")
        return details


class IndoorClimateButton(RelativeLayout):
    pass
