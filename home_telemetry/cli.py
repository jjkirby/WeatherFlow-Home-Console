"""Command-line interface for the Home Telemetry collector."""

import argparse
import asyncio
import logging
import os
from pathlib import Path
import signal
import sqlite3

from .config import DEFAULT_CONFIG, ProviderConfig, load_config
from .coordinator import Coordinator
from .exceptions import ConfigurationError, TelemetryError
from .logging_utils import RedactingLogFilter, redact, safe_label
from .models import Capability, utc_now
from .readers.snapshot import SnapshotReader, SnapshotState
from .registry import Registry
from .storage.database import open_writer
from .storage.migrations import schema_version


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        super().error(redact(message))


def parser():
    cli = SafeArgumentParser(prog="home-telemetry")
    cli.add_argument(
        "--config",
        type=Path,
        default=os.environ.get("HOME_TELEMETRY_CONFIG", DEFAULT_CONFIG),
    )
    sub = cli.add_subparsers(dest="command", required=True)
    for command in ("run", "status"):
        sub.add_parser(command)
    config = sub.add_parser("config").add_subparsers(dest="action", required=True)
    config.add_parser("validate")
    init = config.add_parser("init", help="generate a starter TOML at --config")
    profile = init.add_mutually_exclusive_group(required=True)
    profile.add_argument("--mock", action="store_true")
    profile.add_argument("--sensor-name", help="exact advertised H5074 name")
    init.add_argument("--room", default="Living room")
    init.add_argument("--database", help="target SQLite path")
    init.add_argument("--use-indoor-binding", action="store_true")
    deploy = config.add_parser("deploy", help="install an existing TOML at --config")
    deploy.add_argument("source", type=Path)
    providers = sub.add_parser("providers").add_subparsers(dest="action", required=True)
    providers.add_parser("list")
    providers.add_parser("describe").add_argument("type")
    discover = providers.add_parser("discover")
    discover.add_argument("type")
    discover.add_argument(
        "--provider", help="use settings from a configured provider ID"
    )
    database = sub.add_parser("db").add_subparsers(dest="action", required=True)
    for action in ("status", "purge", "migrate"):
        database.add_parser(action)
    selection = sub.add_parser("selection").add_subparsers(dest="action", required=True)
    selection.add_parser("explain").add_argument("binding")
    return cli


def _print(*values):
    print(*(redact(value) for value in values))


async def _run(config, registry):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        await Coordinator(config, registry).run(stop)
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)


async def _discover(registry, cfg):
    try:
        provider = registry.instantiate(cfg)
        try:
            results = await asyncio.wait_for(provider.discover(), timeout=30)
            for label in results:
                if safe_label(label):
                    _print(label)
        finally:
            await asyncio.wait_for(provider.stop(), timeout=5)
    except Exception:
        raise TelemetryError("discovery failed") from None


def _provider_command(args, registry):
    if args.action == "list":
        for kind, item in sorted(registry.types.items()):
            _print(kind, item.status, "-", item.description)
        for kind, issue in registry.plugin_issues:
            _print(kind, issue)
        return 0
    item = registry.describe(args.type)
    if args.action == "describe":
        _print(args.type, item.status, "-", item.description)
        _print("Capabilities:", ", ".join(sorted(item.capabilities)) or "none")
        return 0
    if item.status != "installed":
        raise TelemetryError(item.description)
    if Capability.DISCOVERY not in item.capabilities:
        raise TelemetryError("this provider does not support discovery")
    cfg = ProviderConfig("discovery", args.type, "discovery", "Discovery")
    if args.provider:
        config = load_config(args.config)
        cfg = next(
            (item for item in config.providers if item.id == args.provider), None
        )
        if cfg is None or cfg.type != args.type or not cfg.enabled:
            raise ConfigurationError(
                "discovery requires an enabled provider ID of this type"
            )
        registry.validate(cfg)
    asyncio.run(_discover(registry, cfg))
    return 0


def _status(config, snapshot):
    _print("Collector:", "running" if snapshot.running else "stopped")
    _print("Database:", config.database, "| schema:", snapshot.schema or "unknown")
    if snapshot.message:
        _print(snapshot.message)
    for cfg in config.providers:
        source = snapshot.sources.get(cfg.id)
        reading = snapshot.latest_by_provider(cfg.id)
        health = source.health if source else None
        days = source.retention_days if source else cfg.retention_days
        _print(
            cfg.id,
            f"({cfg.type})",
            "enabled" if cfg.enabled else "disabled",
            health.status if health else "unavailable",
            reading.status if reading else "unavailable",
            "| last observation:",
            health.last_observation if health and health.last_observation else "-",
            "| retention:",
            f"{days:g} days" if days is not None else "unlimited",
        )
        if health and health.error_summary:
            _print("  Last error:", health.last_error or "-", "-", health.error_summary)
    for name in config.bindings:
        chosen = snapshot.selected(name).selected
        _print("Binding:", name, "->", chosen.source.id if chosen else "none")


def _dispatch(args, registry):
    if args.command == "providers":
        return _provider_command(args, registry)
    if args.command == "config" and args.action in {"init", "deploy"}:
        from .config_setup import generate, install

        if args.action == "deploy":
            content = args.source.expanduser().read_bytes()
        else:
            content = generate(
                args.sensor_name, args.room, args.database, args.use_indoor_binding
            )
        changed = install(content, args.config, registry)
        _print("Installed:" if changed else "Already installed:", args.config)
        return 0
    # Maintenance and status must remain accessible when hardware configuration
    # is incomplete. Strict plugin validation is needed before collection.
    strict = args.command in {"run", "config"}
    config = load_config(
        args.config, registry=registry if strict else None, resolve_settings=strict
    )
    if args.command == "config":
        _print("Configuration valid")
        return 0
    if args.command == "run":
        asyncio.run(_run(config, registry))
        return 0
    if args.command == "db" and args.action in {"migrate", "purge"}:
        with open_writer(config.database) as db:
            if args.action == "migrate":
                _print("Database schema:", schema_version(db.connection))
            else:
                _print("Expired history rows removed:", db.purge(utc_now()))
        return 0
    snapshot = SnapshotReader(config.database).read()
    if args.command == "selection":
        if args.binding not in config.bindings:
            raise ConfigurationError("unknown binding")
        decision = snapshot.selected(args.binding)
        _print(
            "Selected:", decision.selected.source.id if decision.selected else "none"
        )
        if snapshot.message:
            _print(snapshot.message)
        for provider_id, reason in decision.explanations:
            _print(provider_id, "-", reason)
    else:
        _status(config, snapshot)
    return int(
        snapshot.state
        in {
            SnapshotState.BUSY,
            SnapshotState.INCOMPATIBLE,
            SnapshotState.UNAVAILABLE,
        }
    )


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for handler in logging.getLogger().handlers:
        if not any(isinstance(item, RedactingLogFilter) for item in handler.filters):
            handler.addFilter(RedactingLogFilter())
    args = parser().parse_args(argv)
    try:
        return _dispatch(args, Registry())
    except TelemetryError as error:
        _print("Error:", error)
    except (OSError, sqlite3.Error):
        _print("Error: database or runtime resources are unavailable")
    except KeyboardInterrupt:
        return 130
    return 1
