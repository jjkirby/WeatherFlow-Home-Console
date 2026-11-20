from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest

from home_telemetry.config import Binding
from home_telemetry.logging_utils import redact, register_secret
from home_telemetry.models import (
    Capability,
    Connectivity,
    DataQuality,
    HealthStatus,
    IndoorClimateObservation,
    ProviderHealth,
)
from home_telemetry.selection import Source, select

NOW = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)


def observation(key, **kwargs):
    default = dict(device_name="Demo", room="Living room", temperature_c=21.25)
    default.update(kwargs)
    return IndoorClimateObservation(key, "mock", f"device-{key}", NOW, NOW, **default)


def source(key, **kwargs):
    options = dict(
        type="mock",
        display_name="Demo",
        room="Living room",
        enabled=True,
        priority=100,
        stale_seconds=60,
        retention_days=None,
        capabilities=frozenset({Capability.TEMPERATURE}),
        health=ProviderHealth(HealthStatus.HEALTHY),
    )
    options.update(kwargs)
    return Source(key, **options)


class ModelTests(unittest.TestCase):
    def test_optional_values_and_json_copy(self):
        attrs = {"firmware": "Demo v1", "nested": [{"heat_setpoint_c": 22.0}]}
        value = observation("a", attributes=attrs).validated()
        self.assertEqual(value.temperature_c, 21.25)
        self.assertIsNone(value.humidity_percent)
        self.assertIsNone(value.battery_percent)
        attrs["nested"][0]["heat_setpoint_c"] = 19.0
        self.assertEqual(value.attributes["nested"][0]["heat_setpoint_c"], 22.0)

    def test_invalid_observations(self):
        valid = observation("a")
        malformed = (
            replace(valid, observed_at=NOW.replace(tzinfo=None)),
            replace(valid, observed_at=NOW.astimezone(timezone(timedelta(hours=1)))),
            replace(valid, observed_at=NOW + timedelta(seconds=1)),
            replace(valid, humidity_percent=101),
            replace(valid, battery_percent=True),
            replace(valid, temperature_c=float("inf")),
            replace(valid, model_version=2),
            replace(valid, attributes={"item": object()}),
            replace(valid, attributes={"item": float("nan")}),
            replace(valid, attributes={"nested": [{"api_key": "FAKE"}]}),
            replace(valid, attributes={"thing": "Authorization: Bearer FAKE-BEARER"}),
            replace(valid, attributes={12: "invalid key"}),
        )
        for item in malformed:
            with self.subTest(item=item), self.assertRaises(ValueError):
                item.validated()

    def test_central_redaction_for_keys_and_known_values(self):
        secret = "FIXTURE-FAKE-REGISTERED-SECRET"
        register_secret(secret)
        for text in (
            f"value {secret}",
            "access_token=FAKE-ACCESS",
            "refresh_token: FAKE-REFRESH",
            "client_secret='FAKE SECRET'",
            "authorization: Bearer FAKE-BEARER",
            '"password": "FAKE SECRET"',
            "api_key=FAKE-API",
            "Bearer FAKE-VALUE",
            "https://example.invalid/?code=FAKE-CODE",
        ):
            with self.subTest(text=text):
                self.assertIn("[redacted]", redact(text))
                self.assertNotIn("FAKE", redact(text))
        with self.assertRaisesRegex(ValueError, "forbidden text"):
            observation("a", attributes={"firmware": f"seen {secret}"}).validated()
        health = ProviderHealth(
            HealthStatus.ERROR, error_summary=f"error: {secret}"
        ).sanitized()
        self.assertNotIn(secret, health.error_summary)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.sources = {key: source(key) for key in ("main", "alpha", "beta")}
        self.observations = {key: (observation(key),) for key in self.sources}
        self.binding = Binding("main", ("beta", "alpha"))

    def choose(self, binding=None):
        return select(binding or self.binding, self.sources, self.observations, NOW)

    def test_primary_and_ordered_fallback(self):
        self.assertEqual(self.choose().selected.source.id, "main")
        self.observations["main"] = (
            replace(observation("main"), observed_at=NOW - timedelta(seconds=90)),
        )
        decision = self.choose()
        self.assertEqual(decision.selected.source.id, "beta")
        self.assertEqual(
            decision.explanations,
            (
                ("main", "stale"),
                ("beta", "fresh reading selected"),
            ),
        )

    def test_health_missing_capability_and_missing_value(self):
        self.sources["main"] = source("main", health=ProviderHealth(HealthStatus.ERROR))
        self.sources["beta"] = source(
            "beta", capabilities=frozenset({Capability.HUMIDITY})
        )
        self.observations["alpha"] = (observation("alpha", temperature_c=None),)
        self.assertEqual(
            self.choose().explanations,
            (
                ("main", "unavailable"),
                ("beta", "required capability not declared"),
                ("alpha", "required measurement missing"),
            ),
        )
        self.assertIsNone(self.choose().selected)
        self.sources["main"] = source(
            "main",
            health=ProviderHealth(HealthStatus.AUTHENTICATION_REQUIRED),
        )
        self.observations["main"] = ()
        self.assertEqual(
            self.choose().explanations[0], ("main", "authentication_required")
        )

    def test_room_mismatch_and_explicit_cross_room(self):
        self.observations["main"] = (
            observation("main", connectivity=Connectivity.OFFLINE),
        )
        for key in ("alpha", "beta"):
            self.sources[key] = source(key, room="Entryway")
            self.observations[key] = (observation(key, room="Entryway"),)
        self.assertIsNone(self.choose().selected)
        self.assertIn("room mismatch", self.choose().explanations[-1][1])
        self.assertEqual(
            self.choose(
                replace(self.binding, allow_cross_room=True)
            ).selected.source.id,
            "beta",
        )

    def test_priority_then_id_and_binding_threshold(self):
        self.assertEqual(self.choose(Binding()).selected.source.id, "alpha")
        self.sources["beta"] = source("beta", priority=1)
        self.assertEqual(self.choose(Binding()).selected.source.id, "beta")
        self.observations["beta"] = (
            replace(observation("beta"), observed_at=NOW - timedelta(seconds=5)),
        )
        self.assertEqual(
            self.choose(Binding(max_age_seconds=1)).selected.source.id, "alpha"
        )

    def test_no_mix_when_automatically_ranked_source_is_unhealthy(self):
        self.sources["beta"] = source("beta", priority=1, room="Entryway")
        self.observations["beta"] = (
            observation("beta", room="Entryway", quality=DataQuality.INVALID),
        )
        self.assertIsNone(self.choose(Binding()).selected)
        self.assertEqual(
            self.choose(Binding(room="Living room")).selected.source.id, "alpha"
        )
