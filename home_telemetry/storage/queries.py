"""Reader-side SQL and conversion to normalized models."""

import json

from ..config import Binding
from ..models import (
    Capability,
    DataQuality,
    HealthStatus,
    IndoorClimateObservation,
    ProviderHealth,
    parse_time,
    utc_text,
)
from ..selection import Source
from .retention import expired


def settings(connection):
    return {
        row["key"]: json.loads(row["value"])
        for row in connection.execute("SELECT key,value FROM settings")
    }


def bindings(data):
    return {
        name: Binding(
            primary=entry["primary"],
            fallbacks=tuple(entry["fallbacks"]),
            capability=Capability(entry["capability"]),
            room=entry["room"],
            allow_cross_room=entry["allow_cross_room"],
            max_age_seconds=entry["max_age_seconds"],
        )
        for name, entry in data.get("bindings", {}).items()
    }


def sources(connection, now):
    result = {}
    for row in connection.execute("SELECT * FROM providers ORDER BY priority,id"):
        observation = parse_time(row["last_observation"])
        last_connection = parse_time(row["last_connection"])
        last_error = parse_time(row["last_error"])
        error_summary = row["error_summary"]
        if row["type"] == "nest_sdm":
            days = row["retention_days"]
            if observation and expired(now, row["type"], days, observation):
                observation = None
            if last_connection and expired(now, row["type"], days, last_connection):
                last_connection = None
            if last_error and expired(now, row["type"], days, last_error):
                last_error = error_summary = None
        result[row["id"]] = Source(
            row["id"],
            row["type"],
            row["display_name"],
            row["room"],
            bool(row["enabled"]),
            row["priority"],
            row["stale_seconds"],
            row["retention_days"],
            frozenset(map(Capability, json.loads(row["capabilities"]))),
            ProviderHealth(
                HealthStatus(row["status"]),
                observation,
                last_connection,
                last_error,
                error_summary,
                row["consecutive_failures"],
            ).sanitized(),
        )
    return result


def _observation(row, source, now):
    received = parse_time(row["received_at"])
    if expired(now, source.type, source.retention_days, received):
        return None
    return IndoorClimateObservation(
        row["provider_id"],
        source.type,
        row["device_id"],
        parse_time(row["observed_at"]),
        received,
        **json.loads(row["payload"]),
    ).validated()


def latest(connection, providers, now):
    result = {}
    for row in connection.execute(
        "SELECT * FROM latest ORDER BY observed_at DESC, device_id"
    ):
        item = _observation(row, providers[row["provider_id"]], now)
        if item is not None:
            result.setdefault(item.provider_id, []).append(item)
    return result


def history(connection, source, now, limit):
    if source is None:
        return ()
    observations = []
    rows = connection.execute(
        """SELECT * FROM observations WHERE provider_id=?
           ORDER BY received_at DESC,id DESC LIMIT ?""",
        (source.id, limit),
    )
    for row in rows:
        item = _observation(row, source, now)
        if item is not None:
            observations.append(item)
    return tuple(observations)


def temperature_extrema(connection, source, device_id, start, end, now):
    """Return the extrema for one device, with the earliest timestamp on ties."""
    lower, upper, through = (utc_text(value) for value in (start, end, now))
    params = (source.id, device_id, lower, upper, through)
    rows = connection.execute(
        """SELECT provider_id,device_id,observed_at,received_at,payload FROM observations
           WHERE provider_id=? AND device_id=?
             AND observed_at>=? AND observed_at<? AND observed_at<=?
           UNION ALL
           SELECT provider_id,device_id,observed_at,received_at,payload FROM latest
           WHERE provider_id=? AND device_id=?
             AND observed_at>=? AND observed_at<? AND observed_at<=?
           ORDER BY observed_at,received_at""",
        params * 2,
    )
    minimum = maximum = None
    for row in rows:
        item = _observation(row, source, now)
        if (
            item is None
            or item.quality == DataQuality.INVALID
            or item.temperature_c is None
        ):
            continue
        if minimum is None or item.temperature_c < minimum.temperature_c:
            minimum = item
        if maximum is None or item.temperature_c > maximum.temperature_c:
            maximum = item
    return minimum, maximum
