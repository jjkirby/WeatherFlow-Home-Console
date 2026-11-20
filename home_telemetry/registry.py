"""Registry for built-ins and explicitly installed Python entry points."""

from dataclasses import dataclass
from importlib.metadata import entry_points
import inspect
import re

from .exceptions import ConfigurationError, InvalidProviderSetting
from .logging_utils import redact
from .models import Capability, number
from .providers.base import IndoorClimateProvider
from .providers.govee import GoveeProvider
from .providers.mock import MockProvider
from .providers.nest import NestProvider

ENTRY_POINT_GROUP = "home_telemetry.providers"
_TYPE_NAME = re.compile(r"[a-z][a-z0-9_-]{0,63}")


@dataclass(frozen=True, slots=True)
class ProviderType:
    status: str
    description: str
    capabilities: frozenset = frozenset()
    factory: type[IndoorClimateProvider] | None = None


class Registry:
    def __init__(self, *, external=True):
        self.types = {
            "weatherflow_air": ProviderType(
                "planned",
                "Not implemented. WeatherFlow AIR collection is planned.",
                frozenset({Capability.TEMPERATURE, Capability.HUMIDITY}),
            )
        }
        self.plugin_issues = []
        for factory in (MockProvider, GoveeProvider, NestProvider):
            self.register(factory.provider_type, factory)
        if external:
            for entry in entry_points(group=ENTRY_POINT_GROUP):
                if not _TYPE_NAME.fullmatch(entry.name):
                    self.plugin_issues.append(
                        ("(invalid type)", "entry point name ignored")
                    )
                    continue
                if entry.name in self.types:
                    self.plugin_issues.append(
                        (entry.name, "duplicate entry point ignored")
                    )
                    continue
                try:
                    self.register(entry.name, entry.load())
                except (Exception, SystemExit):
                    self.types[entry.name] = ProviderType(
                        "unavailable", "Plugin could not be loaded."
                    )

    def register(self, name, factory):
        if name in self.types:
            raise ConfigurationError("duplicate provider type")
        if (
            not _TYPE_NAME.fullmatch(name)
            or not inspect.isclass(factory)
            or not issubclass(factory, IndoorClimateProvider)
            or inspect.isabstract(factory)
            or factory.provider_type != name
            or not isinstance(factory.capabilities, frozenset)
            or not factory.capabilities
            or any(not isinstance(value, Capability) for value in factory.capabilities)
        ):
            raise ConfigurationError(
                "plugin must declare its type and measurement capabilities"
            )
        limit = factory.max_retention_days
        if limit is not None and not number(limit, 0.001, 1e9):
            raise ConfigurationError("plugin retention limit must be positive")
        self.types[name] = ProviderType(
            "installed" if factory.implemented else "scaffold",
            redact(factory.description),
            factory.capabilities,
            factory,
        )

    def describe(self, name):
        if name not in self.types:
            raise ConfigurationError("unknown provider type; see providers list")
        return self.types[name]

    def validate(self, config):
        try:
            item = self.describe(config.type)
        except ConfigurationError:
            raise ConfigurationError(
                f"provider {config.id}.type: unknown type {config.type}; see providers list"
            ) from None
        if not config.enabled:
            return
        if item.status != "installed":
            raise ConfigurationError(f"provider {config.id}.type: {item.description}")
        try:
            item.factory.validate_config(config)
        except InvalidProviderSetting as error:
            field = "." + redact(error.field) if error.field else ""
            raise ConfigurationError(
                f"provider {config.id}.settings{field}: invalid or missing value"
            ) from None
        except Exception:
            raise ConfigurationError(
                f"provider {config.id}.settings: plugin validation failed"
            ) from None

    def instantiate(self, config):
        item = self.describe(config.type)
        if not config.enabled or item.status != "installed":
            raise ConfigurationError("provider must be enabled and implemented")
        return item.factory(config)
