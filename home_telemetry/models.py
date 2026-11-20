"""Provider-independent observation and health contracts."""

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import json
import math

from .logging_utils import redact, safe_label, secret_key


class Capability(StrEnum):
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    BATTERY = "battery"
    SIGNAL_STRENGTH = "signal_strength"
    CONNECTIVITY = "connectivity"
    DISCOVERY = "discovery"
    THERMOSTAT_MODE = "thermostat_mode"
    HEATING_SETPOINT = "heating_setpoint"
    COOLING_SETPOINT = "cooling_setpoint"
    HVAC_STATUS = "hvac_status"


class HealthStatus(StrEnum):
    STARTING = "starting"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALE = "stale"
    AUTHENTICATION_REQUIRED = "authentication_required"
    UNAVAILABLE = "unavailable"
    STOPPED = "stopped"
    ERROR = "error"


class DataQuality(StrEnum):
    GOOD = "good"
    ESTIMATED = "estimated"
    INVALID = "invalid"


class Connectivity(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


def utc_now():
    return datetime.now(timezone.utc)


def utc_text(value):
    if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be timezone-aware UTC")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def parse_time(value):
    return datetime.fromisoformat(value) if value is not None else None


def number(value, low, high):
    return type(value) in (int, float) and low <= value <= high and math.isfinite(value)


def _validate_json(value, depth=0):
    if depth > 8:
        raise ValueError("attributes are too deeply nested")
    if isinstance(value, dict):
        for key, child in value.items():
            if not safe_label(key) or secret_key(key):
                raise ValueError("attributes contain a forbidden key")
            _validate_json(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _validate_json(child, depth + 1)
    elif isinstance(value, str):
        if value and not safe_label(value):
            raise ValueError("attributes contain forbidden text")
    elif value is not None and type(value) not in (bool, int, float):
        raise ValueError("attributes must contain JSON values")


@dataclass(frozen=True, slots=True)
class IndoorClimateObservation:
    provider_id: str
    provider_type: str
    device_id: str
    observed_at: datetime
    received_at: datetime
    device_name: str | None = None
    room: str | None = None
    temperature_c: float | None = None
    humidity_percent: float | None = None
    battery_percent: float | None = None
    signal_strength: float | None = None
    connectivity: Connectivity | None = None
    quality: DataQuality = DataQuality.GOOD
    attributes: dict = field(default_factory=dict)
    model_version: int = 1

    def validated(self):
        for value in (self.provider_id, self.provider_type, self.device_id):
            if not safe_label(value):
                raise ValueError("invalid observation identity")
        for label in (self.device_name, self.room):
            if label is not None and not safe_label(label):
                raise ValueError("invalid observation label")
        utc_text(self.observed_at)
        utc_text(self.received_at)
        if self.observed_at > self.received_at:
            raise ValueError("observation time is after receipt time")
        for value, low, high in (
            (self.temperature_c, -273.15, 1000),
            (self.humidity_percent, 0, 100),
            (self.battery_percent, 0, 100),
            (self.signal_strength, -200, 100),
        ):
            if value is not None and not number(value, low, high):
                raise ValueError("invalid measurement")
        if type(self.model_version) is not int or self.model_version != 1:
            raise ValueError("unsupported observation model version")
        if not isinstance(self.attributes, dict):
            raise ValueError("attributes must be a JSON object")
        _validate_json(self.attributes)
        for key in ("heat_setpoint_c", "cool_setpoint_c"):
            value = self.attributes.get(key)
            if value is not None and not number(value, -273.15, 1000):
                raise ValueError("invalid temperature setpoint")
        for key in ("thermostat_mode", "hvac_status"):
            value = self.attributes.get(key)
            if value is not None and not safe_label(value):
                raise ValueError("invalid thermostat state")
        try:
            encoded = json.dumps(self.attributes, allow_nan=False)
            quality = DataQuality(self.quality)
            connectivity = (
                None if self.connectivity is None else Connectivity(self.connectivity)
            )
        except (ValueError, TypeError):
            raise ValueError("invalid observation status or attributes") from None
        if len(encoded) > 8192:
            raise ValueError("attributes exceed the size limit")
        return replace(
            self,
            attributes=json.loads(encoded),
            quality=quality,
            connectivity=connectivity,
        )

    def supports_value(self, capability):
        fields = {
            Capability.TEMPERATURE: self.temperature_c,
            Capability.HUMIDITY: self.humidity_percent,
            Capability.BATTERY: self.battery_percent,
            Capability.SIGNAL_STRENGTH: self.signal_strength,
            Capability.CONNECTIVITY: self.connectivity,
            Capability.THERMOSTAT_MODE: self.attributes.get("thermostat_mode"),
            Capability.HEATING_SETPOINT: self.attributes.get("heat_setpoint_c"),
            Capability.COOLING_SETPOINT: self.attributes.get("cool_setpoint_c"),
            Capability.HVAC_STATUS: self.attributes.get("hvac_status"),
        }
        return fields.get(capability) is not None


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    status: HealthStatus
    last_observation: datetime | None = None
    last_connection: datetime | None = None
    last_error: datetime | None = None
    error_summary: str | None = None
    consecutive_failures: int = 0

    def sanitized(self):
        for value in (self.last_observation, self.last_connection, self.last_error):
            if value is not None:
                utc_text(value)
        if type(self.consecutive_failures) is not int or self.consecutive_failures < 0:
            raise ValueError("invalid failure count")
        return replace(
            self,
            status=HealthStatus(self.status),
            error_summary=(
                redact(self.error_summary)[:160] if self.error_summary else None
            ),
        )
