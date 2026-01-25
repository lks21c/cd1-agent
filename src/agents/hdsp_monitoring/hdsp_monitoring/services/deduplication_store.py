"""
Deduplication Store for Alert Management.

Memory-based storage for alert fingerprints to prevent duplicate notifications.
"""

import logging
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, Optional

from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
    DeduplicationEntry,
    ProcessedAlert,
)

logger = logging.getLogger(__name__)


class DeduplicationStore:
    """
    In-memory deduplication store for alerts.

    Stores alert fingerprints with timestamps to:
    - Prevent duplicate notifications within deduplication window
    - Track repeat notifications at configured intervals
    - Clean up stale entries automatically
    """

    def __init__(
        self,
        dedup_window_seconds: int = 300,
        repeat_interval_seconds: int = 3600,
        cleanup_interval_seconds: int = 600,
    ):
        """Initialize deduplication store.

        Args:
            dedup_window_seconds: Window for deduplication (5 min default)
            repeat_interval_seconds: Interval for repeat notifications (1 hour default)
            cleanup_interval_seconds: Interval for cleanup (10 min default)
        """
        self.dedup_window_seconds = dedup_window_seconds
        self.repeat_interval_seconds = repeat_interval_seconds
        self.cleanup_interval_seconds = cleanup_interval_seconds

        self._store: Dict[str, DeduplicationEntry] = {}
        self._lock = Lock()
        self._last_cleanup = datetime.utcnow()

    def check_and_update(self, alert: ProcessedAlert) -> bool:
        """Check if alert should be notified and update store.

        Args:
            alert: Processed alert to check

        Returns:
            True if notification should be sent, False if deduplicated
        """
        with self._lock:
            self._maybe_cleanup()

            fingerprint = alert.fingerprint
            now = datetime.utcnow()

            if fingerprint in self._store:
                entry = self._store[fingerprint]
                entry.update_seen()

                if entry.should_notify(
                    self.dedup_window_seconds,
                    self.repeat_interval_seconds,
                ):
                    entry.mark_notified()
                    logger.debug(
                        f"Alert {fingerprint} passed dedup (repeat #{entry.notification_count})"
                    )
                    return True
                else:
                    logger.debug(f"Alert {fingerprint} deduplicated")
                    return False
            else:
                # New alert
                entry = DeduplicationEntry(
                    fingerprint=fingerprint,
                    alert_name=alert.alert_name,
                    first_seen=alert.first_seen,
                    last_seen=now,
                )
                self._store[fingerprint] = entry

                # First occurrence - wait briefly for grouping
                if (now - alert.first_seen).total_seconds() >= 30:
                    entry.mark_notified()
                    logger.debug(f"New alert {fingerprint} registered and notified")
                    return True
                else:
                    logger.debug(f"New alert {fingerprint} registered, waiting for grouping")
                    return False

    def get_entry(self, fingerprint: str) -> Optional[DeduplicationEntry]:
        """Get deduplication entry by fingerprint.

        Args:
            fingerprint: Alert fingerprint

        Returns:
            DeduplicationEntry or None
        """
        with self._lock:
            return self._store.get(fingerprint)

    def mark_notified(self, fingerprint: str) -> None:
        """Mark alert as notified.

        Args:
            fingerprint: Alert fingerprint
        """
        with self._lock:
            if fingerprint in self._store:
                self._store[fingerprint].mark_notified()

    def mark_all_notified(self, fingerprints: list[str]) -> None:
        """Mark multiple alerts as notified.

        Args:
            fingerprints: List of alert fingerprints
        """
        with self._lock:
            for fp in fingerprints:
                if fp in self._store:
                    self._store[fp].mark_notified()

    def remove(self, fingerprint: str) -> bool:
        """Remove entry from store.

        Args:
            fingerprint: Alert fingerprint

        Returns:
            True if removed, False if not found
        """
        with self._lock:
            if fingerprint in self._store:
                del self._store[fingerprint]
                return True
            return False

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._store.clear()
            logger.info("Deduplication store cleared")

    def _maybe_cleanup(self) -> None:
        """Clean up stale entries if interval passed."""
        now = datetime.utcnow()
        if (now - self._last_cleanup).total_seconds() < self.cleanup_interval_seconds:
            return

        self._cleanup()
        self._last_cleanup = now

    def _cleanup(self) -> None:
        """Remove stale entries."""
        now = datetime.utcnow()
        stale_threshold = now - timedelta(seconds=self.repeat_interval_seconds * 2)

        stale_keys = [
            k for k, v in self._store.items()
            if v.last_seen < stale_threshold
        ]

        for key in stale_keys:
            del self._store[key]

        if stale_keys:
            logger.info(f"Cleaned up {len(stale_keys)} stale dedup entries")

    def get_stats(self) -> Dict:
        """Get store statistics.

        Returns:
            Statistics dictionary
        """
        with self._lock:
            now = datetime.utcnow()
            total = len(self._store)
            notified = sum(1 for e in self._store.values() if e.notification_count > 0)
            repeat = sum(1 for e in self._store.values() if e.notification_count > 1)

            return {
                "total_entries": total,
                "notified_entries": notified,
                "repeat_entries": repeat,
                "dedup_window_seconds": self.dedup_window_seconds,
                "repeat_interval_seconds": self.repeat_interval_seconds,
            }


# Module-level singleton
_store_instance: Optional[DeduplicationStore] = None


def get_deduplication_store() -> DeduplicationStore:
    """Get singleton DeduplicationStore instance."""
    global _store_instance
    if _store_instance is None:
        _store_instance = DeduplicationStore()
    return _store_instance
