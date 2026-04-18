from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EDAMode(str, Enum):
    EMBEDDED = "embedded"
    SURREAL_SERVER = "surreal-server"
    NATS = "nats"


@dataclass(slots=True)
class EDAConfig:
    mode: EDAMode = EDAMode.EMBEDDED
    store: str = "surreal"
    broker: str = "none"
    surreal_url: str = "surrealkv://.gobstopper/eda"

    lease_seconds: int = 30
    poll_interval_seconds: float = 0.2
    idle_sleep_seconds: float = 0.1
