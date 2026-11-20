"""Retention applies by provider and uses the actual time of receipt."""

from datetime import timedelta

from ..config import NEST_MAX_DAYS
from ..models import utc_text

POLICY = """SELECT id, type, retention_days FROM providers
            WHERE retention_days IS NOT NULL OR type = 'nest_sdm'"""


def effective_days(kind, requested):
    if kind == "nest_sdm":
        return min(NEST_MAX_DAYS, requested) if requested is not None else NEST_MAX_DAYS
    return requested


def expired(now, kind, days, received_at):
    days = effective_days(kind, days)
    return days is not None and (now - received_at).total_seconds() >= days * 86400


def purge_expired(connection, now, *, nest_lookahead_seconds=0):
    removed = 0
    for provider_id, kind, days in connection.execute(POLICY).fetchall():
        days = effective_days(kind, days)
        if kind == "nest_sdm":
            days = min(days, NEST_MAX_DAYS - nest_lookahead_seconds / 86400)
        # A timezone-aware datetime cannot represent an earlier cutoff.
        if days >= now.toordinal():
            continue
        cutoff = utc_text(now - timedelta(days=days))
        args = (provider_id, cutoff)
        removed += connection.execute(
            "DELETE FROM observations WHERE provider_id = ? AND received_at <= ?",
            args,
        ).rowcount
        connection.execute(
            "DELETE FROM latest WHERE provider_id = ? AND received_at <= ?",
            args,
        )
        if kind == "nest_sdm":
            connection.execute(
                """UPDATE providers SET
                    last_observation =
                        CASE WHEN last_observation <= ? THEN NULL ELSE last_observation END,
                    last_connection =
                        CASE WHEN last_connection <= ? THEN NULL ELSE last_connection END,
                    error_summary = CASE WHEN last_error <= ? THEN NULL ELSE error_summary END,
                    last_error = CASE WHEN last_error <= ? THEN NULL ELSE last_error END
                    WHERE id = ?""",
                (cutoff, cutoff, cutoff, cutoff, provider_id),
            )
    return removed
