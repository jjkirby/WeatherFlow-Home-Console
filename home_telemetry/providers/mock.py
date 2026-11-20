"""Deterministic observations for development without hardware."""

import asyncio
from datetime import timedelta

from ..exceptions import InvalidProviderSetting
from ..models import (
    Capability,
    Connectivity,
    HealthStatus,
    IndoorClimateObservation,
    ProviderHealth,
    number,
    utc_now,
)
from .base import IndoorClimateProvider


class MockProvider(IndoorClimateProvider):
    provider_type = "mock"
    capabilities = frozenset(
        {
            Capability.TEMPERATURE,
            Capability.HUMIDITY,
            Capability.BATTERY,
            Capability.CONNECTIVITY,
            Capability.DISCOVERY,
        }
    )
    description = "Deterministic simulated temperature and humidity."

    @classmethod
    def validate_config(cls, config):
        ranges = {
            "interval_seconds": (0.001, 86400),
            "temperature_c": (-50, 70),
            "humidity_percent": (0, 100),
            "battery_percent": (0, 100),
            "stale_age_seconds": (0, 86400 * 365),
            "fail_after": (0, 1e9),
        }
        for key, value in config.settings.items():
            valid = (
                type(value) is bool
                if key == "vary"
                else (key in ranges and number(value, *ranges[key]))
            )
            if key == "fail_after":
                valid = valid and type(value) is int
            if not valid:
                field = key if key in ranges or key == "vary" else None
                raise InvalidProviderSetting(field)

    async def discover(self):
        return (self.config.device_id,)

    def observation(self, index, now):
        cfg = self.config
        settings = cfg.settings
        offset = (0, 0.25, 0.5, -0.25)[index % 4] if settings.get("vary") else 0
        return IndoorClimateObservation(
            provider_id=cfg.id,
            provider_type=cfg.type,
            device_id=cfg.device_id,
            device_name=cfg.display_name,
            room=cfg.room,
            temperature_c=settings.get("temperature_c", 21.5) + offset,
            humidity_percent=min(
                100, max(0, settings.get("humidity_percent", 45) + offset)
            ),
            battery_percent=settings.get("battery_percent", 90),
            observed_at=now - timedelta(seconds=settings.get("stale_age_seconds", 0)),
            received_at=now,
            connectivity=Connectivity.ONLINE,
            attributes={"simulated": True},
        )

    async def run(self, publish, report_health):
        settings = self.config.settings
        await report_health(
            ProviderHealth(HealthStatus.HEALTHY, last_connection=utc_now())
        )
        index = 0
        while index != settings.get("fail_after"):
            await publish(self.observation(index, utc_now()))
            index += 1
            await asyncio.sleep(settings.get("interval_seconds", 5))
        raise RuntimeError("simulated provider failure")
