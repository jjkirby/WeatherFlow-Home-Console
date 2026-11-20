"""Deterministic selection from normalized observations and public provider metadata."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .models import (
    Capability,
    Connectivity,
    DataQuality,
    HealthStatus,
    IndoorClimateObservation,
    ProviderHealth,
)


class ReadingStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    AUTHENTICATION_REQUIRED = "authentication_required"


@dataclass(frozen=True, slots=True)
class Source:
    id: str
    type: str
    display_name: str
    room: str | None
    enabled: bool
    priority: int
    stale_seconds: float
    retention_days: float | None
    capabilities: frozenset[Capability]
    health: ProviderHealth


@dataclass(frozen=True, slots=True)
class Reading:
    source: Source
    observation: IndoorClimateObservation | None
    status: ReadingStatus


@dataclass(frozen=True, slots=True)
class Decision:
    selected: Reading | None
    explanations: tuple[tuple[str, str], ...]


def reading_status(source, observation, now, max_age=None):
    if source.health.status == HealthStatus.AUTHENTICATION_REQUIRED and source.enabled:
        return ReadingStatus.AUTHENTICATION_REQUIRED
    if not source.enabled or source.health.status not in {
        HealthStatus.HEALTHY,
        HealthStatus.DEGRADED,
        HealthStatus.STALE,
        HealthStatus.STOPPED,
    }:
        return ReadingStatus.UNAVAILABLE
    if not observation or observation.quality == DataQuality.INVALID:
        return ReadingStatus.UNAVAILABLE
    if observation.connectivity == Connectivity.OFFLINE:
        return ReadingStatus.UNAVAILABLE
    age = (now - observation.observed_at).total_seconds()
    threshold = (
        source.stale_seconds if max_age is None else min(source.stale_seconds, max_age)
    )
    if age > threshold or source.health.status == HealthStatus.STALE:
        return ReadingStatus.STALE
    if source.health.status == HealthStatus.STOPPED:
        return ReadingStatus.UNAVAILABLE
    return ReadingStatus.FRESH


def select(binding, sources, observations, now: datetime):
    ordered = ((binding.primary,) if binding.primary else ()) + binding.fallbacks
    if ordered:
        preferred = sources.get(ordered[0])
    else:
        ordered = tuple(sorted(sources, key=lambda key: (sources[key].priority, key)))
        preferred = next(
            (
                sources[key]
                for key in ordered
                if sources[key].enabled
                and binding.capability in sources[key].capabilities
            ),
            None,
        )
    anchor = binding.room or (preferred.room if preferred else None)
    if anchor is None and preferred:
        preferred_observations = observations.get(preferred.id, ())
        if preferred_observations:
            anchor = preferred_observations[0].room

    explanations = []
    for key in ordered:
        source = sources.get(key)
        if source is None or not source.enabled:
            explanations.append((key, "source disabled or missing"))
            continue
        if binding.capability not in source.capabilities:
            explanations.append((key, "required capability not declared"))
            continue
        # A configured room or primary anchors fallback. An unknown primary room
        # cannot establish that an alternate source measures the same room.
        candidates = observations.get(key, ())
        restrict_room = not binding.allow_cross_room and (
            anchor is not None or preferred is None or key != preferred.id
        )
        if restrict_room and candidates:
            candidates = [
                item
                for item in candidates
                if anchor is not None and (item.room or source.room) == anchor
            ]
            if not candidates:
                explanations.append((key, "room mismatch or room unknown"))
                continue
        if binding.room is not None and binding.allow_cross_room:
            # Within a multi-device provider, prefer its reading in the bound room.
            candidates = sorted(
                candidates, key=lambda item: (item.room or source.room) != anchor
            )
        reason = source.health.status.value
        if source.health.status in {HealthStatus.HEALTHY, HealthStatus.DEGRADED}:
            reason = "no observation"
        if (
            restrict_room
            and not candidates
            and (anchor is None or source.room not in {None, anchor})
        ):
            reason = "room mismatch or room unknown"
        for observation in candidates:
            status = reading_status(source, observation, now, binding.max_age_seconds)
            if status != ReadingStatus.FRESH:
                reason = status.value
                continue
            if not observation.supports_value(binding.capability):
                reason = "required measurement missing"
                continue
            explanations.append((key, "fresh reading selected"))
            return Decision(Reading(source, observation, status), tuple(explanations))
        explanations.append((key, reason))
    return Decision(None, tuple(explanations))
