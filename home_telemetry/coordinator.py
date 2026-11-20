"""Run and supervise each configured provider independently."""

import asyncio
from dataclasses import replace
from functools import partial
import logging

from .exceptions import ConfigurationError
from .models import (
    DataQuality,
    HealthStatus,
    IndoorClimateObservation,
    ProviderHealth,
    utc_now,
    utc_text,
)
from .storage.database import open_writer

_LOG = logging.getLogger("home_telemetry")
_HEARTBEAT_SECONDS = 5
_START_TIMEOUT_SECONDS = 30
_STOP_TIMEOUT_SECONDS = 5


class Coordinator:
    def __init__(self, config, registry, *, clock=utc_now):
        self.config = config
        self.registry = registry
        self.clock = clock
        self.health = {}
        self.invalid_observations = set()
        self.cleanup_seconds = min(config.cleanup_seconds, 60)

    async def run(self, stop):
        ids = set()
        for config in self.config.providers:
            if config.id in ids:
                raise ConfigurationError("providers.id: duplicate provider ID")
            ids.add(config.id)
            self.registry.validate(config)
        with open_writer(self.config.database) as db:
            db.configure(
                self.config,
                self.registry,
                self.clock(),
                nest_lookahead_seconds=self.cleanup_seconds + 2,
            )
            tasks = [
                asyncio.create_task(self._supervise(config, db))
                for config in self.config.providers
                if config.enabled
            ]
            try:
                await self._maintain(db, stop)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                db.maintenance(self.clock(), running=False)

    async def _maintain(self, db, stop):
        loop = asyncio.get_running_loop()
        next_cleanup = loop.time() + self.cleanup_seconds
        while not stop.is_set():
            delay = min(_HEARTBEAT_SECONDS, max(0, next_cleanup - loop.time()))
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except TimeoutError:
                if loop.time() >= next_cleanup:
                    db.maintenance(
                        self.clock(), nest_lookahead_seconds=self.cleanup_seconds + 2
                    )
                    next_cleanup = loop.time() + self.cleanup_seconds
                else:
                    db.heartbeat(self.clock())

    async def _report(self, cfg, db, health):
        if not isinstance(health, ProviderHealth):
            raise ValueError("invalid provider health")
        # Publish a framework-owned summary. Third-party errors can include
        # response bodies or freshly issued secrets unknown to the redactor.
        health = replace(
            health,
            last_error=health.last_error
            or (self.clock() if health.error_summary else None),
            error_summary=(
                "Provider reported a failure" if health.error_summary else None
            ),
        ).sanitized()
        db.health(cfg.id, health)
        self.health[cfg.id] = health
        self.invalid_observations.discard(cfg.id)

    async def _publish(self, cfg, db, observation):
        health = self.health.get(cfg.id, ProviderHealth(HealthStatus.STARTING))
        try:
            if not isinstance(observation, IndoorClimateObservation):
                raise ValueError("invalid observation model")
            if (observation.provider_id, observation.provider_type) != (
                cfg.id,
                cfg.type,
            ):
                raise ValueError("observation does not match the active provider")
            utc_text(observation.received_at)
            # Use the time at the trust boundary for receipt-based retention.
            obs = replace(
                observation, received_at=self.clock(), room=observation.room or cfg.room
            )
            db.record(obs, cfg.heartbeat_seconds)
        except (ValueError, TypeError, OverflowError):
            summary = "Provider sent an invalid observation"
            updated = ProviderHealth(
                HealthStatus.DEGRADED,
                last_error=self.clock(),
                error_summary=summary,
                consecutive_failures=health.consecutive_failures + 1,
            )
            db.health(cfg.id, updated)
            self.health[cfg.id] = updated
            self.invalid_observations.add(cfg.id)
            _LOG.warning("%s (%s)", summary, cfg.id)
            return
        if obs.quality != DataQuality.INVALID and (
            health.status == HealthStatus.STARTING
            or cfg.id in self.invalid_observations
        ):
            self.invalid_observations.discard(cfg.id)
            await self._report(cfg, db, ProviderHealth(HealthStatus.HEALTHY))

    async def _supervise(self, cfg, db):
        provider = None
        stage = "startup"
        failed = False
        try:
            provider = self.registry.instantiate(cfg)
            async with asyncio.timeout(_START_TIMEOUT_SECONDS):
                await provider.start(
                    partial(self._publish, cfg, db), partial(self._report, cfg, db)
                )
            stage = "worker"
            await provider.wait()
            raise RuntimeError("provider worker exited")
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
            failed = True
            self._failure(cfg, db, stage)
        except (Exception, SystemExit):
            failed = True
            self._failure(cfg, db, stage)
        finally:
            if provider is not None:
                try:
                    await asyncio.wait_for(
                        provider.stop(), timeout=_STOP_TIMEOUT_SECONDS
                    )
                except Exception:
                    failed = True
                    self._failure(cfg, db, "shutdown")
            if not failed:
                db.health(cfg.id, ProviderHealth(HealthStatus.STOPPED))

    def _failure(self, cfg, db, stage):
        status = self.health.get(cfg.id, ProviderHealth(HealthStatus.STARTING))
        summary = f"Provider {stage} failed"
        updated = ProviderHealth(
            HealthStatus.ERROR,
            last_error=self.clock(),
            error_summary=summary,
            consecutive_failures=status.consecutive_failures + 1,
        )
        db.health(cfg.id, updated)
        self.health[cfg.id] = updated
        _LOG.warning("%s (%s)", summary, cfg.id)
