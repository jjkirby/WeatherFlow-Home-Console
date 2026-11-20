"""TOML configuration shared by the CLI and coordinator."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import tomllib

from .exceptions import ConfigurationError
from .logging_utils import register_secret, safe_label, secret_key
from .models import Capability, number

DEFAULT_CONFIG = Path("~/.config/home-telemetry/config.toml")
DEFAULT_DATABASE = Path("~/.local/share/home-telemetry/telemetry.db")
_IDENTIFIER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}")
_ENV = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
NEST_MAX_DAYS = 10


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    id: str
    type: str
    device_id: str
    display_name: str
    room: str | None = None
    enabled: bool = True
    priority: int = 100
    stale_seconds: float = 120
    retention_days: float | None = None
    heartbeat_seconds: float = 300
    settings: dict = field(default_factory=dict, repr=False)


@dataclass(frozen=True, slots=True)
class Binding:
    primary: str | None = None
    fallbacks: tuple[str, ...] = ()
    capability: Capability = Capability.TEMPERATURE
    room: str | None = None
    allow_cross_room: bool = False
    max_age_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class Config:
    database: Path
    providers: tuple[ProviderConfig, ...]
    bindings: dict[str, Binding]
    panel_sources: tuple[str, ...] | None
    cleanup_seconds: float
    use_indoor_binding: bool = False


def _table(raw, allowed, where):
    if not isinstance(raw, dict) or raw.keys() - allowed:
        raise ConfigurationError(f"{where}: expected a table with supported fields")
    return raw


def _identifier(value, where):
    if not safe_label(value) or not _IDENTIFIER.fullmatch(value):
        raise ConfigurationError(f"{where}: expected a logical ID")
    return value


def _label(value, where):
    if not safe_label(value):
        raise ConfigurationError(f"{where}: expected a short display label")
    return value


def _bool(value, where):
    if type(value) is not bool:
        raise ConfigurationError(f"{where}: expected a boolean")
    return value


def _positive(value, where):
    if not number(value, 0.001, 1e9):
        raise ConfigurationError(f"{where}: expected a positive number")
    return value


def _references(value, env, where, sensitive=False):
    if isinstance(value, dict):
        if sensitive:
            raise ConfigurationError(
                f"{where}: use an environment reference for credentials"
            )
        return {
            key: _references(item, env, where, secret_key(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        if sensitive:
            raise ConfigurationError(
                f"{where}: use an environment reference for credentials"
            )
        return [_references(item, env, where) for item in value]
    match = _ENV.fullmatch(value) if isinstance(value, str) else None
    if match:
        name = match[1]
        if not env.get(name):
            raise ConfigurationError(
                f"{where}: required environment variable {name} is missing"
            )
        register_secret(env[name])
        return env[name]
    if sensitive or (isinstance(value, str) and "${" in value):
        raise ConfigurationError(f"{where}: use a whole-value environment reference")
    return value


def _provider(raw, env, resolve_settings):
    raw = _table(
        raw,
        {
            "id",
            "type",
            "device_id",
            "display_name",
            "room",
            "enabled",
            "priority",
            "stale_seconds",
            "retention_days",
            "heartbeat_seconds",
            "settings",
        },
        "providers",
    )
    provider_id = _identifier(raw.get("id"), "providers.id")
    where = f"provider {provider_id}"
    kind = _identifier(raw.get("type"), f"{where}.type")
    enabled = _bool(raw.get("enabled", True), f"{where}.enabled")
    settings = raw.get("settings", {})
    if not isinstance(settings, dict):
        raise ConfigurationError(f"{where}.settings: expected a table")
    priority = raw.get("priority", 100)
    if type(priority) is not int or not -(2**63) <= priority < 2**63:
        raise ConfigurationError(f"{where}.priority: expected a 64-bit integer")
    retention = raw.get("retention_days")
    if retention == "unlimited":
        retention = None
    elif retention is not None:
        retention = _positive(retention, f"{where}.retention_days")
    if kind == "nest_sdm":
        retention = (
            min(retention, NEST_MAX_DAYS) if retention is not None else NEST_MAX_DAYS
        )
    room = raw.get("room")
    return ProviderConfig(
        id=provider_id,
        type=kind,
        device_id=_identifier(raw.get("device_id", provider_id), f"{where}.device_id"),
        display_name=_label(
            raw.get("display_name", provider_id), f"{where}.display_name"
        ),
        room=_label(room, f"{where}.room") if room is not None else None,
        enabled=enabled,
        priority=priority,
        stale_seconds=_positive(
            raw.get("stale_seconds", 120), f"{where}.stale_seconds"
        ),
        retention_days=retention,
        heartbeat_seconds=_positive(
            raw.get("heartbeat_seconds", 300), f"{where}.heartbeat_seconds"
        ),
        settings=(
            _references(settings, env, f"{where}.settings")
            if enabled and resolve_settings
            else {}
        ),
    )


def _source_list(value, where, known):
    if not isinstance(value, list):
        raise ConfigurationError(f"{where}: expected a list of provider IDs")
    sources = tuple(_identifier(item, where) for item in value)
    if set(sources) - known or len(set(sources)) != len(sources):
        raise ConfigurationError(f"{where}: unknown or duplicate provider ID")
    return sources


def _binding(raw, where, known):
    raw = _table(
        raw,
        {
            "primary",
            "fallbacks",
            "capability",
            "room",
            "allow_cross_room",
            "max_age_seconds",
        },
        where,
    )
    primary = raw.get("primary")
    if primary is not None:
        _source_list([primary], f"{where}.primary", known)
    fallbacks = _source_list(raw.get("fallbacks", []), f"{where}.fallbacks", known)
    if primary in fallbacks:
        raise ConfigurationError(f"{where}.fallbacks: repeats the primary source")
    try:
        capability = Capability(raw.get("capability", "temperature"))
        if capability == Capability.DISCOVERY:
            raise ValueError
    except (ValueError, TypeError):
        raise ConfigurationError(
            f"{where}.capability: expected a measurement capability"
        ) from None
    room = raw.get("room")
    age = raw.get("max_age_seconds")
    return Binding(
        primary,
        fallbacks,
        capability,
        _label(room, f"{where}.room") if room is not None else None,
        _bool(raw.get("allow_cross_room", False), f"{where}.allow_cross_room"),
        _positive(age, f"{where}.max_age_seconds") if age is not None else None,
    )


def load_config(path=DEFAULT_CONFIG, *, env=None, registry=None, resolve_settings=True):
    env = os.environ if env is None else env
    path = Path(path).expanduser()
    try:
        with path.open("rb") as stream:
            raw = tomllib.load(stream)
    except OSError:
        raise ConfigurationError("configuration file cannot be opened") from None
    except (tomllib.TOMLDecodeError, UnicodeError):
        raise ConfigurationError(
            "configuration file contains invalid TOML or UTF-8"
        ) from None
    _table(
        raw, {"collector", "providers", "bindings", "panel", "console"}, "configuration"
    )
    collector = _table(
        raw.get("collector", {}), {"database", "cleanup_seconds"}, "collector"
    )
    db = collector.get("database", str(DEFAULT_DATABASE))
    if not safe_label(db):
        raise ConfigurationError("collector.database: expected a file path")
    database = Path(db).expanduser()
    if not database.is_absolute():
        database = path.resolve().parent / database
    entries = raw.get("providers", [])
    if not isinstance(entries, list):
        raise ConfigurationError("providers: expected an array of provider tables")
    providers = tuple(_provider(entry, env, resolve_settings) for entry in entries)
    for item in providers:
        for value in (item.id, item.type, item.device_id, item.display_name, item.room):
            if value is not None and not safe_label(value):
                raise ConfigurationError(
                    "provider public metadata contains a credential"
                )
    known = {item.id for item in providers}
    if len(known) != len(providers):
        raise ConfigurationError("providers.id: duplicate provider ID")
    if len({item.device_id for item in providers}) != len(providers):
        raise ConfigurationError("providers.device_id: duplicate logical device ID")
    bindings = raw.get("bindings", {})
    if not isinstance(bindings, dict):
        raise ConfigurationError("bindings: expected a table")
    parsed_bindings = {}
    for name, value in bindings.items():
        name = _identifier(name, "bindings")
        parsed_bindings[name] = _binding(value, f"binding {name}", known)
    panel = _table(raw.get("panel", {}), {"sources"}, "panel")
    panel_sources = (
        _source_list(panel["sources"], "panel.sources", known)
        if "sources" in panel
        else None
    )
    console = _table(raw.get("console", {}), {"use_indoor_binding"}, "console")
    use_indoor = _bool(
        console.get("use_indoor_binding", False), "console.use_indoor_binding"
    )
    if use_indoor and (
        "indoor" not in parsed_bindings
        or parsed_bindings["indoor"].capability != Capability.TEMPERATURE
    ):
        raise ConfigurationError(
            "console.use_indoor_binding: requires bindings.indoor with temperature capability"
        )
    config = Config(
        database,
        providers,
        parsed_bindings,
        panel_sources,
        _positive(collector.get("cleanup_seconds", 60), "collector.cleanup_seconds"),
        use_indoor,
    )
    if registry is not None:
        for provider in providers:
            registry.validate(provider)
    return config
