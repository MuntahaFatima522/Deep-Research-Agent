from typing import Any


class Budget:
    """Tracks and enforces limits on searches and research rounds."""

    def __init__(self, max_searches: int = 12, max_rounds: int = 2, max_searches_per_worker: int = 4) -> None:
        self.max_searches = max_searches
        self.max_rounds = max_rounds
        self.max_searches_per_worker = max_searches_per_worker
        self.total_searches = 0
        self.worker_searches: dict[str, int] = {}

    def can_search(self, worker_id: str | None = None) -> bool:
        """Check if global search limit and per-worker limit allow another search."""
        if self.total_searches >= self.max_searches:
            return False
        if worker_id is not None:
            count = self.worker_searches.get(worker_id, 0)
            if count >= self.max_searches_per_worker:
                return False
        return True

    def record_search(self, worker_id: str | None = None, count: int = 1) -> None:
        """Record executed searches globally and per worker."""
        self.total_searches += count
        if worker_id is not None:
            self.worker_searches[worker_id] = self.worker_searches.get(worker_id, 0) + count

    def summary(self) -> dict[str, Any]:
        """Return snapshot of budget consumption."""
        return {
            "total_searches": self.total_searches,
            "max_searches": self.max_searches,
            "max_rounds": self.max_rounds,
            "worker_searches": dict(self.worker_searches),
        }
