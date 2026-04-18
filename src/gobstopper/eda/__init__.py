"""Event-driven architecture primitives for Gobstopper."""

from .config import EDAConfig, EDAMode
from .dispatcher import EventDispatcher
from .inprocess_bridge import InProcessBridge
from .interfaces import BrokerBridge, Dispatcher, EventHandler, EventStore
from .memory_store import InMemoryEventStore
from .models import EventEnvelope, new_event
from .surreal_store import SurrealEventStore

__all__ = [
    "EDAConfig",
    "EDAMode",
    "EventEnvelope",
    "new_event",
    "EventStore",
    "EventHandler",
    "BrokerBridge",
    "Dispatcher",
    "EventDispatcher",
    "InMemoryEventStore",
    "SurrealEventStore",
    "InProcessBridge",
]
