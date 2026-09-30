from collections.abc import Callable

from mednexus.events.contracts import ClinicalEvent


class InMemoryIdempotencyStore:
    """Test/local implementation; production consumers use Redis SET NX with TTL."""

    def __init__(self) -> None:
        self._processed: set[str] = set()

    def contains(self, event_id: str) -> bool:
        return event_id in self._processed

    def mark_processed(self, event_id: str) -> None:
        self._processed.add(event_id)


def process_once(
    event: ClinicalEvent,
    store: InMemoryIdempotencyStore,
    handler: Callable[[ClinicalEvent], None],
) -> bool:
    event_id = str(event.event_id)
    if store.contains(event_id):
        return False
    handler(event)
    store.mark_processed(event_id)
    return True
