"""Read Govee H5074 measurements from Bluetooth advertisements."""

import asyncio
import logging
from time import monotonic

from ..exceptions import InvalidProviderSetting
from ..logging_utils import safe_label
from ..models import (
    Capability,
    HealthStatus,
    IndoorClimateObservation,
    ProviderHealth,
    utc_now,
)
from .base import IndoorClimateProvider

_LOG = logging.getLogger(__name__)
_H5074_PREFIX = "Govee_H5074_"
_MANUFACTURER_ID = 0xEC88
_PENDING_LIMIT = 32
_PENDING_SECONDS = 30


def decode_h5074(payload: bytes) -> tuple[float, float, int]:
    """Decode a seven-byte H5074 manufacturer payload from Bleak."""
    if not isinstance(payload, bytes) or len(payload) != 7:
        raise ValueError("expected a seven-byte H5074 payload")
    temperature = int.from_bytes(payload[1:3], "little", signed=True) / 100
    humidity = int.from_bytes(payload[3:5], "little") / 100
    battery = payload[5]
    if temperature < -273.15 or humidity > 100 or battery > 100:
        raise ValueError("invalid measurement in H5074 payload")
    return temperature, humidity, battery


class _AdvertisementMatcher:
    def __init__(self, sensor_name):
        self.sensor_name = sensor_name
        self.address = None
        self.pending = {}

    def sample(self, device, advertisement):
        address = device.address
        name = advertisement.local_name or device.name
        if name and name != self.sensor_name:
            self.pending.pop(address, None)
            if address == self.address:
                self.address = None
            return None
        if self.address is not None and address != self.address:
            return None
        if name == self.sensor_name:
            self.address = address

        sample = None
        payload = advertisement.manufacturer_data.get(_MANUFACTURER_ID)
        if payload is not None:
            try:
                values = decode_h5074(payload)
            except ValueError:
                self.pending.pop(address, None)
                return None
            sample = (*values, utc_now())

        if address == self.address:
            pending = self.pending.pop(address, None)
            if (
                sample is None
                and pending
                and monotonic() - pending[0] <= _PENDING_SECONDS
            ):
                sample = pending[1]
            return sample
        if sample is not None:
            # Handle manufacturer data arriving before the name. Only keep a
            # recent candidate per address and cap the number of nearby devices.
            self.pending.pop(address, None)
            if len(self.pending) >= _PENDING_LIMIT:
                self.pending.pop(next(iter(self.pending)))
            self.pending[address] = (monotonic(), sample)
        return None


class GoveeProvider(IndoorClimateProvider):
    provider_type = "govee_ble"
    description = (
        "Govee H5074 temperature, humidity, and battery from BLE advertisements."
    )
    capabilities = frozenset(
        {
            Capability.TEMPERATURE,
            Capability.HUMIDITY,
            Capability.BATTERY,
        }
    )

    @classmethod
    def validate_config(cls, config):
        name = config.settings.get("sensor_name")
        if (
            not safe_label(name)
            or not name.startswith(_H5074_PREFIX)
            or not name.removeprefix(_H5074_PREFIX).strip()
            or name != name.strip()
        ):
            raise InvalidProviderSetting("sensor_name")
        if config.settings.keys() - {"sensor_name"}:
            raise InvalidProviderSetting()

    async def run(self, publish, report_health):
        try:
            from bleak import BleakScanner
        except ImportError:
            _LOG.error(
                "Govee H5074 requires Bleak. Install the package with the govee extra."
            )
            raise RuntimeError("Bleak is unavailable") from None

        config = self.config
        matcher = _AdvertisementMatcher(config.settings["sensor_name"])
        samples = asyncio.Queue(maxsize=32)

        def on_advertisement(device, advertisement):
            sample = matcher.sample(device, advertisement)
            if sample is not None:
                if samples.full():
                    samples.get_nowait()
                samples.put_nowait(sample)

        async with BleakScanner(detection_callback=on_advertisement):
            await report_health(ProviderHealth(HealthStatus.HEALTHY))
            while True:
                temperature, humidity, battery, timestamp = await samples.get()
                await publish(
                    IndoorClimateObservation(
                        provider_id=self.provider_id,
                        provider_type=self.provider_type,
                        device_id=config.device_id,
                        device_name=config.display_name,
                        room=config.room,
                        temperature_c=temperature,
                        humidity_percent=humidity,
                        battery_percent=battery,
                        observed_at=timestamp,
                        received_at=timestamp,
                    )
                )
