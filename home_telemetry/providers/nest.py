"""Google Nest SDM scaffold, pending user OAuth and mocked API tests."""

from ..config import NEST_MAX_DAYS
from ..models import Capability
from .base import IndoorClimateProvider


class NestProvider(IndoorClimateProvider):
    provider_type = "nest_sdm"
    implemented = False
    description = (
        "Not implemented. User authorization and live SDM collection are planned."
    )
    max_retention_days = NEST_MAX_DAYS
    capabilities = frozenset(
        {
            Capability.TEMPERATURE,
            Capability.HUMIDITY,
            Capability.CONNECTIVITY,
            Capability.THERMOSTAT_MODE,
            Capability.HEATING_SETPOINT,
            Capability.COOLING_SETPOINT,
            Capability.HVAC_STATUS,
        }
    )

    async def run(self, publish, report_health):
        raise NotImplementedError(self.description)
