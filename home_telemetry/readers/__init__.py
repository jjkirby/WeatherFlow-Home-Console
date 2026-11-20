"""Stable read-only API for console integrations."""

from .snapshot import Snapshot, SnapshotReader, SnapshotState

__all__ = ["Snapshot", "SnapshotReader", "SnapshotState"]
