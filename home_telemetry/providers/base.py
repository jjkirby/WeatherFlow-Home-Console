"""Public provider plugin interface, version 1."""

from abc import ABC, abstractmethod
import asyncio
from collections.abc import Awaitable, Callable

from ..models import IndoorClimateObservation, ProviderHealth

Publish = Callable[[IndoorClimateObservation], Awaitable[None]]
ReportHealth = Callable[[ProviderHealth], Awaitable[None]]


class IndoorClimateProvider(ABC):
    provider_type = ""
    capabilities = frozenset()
    implemented = True
    description = ""
    max_retention_days = None

    def __init__(self, config):
        self.config = config
        self._task = None

    @property
    def provider_id(self):
        return self.config.id

    @classmethod
    def validate_config(cls, config):
        """Raise InvalidProviderSetting with a schema field name."""

    async def start(self, publish: Publish, report_health: ReportHealth):
        """Start one cancellable worker on the coordinator's event loop."""
        self._task = asyncio.create_task(self._run_worker(publish, report_health))

    async def _run_worker(self, publish, report_health):
        try:
            await self.run(publish, report_health)
        except SystemExit:
            raise RuntimeError("provider worker attempted to exit") from None

    async def wait(self):
        """Wait for the worker to finish or fail."""
        await self._task

    async def stop(self):
        """Cancel the worker and allow its finally blocks to release resources."""
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def discover(self):
        """Return an iterable of safe display labels when discovery is supported."""
        raise NotImplementedError

    @abstractmethod
    async def run(self, publish: Publish, report_health: ReportHealth):
        """Publish observations and report connection and health transitions."""
