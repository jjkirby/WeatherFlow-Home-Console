import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from home_telemetry.config import ProviderConfig, load_config
from home_telemetry.exceptions import ConfigurationError
from home_telemetry.models import Capability
from home_telemetry.providers.mock import MockProvider
from home_telemetry.registry import ENTRY_POINT_GROUP, Registry


MOCK = """
[[providers]]
id = "fake-a"
type = "mock"
device_id = "fake-device-a"
priority = 10
room = "Demo room"
"""


class ConfigTests(unittest.TestCase):
    def read(self, content, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(content)
            return load_config(path, **kwargs)

    def test_example_and_disabled_scaffolds(self):
        config = load_config(
            Path("deploy/home-telemetry.toml.example"),
            registry=Registry(external=False),
        )
        self.assertEqual(len(config.providers), 5)
        self.assertEqual(config.panel_sources[:2], ("demo-main", "demo-backup"))
        self.assertEqual(config.bindings["indoor"].fallbacks, ("demo-backup",))
        self.assertEqual(config.providers[0].priority, 10)
        self.assertIsNone(config.providers[0].retention_days)

    def test_binds_known_ids_and_checks_types(self):
        for config in (
            MOCK + '[bindings.indoor]\nprimary="unknown"\n',
            MOCK + '[bindings.indoor]\ncapability="discovery"\n',
            MOCK + '[bindings.indoor]\nprimary=["fake-a"]\n',
            MOCK.replace("priority = 10", "priority = true"),
        ):
            with self.subTest(config=config), self.assertRaises(ConfigurationError):
                self.read(config)

    def test_rejects_duplicate_ids_and_devices(self):
        for other in (
            MOCK.replace("fake-device-a", "fake-device-b"),
            MOCK.replace('"fake-a"', '"fake-b"'),
        ):
            with (
                self.subTest(other=other),
                self.assertRaisesRegex(ConfigurationError, "duplicate"),
            ):
                self.read(MOCK + other)

    def test_environment_reference_missing_and_secret_avoids_repr(self):
        content = MOCK + '[providers.settings]\napi_key="${EXAMPLE_API_KEY}"\n'
        with self.assertRaisesRegex(
            ConfigurationError, r"fake-a.settings.*EXAMPLE_API_KEY"
        ):
            self.read(content, env={})
        secret = "EXAMPLE-FAKE-API-SECRET"
        result = self.read(content, env={"EXAMPLE_API_KEY": secret})
        self.assertEqual(result.providers[0].settings["api_key"], secret)
        self.assertNotIn(secret, repr(result))
        with self.assertRaisesRegex(ConfigurationError, "whole-value") as failure:
            self.read(content.replace("${EXAMPLE_API_KEY}", "EXAMPLE-FAKE-LITERAL"))
        self.assertNotIn("EXAMPLE-FAKE-LITERAL", str(failure.exception))
        with self.assertRaisesRegex(ConfigurationError, "environment reference"):
            self.read(
                MOCK + '[providers.settings]\napi_key={ nested = "EXAMPLE-FAKE" }\n'
            )

    def test_nest_maximum_and_disabled_environment_resolution(self):
        nest = MOCK.replace('type = "mock"', 'type = "nest_sdm"')
        nest += (
            "enabled=false\nretention_days=100\n[providers.settings]\n"
            'refresh_token="${EXAMPLE_REFRESH_TOKEN}"'
        )
        config = self.read(nest, env={}, registry=Registry(external=False))
        self.assertEqual(config.providers[0].retention_days, 10)
        self.assertEqual(config.providers[0].settings, {})

    def test_invalid_govee_and_mock_settings(self):
        registry = Registry(external=False)
        with self.assertRaisesRegex(
            ConfigurationError, r"fake-a.settings\.sensor_name"
        ):
            self.read(MOCK.replace('"mock"', '"govee_ble"'), registry=registry)
        with self.assertRaisesRegex(ConfigurationError, r"fake-a.settings\.fail_after"):
            self.read(
                MOCK + "[providers.settings]\nfail_after=1.5\n", registry=registry
            )


class ExternalMock(MockProvider):
    provider_type = "external_demo"


class MissingCapability(MockProvider):
    provider_type = "missing_demo"
    capabilities = frozenset()


class RegistryTests(unittest.TestCase):
    def test_builtins_and_unknown_type(self):
        registry = Registry(external=False)
        found = registry.describe("mock")
        self.assertIn(Capability.DISCOVERY, found.capabilities)
        self.assertIsInstance(
            registry.instantiate(ProviderConfig("demo", "mock", "demo", "Demo")),
            MockProvider,
        )
        self.assertEqual(registry.describe("weatherflow_air").status, "planned")
        with self.assertRaisesRegex(ConfigurationError, r"demo.type.*unknown"):
            registry.validate(
                ProviderConfig("demo", "external_unknown", "demo", "Demo")
            )
        with self.assertRaisesRegex(ConfigurationError, "duplicate"):
            registry.register("mock", MockProvider)
        with self.assertRaisesRegex(ConfigurationError, "capabilities"):
            registry.register(MissingCapability.provider_type, MissingCapability)

    def test_entry_points_isolated_and_builtin_cannot_be_shadowed(self):
        def fail():
            raise ImportError("EXAMPLE-FAKE-RAW-RESPONSE")

        entries = [
            SimpleNamespace(name="external_demo", load=lambda: ExternalMock),
            SimpleNamespace(name="broken_demo", load=fail),
            SimpleNamespace(name="mock", load=fail),
            SimpleNamespace(name="../untrusted", load=fail),
        ]
        with patch(
            "home_telemetry.registry.entry_points", return_value=entries
        ) as discover:
            registry = Registry()
        discover.assert_called_once_with(group=ENTRY_POINT_GROUP)
        self.assertIs(registry.describe("external_demo").factory, ExternalMock)
        self.assertEqual(registry.describe("broken_demo").status, "unavailable")
        self.assertNotIn(
            "EXAMPLE-FAKE-RAW-RESPONSE", registry.describe("broken_demo").description
        )
        self.assertIs(registry.describe("mock").factory, MockProvider)
        self.assertNotIn("../untrusted", registry.types)

    def test_environment_file_example_and_provider_docs(self):
        registry = Registry(external=False)
        filenames = {"govee_ble": "govee", "nest_sdm": "nest"}
        for kind in registry.types:
            with self.subTest(kind=kind):
                doc = Path("docs/providers", filenames.get(kind, kind) + ".md")
                contents = doc.read_text()
                self.assertIn(f'type = "{kind}"', contents)
                if registry.describe(kind).status != "installed":
                    self.assertIn("enabled = false", contents)
        self.assertIn("H5074", Path("docs/providers/govee.md").read_text())
        self.assertFalse(os.path.exists("deploy/collector.env"))
