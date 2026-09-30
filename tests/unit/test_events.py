from mednexus.events.contracts import ClinicalEvent
from mednexus.events.processing import InMemoryIdempotencyStore, process_once


def test_duplicate_event_is_processed_once():
    event = ClinicalEvent(event_type="admission.created", subject_id=1, payload={"source": "simulator"})
    store = InMemoryIdempotencyStore()
    handled = []

    assert process_once(event, store, handled.append) is True
    assert process_once(event, store, handled.append) is False
    assert handled == [event]
