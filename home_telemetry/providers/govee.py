"""Govee BLE scaffold, pending model identification and hardware tests."""

from ..models import Capability
from .base import IndoorClimateProvider


class GoveeProvider(IndoorClimateProvider):
    provider_type = "govee_ble"
    implemented = False
    description = (
        "Not implemented. Discovery and decoding require a verified sensor model."
    )
    capabilities = frozenset(
        {
            Capability.TEMPERATURE,
            Capability.HUMIDITY,
            Capability.BATTERY,
            Capability.SIGNAL_STRENGTH,
            Capability.DISCOVERY,
        }
    )

    async def run(self, publish, report_health):
        raise NotImplementedError(self.description)
