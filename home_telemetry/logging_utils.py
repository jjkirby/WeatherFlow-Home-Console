"""Redact credentials at the boundaries where provider data leaves the process."""

import logging
import re

_SECRET_KEY = re.compile(
    r"(?:token|client[_-]?secret|authorization|password|api[_-]?key|bearer|"
    r"oauth[_-]?code|auth[_-]?code|credential|private[_-]?key|secret)",
    re.I,
)
_AUTHORIZATION_HEADER = re.compile(
    r"""\bauthorization['"]?\s*[:=]\s*[^\r\n]+""",
    re.I,
)
_SECRET_TEXT = re.compile(
    r"\bbearer\s+[^\s,;]+|"
    r"[\w.%-]*(?:token|secret|authorization|password|api[_-]?key|"
    r"auth[_-]?code|oauth[_-]?code|credential|private[_-]?key|code)[\w.%-]*"
    r"""['"]?\s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,;&]+)""",
    re.I,
)
_secrets = set()


def secret_key(key):
    return key.casefold() == "code" or bool(_SECRET_KEY.search(key))


def register_secret(value):
    if value:
        _secrets.add(value)


def redact(value):
    value = str(value)
    value = _AUTHORIZATION_HEADER.sub("[redacted]", value)
    value = _SECRET_TEXT.sub("[redacted]", value)
    for secret in sorted(_secrets, key=len, reverse=True):
        value = value.replace(secret, "[redacted]")
    return value


def safe_label(value):
    return (
        isinstance(value, str)
        and 0 < len(value) <= 160
        and value.isprintable()
        and redact(value) == value
    )


class RedactingLogFilter(logging.Filter):
    """Sanitize rendered messages and suppress raw provider tracebacks."""

    def filter(self, record):
        record.msg = redact(record.getMessage())
        record.args = ()
        record.exc_info = record.exc_text = record.stack_info = None
        return True
