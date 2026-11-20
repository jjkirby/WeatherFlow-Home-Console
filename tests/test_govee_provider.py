import asyncio
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from home_telemetry.config import Binding, Config, ProviderConfig
from home_telemetry.coordinator import Coordinator
from home_telemetry.exceptions import ConfigurationError
from home_telemetry.models import HealthStatus
from home_telemetry.providers.govee import _AdvertisementMatcher, decode_h5074
from home_telemetry.readers import SnapshotReader
from home_telemetry.registry import Registry

# Captured on macOS with Bleak. The address is deliberately synthetic.
SENSOR_NAME = "Govee_H5074_9844"
MANUFACTURER_ID = 0xEC88
CAPTURE = bytes.fromhex("00 cd 08 41 0a 64 02")


def device(address, name=None):
    return SimpleNamespace(address=address, name=name)


def advertisement(name=None, payload=None, manufacturer=MANUFACTURER_ID):
    data = {} if payload is None else {manufacturer: payload}
    return SimpleNamespace(local_name=name, manufacturer_data=data, rssi=-62)


class H5074DecoderTests(unittest.TestCase):
    def test_macos_capture(self):
        self.assertEqual(decode_h5074(CAPTURE), (22.53, 26.25, 100))

    def test_signed_below_freezing_temperature(self):
        self.assertEqual(
            decode_h5074(bytes.fromhex("00 f3 fd 41 0a 64 02")),
            (-5.25, 26.25, 100),
        )

    def test_malformed_packets(self):
        for payload in (
            b"",
            CAPTURE[:-1],
            CAPTURE + b"\x00",
            bytes.fromhex("00 00 80 41 0a 64 02"),  # Below absolute zero
            bytes.fromhex("00 cd 08 11 27 64 02"),  # 100.01% RH
            bytes.fromhex("00 cd 08 41 0a 65 02"),  # 101% battery
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                decode_h5074(payload)


class H5074MatcherTests(unittest.TestCase):
    def test_name_and_payload_arrive_in_separate_callbacks(self):
        matcher = _AdvertisementMatcher(SENSOR_NAME)
        target = device("target")
        self.assertIsNone(matcher.sample(target, advertisement(name=SENSOR_NAME)))
        self.assertIsNone(
            matcher.sample(device("other"), advertisement(payload=CAPTURE))
        )
        actual = matcher.sample(target, advertisement(payload=CAPTURE))
        self.assertEqual(actual[:3], (22.53, 26.25, 100))

    def test_payload_can_arrive_first_but_cannot_cross_device_addresses(self):
        matcher = _AdvertisementMatcher(SENSOR_NAME)
        target = device("target")
        self.assertIsNone(
            matcher.sample(device("other"), advertisement(payload=CAPTURE))
        )
        self.assertIsNone(matcher.sample(target, advertisement(payload=CAPTURE)))
        result = matcher.sample(target, advertisement(name=SENSOR_NAME))
        self.assertEqual(result[:3], (22.53, 26.25, 100))
        self.assertIsNone(matcher.sample(target, advertisement(name=SENSOR_NAME)))

    def test_other_models_and_manufacturer_ids_are_ignored(self):
        matcher = _AdvertisementMatcher(SENSOR_NAME)
        target = device("target")
        for name in ("Govee_H5083_9844", "Govee_H5074_1111", "Govee_H5074_9844_other"):
            other = device("other", name=SENSOR_NAME)
            self.assertIsNone(matcher.sample(other, advertisement(name, CAPTURE)))
        self.assertIsNone(
            matcher.sample(target, advertisement(SENSOR_NAME, CAPTURE, 0x0001))
        )
        self.assertIsNone(
            matcher.sample(target, advertisement(SENSOR_NAME, CAPTURE[:-1]))
        )
        self.assertIsNone(
            matcher.sample(target, advertisement("Govee_H5083_9844", CAPTURE))
        )
        self.assertIsNone(matcher.sample(target, advertisement(payload=CAPTURE)))

    def test_expired_payload_is_not_replayed_when_name_arrives(self):
        matcher = _AdvertisementMatcher(SENSOR_NAME)
        target = device("target")
        with patch("home_telemetry.providers.govee.monotonic", side_effect=[100, 131]):
            self.assertIsNone(matcher.sample(target, advertisement(payload=CAPTURE)))
            self.assertIsNone(matcher.sample(target, advertisement(name=SENSOR_NAME)))


class H5074ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_offline_scan_sqlite_selection_and_stop(self):
        addresses = iter(("mac-uuid-before-restart", "mac-uuid-after-restart"))
        scans = []

        class FakeScanner:
            def __init__(self, *, detection_callback):
                self.callback = detection_callback
                self.closed = False
                scans.append(self)

            async def __aenter__(self):
                target = device(next(addresses))
                self.callback(target, advertisement(name=SENSOR_NAME))
                self.callback(
                    device("wrong"), advertisement("Govee_H5083_9844", CAPTURE)
                )
                self.callback(target, advertisement(payload=CAPTURE))
                repeat = advertisement(payload=CAPTURE)
                repeat.rssi = -71
                self.callback(target, repeat)
                return self

            async def __aexit__(self, *_exception_info):
                self.closed = True

        registry = Registry(external=False)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "govee.db"
            govee = ProviderConfig(
                "my-govee",
                "govee_ble",
                "stable-device-id",
                "Govee H5074",
                room="Living room",
                settings={"sensor_name": SENSOR_NAME},
            )
            config = Config(
                path, (govee,), {"indoor": Binding(primary="my-govee")}, None, 60
            )
            reader = SnapshotReader(path)
            with patch.dict(
                sys.modules, {"bleak": SimpleNamespace(BleakScanner=FakeScanner)}
            ):
                for _ in range(2):
                    stop = asyncio.Event()
                    task = asyncio.create_task(Coordinator(config, registry).run(stop))
                    try:
                        async with asyncio.timeout(2):
                            while True:
                                selected = reader.read().selected("indoor").selected
                                if selected is not None:
                                    break
                                await asyncio.sleep(0.005)
                        self.assertEqual(selected.source.id, "my-govee")
                        self.assertEqual(
                            selected.observation.device_id, "stable-device-id"
                        )
                        self.assertEqual(selected.observation.temperature_c, 22.53)
                        self.assertEqual(selected.observation.humidity_percent, 26.25)
                        self.assertEqual(selected.observation.battery_percent, 100)
                        self.assertEqual(
                            selected.source.health.status, HealthStatus.HEALTHY
                        )
                    finally:
                        stop.set()
                        await asyncio.wait_for(task, 2)
                    self.assertTrue(scans[-1].closed)
            self.assertEqual(len(scans), 2)
            self.assertEqual(len(reader.recent_history("my-govee")), 1)

    def test_config_rejects_other_models(self):
        registry = Registry(external=False)
        config = ProviderConfig(
            "govee",
            "govee_ble",
            "device",
            "Govee",
            settings={"sensor_name": "Govee_H5083_9844"},
        )
        with self.assertRaisesRegex(ConfigurationError, r"settings\.sensor_name"):
            registry.validate(config)
