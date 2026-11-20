import re


class TelemetryError(Exception):
    """An error with a message suitable for the CLI."""


class ConfigurationError(TelemetryError):
    """Invalid collector configuration."""


class InvalidProviderSetting(ConfigurationError):
    """Report a schema field, without allowing arbitrary exception messages."""

    def __init__(self, field=None):
        self.field = (
            field
            if isinstance(field, str)
            and re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_.-]{0,79}", field)
            else None
        )
        super().__init__("invalid provider setting")


class SchemaError(TelemetryError):
    """Unsupported or uninitialized database schema."""


class WriterBusy(TelemetryError):
    """Another collector or maintenance command holds the writer lock."""
